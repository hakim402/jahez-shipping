import copy
import json
import secrets
import subprocess
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import httpx
from django.contrib.auth.models import User, Permission
from django.db import connection, transaction
from django.test import TransactionTestCase, Client, override_settings, SimpleTestCase
from django.utils import timezone

from apps.containers.models import Container, ContainerEvent
from apps.containers.pipeline import prepare, translate_labels, RefreshError
from apps.containers.refresh import refresh_container, run_provider
from apps.integrations.sealegend import SourceError

FIXTURE = Path(__file__).parent / "fixtures" / "sealegend_synthetic.json"
REFERENCE = "DEMOAB123456"
NUMBER = "TEST1234567"


def source(**changes):
    data = json.loads(FIXTURE.read_bytes())
    data["result"].update(changes)
    return json.dumps(data).encode()


def prepared(body=None, number=NUMBER, labels=None):
    return prepare(REFERENCE, number, labels or {}, body=body or FIXTURE.read_bytes())


class RefreshTests(TransactionTestCase):
    def setUp(self):
        self.obj = Container.objects.create(search_reference=REFERENCE, manual_notes_en="Private office text", manual_notes_ar="نص داخلي", manual_status_override="on_hold")
        self.manual = ContainerEvent.objects.create(container=self.obj, title_en="Manual note", title_ar="تحديث يدوي")

    def execute(self, data=None):
        with patch("apps.containers.refresh.run_provider", return_value=data or prepared()):
            result = refresh_container(self.obj.pk)
        self.obj.refresh_from_db()
        return result

    def test_binding_idempotency_changed_eta_preserves_manual_private_fields_and_timezone(self):
        result = self.execute()
        self.assertTrue(result.ok); self.assertEqual(result.code, "updated")
        self.assertEqual(self.obj.container_number, NUMBER)
        self.assertEqual(self.obj.carrier_status, "in_transit"); self.assertEqual(self.obj.display_status, "on_hold")
        self.assertFalse(self.obj.is_published)
        self.assertEqual(self.obj.manual_notes_en, "Private office text")
        self.assertEqual(self.obj.events.filter(origin="carrier").count(), 3)
        self.assertFalse(self.obj.events.filter(origin="carrier", is_public=True).exists())
        self.assertEqual(self.obj.arrival_estimated["raw"], "2026-02-03 21:00:00")
        self.assertIsNone(self.obj.arrival_estimated["source_timezone"]); self.assertIsNone(self.obj.arrival_estimated["normalized_instant"])
        self.assertIsNotNone(self.obj.last_refresh_success_at); self.assertIsNone(self.obj.refresh_claim)
        event = self.obj.events.get(origin="carrier", raw_status="DG")
        result = self.execute(); self.assertEqual(result.code, "unchanged")
        self.assertEqual(self.obj.events.count(), 4)
        data = json.loads(FIXTURE.read_bytes())
        for node in data["result"]["containerList"][0]["nodeList"]:
            if node["movementCode"] == "DG": node["estimateDate"] = "2026-02-05"
        self.assertTrue(self.execute(prepared(json.dumps(data).encode())).ok)
        event.refresh_from_db()
        self.assertEqual(event.source_time["raw"], "2026-02-05"); self.assertEqual(event.source_time["precision"], "date")
        self.assertEqual(self.obj.events.count(), 4)
        self.manual.refresh_from_db(); self.assertEqual(self.manual.title_en, "Manual note")

    def test_multiple_requires_selection_and_mismatch_rejects_before_ai(self):
        data = json.loads(FIXTURE.read_bytes()); other = copy.deepcopy(data["result"]["containerList"][0]); other["ctnno"] = "DEMO7654321"
        data["result"]["containerList"].append(other)
        body = json.dumps(data).encode()
        with override_settings(GROQ_ENABLED=True), patch("apps.containers.pipeline.translate_labels") as ai:
            with self.assertRaises(RefreshError) as error: prepare(REFERENCE, "", {}, body=body)
            self.assertEqual(error.exception.code, "ambiguous_container"); ai.assert_not_called()
        chosen = prepared(body)
        self.obj.container_number = NUMBER; self.obj.save()
        self.assertTrue(self.execute(chosen).ok)
        # B/L-wide equipment is not copied into one of several containers.
        self.assertIsNone(self.obj.equipment_quantity)
        with self.assertRaises(RefreshError) as error: prepared(source(containerList=[other]))
        self.assertEqual(error.exception.code, "identity_mismatch")
        bad = prepared(); bad["selected"] = "DEMO7654321"
        self.assertFalse(self.execute(bad).ok)

    def test_partial_response_omissions_never_erase_last_good_facts_or_events(self):
        self.execute(); old = self.obj.arrival_estimated; vessel = self.obj.vessel
        data = source(ctnSizeCount=None, pol=None, pod=None, containerList=[{"ctnno": NUMBER, "nodeList": []}])
        self.assertTrue(self.execute(prepared(data)).ok)
        self.assertEqual(self.obj.arrival_estimated, old); self.assertEqual(self.obj.vessel, vessel)
        self.assertEqual(self.obj.carrier_status, "in_transit"); self.assertEqual(self.obj.events.count(), 4)
        self.assertEqual(self.obj.manual_notes_ar, "نص داخلي")

    def test_failure_keeps_facts_success_time_and_logs_only_safe_code(self):
        self.execute(); before = self.obj.arrival_estimated; success = self.obj.last_refresh_success_at
        for code in ("timeout", "ai_unavailable", "invalid_extraction", "identity_mismatch"):
            with patch("apps.containers.refresh.run_provider", side_effect=RefreshError(code)):
                result = refresh_container(self.obj.pk)
            self.assertEqual(result.code, code); self.assertFalse(result.ok)
            self.obj.refresh_from_db(); self.assertEqual(self.obj.arrival_estimated, before)
            self.assertEqual(self.obj.last_refresh_success_at, success); self.assertEqual(self.obj.last_failure_code, code)
            self.assertIsNone(self.obj.refresh_claim)
        with patch("apps.containers.refresh.run_provider", side_effect=RuntimeError("SECRET payload reference")):
            self.assertEqual(refresh_container(self.obj.pk).code, "unavailable")
        self.obj.refresh_from_db(); self.assertNotIn("SECRET", self.obj.last_failure_code)

    def test_overlapping_claim_manual_edit_and_archive_are_not_overwritten(self):
        def provider(snapshot):
            self.assertFalse(connection.in_atomic_block)
            # A second independent entry cannot take the claim or invoke a provider.
            with patch("apps.containers.refresh.run_provider") as second:
                self.assertFalse(refresh_container(snapshot.pk).ok); second.assert_not_called()
            current = Container.objects.get(pk=snapshot.pk)
            current.manual_notes_en = "Newer manual edit"; current.archived_at = timezone.now(); current.save()
            return prepared()
        with patch("apps.containers.refresh.run_provider", side_effect=provider):
            result = refresh_container(self.obj.pk)
        self.assertEqual(result.code, "concurrent_change")
        self.obj.refresh_from_db(); self.assertEqual(self.obj.manual_notes_en, "Newer manual edit")
        self.assertIsNotNone(self.obj.archived_at); self.assertEqual(self.obj.events.count(), 1)
        self.assertIsNone(self.obj.last_refresh_success_at)

    def test_two_parallel_requests_execute_only_one_provider(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        from django.db import connections
        entered, release = Event(), Event()
        calls = []
        def provider(snapshot):
            calls.append(snapshot.pk); entered.set()
            if not release.wait(3): raise AssertionError("test synchronization timeout")
            return prepared()
        def request():
            try: return refresh_container(self.obj.pk)
            finally: connections.close_all()
        with patch("apps.containers.refresh.run_provider",side_effect=provider), ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(request)
            try:
                self.assertTrue(entered.wait(3))
                second=pool.submit(request).result(timeout=3)
                self.assertFalse(second.ok)
            finally: release.set()
            self.assertTrue(first.result(timeout=3).ok)
        self.assertEqual(calls,[self.obj.pk])

    def test_expired_claim_recovered_and_old_owner_cannot_commit(self):
        import uuid
        old = uuid.uuid4()
        Container.objects.filter(pk=self.obj.pk).update(refresh_claim=old, refresh_claim_expires_at=timezone.now()-timedelta(seconds=1))
        self.assertTrue(self.execute().ok)
        self.obj.refresh_from_db(); self.assertIsNone(self.obj.refresh_claim)
        def provider(snapshot):
            Container.objects.filter(pk=snapshot.pk).update(refresh_claim=uuid.uuid4(), revision=snapshot.revision+1)
            return prepared()
        with patch("apps.containers.refresh.run_provider", side_effect=provider):
            self.assertEqual(refresh_container(self.obj.pk).code, "concurrent_change")

    def test_archived_no_calls_and_network_inside_transaction_refused(self):
        self.obj.archived_at = timezone.now(); self.obj.save()
        with patch("apps.containers.refresh.run_provider") as provider:
            self.assertFalse(refresh_container(self.obj.pk).ok); provider.assert_not_called()
        with transaction.atomic(), self.assertRaisesRegex(RuntimeError, "autocommit"):
            refresh_container(self.obj.pk)

    def test_unknown_and_undated_empty_return_do_not_fabricate_arrival_or_completion(self):
        nodes = [{"movementCode":"EMPTY_RETURN", "movementName":"Empty returned", "eventPort":"BBBBB"}]
        self.assertTrue(self.execute(prepared(source(containerList=[{"ctnno":NUMBER,"nodeList":nodes}]))).ok)
        self.assertEqual(self.obj.last_failure_code, "unknown_status")
        self.assertEqual(self.obj.carrier_status, "unknown"); self.assertIsNone(self.obj.arrival_actual)
        event = self.obj.events.get(origin="carrier")
        self.assertIsNone(event.source_time); self.assertEqual(event.designation, "unknown")

    def test_manual_date_cannot_become_carrier_status_and_actual_arrival_requires_source(self):
        from tests.test_containers import source_time
        self.obj.arrival_actual = source_time("2026-01-01", "actual", "date"); self.obj.save()
        nodes = [{"movementCode":"DG", "movementName":"Arrival", "eventPort":"BBBBB", "estimateDate":"2026-02-03"}]
        self.assertTrue(self.execute(prepared(source(containerList=[{"ctnno":NUMBER,"nodeList":nodes}]))).ok)
        self.assertEqual(self.obj.carrier_status, "unknown")
        nodes[0]["actualDate"] = "2026-02-04"
        self.assertTrue(self.execute(prepared(source(containerList=[{"ctnno":NUMBER,"nodeList":nodes}]))).ok)
        self.assertEqual(self.obj.carrier_status, "arrived")
        self.assertTrue(self.execute().ok)
        self.assertEqual(self.obj.carrier_status, "arrived")

    def test_invalid_payload_rolls_back_parent_and_events_and_does_not_publish(self):
        data = prepared(); data["candidate"]["containers"][0]["milestones"][1]["estimated"]["designation"] = "actual"
        self.assertFalse(self.execute(data).ok); self.assertEqual(self.obj.container_number, "")
        self.assertEqual(self.obj.events.count(), 1); self.assertIsNone(self.obj.last_refresh_success_at)
        data = prepared(); data["candidate"]["containers"][0]["milestones"][1]["location_code"] = None
        self.assertFalse(self.execute(data).ok); self.assertEqual(self.obj.events.count(), 1)
        self.assertEqual(self.obj.source_evidence, {})

    def test_source_route_change_rejected_and_revisited_estimates_ambiguous(self):
        self.execute(); result = self.execute(prepared(source(pod="CCCCC")))
        self.assertEqual(result.code, "identity_mismatch"); self.assertEqual(self.obj.destination_code, "BBBBB")
        data = json.loads(FIXTURE.read_bytes()); node=copy.deepcopy(data["result"]["containerList"][0]["nodeList"][1]); node["estimateDate"]="2026-02-09"
        data["result"]["containerList"][0]["nodeList"].append(node)
        self.assertFalse(self.execute(prepared(json.dumps(data).encode())).ok)
        self.assertEqual(self.obj.events.count(), 4)

    def test_admin_refresh_permission_csrf_feedback_and_stale_form(self):
        owner = User.objects.create_superuser("DEMO-owner", password=secrets.token_urlsafe(24))
        staff = User.objects.create_user("DEMO-viewer", is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename="view_container"))
        url = f"/en/admin/containers/container/{self.obj.pk}/refresh/"
        client=Client(enforce_csrf_checks=True); client.force_login(staff)
        self.assertEqual(client.get(url).status_code, 403); self.assertEqual(client.post(url).status_code,403)
        client.force_login(owner)
        with patch("apps.containers.admin.refresh_container") as service:
            self.assertEqual(client.get(url).status_code,200); service.assert_not_called()
            self.assertEqual(client.post(url).status_code,403); service.assert_not_called()
        token=client.cookies["jahez_shipping_csrf"].value
        with patch("apps.containers.refresh.run_provider", return_value=prepared()):
            response=client.post(url,{"csrfmiddlewaretoken":token},follow=True)
        self.assertContains(response,"Carrier check completed")
        with patch("apps.containers.refresh.run_provider",side_effect=RefreshError("timeout")):
            response=client.post(url.replace('/en/','/ar/'),{"csrfmiddlewaretoken":token},follow=True)
        self.assertContains(response,"saved facts were kept" if 'lang="en"' in response.content.decode() else "حُفظت")
        # A pre-refresh form must not put stale source fields back over the accepted refresh.
        from tests.test_container_admin import ContainerAdminTests
        helper=ContainerAdminTests(); data=helper.payload(self.obj)
        data["manual_notes_en"]="stale overwrite"
        client=Client();client.force_login(owner)
        response=client.post(f"/en/admin/containers/container/{self.obj.pk}/change/",data)
        self.assertEqual(response.status_code,200); self.assertContains(response,"Reload it before saving")
        self.obj.refresh_from_db(); self.assertEqual(self.obj.manual_notes_en,"Private office text")


