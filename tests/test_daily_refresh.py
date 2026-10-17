import configparser
from datetime import timedelta
from io import StringIO
import json
from pathlib import Path
import shlex
import tempfile
from unittest.mock import patch
import uuid
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.core.management import call_command, CommandError
from django.db import connection
from django.test import TransactionTestCase, SimpleTestCase, override_settings
from django.utils import timezone, translation

from apps.containers.management.commands.refresh_containers import batch_lock
from apps.containers.models import Container
from apps.containers.refresh import RefreshResult, refresh_container
from apps.containers.tracking import attention_text
from tests.test_container_refresh import prepared
from tests.test_containers import source_time

COMMAND = "apps.containers.management.commands.refresh_containers"


class DailyRefreshTests(TransactionTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="jahez-daily-test-")
        self.addCleanup(self.directory.cleanup)
        self.settings_override = override_settings(DATA_DIR=Path(self.directory.name))
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.out = StringIO()

    def obj(self, **fields):
        return Container.objects.create(search_reference="DEMOAB123456", **fields)

    def command(self, **options):
        self.out = StringIO()
        call_command("refresh_containers", stdout=self.out, stderr=StringIO(), **options)
        return json.loads(self.out.getvalue()) if self.out.getvalue() else None

    def summary(self):
        return json.loads(self.out.getvalue())

    def test_active_selection_includes_private_and_past_eta_but_skips_archived_completed(self):
        private = self.obj(arrival_estimated=source_time("2000-01-01", precision="date"))
        public = self.obj(is_published=True, carrier_status="arrived")
        override = self.obj(carrier_status="completed", manual_status_override="on_hold")
        self.obj(archived_at=timezone.now())
        self.obj(manual_status_override="completed")
        called = []
        def service(pk, *, active_only):
            self.assertFalse(connection.in_atomic_block)
            self.assertTrue(active_only)
            called.append(pk)
            return RefreshResult(True, "unchanged")
        with patch(COMMAND + ".refresh_container", side_effect=service):
            summary = self.command(active=True)
        self.assertEqual(called, [private.pk, public.pk])
        self.assertNotIn(override.pk, called)
        self.assertEqual((summary["attempted"], summary["unchanged"], summary["failed"]), (2, 2, 0))

    def test_single_selection_and_absent_or_finished_no_work(self):
        target = self.obj(); other = self.obj()
        with patch(COMMAND + ".refresh_container", return_value=RefreshResult(True, "updated", True)) as service:
            self.assertEqual(self.command(container=target.pk)["changed"], 1)
            service.assert_called_once_with(target.pk, active_only=True)
        for fields in ({"archived_at": timezone.now()}, {"manual_status_override": "completed"}):
            obj = self.obj(**fields)
            with patch(COMMAND + ".refresh_container") as service:
                self.assertEqual(self.command(container=obj.pk)["selected"], 0)
                service.assert_not_called()
        self.assertEqual(self.command(container=other.pk + 99999)["selected"], 0)

    def test_dry_run_and_status_have_no_provider_lock_or_database_writes(self):
        self.obj()
        before = list(Container.objects.values())
        for flag in ("--dry-run", "--status"):
            out = StringIO()
            with patch(COMMAND + ".refresh_container") as service, patch(COMMAND + ".batch_lock") as lock:
                with self.assertNumQueries(1):
                    call_command("refresh_containers", "--active", flag, stdout=out)
                service.assert_not_called(); lock.assert_not_called()
            self.assertTrue(json.loads(out.getvalue())["dry_run"])
        self.assertEqual(list(Container.objects.values()), before)
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])

    def test_failure_and_exception_are_isolated_no_retries_or_sensitive_output(self):
        for _ in range(3): self.obj()
        with patch(COMMAND + ".refresh_container", side_effect=[RefreshResult(False, "timeout"),
                RuntimeError("private carrier reference key content"), RefreshResult(True, "updated", True)]) as service:
            with self.assertRaises(CommandError) as error:
                self.command(active=True, quiet=True)
        self.assertEqual(error.exception.returncode, 1)
        self.assertEqual(service.call_count, 3)
        self.assertEqual((self.summary()["failed"], self.summary()["changed"]), (2, 1))
        self.assertNotIn("DEMOAB", self.out.getvalue())
        self.assertNotIn("private carrier", str(error.exception) + self.out.getvalue())
        with batch_lock(): pass  # Exceptions release the batch lock.

    def test_overlap_lock_is_shared_and_symlink_refused(self):
        self.obj()
        with batch_lock(), patch(COMMAND + ".refresh_container") as service:
            with self.assertRaises(CommandError) as error:
                self.command(active=True)
            self.assertEqual(error.exception.returncode, 75); service.assert_not_called()
        lock = Path(self.directory.name) / ".container-refresh.lock"
        self.assertEqual(lock.stat().st_mode & 0o777, 0o600)
        lock.unlink()
        target = Path(self.directory.name) / "preserve.txt"; target.write_text("untouched")
        lock.symlink_to(target)
        with self.assertRaises(CommandError):
            self.command(active=True)
        self.assertEqual(target.read_text(), "untouched")

    def test_limit_reports_incomplete_and_oldest_attempt_is_first(self):
        now = timezone.now()
        recent = self.obj(last_refresh_attempt_at=now)
        old = self.obj(last_refresh_attempt_at=now-timedelta(days=3))
        never = self.obj()
        with patch(COMMAND + ".refresh_container", return_value=RefreshResult(True, "unchanged")) as service:
            with self.assertRaises(CommandError) as error:
                self.command(active=True, limit=2)
        self.assertEqual(error.exception.returncode, 2)
        self.assertEqual([c.args[0] for c in service.call_args_list], [never.pk, old.pk])
        self.assertTrue(self.summary()["more_eligible"])
        self.assertNotIn(recent.pk, [c.args[0] for c in service.call_args_list])

    def test_deadline_reserves_whole_refresh_and_never_starts_next(self):
        self.obj(); self.obj()
        with patch(COMMAND + ".time.monotonic", side_effect=[100, 101, 151]), \
                patch(COMMAND + ".refresh_container", return_value=RefreshResult(True, "unchanged")) as service:
            with self.assertRaises(CommandError) as error:
                self.command(active=True, max_seconds=60)
        self.assertEqual(error.exception.returncode, 2)
        self.assertEqual(service.call_count, 1)
        self.assertEqual(self.summary()["deferred"], 1)

    def test_unchanged_and_no_work_quiet_but_review_needed_is_visible(self):
        self.assertIsNone(self.command(active=True, quiet=True))
        self.obj()
        with patch(COMMAND + ".refresh_container", return_value=RefreshResult(True, "unchanged")):
            self.assertIsNone(self.command(active=True, quiet=True))
        with patch(COMMAND + ".refresh_container", return_value=RefreshResult(True, "unknown_status")):
            with self.assertRaises(CommandError): self.command(active=True, quiet=True)
        self.assertEqual(self.summary()["attention"], 1)

    def test_invalid_bounds_fail_before_any_work(self):
        for kwargs in ({"limit": 0}, {"limit": 101}, {"max_seconds": 59}, {"max_seconds": 901}, {"container": 0}):
            with patch(COMMAND + ".batch_lock") as lock, patch(COMMAND + ".refresh_container") as service:
                with self.assertRaises(CommandError):
                    self.command(**({"active": True} if "container" not in kwargs else {}), **kwargs)
                lock.assert_not_called(); service.assert_not_called()

    def test_real_service_twice_is_idempotent_preserves_manual_and_private_state(self):
        obj = self.obj(manual_status_override="on_hold", manual_notes_en="Office note")
        with patch("apps.containers.refresh.run_provider", return_value=prepared()) as provider:
            first = self.command(active=True)
            ids = list(obj.events.values_list("pk", flat=True))
            second = self.command(active=True)
        self.assertEqual(provider.call_count, 2)
        self.assertEqual((first["changed"], second["unchanged"]), (1, 1))
        self.assertEqual(list(obj.events.values_list("pk", flat=True)), ids)
        obj.refresh_from_db()
        self.assertEqual((obj.manual_notes_en, obj.manual_status_override), ("Office note", "on_hold"))
        self.assertFalse(obj.is_published); self.assertFalse(obj.events.filter(is_public=True).exists())
        self.assertIsNotNone(obj.last_refresh_success_at)
        with translation.override("en"):
            self.assertEqual(attention_text(obj), "Up to date")

    def test_manual_claim_blocks_command_and_selection_race_skips_completed_before_network(self):
        obj = self.obj(refresh_claim=uuid.uuid4(), refresh_claim_expires_at=timezone.now()+timedelta(seconds=20))
        with patch("apps.containers.refresh.run_provider") as provider:
            with self.assertRaises(CommandError): self.command(active=True)
            provider.assert_not_called()
        obj.refresh_claim = obj.refresh_claim_expires_at = None
        obj.manual_status_override = "completed"; obj.save()
        before = obj.revision
        with patch("apps.containers.refresh.run_provider") as provider:
            result = refresh_container(obj.pk, active_only=True)
            provider.assert_not_called()
        obj.refresh_from_db()
        self.assertEqual(result.code, "skipped"); self.assertEqual(obj.revision, before)

    def test_attention_and_bilingual_admin_filters_are_read_only(self):
        now = timezone.now()
        current = self.obj(last_refresh_success_at=now, carrier_status="in_transit")
        never = self.obj()
        stale = self.obj(last_refresh_success_at=now-timedelta(hours=31))
        failed = self.obj(last_refresh_success_at=now, last_failure_code="timeout")
        review = self.obj(last_refresh_success_at=now, last_failure_code="unknown_status")
        archived = self.obj(archived_at=now)
        completed = self.obj(manual_status_override="completed")
        checking = self.obj(refresh_claim=uuid.uuid4(), refresh_claim_expires_at=now+timedelta(seconds=20))
        expected = [(current,"Up to date"), (never,"Not checked yet"), (stale,"Stale — last successful check is over 30 hours old"),
                    (failed,"Last check failed — retry or verify manual facts"), (review,"Carrier stages need review"),
                    (archived,"Archived — daily checks skipped"), (completed,"Completed — daily checks skipped"), (checking,"Checking carrier")]
        with translation.override("en"):
            for obj,text in expected: self.assertEqual(attention_text(obj,now), text)
        with translation.override("ar"):
            self.assertEqual(attention_text(stale,now), "بيانات قديمة — مضى أكثر من 30 ساعة على آخر تحقق ناجح")
        user=User.objects.create_superuser("DEMO-daily-admin", password=None)
        self.client.force_login(user)
        with patch("apps.containers.refresh.run_provider") as provider:
            response=self.client.get("/en/admin/containers/container/?attention=needed")
            self.assertEqual(response.status_code,200)
            ids={row.pk for row in response.context["cl"].result_list}
            self.assertEqual(ids,{never.pk,stale.pk,failed.pk,review.pk,checking.pk})
            response=self.client.get("/ar/admin/containers/container/?attention=current")
            self.assertEqual({row.pk for row in response.context["cl"].result_list},{current.pk})
            self.assertContains(self.client.get(f"/ar/admin/containers/container/{stale.pk}/change/"), "بيانات قديمة")
            provider.assert_not_called()

    def test_public_get_post_and_missing_tracking_never_run_command_or_providers(self):
        with patch(COMMAND + ".Command.handle") as command, patch("apps.containers.refresh.run_provider") as provider, \
                patch("apps.integrations.groq.create_client") as groq:
            for language in ("en","ar"):
                self.assertEqual(self.client.get(f"/{language}/").status_code,200)
                self.assertEqual(self.client.get(f"/{language}/who-we-are/").status_code,200)
                self.assertEqual(self.client.post(f"/{language}/",{"code":"DEMO"}).status_code,405)
                self.assertEqual(self.client.get(f"/{language}/track/DEMO/").status_code,400)
            command.assert_not_called();provider.assert_not_called();groq.assert_not_called()


