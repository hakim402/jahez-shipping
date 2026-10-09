import io
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth.models import User, Group
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, Client, override_settings
from django.utils import timezone
from apps.shipments.models import Customer, Shipment, ShipmentItem, TrackingLeg, TrackingEvent, Document, AuditEntry, Status
from apps.shipments.services import save_shipment, save_child, archive_shipment, rotate_shipment_reference, delayed_shipments
from apps.shipments.uploads import inspect_upload, store_document
from apps.core.management.commands.seed_demo import sample_pdf


class ManualOperationsTests(TestCase):
    def setUp(self):
        cache.clear()
        call_command("setup_roles", stdout=io.StringIO())
        self.ops = User.objects.create_user("DEMO-operations-test", is_staff=True)
        self.ops.groups.add(Group.objects.get(name="Shipping Operations"))
        self.readonly = User.objects.create_user("DEMO-readonly-test", is_staff=True)
        self.readonly.groups.add(Group.objects.get(name="Shipping Read Only"))
        self.customer = Customer.objects.create(name="PRIVATE-CUSTOMER", company="PRIVATE-COMPANY", email="private@example.invalid", phone="PRIVATE-PHONE", address="PRIVATE-ADDRESS")
        self.shipment = Shipment.objects.create(customer=self.customer, published=True, origin_en="China", origin_ar="الصين", destination_en="UAE", destination_ar="الإمارات", bill_number="PRIVATE-BILL", internal_order="PRIVATE-ORDER", internal_notes="PRIVATE-NOTES")

    def post_tracking(self, lang="en", reference=None):
        return self.client.post(f"/{lang}/", {"reference": reference or self.shipment.reference})

    def test_authorized_admin_can_create_publish_and_track_manual_shipment(self):
        self.client.force_login(self.ops)
        r = self.client.post('/en/admin/shipments/customer/add/', {'name': 'DEMO admin workflow', 'company': 'DEMO company', '_save': 'Save'})
        self.assertEqual(r.status_code, 302)
        customer = Customer.objects.get(name='DEMO admin workflow')
        payload = {'customer': customer.pk, 'internal_order': 'DEMO-ADMIN-FLOW', 'mode': 'sea', 'tracking_mode': 'manual', 'status': 'created', 'origin_en': 'China', 'origin_ar': 'الصين', 'destination_en': 'UAE', 'destination_ar': 'الإمارات', 'published': 'on', 'revision_token': '0', '_save': 'Save'}
        for prefix in ('items','legs','events'):
            payload.update({prefix+'-TOTAL_FORMS': '0',prefix+'-INITIAL_FORMS': '0',prefix+'-MIN_NUM_FORMS': '0',prefix+'-MAX_NUM_FORMS': '1000'})
        r = self.client.post('/en/admin/shipments/shipment/add/', payload)
        self.assertEqual(r.status_code, 302, str(r.context['adminform'].form.errors) if r.context and 'adminform' in r.context else '')
        shipment = Shipment.objects.get(internal_order='DEMO-ADMIN-FLOW')
        r = self.client.post('/en/admin/shipments/shipmentitem/add/', {'shipment': shipment.pk, 'description_en': 'DEMO approved mugs', 'description_ar': 'أكواب معتمدة تجريبية', 'quantity': '120', 'unit': 'units', 'unit_ar': 'قطعة', 'cartons': '6', 'public': 'on', '_save': 'Save'})
        self.assertEqual(r.status_code, 302)
        r = self.client.post('/en/admin/shipments/trackingevent/add/', {'shipment': shipment.pk, 'occurred_at_0': '2026-10-01', 'occurred_at_1': '09:00:00', 'title_en': 'DEMO received', 'title_ar': 'استلام تجريبي', 'mapped_status': 'warehouse', 'public': 'on', '_save': 'Save'})
        self.assertEqual(r.status_code, 302)
        self.client.logout()
        r = self.client.post('/en/', {'reference': shipment.reference})
        self.assertEqual(r.context['state'], 'found')
        self.assertContains(r, 'DEMO approved mugs')
        self.assertContains(r, 'DEMO received')
        self.assertTrue(AuditEntry.objects.filter(shipment=shipment,action='shipment.created').exists())

    def test_random_reference_has_160_bits_and_is_not_identifier(self):
        references = {Shipment(customer=self.customer).reference for _ in range(500)}
        self.assertEqual(len(references), 500)
        self.assertTrue(all(len(r) == 44 and r.startswith("JHZ-") for r in references))

    def test_default_private_records_and_bilingual_public_validation(self):
        self.assertFalse(Shipment(customer=self.customer).published)
        self.assertFalse(ShipmentItem().public)
        self.assertFalse(TrackingEvent().public)
        with self.assertRaises(ValidationError):
            Shipment(customer=self.customer, published=True).full_clean()

    def test_private_fields_never_reach_public_context_or_html(self):
        ShipmentItem.objects.create(shipment=self.shipment, description_en="APPROVED-CUP", description_ar="كوب معتمد", quantity=120, unit_ar="قطعة", public=True, sku="PRIVATE-SKU")
        ShipmentItem.objects.create(shipment=self.shipment, description_en="PRIVATE-PRODUCT", quantity=1)
        TrackingEvent.objects.create(shipment=self.shipment, title_en="APPROVED-EVENT", title_ar="مرحلة معتمدة", body_en="Approved note", body_ar="ملاحظة معتمدة", public=True, raw_text="PRIVATE-RAW", location="PRIVATE-LOCATION", provider_identity="PRIVATE-PROVIDER")
        TrackingEvent.objects.create(shipment=self.shipment, title_en="PRIVATE-EVENT", public=False)
        TrackingLeg.objects.create(shipment=self.shipment, tracking_number="PRIVATE-CARRIER")
        for lang in ("en", "ar"):
            r = self.post_tracking(lang)
            self.assertEqual(r.status_code, 200)
            for private in [self.shipment.reference, "PRIVATE-CUSTOMER", "PRIVATE-COMPANY", "private@example.invalid", "PRIVATE-PHONE", "PRIVATE-ADDRESS", "PRIVATE-BILL", "PRIVATE-ORDER", "PRIVATE-NOTES", "PRIVATE-SKU", "PRIVATE-PRODUCT", "PRIVATE-RAW", "PRIVATE-LOCATION", "PRIVATE-PROVIDER", "PRIVATE-EVENT", "PRIVATE-CARRIER"]:
                self.assertNotContains(r, private)
            self.assertContains(r, "كوب معتمد" if lang == "ar" else "APPROVED-CUP")
            self.assertNotIsInstance(r.context["result"], Shipment)
            self.assertEqual(r["Cache-Control"], "no-store")
            self.assertEqual(r["X-Robots-Tag"], "noindex, nofollow")

    def test_unknown_unpublished_archive_and_bill_lookups_are_indistinguishable(self):
        references = ["JHZ-" + "F" * 40, "PRIVATE-BILL", "PRIVATE-ORDER"]
        for reference in references:
            self.assertEqual(self.post_tracking(reference=reference).context["state"], "not_found")
        self.shipment.published = False
        self.shipment.save()
        self.assertEqual(self.post_tracking().context["state"], "not_found")
        self.shipment.published = True
        self.shipment.save()
        archive_shipment(self.shipment, self.ops)
        self.assertEqual(self.post_tracking().context["state"], "not_found")
        self.assertTrue(Shipment.objects.filter(pk=self.shipment.pk).exists())
        archive_shipment(self.shipment, self.ops, restore=True)
        self.shipment.refresh_from_db()
        self.assertFalse(self.shipment.published)

    def test_reference_rotation_revokes_without_recording_capability(self):
        old = self.shipment.reference
        rotate_shipment_reference(self.shipment, self.ops)
        self.shipment.refresh_from_db()
        self.assertNotEqual(self.shipment.reference, old)
        self.assertEqual(self.post_tracking(reference=old).context["state"], "not_found")
        self.assertEqual(self.post_tracking().context["state"], "no_updates")
        self.assertNotIn(old, str(list(AuditEntry.objects.values("changes"))))

    def test_query_parameters_cannot_return_stored_tracking(self):
        r = self.client.get("/en/", {"reference": self.shipment.reference})
        self.assertIsNone(r.context["state"])
        self.assertNotContains(r, self.shipment.reference)

    def test_lookup_rate_limit_and_cache_failure_are_honest(self):
        for _ in range(30):
            self.assertEqual(self.post_tracking().status_code, 200)
        r = self.post_tracking()
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r["Retry-After"], "300")
        with patch("apps.core.limits.cache.add", side_effect=ConnectionError), patch("apps.core.views.find_public") as lookup:
            r = self.post_tracking()
            self.assertEqual(r.status_code, 503)
            lookup.assert_not_called()

    def test_database_failure_is_503_without_exception_details(self):
        from django.db import OperationalError
        with patch("apps.core.views.find_public", side_effect=OperationalError("PRIVATE-SQL-FAILURE")):
            r = self.post_tracking()
            self.assertEqual(r.status_code, 503)
            self.assertNotContains(r, "PRIVATE-SQL-FAILURE", status_code=503)

    def test_no_updates_unknown_eta_and_business_timezone(self):
        r = self.post_tracking()
        self.assertEqual(r.context["state"], "no_updates")
        self.assertContains(r, "Awaiting a confirmed estimate")
        self.assertContains(r, "Asia/Kabul")
        self.assertNotContains(r, "synthetic example")

    def test_demo_database_records_are_hidden_in_production(self):
        self.shipment.is_demo = True
        self.shipment.save()
        with override_settings(DEBUG=False):
            self.assertEqual(self.post_tracking().context["state"], "not_found")
        with override_settings(DEBUG=True):
            self.assertContains(self.post_tracking(), "SYNTHETIC EXAMPLE")

    def test_status_correction_and_stale_edit_require_explicit_control(self):
        self.shipment.status = Status.DELIVERED
        self.shipment.save()
        obj = Shipment.objects.get(pk=self.shipment.pk)
        obj.status = Status.TRANSIT
        with self.assertRaises(ValidationError):
            save_shipment(obj, self.ops, obj.revision)
        save_shipment(obj, self.ops, obj.revision, correction_reason="DEMO correction confirmed by operations")
        self.assertIn("correction_reason", AuditEntry.objects.latest("pk").changes)
        with self.assertRaises(ValidationError):
            save_shipment(obj, self.ops, expected_revision=0)

    def test_lock_requires_reason_and_explicit_release(self):
        self.shipment.status_locked = True
        self.shipment.override_reason = "DEMO manual freight lock"
        self.shipment.save()
        obj = Shipment.objects.get(pk=self.shipment.pk)
        obj.status_locked = False
        with self.assertRaises(ValidationError):
            save_shipment(obj, self.ops, obj.revision)
        save_shipment(obj, self.ops, obj.revision, correction_reason="DEMO lock released")
        self.assertFalse(Shipment.objects.get(pk=obj.pk).status_locked)

    def test_old_or_one_leg_delivery_event_never_changes_shipment_status(self):
        leg = TrackingLeg.objects.create(shipment=self.shipment, tracking_number="DEMO-LEG-1")
        TrackingLeg.objects.create(shipment=self.shipment, sequence=2, tracking_number="DEMO-LEG-2")
        event = TrackingEvent(shipment=self.shipment, leg=leg, occurred_at=timezone.now()-timedelta(days=5), title_en="One leg delivered", mapped_status=Status.DELIVERED)
        save_child(event, self.ops)
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.status, Status.CREATED)

    def test_cross_shipment_leg_and_negative_quantity_fail(self):
        other = Shipment.objects.create(customer=self.customer)
        leg = TrackingLeg.objects.create(shipment=other, tracking_number="DEMO-OTHER")
        with self.assertRaises(ValidationError):
            TrackingEvent(shipment=self.shipment, leg=leg, title_en="Mismatch").full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ShipmentItem.objects.create(shipment=self.shipment, description_en="invalid", quantity=-1)

    def test_delay_excludes_missing_eta_failed_sync_and_completed(self):
        self.assertFalse(delayed_shipments().filter(pk=self.shipment.pk).exists())
        TrackingLeg.objects.create(shipment=self.shipment, tracking_number="DEMO-LEG", last_error="provider unavailable")
        self.assertFalse(delayed_shipments().filter(pk=self.shipment.pk).exists())
        self.shipment.eta = timezone.now()-timedelta(hours=1)
        self.shipment.save()
        self.assertTrue(delayed_shipments().filter(pk=self.shipment.pk).exists())
        self.shipment.status = Status.DELIVERED
        self.shipment.save()
        self.assertFalse(delayed_shipments().filter(pk=self.shipment.pk).exists())

    def test_readonly_staff_can_read_but_all_mutations_fail(self):
        self.client.force_login(self.readonly)
        for path in ["/en/admin/shipments/shipment/", f"/en/admin/shipments/shipment/{self.shipment.pk}/change/", "/ar/admin/shipments/shipment/"]:
            self.assertEqual(self.client.get(path).status_code, 200)
        for path in ["/en/admin/shipments/customer/add/", f"/en/admin/shipments/shipment/{self.shipment.pk}/change/", "/en/admin/shipments/trackingevent/add/", "/en/admin/shipments/document/upload/", f"/en/admin/shipments/shipment/{self.shipment.pk}/control/?action=archive"]:
            self.assertEqual(self.client.post(path, {"published": True, "confirm": "yes", "action": "archive"}).status_code, 403)
        with self.assertRaises(PermissionDenied):
            save_child(ShipmentItem(shipment=self.shipment, description_en="attempt", quantity=1), self.readonly)

    def test_multileg_delivery_requires_explicit_confirmation_in_write_service(self):
        TrackingLeg.objects.create(shipment=self.shipment, sequence=1)
        TrackingLeg.objects.create(shipment=self.shipment, sequence=2)
        self.shipment.status = Status.DELIVERED
        with self.assertRaises(ValidationError):
            save_shipment(self.shipment, self.ops, self.shipment.revision)
        self.assertEqual(Shipment.objects.get(pk=self.shipment.pk).status, Status.CREATED)
        save_shipment(self.shipment, self.ops, self.shipment.revision, confirm_complete_shipment=True)
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.status, Status.DELIVERED)
        self.assertTrue(AuditEntry.objects.filter(action="shipment.updated", shipment=self.shipment).exists())

    def test_dashboard_counts_are_database_and_permission_bound(self):
        self.client.force_login(self.ops)
        r = self.client.get("/en/admin/")
        self.assertEqual(r.context["metrics"], {"pending": 1, "transit": 0, "delivered": 0, "attention": 0})
        self.shipment.eta = timezone.now()-timedelta(days=1)
        self.shipment.save()
        self.assertEqual(self.client.get("/en/admin/").context["metrics"]["attention"], 1)
        archive_shipment(self.shipment, self.ops)
        self.assertEqual(self.client.get("/en/admin/").context["metrics"]["pending"], 0)
        empty_staff = User.objects.create_user("no-permissions", is_staff=True)
        self.client.force_login(empty_staff)
        r = self.client.get("/en/admin/")
        self.assertNotIn("metrics", r.context)
        self.assertEqual(self.client.get("/en/admin/shipments/shipment/").status_code, 403)

    def test_archive_requires_csrf_and_a_confirmation_post(self):
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.ops)
        path = f"/en/admin/shipments/shipment/{self.shipment.pk}/control/?action=archive"
        self.assertEqual(c.get(path).status_code, 200)
        self.shipment.refresh_from_db()
        self.assertIsNone(self.shipment.archived_at)
        self.assertEqual(c.post(path, {"action": "archive", "confirm": "yes"}).status_code, 403)

    def test_audit_cannot_be_mutated_or_deleted_in_admin(self):
        entry = AuditEntry.objects.create(shipment=self.shipment, action="test", object_type="shipment", object_id=str(self.shipment.pk))
        self.client.force_login(self.ops)
        self.assertEqual(self.client.post(f"/en/admin/shipments/auditentry/{entry.pk}/change/", {"action": "forged"}).status_code, 403)
        self.assertEqual(self.client.post(f"/en/admin/shipments/shipment/{self.shipment.pk}/delete/").status_code, 403)

    def test_valid_upload_private_download_and_audit(self):
        upload = SimpleUploadedFile("DEMO-bill.pdf", sample_pdf(), content_type="application/pdf")
        document = store_document(self.shipment, upload, "bill", inspect_upload(upload), self.ops)
        self.assertTrue(document.file.storage.exists(document.file.name))
        self.assertNotIn("DEMO-bill", document.file.name)
        with self.assertRaises(ValueError):
            _ = document.file.url
        path = f"/en/admin/shipments/document/{document.pk}/download/"
        self.assertEqual(self.client.get(path).status_code, 302)
        self.client.force_login(self.readonly)
        self.assertEqual(self.client.get(path).status_code, 403)
        self.client.force_login(self.ops)
        r = self.client.get(path)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r["Content-Disposition"].startswith("attachment;"))
        self.assertIn("no-store", r["Cache-Control"])
        self.assertIn("private", r["Cache-Control"])
        self.assertTrue(b"".join(r.streaming_content).startswith(b"%PDF-"))
        self.assertTrue(AuditEntry.objects.filter(action="document.downloaded").exists())
        self.assertEqual(self.client.get("/media/"+document.file.name).status_code, 404)

    def test_upload_rejects_fake_mime_oversize_encrypted_active_and_page_limits(self):
        for upload in [SimpleUploadedFile("bad.pdf", b"<script>bad</script>", content_type="application/pdf"), SimpleUploadedFile("wrong.png", sample_pdf(), content_type="image/png"), SimpleUploadedFile("large.pdf", b"x"*(5*1024*1024+1), content_type="application/pdf")]:
            with self.assertRaises(ValidationError):
                inspect_upload(upload)
        from pypdf import PdfWriter
        from pypdf.generic import NameObject, DictionaryObject, TextStringObject
        for kind in ("encrypted", "active", "pages"):
            writer = PdfWriter()
            for _ in range(41 if kind == "pages" else 1):
                writer.add_blank_page(width=100,height=100)
            if kind == "encrypted":
                writer.encrypt("DEMO-password")
            if kind == "active":
                writer._root_object[NameObject("/OpenAction")] = DictionaryObject({NameObject("/S"): NameObject("/JavaScript"), NameObject("/JS"): TextStringObject("alert('x')")})
            output = io.BytesIO()
            writer.write(output)
            with self.subTest(kind=kind), self.assertRaises(ValidationError):
                inspect_upload(SimpleUploadedFile("bad.pdf", output.getvalue(), content_type="application/pdf"))

    def test_plain_png_jpeg_and_inspection_timeout(self):
        from PIL import Image
        for kind, extension, mime in [("PNG", "png", "image/png"), ("JPEG", "jpg", "image/jpeg")]:
            output = io.BytesIO()
            Image.new("RGB", (100,100), "white").save(output, format=kind)
            result = inspect_upload(SimpleUploadedFile("sample."+extension, output.getvalue(), content_type=mime))
            self.assertEqual(result["mime"], mime)
        import subprocess
        with patch("apps.shipments.uploads.subprocess.run", side_effect=subprocess.TimeoutExpired("inspect",8)), self.assertRaises(ValidationError):
            inspect_upload(SimpleUploadedFile("sample.pdf", sample_pdf(), content_type="application/pdf"))

    def test_file_storage_precedes_short_database_transaction(self):
        from django.db import connection
        # TestCase itself wraps a transaction; inspect the service's inner atomic depth.
        before = len(connection.atomic_blocks)
        upload = SimpleUploadedFile("sample.pdf",sample_pdf(),content_type="application/pdf")
        metadata = inspect_upload(upload)
        from django.core.files.storage import default_storage
        original = default_storage.save
        def save(*args, **kwargs):
            self.assertEqual(len(connection.atomic_blocks), before)
            return original(*args, **kwargs)
        with patch("apps.shipments.uploads.default_storage.save", side_effect=save):
            store_document(self.shipment,upload,"bill",metadata,self.ops)

    def test_seed_idempotent_without_modifying_reviewed_records(self):
        with override_settings(DEBUG=True):
            call_command("seed_demo", stdout=io.StringIO())
            count = Shipment.objects.count()
            obj = Shipment.objects.get(internal_order="DEMO-MANUAL",is_demo=True)
            obj.published = False
            obj.save()
            call_command("seed_demo", stdout=io.StringIO())
            self.assertEqual(Shipment.objects.count(), count)
            obj.refresh_from_db()
            self.assertFalse(obj.published)