@override_settings(GROQ_ENABLED=True,GROQ_API_KEY="test-key-not-real",GROQ_TEXT_MODEL="openai/gpt-oss-120b",GROQ_TEXT_OUTPUT_MODE="schema",GROQ_MAX_TOKENS=1024)
class TranslationTests(SimpleTestCase):
    def reply(self, content, finish="stop"):
        return httpx.Response(200,json={"id":"DEMO-response","object":"chat.completion","created":1,"model":"openai/gpt-oss-120b","choices":[{"index":0,"finish_reason":finish,"message":{"role":"assistant","content":content}}]})

    def test_sdk_uses_documented_endpoint_no_tools_and_strict_schema_without_keys_in_content(self):
        def handle(request):
            self.assertEqual(str(request.url),"https://api.groq.com/openai/v1/chat/completions")
            body=json.loads(request.content)
            self.assertEqual(body["response_format"]["type"],"json_schema")
            self.assertTrue(body["response_format"]["json_schema"]["strict"])
            self.assertNotIn("tools",body); self.assertNotIn("test-key",request.content.decode())
            self.assertNotIn(REFERENCE,request.content.decode()); self.assertNotIn(NUMBER,request.content.decode())
            return self.reply(json.dumps({"labels":[{"source":"EXAMPLE ORIGIN","ar":"ميناء تجريبي"}]}))
        self.assertEqual(translate_labels(["EXAMPLE ORIGIN"],transport=httpx.MockTransport(handle)),{"EXAMPLE ORIGIN":"ميناء تجريبي"})

    def test_json_mode_and_malformed_injected_unsupported_output_rejected(self):
        bad=["not json", json.dumps({"labels":[],"command":"curl bad"}), json.dumps({"labels":[{"source":"OTHER","ar":"ميناء"}]}),json.dumps({"labels":[{"source":"PORT","ar":"https://bad.test"}]}),json.dumps({"labels":[{"source":"PORT","ar":"وصلت ٢٠٢٦"}]})]
        for content in bad:
            with self.subTest(content=content),self.assertRaises(RefreshError):
                translate_labels(["PORT"],transport=httpx.MockTransport(lambda r:self.reply(content)))
        with override_settings(GROQ_TEXT_OUTPUT_MODE="json"):
            def handle(request):
                self.assertEqual(json.loads(request.content)["response_format"],{"type":"json_object"})
                return self.reply('{"labels":[{"source":"PORT","ar":"ميناء"}]}')
            self.assertEqual(translate_labels(["PORT"],transport=httpx.MockTransport(handle)),{"PORT":"ميناء"})

    def test_provider_failure_and_truncation_never_retry_or_accept_partial_output(self):
        calls=[]
        def unavailable(request):
            calls.append(request)
            return httpx.Response(503,json={"error":{"message":"private provider payload"}})
        with self.assertRaises(RefreshError) as error:
            translate_labels(["PORT"],transport=httpx.MockTransport(unavailable))
        self.assertEqual(error.exception.code,"ai_unavailable");self.assertEqual(len(calls),1)
        with self.assertRaises(RefreshError):
            translate_labels(["PORT"],transport=httpx.MockTransport(lambda r:self.reply('{"labels":[]}',"length")))
        with self.assertRaises(RefreshError):
            translate_labels(["PORT"],transport=httpx.MockTransport(lambda r:self.reply('{"labels":[],"labels":[]}')))

    def test_unchanged_names_reuse_translations_even_with_changed_eta(self):
        labels={"EXAMPLE ORIGIN":"منشأ تجريبي","EXAMPLE DESTINATION":"وجهة تجريبية"}
        with patch("apps.containers.pipeline.translate_labels") as ai:
            result=prepared(labels=labels); ai.assert_not_called(); self.assertFalse(result["ai_used"])
        with override_settings(GROQ_TEXT_MODEL="not-supported"):
            with self.assertRaises(RefreshError) as error:translate_labels(["PORT"])
            self.assertEqual(error.exception.code,"ai_unavailable")

    def test_source_identity_date_and_extra_fields_are_strictly_grounded(self):
        data=json.loads(FIXTURE.read_bytes());data['result']['bkgNo']='OTHER123456'
        with self.assertRaises(SourceError):prepared(json.dumps(data).encode())
        data=json.loads(FIXTURE.read_bytes());data['result']['containerList'][0]['nodeList'][0]['actualDate']='2026-02-30'
        with self.assertRaises(SourceError):prepared(json.dumps(data).encode())


class WorkerDeadlineTests(SimpleTestCase):
    def test_killable_provider_deadline_and_safe_worker_error(self):
        import sys, time
        from types import SimpleNamespace
        snapshot=SimpleNamespace(search_reference="bad", container_number="", source_evidence={})
        with self.assertRaises(RefreshError) as error:
            run_provider(snapshot)
        self.assertEqual(error.exception.code,"invalid_reference")
        original=subprocess.Popen
        created=[]
        def sleeping_worker(*args,**kwargs):
            process=original([sys.executable,"-c","import time; time.sleep(10)"],**kwargs)
            created.append(process)
            return process
        start=time.monotonic()
        with patch("apps.containers.refresh.PROVIDER_SECONDS",0.15),patch("apps.containers.refresh.subprocess.Popen",side_effect=sleeping_worker),self.assertRaises(RefreshError) as error:
            run_provider(snapshot)
        self.assertEqual(error.exception.code,"timeout")
        self.assertLess(time.monotonic()-start,3)
        self.assertIsNotNone(created[0].poll())
