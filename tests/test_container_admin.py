import copy
import secrets
from unittest.mock import patch

from django.contrib.auth.models import User, Permission
from django.contrib.admin.models import LogEntry
from django.test import TestCase, Client
from django.utils import timezone

from apps.containers.models import Container, ContainerEvent
from apps.containers.values import Status
from tests.test_containers import source_time


class ContainerAdminTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser("DEMO-admin-owner", password=secrets.token_urlsafe(24))
        self.client.force_login(self.owner)
        self.add_url = "/en/admin/containers/container/add/"
        self.list_url = "/en/admin/containers/container/"

    def payload(self, obj=None, **extra):
        data = {"expected_revision": str(obj.revision if obj else 0), "search_reference": obj.search_reference if obj else "DEMOAB123456", "container_number": obj.container_number if obj else "",
                "equipment_type": "40HC", "equipment_quantity": "1", "origin_code": "AAAAA", "destination_code": "BBBBB",
                "origin_label_en": "Example origin", "origin_label_ar": "ميناء تجريبي", "destination_label_en": "Example destination", "destination_label_ar": "وجهة تجريبية",
                "vessel": "EXAMPLE VESSEL", "voyage": "100E", "manual_status_override": "", "manual_notes_en": "", "manual_notes_ar": "",
                "events-TOTAL_FORMS": "0", "events-INITIAL_FORMS": "0", "events-MIN_NUM_FORMS": "0", "events-MAX_NUM_FORMS": "50", "_save": "Save"}
        for field in ("departure_actual", "departure_estimated", "arrival_actual", "arrival_estimated"):
            value = getattr(obj, field, None) if obj else None
            data[field + "_0"] = value["raw"] if value else ""
            data[field + "_1"] = (value["source_timezone"] or "") if value else ""
        if obj and obj.is_published:
            data["is_published"] = "on"
        if obj and obj.archived_at:
            data["is_archived"] = "on"
        data.update(extra)
        return data

    def url(self, obj, lang="en"):
        return f"/{lang}/admin/containers/container/{obj.pk}/change/"

    def assert_saved(self, response):
        if response.status_code == 200 and response.context:
            self.assertEqual(response.context["adminform"].form.errors, {}, "parent form errors")
            for inline in response.context["inline_admin_formsets"]:
                self.assertEqual(inline.formset.errors, [], "inline form errors")
                self.assertEqual(list(inline.formset.non_form_errors()), [], "inline formset errors")
        self.assertEqual(response.status_code, 302)

    def add_event_data(self, data, event=None, **extra):
        data.update({"events-TOTAL_FORMS": "1", "events-INITIAL_FORMS": "1" if event else "0",
                     "events-0-title_en": "Manual departure", "events-0-title_ar": "مغادرة يدوية",
                     "events-0-detail_en": "Office-confirmed update", "events-0-detail_ar": "تحديث مؤكد من المكتب",
                     "events-0-location": "EXAMPLE PORT", "events-0-designation": "actual",
                     "events-0-source_time_0": "2026-01-02 22:30", "events-0-source_time_1": ""})
        if event:
            data["events-0-id"] = str(event.pk)
        data.update(extra)
        return data

    def test_add_unbound_private_then_confirm_binding_and_keep_source_readonly(self):
        self.assert_saved(self.client.post(self.add_url, self.payload()))
        obj = Container.objects.get()
        self.assertFalse(obj.is_published)
        self.assertEqual(obj.container_number, "")
        result = self.client.post(self.url(obj), self.payload(obj, container_number="TEST1234567"))
        self.assertEqual(result.status_code, 200)
        self.assertIn("confirm_identity", result.context["adminform"].form.errors)
        self.assert_saved(self.client.post(self.url(obj), self.payload(obj, container_number="TEST1234567", confirm_identity="on")))
        obj.refresh_from_db()
        self.assertEqual(obj.container_number, "TEST1234567")
        self.assert_saved(self.client.post(self.url(obj), self.payload(obj, container_number="DEMO7654321", search_reference="OTHER123456", source_website="http://127.0.0.1", raw_status="FORGED", carrier_status="completed")))
        obj.refresh_from_db()
        self.assertEqual((obj.container_number, obj.search_reference), ("TEST1234567", "DEMOAB123456"))
        self.assertEqual(obj.carrier_status, Status.UNKNOWN)
        self.assertEqual(obj.raw_status, "")

    def test_publication_archive_unarchive_confirmation_and_no_destructive_delete(self):
        obj = Container.objects.create(search_reference="DEMOAB123456")
        result = self.client.post(self.url(obj), self.payload(obj, is_published="on"))
        self.assertEqual(result.status_code, 200)
        self.assertIn("confirm_publication", result.context["adminform"].form.errors)
        self.assert_saved(self.client.post(self.url(obj), self.payload(obj, is_published="on", confirm_publication="on")))
        obj.refresh_from_db(); code = obj.lookup_code
        self.assertContains(self.client.get(self.url(obj)), "data-jahez-copy")
        self.assert_saved(self.client.post(self.url(obj), self.payload(obj, is_archived="on")))
        obj.refresh_from_db(); self.assertIsNotNone(obj.archived_at)
        self.assertNotContains(self.client.get(self.url(obj)), "data-jahez-copy-status")
        data = self.payload(obj); data.pop("is_archived")
        result = self.client.post(self.url(obj), data)
        self.assertEqual(result.status_code, 200)
        data["confirm_publication"] = "on"
        self.assert_saved(self.client.post(self.url(obj), data))
        obj.refresh_from_db(); self.assertIsNone(obj.archived_at); self.assertEqual(obj.lookup_code, code)
        data = self.payload(obj); data.pop("is_published")
        self.assert_saved(self.client.post(self.url(obj), data))
        obj.refresh_from_db(); self.assertFalse(obj.is_published)
        self.assertEqual(self.client.post(f"/en/admin/containers/container/{obj.pk}/delete/", {"post": "yes"}).status_code, 403)
        self.assertTrue(Container.objects.filter(pk=obj.pk).exists())

    def test_bilingual_manual_event_create_edit_override_and_ordinary_admin_log(self):
        obj = Container.objects.create(search_reference="DEMOAB123456", carrier_status=Status.IN_TRANSIT)
        data = self.add_event_data(self.payload(obj, manual_status_override="on_hold", manual_notes_en="Private office note", manual_notes_ar="ملاحظة داخلية"))
        self.assert_saved(self.client.post(self.url(obj), data))
        obj.refresh_from_db(); event = obj.events.get()
        self.assertEqual(obj.display_status, Status.ON_HOLD)
        self.assertEqual(event.origin, "manual"); self.assertFalse(event.is_public)
        self.assertIsNone(event.source_time["source_timezone"])
        self.assertIsNone(event.source_time["normalized_instant"])
        data = self.add_event_data(self.payload(obj), event, **{"events-0-title_en": "Corrected manual update"})
        self.assert_saved(self.client.post(self.url(obj), data))
        obj.refresh_from_db(); event.refresh_from_db()
        self.assertEqual(obj.display_status, Status.IN_TRANSIT)
        self.assertEqual(event.title_en, "Corrected manual update")
        self.assertEqual(obj.events.count(), 1)
        self.assertTrue(LogEntry.objects.filter(object_id=str(obj.pk), user=self.owner).exists())
        self.assertContains(self.client.get(self.url(obj)), "Use carrier status (clear override)")
        arabic = self.client.get(self.url(obj, "ar"))
        self.assertContains(arabic, "مغادرة يدوية")

    def test_manual_event_publication_requires_confirmation_and_bilingual_details(self):
        obj = Container.objects.create(search_reference="DEMOAB123456")
        data = self.add_event_data(self.payload(obj), **{"events-0-is_public": "on"})
        result = self.client.post(self.url(obj), data)
        self.assertEqual(result.status_code, 200); self.assertEqual(obj.events.count(), 0)
        data["confirm_publication"] = "False"
        self.assertEqual(self.client.post(self.url(obj), data).status_code, 200)
        data["confirm_publication"] = "on"
        data["events-0-detail_ar"] = ""
        self.assertEqual(self.client.post(self.url(obj), data).status_code, 200)
        data["events-0-detail_ar"] = "تحديث مؤكد"
        self.assert_saved(self.client.post(self.url(obj), data))
        self.assertTrue(obj.events.get().is_public)
        obj.refresh_from_db(); self.assertFalse(obj.is_published)

    def test_forged_carrier_or_other_parent_event_cannot_be_edited_or_published(self):
        obj = Container.objects.create(search_reference="DEMOAB123456")
        carrier = ContainerEvent.objects.create(container=obj, origin="carrier", source_event_id="DEMO-carrier-id", title_en="Carrier fact")
        other_parent = Container.objects.create(search_reference="DEMOXY654321")
        other = ContainerEvent.objects.create(container=other_parent, title_en="Other parent's note")
        for forged in (carrier, other):
            response = self.client.post(self.url(obj), self.add_event_data(self.payload(obj, confirm_publication="on"), forged, **{"events-0-title_en": "FORGED", "events-0-is_public": "on"}))
            self.assertNotEqual(response.status_code, 302)
            forged.refresh_from_db(); self.assertFalse(forged.is_public)
            self.assertNotEqual(forged.title_en, "FORGED")
        self.assertEqual(ContainerEvent.objects.count(), 2)

    def test_staff_permissions_and_view_only_layout_do_not_allow_writes(self):
        obj = Container.objects.create(search_reference="DEMOAB123456")
        user = User.objects.create_user("DEMO-staff", password=secrets.token_urlsafe(24), is_staff=True)
        client = Client(); client.force_login(user)
        self.assertEqual(client.get(self.list_url).status_code, 403)
        self.assertEqual(client.get(self.add_url).status_code, 403)
        user.user_permissions.add(Permission.objects.get(codename="view_container"), Permission.objects.get(codename="view_containerevent"))
        self.assertEqual(client.get(self.list_url).status_code, 200)
        self.assertEqual(client.get(self.url(obj)).status_code, 200)
        self.assertEqual(client.post(self.url(obj), self.payload(obj, is_published="on", confirm_publication="on")).status_code, 403)
        user.user_permissions.add(Permission.objects.get(codename="change_container"))
        data = self.add_event_data(self.payload(obj))
        self.assert_saved(client.post(self.url(obj), data))
        self.assertEqual(obj.events.count(), 0)
        self.assertEqual(client.post(self.add_url, self.payload()).status_code, 403)

    def test_admin_csrf_checks_and_default_private_add(self):
        client = Client(enforce_csrf_checks=True); client.force_login(self.owner)
        client.get(self.add_url)
        self.assertEqual(client.post(self.add_url, self.payload()).status_code, 403)
        data = self.payload(); data["csrfmiddlewaretoken"] = client.cookies["jahez_shipping_csrf"].value
        self.assertEqual(client.post(self.add_url, data, HTTP_ORIGIN="https://invalid.test").status_code, 403)
        self.assert_saved(client.post(self.add_url, data, HTTP_ORIGIN="http://testserver"))
        self.assertFalse(Container.objects.get().is_published)

    def test_manual_copy_dates_validate_precision_and_preserve_explicit_existing_instant(self):
        obj = Container.objects.create(search_reference="DEMOAB123456", arrival_estimated=source_time(zone="UTC", instant="2026-02-03T21:00:00Z"))
        self.assert_saved(self.client.post(self.url(obj), self.payload(obj, manual_notes_en="Independent update")))
        obj.refresh_from_db(); self.assertEqual(obj.arrival_estimated["normalized_instant"], "2026-02-03T21:00:00Z")
        data = self.payload(obj, arrival_estimated_0="2026-02-04", arrival_estimated_1="")
        self.assert_saved(self.client.post(self.url(obj), data))
        obj.refresh_from_db()
        self.assertEqual(obj.arrival_estimated, source_time("2026-02-04", precision="date"))
        invalid = self.client.post(self.url(obj, "ar"), self.payload(obj, arrival_estimated_0="2026-02-30"))
        self.assertEqual(invalid.status_code, 200)
        self.assertNotContains(invalid, "لا توجد أخطاء لتصحيحها.")
        self.assertContains(invalid, "يرجى مراجعة الحقول والرسائل المبيّنة أدناه.")
        self.assertContains(invalid, "أدخل نص الوقت")

    def test_timeline_source_order_unknown_time_xss_and_advanced_privacy(self):
        obj = Container.objects.create(search_reference="DEMOAB123456")
        ContainerEvent.objects.create(container=obj, title_en="Later event", designation="actual", source_time=source_time("2026-02-04 10:00", "actual"))
        ContainerEvent.objects.create(container=obj, title_en="Earlier event", designation="actual", source_time=source_time("2026-02-03", "actual", "date"))
        ContainerEvent.objects.create(container=obj, title_en="Undated marker <script>alert(1)</script>")
        response = self.client.get(self.url(obj))
        html = response.content.decode()
        self.assertLess(html.index("Earlier event"), html.index("Later event"))
        self.assertLess(html.index("Later event"), html.index("Undated marker"))
        self.assertContains(response, "Timezone not supplied")
        self.assertContains(response, "Date only")
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")
        for name in ("refresh_claim", "source_evidence", "source_fingerprint", "dedupe_key"):
            self.assertNotContains(response, 'name="'+name+'"')
        self.assertContains(response, "Source and advanced details")
        self.assertContains(response, "Save manual edits first")
        self.assertContains(response, "Refresh now")

    def test_list_search_archive_filter_and_bilingual_navigation_without_provider_calls(self):
        active = Container.objects.create(search_reference="DEMOAB123456", container_number="TEST1234567")
        archived = Container.objects.create(search_reference="DEMOXY654321", archived_at=timezone.now())
        with patch("apps.integrations.sealegend.retrieve_candidate") as source, patch("apps.integrations.groq.create_client") as ai:
            response = self.client.get(self.list_url, {"archive": "active"})
            self.assertContains(response, active.search_reference); self.assertNotContains(response, archived.search_reference)
            response = self.client.get(self.list_url, {"archive": "archived"})
            self.assertNotContains(response, active.search_reference); self.assertContains(response, archived.search_reference)
            self.assertContains(self.client.get(self.list_url, {"q": "TEST1234567"}), active.search_reference)
            for language in ("en", "ar"):
                response = self.client.get(f"/{language}/admin/containers/container/")
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'dir="rtl"' if language == "ar" else 'dir="ltr"')
                self.assertContains(response, "navigationOpen")
                self.assertContains(response, "الحاويات" if language == "ar" else "Containers")
                self.assertNotContains(response, "carrier-health")
            source.assert_not_called(); ai.assert_not_called()
