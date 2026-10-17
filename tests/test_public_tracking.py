import copy
from datetime import timedelta
import json
import logging
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import DatabaseError
from django.db.models import Model
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from apps.containers.models import Container, ContainerEvent
from apps.containers.pipeline import RefreshError
from apps.containers.public_data import validate_snapshot, projection
from apps.containers.publication import publish_reviewed
from apps.containers.refresh import refresh_container
from apps.core.safe_logging import SafeFormatter
from tests.test_container_refresh import prepared, FIXTURE
from tests import test_container_admin
from tests.test_containers import source_time


class PublicTrackingTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.obj = Container.objects.create(search_reference="DEMOAB123456", manual_notes_en="PRIVATE-OFFICE-NOTE", manual_notes_ar="ملاحظة خاصة")

    def refresh(self, payload=None):
        with patch("apps.containers.refresh.run_provider", return_value=payload or prepared()):
            result = refresh_container(self.obj.pk)
        self.obj.refresh_from_db()
        self.assertTrue(result.ok)
        return result

    def publish(self):
        self.obj.is_published = True
        self.obj.save(update_fields=["is_published"])
        publish_reviewed(self.obj)
        self.obj.refresh_from_db()

    def url(self, language="en", obj=None):
        return (obj or self.obj).tracking_path(language)

    def enable_auto(self):
        self.obj.auto_publish_carrier_updates = True
        self.obj.save(update_fields=["auto_publish_carrier_updates"])

    def changed_eta(self):
        data=json.loads(FIXTURE.read_bytes())
        for node in data["result"]["containerList"][0]["nodeList"]:
            if node["movementCode"]=="DG": node["estimateDate"]="2026-02-05"
        return prepared(json.dumps(data).encode())

    def test_home_and_lookup_initial_invalid_normalized_code_and_generic_not_found(self):
        self.assertFalse(self.obj.auto_publish_carrier_updates)
        for lang in ("en","ar"):
            response=self.client.get(f"/{lang}/")
            self.assertContains(response,'name="code"'); self.assertContains(response,'type="submit"')
            self.assertContains(self.client.get(f"/{lang}/track/"), 'id="reference"')
            response=self.client.get(f"/{lang}/track/",{"code":"PRIVATE-BL-INPUT"})
            self.assertEqual(response.status_code,400);self.assertNotContains(response,"PRIVATE-BL-INPUT",status_code=400)
            self.assertContains(response,'aria-invalid="true"',status_code=400)
            self.assertNotContains(response,'name="username"',status_code=400)
            response=self.client.get(f"/{lang}/track/",{"code":"  "+self.obj.lookup_code.lower()+"  "})
            self.assertEqual(response.status_code,302);self.assertEqual(response["Location"],self.url(lang))
        for raw in ("1","JHZ-"+"1"*26,"<script>unsafe</script>","JHZ-"+"A"*200):
            self.assertEqual(self.client.get("/en/track/",{"code":raw}).status_code,400)
        self.assertEqual(self.client.get("/en/track/?code=x&code=y").status_code,400)

    def test_private_archived_missing_and_unreviewed_published_have_identical_public_absence(self):
        private=self.client.get(self.url())
        self.assertEqual(private.status_code,404)
        self.obj.is_published=True;self.obj.save()
        self.assertEqual(self.client.get(self.url()).content,private.content)
        self.publish()
        self.obj.archived_at=timezone.now();self.obj.save()
        self.assertEqual(self.client.get(self.url()).content,private.content)
        missing=self.client.get("/en/track/JHZ-"+"A"*26+"/")
        self.assertEqual(missing.content,private.content)

    @override_settings(SHIPPING_WHATSAPP_NUMBER='+971 (50) 123-4567')
    def test_found_projection_and_headers_exclude_all_private_fields_and_models(self):
        self.refresh()
        event=ContainerEvent.objects.create(container=self.obj,title_en="Reviewed office update",title_ar="تحديث مكتب معتمد",detail_en="Approved public detail",detail_ar="تفصيل عام معتمد",is_public=True)
        ContainerEvent.objects.create(container=self.obj,title_en="PRIVATE-EVENT-TEXT")
        other=Container.objects.create(search_reference="DEMOLK456789")
        ContainerEvent.objects.create(container=other,title_en="OTHER-JOURNEY-EVENT",is_public=True)
        self.publish()
        response=self.client.get(self.url())
        self.assertEqual(response.status_code,200)
        for private in (self.obj.search_reference,"PRIVATE-OFFICE-NOTE","PRIVATE-EVENT-TEXT","OTHER-JOURNEY-EVENT",self.obj.source_fingerprint,event.dedupe_key,"source_evidence","refresh_claim","manual_status"):
            self.assertNotIn(private,response.content.decode())
        public=response.context["shipment"]
        self.assertIsInstance(public,dict)
        self.assertNotIsInstance(public,Model)
        self.assertEqual(set(public),{"container_number","equipment_type","equipment_quantity","origin","destination","vessel","voyage","status","departure_actual","departure_estimated","arrival_actual","arrival_estimated","events","checked","stale","limited"})
        self.assertFalse(any("key" in entry or "id" in entry or "raw_status" in entry for entry in public["events"]))
        self.assertContains(response,"Reviewed office update");self.assertContains(response,"Approved public detail")
        self.assertContains(response,"https://wa.me/971501234567")
        self.assertNotIn(self.obj.lookup_code,response.context["canonical_url"])
        self.assertEqual(response["Referrer-Policy"],"no-referrer")
        self.assertContains(response,'<meta name="referrer" content="no-referrer">')
        self.assertIn("no-store",response["Cache-Control"])
        self.assertEqual(response["X-Robots-Tag"],"noindex, nofollow")
        self.assertContains(response,self.url("ar"))
        self.assertEqual(self.client.get(self.url("ar")).status_code,200)

    def test_date_only_actual_estimated_missing_zone_and_no_inferred_arrival(self):
        self.obj.departure_actual=source_time("2026-01-02",precision="date",designation="actual")
        self.obj.arrival_estimated=source_time("2000-01-01",precision="date")
        self.obj.carrier_status="in_transit";self.obj.save();self.publish()
        response=self.client.get(self.url())
        self.assertContains(response,"Date only");self.assertContains(response,"Timezone not supplied")
        self.assertContains(response,"Actual");self.assertContains(response,"Estimated")
        self.assertNotContains(response,"2000-01-01 00:00")
        self.assertEqual(response.context["shipment"]["status"],"In transit")
        self.assertIsNone(response.context["shipment"]["arrival_actual"])
        self.assertContains(response,"No published updates yet")
        arabic=self.client.get(self.url("ar"))
        self.assertContains(arabic,"ميناء المنشأ")
        self.assertContains(arabic,"المغادرة")

    def test_stale_fresh_unknown_check_time_and_temporary_unavailability_are_bilingual(self):
        self.obj.last_refresh_success_at=timezone.now()-timedelta(hours=31);self.obj.save();self.publish()
        self.assertContains(self.client.get(self.url()),"may be out of date")
        self.assertContains(self.client.get(self.url("ar")),"قد تكون هذه التحديثات قديمة")
        self.obj.last_refresh_success_at=timezone.now();self.obj.save();self.publish()
        self.assertNotContains(self.client.get(self.url()),"may be out of date")
        for language in ("en","ar"):
            with patch("apps.containers.public_views.cache.add",side_effect=ConnectionError("PRIVATE-CACHE-ERROR")):
                response=self.client.get(self.url(language))
                self.assertEqual(response.status_code,503);self.assertEqual(response["Retry-After"],"60")
                self.assertNotIn(b"PRIVATE-CACHE-ERROR",response.content)
        with patch("apps.containers.public_views.Container.objects.filter",side_effect=DatabaseError("PRIVATE-SQL")):
            response=self.client.get(self.url())
            self.assertEqual(response.status_code,503);self.assertNotIn(b"PRIVATE-SQL",response.content)

    def test_public_requests_do_not_write_records_or_invoke_refresh_command_source_or_ai(self):
        self.refresh();self.publish()
        before=list(Container.objects.values());events=list(ContainerEvent.objects.values())
        with patch("apps.containers.refresh.refresh_container") as service, patch("apps.containers.refresh.run_provider") as provider, \
             patch("apps.integrations.groq.create_client") as ai, patch("apps.integrations.sealegend.retrieve_body") as source, \
             patch("apps.containers.management.commands.refresh_containers.Command.handle") as command:
            for lang in ("en","ar"):
                self.assertEqual(self.client.get(self.url(lang)).status_code,200)
                self.assertEqual(self.client.get(f"/{lang}/track/",{"code":"INVALID"}).status_code,400)
                self.assertEqual(self.client.post(self.url(lang),{"refresh":"true"}).status_code,405)
            for mocked in (service,provider,ai,source,command):mocked.assert_not_called()
        self.assertEqual(list(Container.objects.values()),before)
        self.assertEqual(list(ContainerEvent.objects.values()),events)

    def test_rate_limit_is_shared_across_codes_and_languages_and_does_not_trust_x_forwarded_for(self):
        for i in range(30):
            response=self.client.get(f"/{'en' if i%2 else 'ar'}/track/INVALID/",HTTP_X_FORWARDED_FOR=f"192.0.2.{i}")
            self.assertEqual(response.status_code,400)
        response=self.client.get(self.url())
        self.assertEqual(response.status_code,429);self.assertEqual(response["Retry-After"],"300")
        self.assertNotContains(response,self.obj.lookup_code,status_code=429)
        self.assertEqual(self.client.get(self.url(),REMOTE_ADDR="192.0.2.70").status_code,404)

    def test_log_formatter_never_records_capability_query_reference_or_errors(self):
        output=StringIO();handler=logging.StreamHandler(output);handler.setFormatter(SafeFormatter())
        logger=logging.getLogger("jahez.request");logger.addHandler(handler)
        try:
            self.client.get("/en/track/",{"code":"PRIVATE-BL-INPUT"})
            self.client.get(self.url())
        finally:logger.removeHandler(handler)
        self.assertNotIn("PRIVATE-BL-INPUT",output.getvalue())
        self.assertNotIn(self.obj.lookup_code,output.getvalue())
        self.assertNotIn(self.obj.search_reference,output.getvalue())

    def test_auto_off_keeps_live_private_changes_out_until_human_confirmation(self):
        self.refresh();self.publish()
        approved=copy.deepcopy(self.obj.public_snapshot)
        self.refresh(self.changed_eta())
        self.assertEqual(self.obj.arrival_estimated["raw"],"2026-02-05")
        self.assertEqual(self.obj.public_snapshot,approved)
        response=self.client.get(self.url())
        self.assertContains(response,"2026-02-03");self.assertNotContains(response,"2026-02-05")
        publish_reviewed(self.obj);self.obj.refresh_from_db()
        self.assertContains(self.client.get(self.url()),"2026-02-05")

    def test_auto_opt_in_updates_validated_timeline_but_not_ai_labels_or_private_manual_content(self):
        self.refresh()
        self.obj.origin_label_ar="ميناء معتمد";self.obj.destination_label_ar="وجهة معتمدة";self.obj.save();self.publish();self.enable_auto()
        private=ContainerEvent.objects.create(container=self.obj,title_en="PRIVATE-NEW-MANUAL",title_ar="خاص")
        data=self.changed_eta();data["labels"]={"EXAMPLE ORIGIN":"ترجمة جديدة","EXAMPLE DESTINATION":"ترجمة أخرى"}
        self.refresh(data)
        self.assertEqual(self.obj.public_snapshot["facts"]["arrival_estimated"]["raw"],"2026-02-05")
        self.assertEqual(self.obj.public_snapshot["facts"]["origin_label_ar"],"ميناء معتمد")
        self.assertEqual(self.obj.origin_label_ar,"ترجمة جديدة")
        self.assertContains(self.client.get(self.url()),"2026-02-05")
        self.assertNotContains(self.client.get(self.url()),"PRIVATE-NEW-MANUAL")
        self.assertNotContains(self.client.get(self.url("ar")),"ترجمة جديدة")
        private.refresh_from_db();self.assertFalse(private.is_public)
        self.assertEqual(self.obj.events.filter(origin="carrier").count(),3)
        self.assertEqual(len(self.obj.public_snapshot["events"]),3)

    def test_auto_never_publishes_private_parent_or_unknown_undated_stage_and_keeps_last_approved_on_failure(self):
        self.enable_auto();self.refresh()
        self.assertFalse(self.obj.is_published);self.assertEqual(self.obj.public_snapshot,{})
        self.assertFalse(self.obj.events.filter(is_public=True).exists())
        self.publish();before=copy.deepcopy(self.obj.public_snapshot)
        data=json.loads(FIXTURE.read_bytes())
        for node in data["result"]["containerList"][0]["nodeList"]:
            if node["movementCode"]=="DG":node.update(movementCode="ZZ",estimateDate="",actualDate="")
        result=self.refresh(prepared(json.dumps(data).encode()))
        self.assertEqual(result.code,"unknown_status")
        self.assertEqual(self.obj.public_snapshot,before)
        self.assertFalse(self.obj.events.filter(raw_status="ZZ",is_public=True).exists())
        with patch("apps.containers.refresh.run_provider",side_effect=RefreshError("timeout")):
            self.assertFalse(refresh_container(self.obj.pk).ok)
        self.obj.refresh_from_db();self.assertEqual(self.obj.public_snapshot,before)

    def test_auto_does_not_publish_omitted_private_fields_or_unreviewed_manual_override(self):
        self.refresh();self.publish();self.enable_auto()
        self.obj.vessel="PRIVATE-EDITED-VESSEL";self.obj.save()
        data=json.loads(FIXTURE.read_bytes())
        data["result"]["containerList"][0]["nodeList"]=[n for n in data["result"]["containerList"][0]["nodeList"] if n["movementCode"]=="DG"]
        self.refresh(prepared(json.dumps(data).encode()))
        self.assertNotIn("PRIVATE-EDITED-VESSEL",json.dumps(self.obj.public_snapshot))
        before=copy.deepcopy(self.obj.public_snapshot)
        self.obj.manual_status_override="on_hold";self.obj.save()
        self.refresh(self.changed_eta())
        self.assertEqual(self.obj.public_snapshot,before)

    def test_automatic_publication_failure_rolls_back_all_facts_and_events(self):
        self.refresh();self.publish();self.enable_auto()
        before=copy.deepcopy(self.obj.public_snapshot);old_eta=self.obj.arrival_estimated
        with patch("apps.containers.refresh.run_provider",return_value=self.changed_eta()), \
             patch("apps.containers.publication.auto_publish",side_effect=ValueError("PRIVATE-PUBLICATION-ERROR")):
            self.assertFalse(refresh_container(self.obj.pk).ok)
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.arrival_estimated,old_eta)
        self.assertEqual(self.obj.public_snapshot,before)
        self.assertEqual(self.obj.last_failure_code,"invalid_extraction")

    def test_corrupted_snapshot_extra_fields_fail_closed_and_xss_is_escaped(self):
        self.obj.vessel='<script>alert("example")</script>';self.obj.save();self.publish()
        response=self.client.get(self.url())
        self.assertContains(response,"&lt;script&gt;");self.assertNotContains(response,"<script>alert")
        corrupt=copy.deepcopy(self.obj.public_snapshot);corrupt["private_reference"]="SECRET-UNREVIEWED"
        Container.objects.filter(pk=self.obj.pk).update(public_snapshot=corrupt)
        response=self.client.get(self.url())
        self.assertEqual(response.status_code,503)
        self.assertNotContains(response,"SECRET-UNREVIEWED",status_code=503)

    def test_admin_first_publication_auto_confirmation_private_edits_and_manual_withdrawal(self):
        self.refresh()
        owner=User.objects.create_superuser("DEMO-publication-owner",password=None);self.client.force_login(owner)
        url=f"/en/admin/containers/container/{self.obj.pk}/change/"
        def payload(**changes):
            self.obj.refresh_from_db()
            return test_container_admin.ContainerAdminTests.payload(self,self.obj,**changes)
        response=self.client.post(url,payload(is_published="on",auto_publish_carrier_updates="on"))
        self.assertEqual(response.status_code,200)
        self.assertIn("confirm_publication",response.context["adminform"].form.errors)
        response=self.client.post(url,payload(is_published="on",confirm_publication="on"))
        self.assertEqual(response.status_code,302)
        self.obj.refresh_from_db();self.assertFalse(self.obj.auto_publish_carrier_updates)
        self.assertTrue(self.obj.public_snapshot)
        response=self.client.post(url,payload(auto_publish_carrier_updates="on"))
        self.assertEqual(response.status_code,200)
        response=self.client.post(url,payload(auto_publish_carrier_updates="on",confirm_publication="on"))
        self.assertEqual(response.status_code,302)
        self.obj.refresh_from_db();self.assertTrue(self.obj.auto_publish_carrier_updates)
        approved=copy.deepcopy(self.obj.public_snapshot)
        self.assertEqual(self.client.post(url,payload(vessel="PRIVATE-WORKING-VESSEL",auto_publish_carrier_updates="on")).status_code,302)
        self.obj.refresh_from_db();self.assertEqual(self.obj.public_snapshot,approved)
        event=ContainerEvent.objects.create(container=self.obj,title_en="Reviewed manual event",title_ar="تحديث معتمد",is_public=True)
        publish_reviewed(self.obj);self.obj.refresh_from_db()
        self.assertContains(self.client.get(self.url()),"Reviewed manual event")
        event.is_public=False;event.save()
        self.assertEqual(self.client.post(url,payload(auto_publish_carrier_updates="on")).status_code,302)
        self.assertNotContains(self.client.get(self.url()),"Reviewed manual event")
        self.assertEqual(self.client.post(url,payload(is_archived="on",auto_publish_carrier_updates="on")).status_code,302)
        self.assertEqual(self.client.get(self.url()).status_code,404)

    def test_large_reviewed_timeline_is_bounded_without_leaking_other_rows(self):
        # Multi-byte text proves the byte cap rather than only the event count cap.
        for i in range(22):
            ContainerEvent.objects.create(container=self.obj,title_en=f"Reviewed {i}",title_ar="معتمد",detail_en="😀"*2000,detail_ar="😀"*2000,is_public=True)
        self.publish()
        self.assertLessEqual(len(json.dumps(self.obj.public_snapshot,ensure_ascii=False).encode()),262144)
        self.assertTrue(self.obj.public_snapshot["limited"])
        self.assertContains(self.client.get(self.url()),"recent published updates")