class SchedulerPackageTests(SimpleTestCase):
    def test_parse_scoped_oneshot_and_explicit_timezone_timer_without_activation(self):
        root=Path(__file__).resolve().parents[1]/"deploy"/"systemd"
        service=configparser.ConfigParser(interpolation=None, strict=False);service.read(root/"jahez-shipping-refresh.service")
        timer=configparser.ConfigParser(interpolation=None);timer.read(root/"jahez-shipping-refresh.timer")
        self.assertEqual(service["Service"]["Type"],"oneshot")
        self.assertEqual(service["Service"]["Restart"],"no")
        self.assertGreater(int(service["Service"]["TimeoutStartSec"]),900)
        args=shlex.split(service["Service"]["ExecStart"])
        self.assertEqual(args[:3],["/usr/bin/docker","compose","--env-file"])
        self.assertIn("jahez-shipping-prod",args)
        self.assertEqual(args[args.index("exec")+1:],["--interactive=false","-T","web","python","manage.py","refresh_containers","--active","--limit","50","--max-seconds","900","--quiet"])
        self.assertNotIn("run",args);self.assertNotIn("up",args)
        self.assertEqual(timer["Timer"]["OnCalendar"],"*-*-* 09:00:00 Asia/Kabul")
        self.assertEqual(timer["Timer"]["Persistent"],"true")
        self.assertEqual(timer["Timer"]["Unit"],"jahez-shipping-refresh.service")
        self.assertEqual(timer["Timer"]["RandomizedDelaySec"],"0")
        self.assertNotIn("OnBootSec",timer["Timer"])
        local=timezone.datetime(2026,10,17,9,tzinfo=ZoneInfo("Asia/Kabul"))
        self.assertEqual(local.astimezone(ZoneInfo("UTC")).strftime("%H:%M"),"04:30")
