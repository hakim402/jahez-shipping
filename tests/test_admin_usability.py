import io
from datetime import timedelta
from unittest.mock import patch
from django.contrib import admin
from django.contrib.auth.models import User, Group, Permission
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone, translation
from apps.core.admin import navigation
from apps.shipments.deletion import confirmation_token, delete_record, clean_file_removals
from apps.shipments.forms import ShipmentForm, CustomerForm, ItemForm, LegForm, EventForm, DocumentUploadForm
from apps.shipments.models import Customer, Shipment, ShipmentItem, TrackingLeg, TrackingEvent, Document, AuditEntry, FileRemoval


class AdminUsabilityTests(TestCase):
    def setUp(self):
        cache.clear()
        call_command("setup_roles", stdout=io.StringIO())
        self.owner = User.objects.create_superuser("DEMO-admin-review", password=None)
        self.ops = User.objects.create_user("DEMO-operations-review", is_staff=True)
        self.ops.groups.add(Group.objects.get(name="Shipping Operations"))
        self.readonly = User.objects.create_user("DEMO-reader-review", is_staff=True)
        self.readonly.groups.add(Group.objects.get(name="Shipping Read Only"))
        self.customer = Customer.objects.create(name="DEMO customer")
        self.shipment = Shipment.objects.create(customer=self.customer)
        self.client.force_login(self.owner)

    def delete(self, obj, actor=None):
        actor = actor or self.owner
        delete_record(type(obj), obj.pk, actor, confirmation_token(obj, actor), "DEMO duplicate record")

    def test_confirmed_deletion_and_retained_history_without_private_capability(self):
        item = ShipmentItem.objects.create(shipment=self.shipment, description_en="DEMO duplicate", quantity=1)
        url = reverse("admin:shipments_shipmentitem_delete", args=[item.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ShipmentItem.objects.filter(pk=item.pk).exists())
        token = response.context["form"].initial["token"]
        self.assertEqual(self.client.post(url, {"token": token, "reason": "DEMO duplicate"}).status_code, 200)
        self.assertTrue(ShipmentItem.objects.filter(pk=item.pk).exists())
        response = self.client.post(url, {"token": token, "reason": "DEMO duplicate", "confirm": "on"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ShipmentItem.objects.filter(pk=item.pk).exists())
        history = AuditEntry.objects.get(action="shipmentitem.deleted")
        self.assertEqual(history.shipment, self.shipment)
        self.assertEqual(history.changes["reason"], "DEMO duplicate")
        self.assertNotIn(self.shipment.reference, str(history.changes))

    def test_permissions_and_csrf_cannot_be_bypassed(self):
        item = ShipmentItem.objects.create(shipment=self.shipment, description_en="DEMO item", quantity=1)
        url = reverse("admin:shipments_shipmentitem_delete", args=[item.pk])
        for actor in (self.ops, self.readonly):
            self.client.force_login(actor)
            self.assertEqual(self.client.get(url).status_code, 403)
            with self.assertRaises(PermissionDenied):
                self.delete(item, actor)
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.owner)
        self.assertEqual(secure.post(url, {"token": confirmation_token(item, self.owner), "confirm": "on", "reason": "DEMO"}).status_code, 403)

    def test_changed_expired_tampered_and_wrong_actor_tokens_are_rejected(self):
        item = ShipmentItem.objects.create(shipment=self.shipment, description_en="DEMO item", quantity=1)
        token = confirmation_token(item, self.owner)
        item.quantity = 2
        item.save()
        with self.assertRaises(ValidationError):
            delete_record(type(item), item.pk, self.owner, token, "DEMO")
        for token in ("invalid", confirmation_token(item, self.ops)):
            with self.assertRaises(ValidationError):
                delete_record(type(item), item.pk, self.owner, token, "DEMO")
        with patch("django.core.signing.time.time", return_value=100):
            expired = confirmation_token(item, self.owner)
        with self.assertRaises(ValidationError):
            delete_record(type(item), item.pk, self.owner, expired, "DEMO")
        self.assertTrue(ShipmentItem.objects.filter(pk=item.pk).exists())

    def test_active_shipment_linked_customer_and_linked_shipment_are_protected(self):
        with self.assertRaises(ValidationError):
            self.delete(self.shipment)
        with self.assertRaises(ValidationError):
            self.delete(self.customer)
        self.shipment.archived_at = timezone.now()
        self.shipment.save()
        ShipmentItem.objects.create(shipment=self.shipment, description_en="DEMO item", quantity=1)
        with self.assertRaises(ValidationError):
            self.delete(self.shipment)

    def test_archived_empty_shipment_deletion_keeps_audit_entries(self):
        self.shipment.archived_at = timezone.now()
        self.shipment.save()
        pk = self.shipment.pk
        AuditEntry.objects.create(shipment=self.shipment, action="shipment.created", object_type="shipment", object_id=str(pk))
        self.delete(self.shipment)
        self.assertFalse(Shipment.objects.filter(pk=pk).exists())
        self.assertEqual(AuditEntry.objects.filter(object_type="shipment", object_id=str(pk)).count(), 2)
        self.assertFalse(AuditEntry.objects.filter(object_type="shipment", object_id=str(pk), shipment__isnull=False).exists())
        with self.assertRaises(PermissionDenied):
            self.delete(AuditEntry.objects.first())

    def test_manual_events_delete_but_carrier_history_and_registered_references_do_not(self):
        event = TrackingEvent.objects.create(shipment=self.shipment, title_en="DEMO manual")
        pk = event.pk
        self.delete(event)
        self.assertFalse(TrackingEvent.objects.filter(pk=pk).exists())
        carrier = TrackingEvent.objects.create(shipment=self.shipment, title_en="DEMO carrier", source="carrier")
        with self.assertRaises(ValidationError):
            self.delete(carrier)
        for state in ("pending", "registered", "stopped"):
            leg = TrackingLeg.objects.create(shipment=self.shipment, sequence=10+TrackingLeg.objects.count(), tracking_number="DEMO-"+state, registration_state=state)
            with self.assertRaises(ValidationError):
                self.delete(leg)

    def test_existing_ai_sources_protect_documents_and_events(self):
        from apps.ai.models import AIDraft
        event = TrackingEvent.objects.create(shipment=self.shipment, title_en="DEMO source")
        AIDraft.objects.create(shipment=self.shipment, event=event, kind="message", dedupe_key="DEMO", source_version="DEMO", expires_at=timezone.now()+timedelta(days=1))
        with self.assertRaises(ValidationError):
            self.delete(event)
        doc = Document.objects.create(shipment=self.shipment, file="documents/DEMO-source.png", original_filename="DEMO-source.png", mime_type="image/png", size=4, checksum="DEMO")
        AIDraft.objects.create(shipment=self.shipment, document=doc, kind="extraction", dedupe_key="DEMO-DOCUMENT", source_version="DEMO", expires_at=timezone.now()+timedelta(days=1))
        with self.assertRaises(ValidationError):
            self.delete(doc)

    def document(self):
        obj = Document(shipment=self.shipment, category="other", original_filename="DEMO.txt", mime_type="image/png", size=4, checksum="DEMO")
        obj.file.save("DEMO-delete.png", ContentFile(b"DEMO"), save=True)
        return obj

    def test_document_file_cleanup_runs_only_after_commit_and_recovers_failures(self):
        doc = self.document()
        name = doc.file.name
        storage = doc.file.storage
        with self.captureOnCommitCallbacks(execute=True):
            self.delete(doc)
            self.assertTrue(storage.exists(name))
        self.assertFalse(storage.exists(name))
        self.assertFalse(FileRemoval.objects.exists())
        doc = self.document()
        name = doc.file.name
        with patch.object(storage, "delete", side_effect=OSError("DEMO-storage-outage")):
            with self.captureOnCommitCallbacks(execute=True):
                self.delete(doc)
        self.assertTrue(FileRemoval.objects.filter(storage_name=name).exists())
        clean_file_removals()
        self.assertFalse(storage.exists(name))
        self.assertFalse(FileRemoval.objects.exists())

    def test_rollback_does_not_remove_file_or_leave_cleanup_job(self):
        from django.db import transaction
        doc = self.document()
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.delete(doc)
                raise RuntimeError("DEMO rollback")
        self.assertTrue(Document.objects.filter(pk=doc.pk).exists())
        self.assertTrue(doc.file.storage.exists(doc.file.name))
        self.assertFalse(FileRemoval.objects.exists())

    def test_public_record_deletion_needs_publication_permission(self):
        self.ops.user_permissions.add(Permission.objects.get(codename="delete_shipmentitem"))
        self.ops.groups.clear()
        self.ops.user_permissions.add(*Permission.objects.filter(codename__in=("view_shipmentitem", "view_shipment")))
        item = ShipmentItem.objects.create(shipment=self.shipment, description_en="DEMO item", quantity=1, public=True)
        with self.assertRaises(PermissionDenied):
            self.delete(item, self.ops)

    def test_navigation_unique_and_permission_filtered_in_both_languages(self):
        request = RequestFactory().get("/en/admin/")
        request.user = self.owner
        for lang in ("en", "ar"):
            with translation.override(lang):
                groups = navigation(request)
                links = [item["link"] for group in groups for item in group["items"]]
                self.assertEqual(len(links), len(set(links)))
                self.assertTrue(all(link.startswith("/"+lang+"/") for link in links))
        request.user = self.readonly
        allowed = [str(item["title"]) for group in navigation(request) for item in group["items"] if item["permission"](request)]
        self.assertNotIn("Users", allowed)
        self.assertNotIn("Groups", allowed)

    def test_help_translated_and_forms_render_in_both_languages(self):
        for lang in ("en", "ar"):
            with translation.override(lang):
                for cls in (CustomerForm, ShipmentForm, ItemForm, LegForm, EventForm, DocumentUploadForm):
                    form = cls()
                    self.assertTrue(any(field.help_text for field in form.fields.values()))
                    for field in form.fields.values():
                        if field.help_text and lang == "ar":
                            self.assertTrue(any('\u0600' <= ch <= '\u06ff' for ch in str(field.help_text)))
            for model in ("customer", "shipment", "shipmentitem", "trackingleg", "trackingevent"):
                response = self.client.get(f"/{lang}/admin/shipments/{model}/add/")
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "AI tools await their approved phase")

    def test_dashboard_filters_match_counts_and_no_duplicate_setup_panel(self):
        response = self.client.get("/en/admin/")
        self.assertContains(response, "?stage=pending")
        self.assertContains(response, "?stage=transit")
        self.assertContains(response, "?stage=attention")
        self.assertContains(response, "?stage=delivered")
        self.assertNotContains(response, "AI awaits its approved phase")
        self.assertEqual(self.client.get("/en/admin/shipments/shipment/?stage=pending").context["cl"].result_count, 1)
        self.assertEqual(self.client.get("/en/admin/shipments/shipment/?stage=transit").context["cl"].result_count, 0)
        Shipment.objects.create(customer=self.customer, status="delivered")
        Shipment.objects.create(customer=self.customer, status="delivered", archived_at=timezone.now())
        self.assertEqual(self.client.get("/en/admin/").context["metrics"]["delivered"], 1)
        self.assertEqual(self.client.get("/en/admin/shipments/shipment/?stage=delivered").context["cl"].result_count, 1)

    def test_bulk_delete_is_not_offered_and_history_is_immutable(self):
        request = RequestFactory().get("/en/admin/")
        request.user = self.owner
        for model in (Shipment, Customer, ShipmentItem, Document):
            self.assertNotIn("delete_selected", admin.site._registry[model].get_actions(request))
        self.assertFalse(admin.site._registry[AuditEntry].has_delete_permission(request))
