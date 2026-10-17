import base64
import copy
import hashlib
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.apps import apps
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import connection, IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, override_settings
from django.utils import timezone, translation

from apps.containers.models import Container, ContainerEvent
from apps.containers.values import Status, lookup_code, validate_source_time


def source_time(raw="2026-02-03 21:00", designation="estimated", precision="minute", zone=None, instant=None):
    return {"raw": raw, "precision": precision, "designation": designation,
            "source_timezone": zone, "normalized_instant": instant}


class ContainerModelTests(TestCase):
    def make_container(self, **values):
        return Container.objects.create(search_reference="DEMOAB123456", **values)

    def test_exactly_two_business_models_and_default_private_unbound_journey(self):
        business = [m._meta.label for m in apps.get_models() if m._meta.app_label not in {"auth", "contenttypes", "sessions", "admin"}]
        self.assertEqual(set(business), {"containers.Container", "containers.ContainerEvent"})
        self.assertFalse(set(connection.introspection.table_names()) & {"shipments_shipment", "shipments_customer", "tracking_integrationjob", "ai_aidraft"})
        item = self.make_container()
        self.assertEqual(item.container_number, "")
        self.assertFalse(item.is_published)
        self.assertIsNone(item.archived_at)
        self.assertIsNone(item.equipment_quantity)
        self.assertIsNone(item.arrival_estimated)
        self.assertEqual(item.display_status, Status.UNKNOWN)
        self.assertTrue(item.needs_review)
        self.assertIn(Container, admin.site._registry)
        self.assertNotIn(ContainerEvent, admin.site._registry)

    def test_lookup_has_128_random_bits_is_shared_stable_and_contains_no_internal_identity(self):
        with patch("apps.containers.values.secrets.token_bytes", return_value=bytes(range(16))) as random:
            code = lookup_code()
        random.assert_called_once_with(16)
        self.assertEqual(base64.b32decode(code[4:] + "======"), bytes(range(16)))
        item = self.make_container()
        code = item.lookup_code
        self.assertEqual(len(code), 30)
        self.assertEqual(str(item), code)
        self.assertNotIn(item.search_reference, item.tracking_path())
        self.assertEqual(item.tracking_path("ar"), f"/ar/track/{code}/")
        item.manual_notes_en = "Independent note"
        item.save()
        item.refresh_from_db()
        self.assertEqual(item.lookup_code, code)
        self.assertEqual(item.revision, 1)
        self.assertEqual(len({lookup_code() for _ in range(100)}), 100)
        with self.assertRaises(ValueError):
            item.tracking_path("../admin")
        item.lookup_code = lookup_code()
        with self.assertRaises(ValidationError):
            item.save()

    def test_multi_container_binding_requires_selection_and_bound_identity_never_switches(self):
        item = self.make_container()
        with self.assertRaises(ValidationError):
            item.bind_container(["TEST1234567", "DEMO7654321"])
        self.assertEqual(item.container_number, "")
        item.bind_container(["TEST1234567", "DEMO7654321"], selected_number="DEMO7654321")
        item.save()
        self.assertEqual(item.container_number, "DEMO7654321")
        self.assertEqual(item.bind_container(["DEMO7654321", "TEST1234567"]), "DEMO7654321")
        for numbers, selected in ((["TEST1234567"], None), (["TEST1234567", "DEMO7654321"], "TEST1234567")):
            with self.assertRaises(ValidationError):
                item.bind_container(numbers, selected_number=selected)
        for field, value in (("container_number", "TEST1234567"), ("container_number", ""), ("search_reference", "OTHER123456")):
            changed = Container.objects.get(pk=item.pk)
            setattr(changed, field, value)
            with self.assertRaises(ValidationError):
                changed.save()

    def test_one_source_container_binds_without_saving_and_invalid_lists_refuse(self):
        item = self.make_container()
        item.bind_container(["TEST1234567"])
        self.assertEqual(Container.objects.get(pk=item.pk).container_number, "")
        for numbers in ([], [""], ["DEMOAB123456"], ["EXAMPLE VESSEL/100E"], "TEST1234567", [123]):
            with self.assertRaises(ValidationError):
                item.bind_container(numbers)

    def test_journey_combination_is_unique_but_physical_container_and_bl_can_repeat(self):
        key = uuid.uuid4()
        one = self.make_container(journey_key=key, container_number="TEST1234567")
        two = self.make_container(journey_key=key, container_number="DEMO7654321")
        later = self.make_container(container_number="TEST1234567")
        self.assertNotEqual(one.journey_key, later.journey_key)
        self.assertEqual(one.search_reference, two.search_reference)
        with self.assertRaises(ValidationError):
            self.make_container(journey_key=key, container_number="TEST1234567")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Container.objects.bulk_create([Container(search_reference=one.search_reference, journey_key=key, container_number=one.container_number)])
        pending = self.make_container(journey_key=key)
        with self.assertRaises(ValidationError):
            self.make_container(journey_key=key)
        self.assertFalse(pending.is_published)

    def test_reference_container_and_source_urls_cannot_be_confused(self):
        for kwargs in ({"container_number": "DEMOAB123456"}, {"container_number": "EXAMPLE/100E"}, {"source_website": "http://127.0.0.1"}, {"source_adapter": "arbitrary"}, {"equipment_quantity": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                self.make_container(**kwargs)
        with self.assertRaises(ValidationError):
            Container.objects.create(search_reference="../private")

    @override_settings(TIME_ZONE="Asia/Kabul", BUSINESS_TIME_ZONE="Asia/Kabul")
    def test_unzoned_and_date_only_timestamps_round_trip_without_normalization(self):
        date = source_time("2026-02-03", precision="date")
        minute = source_time()
        second = source_time("2026-01-02 22:30:00", "actual", "second")
        item = self.make_container(arrival_estimated=date, departure_actual=second, departure_estimated=minute)
        item.refresh_from_db()
        self.assertEqual(item.arrival_estimated, date)
        self.assertEqual(item.departure_actual, second)
        self.assertEqual(item.departure_estimated, minute)
        self.assertIsNone(item.arrival_actual)
        self.assertIsNone(item.arrival_estimated["normalized_instant"])
        self.assertEqual(item.carrier_status, Status.UNKNOWN)

    def test_time_validation_rejects_fabricated_precision_instant_and_classification(self):
        for bad in (source_time("2026-02-30", precision="date"), source_time(instant="2026-02-03T21:00:00Z"),
                    source_time(precision="date"), source_time(zone="Imaginary/Nowhere"),
                    source_time(instant="2026-02-03T21:00:00", zone="UTC"),
                    source_time(instant="2026-02-03T20:00:00Z", zone="UTC"),
                    source_time("2026-02-03", precision="date", zone="UTC", instant="2026-02-03T00:00:00Z"),
                    source_time(zone="+14:59"), {}, [], source_time(precision=[])):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                self.make_container(arrival_estimated=bad)
        with self.assertRaises(ValidationError):
            self.make_container(arrival_actual=source_time())
        known = source_time(zone="Asia/Kabul", instant="2026-02-03T16:30:00Z")
        self.assertIsNone(validate_source_time(known))
        with self.assertRaises(ValidationError):
            validate_source_time(source_time("2026-03-08 02:30", zone="America/New_York", instant="2026-03-08T07:30:00Z"))

    def test_unknown_empty_return_and_past_eta_never_imply_collection(self):
        for status in ("MT", "NEW_UNKNOWN_STAGE", ""):
            item = self.make_container(raw_status=status, arrival_estimated=source_time("2020-01-01", precision="date"))
            self.assertEqual(item.display_status, Status.UNKNOWN)
            self.assertTrue(item.needs_review)
        with self.assertRaises(ValidationError):
            self.make_container(carrier_status="delivered")

    def test_manual_override_returns_to_carrier_and_health_fields_are_bounded(self):
        item = self.make_container(carrier_status=Status.IN_TRANSIT, manual_status_override=Status.ON_HOLD,
                                   manual_notes_en="Contact the office", manual_notes_ar="يرجى التواصل مع المكتب")
        self.assertEqual(item.display_status, Status.ON_HOLD)
        item.clear_manual_status_override()
        self.assertEqual(item.display_status, Status.IN_TRANSIT)
        self.assertEqual(item.manual_notes_ar, "يرجى التواصل مع المكتب")
        self.assertEqual(item.revision, 1)
        item.last_refresh_success_at = timezone.now() - timedelta(days=1)
        item.last_refresh_attempt_at = timezone.now()
        item.last_failure_code = "timeout"
        item.save()
        item.refresh_from_db()
        self.assertLess(item.last_refresh_success_at, item.last_refresh_attempt_at)
        with self.assertRaises(ValidationError):
            self.make_container(last_failure_code="PRIVATE response body")
        with self.assertRaises(ValidationError):
            self.make_container(refresh_claim=uuid.uuid4())
        with self.assertRaises(IntegrityError), transaction.atomic():
            Container.objects.bulk_create([Container(search_reference="DEMOAB123456", refresh_claim=uuid.uuid4())])

    def test_accepted_evidence_is_bounded_and_matches_current_source(self):
        fingerprint = hashlib.sha256(b"DEMO source").hexdigest()
        evidence = {"adapter": "sealegend-web-proof-v1", "source_sha256": fingerprint,
                    "observed_at": timezone.now().isoformat(), "facts": {"pol": "AAAAA", "pod": "BBBBB"}}
        item = self.make_container(source_evidence=evidence, source_fingerprint=fingerprint)
        self.assertEqual(item.source_evidence, evidence)
        for bad in ({**evidence, "extra_page": "not allowed"}, {**evidence, "facts": {"raw": "x" * 8192}},
                    {**evidence, "adapter": "arbitrary"}, {**evidence, "source_sha256": "a" * 64}, [], ""):
            with self.subTest(bad_type=type(bad)), self.assertRaises(ValidationError):
                self.make_container(source_evidence=bad, source_fingerprint=fingerprint)

    def test_english_and_arabic_labels_errors_and_shared_code_form(self):
        with translation.override("en"):
            self.assertEqual(str(Container._meta.verbose_name), "Container")
        with translation.override("ar"):
            self.assertEqual(str(Container._meta.verbose_name), "حاوية")
            self.assertEqual(str(Status.IN_TRANSIT.label), "قيد النقل")
            with self.assertRaises(ValidationError) as error:
                self.make_container(container_number="INVALID")
            self.assertIn("أحرف", str(error.exception))
        item = self.make_container(is_published=True, archived_at=timezone.now())
        with patch("apps.integrations.sealegend.retrieve_candidate") as source, patch("apps.integrations.groq.create_client") as ai:
            for language in ("en", "ar"):
                self.assertEqual(self.client.get(item.tracking_path(language)).status_code, 404)
            self.assertContains(self.client.get(f"/{language}/"), 'name="code"')
            source.assert_not_called(); ai.assert_not_called()


class EventModelTests(TestCase):
    def setUp(self):
        self.container = Container.objects.create(search_reference="DEMOAB123456", container_number="TEST1234567",
            manual_notes_en="Private manual note", manual_status_override=Status.ON_HOLD)
        self.facts = {"raw_status": "DG", "location_code": "BBBBB", "designation": "estimated", "source_time": source_time(),
                      "raw_text": "Expected arrival", "title_en": "Estimated arrival", "title_ar": "الوصول المتوقع"}

    def test_repeated_estimate_and_changed_eta_update_one_private_milestone(self):
        one, created = ContainerEvent.objects.record_carrier(container=self.container, **self.facts)
        again, created_again = ContainerEvent.objects.record_carrier(container=self.container, **self.facts)
        self.assertTrue(created); self.assertFalse(created_again)
        self.assertEqual(one.pk, again.pk)
        self.facts["source_time"] = source_time("2026-02-05 08:15")
        self.facts["raw_text"] = "Estimate revised to a different date"
        revised, created = ContainerEvent.objects.record_carrier(container=self.container, **self.facts)
        self.assertFalse(created)
        self.assertEqual(one.pk, revised.pk)
        self.assertEqual(revised.source_time["raw"], "2026-02-05 08:15")
        self.assertFalse(revised.is_public)
        self.assertEqual(ContainerEvent.objects.count(), 1)

    def test_source_event_id_is_stable_across_changed_source_facts(self):
        self.facts["source_event_id"] = "DEMO-event-123"
        event, _ = ContainerEvent.objects.record_carrier(container=self.container, **self.facts)
        self.facts.update(raw_text="Changed source words", source_time=source_time("2026-02-06 13:00"), location_code="CCCCC")
        corrected, created = ContainerEvent.objects.record_carrier(container=self.container, **self.facts)
        self.assertFalse(created)
        self.assertEqual(event.pk, corrected.pk)

    def test_actual_events_dedupe_on_facts_and_keep_different_times_or_legs(self):
        self.facts.update(designation="actual", source_time=source_time("2026-02-03 21:00", "actual"))
        first, _ = ContainerEvent.objects.record_carrier(container=self.container, **self.facts)
        repeat, created = ContainerEvent.objects.record_carrier(container=self.container, **self.facts)
        self.assertFalse(created); self.assertEqual(first.pk, repeat.pk)
        self.facts["source_time"] = source_time("2026-02-04 21:00", "actual")
        different, created = ContainerEvent.objects.record_carrier(container=self.container, **self.facts)
        self.assertTrue(created); self.assertNotEqual(first.pk, different.pk)
        self.facts["source_leg"] = "DEMO-return-leg"
        _, created = ContainerEvent.objects.record_carrier(container=self.container, **self.facts)
        self.assertTrue(created)

    def test_carrier_upsert_cannot_publish_or_overwrite_manual_events_notes_or_override(self):
        manual = ContainerEvent.objects.create(container=self.container, title_en="Manual event", detail_ar="تحديث يدوي")
        manual_two = ContainerEvent.objects.create(container=self.container, title_en="Manual event", detail_ar="تحديث يدوي")
        self.assertNotEqual(manual.dedupe_key, manual_two.dedupe_key)
        self.assertFalse(manual.is_public)
        for _ in range(2):
            ContainerEvent.objects.record_carrier(container=self.container, **self.facts)
        self.container.refresh_from_db(); manual.refresh_from_db()
        self.assertEqual(manual.title_en, "Manual event")
        self.assertEqual(self.container.manual_notes_en, "Private manual note")
        self.assertEqual(self.container.display_status, Status.ON_HOLD)
        self.assertEqual(ContainerEvent.objects.filter(origin="manual").count(), 2)
        with self.assertRaises(ValueError):
            ContainerEvent.objects.record_carrier(container=self.container, **self.facts, is_public=True)
        with self.assertRaises(ProtectedError):
            self.container.delete()

    def test_event_identity_designation_missing_time_and_database_uniqueness(self):
        for changes in ({"designation": "actual"}, {"source_time": {}}, {"raw_status": "", "location_code": ""}, {"designation": "actual", "source_time": None}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                ContainerEvent.objects.record_carrier(container=self.container, **{**self.facts, **changes})
        one, _ = ContainerEvent.objects.record_carrier(container=self.container, **self.facts)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContainerEvent.objects.bulk_create([ContainerEvent(container=self.container, origin="carrier", dedupe_key=one.dedupe_key)])
        one.origin = "manual"
        with self.assertRaises(ValidationError):
            one.save()
        unknown = ContainerEvent.objects.create(container=self.container, title_en="Undated manual update")
        self.assertEqual(unknown.designation, "unknown")
        self.assertIsNone(unknown.source_time)
        self.assertFalse(unknown.is_public)

    def test_estimate_and_actual_have_separate_identities_and_no_implicit_publication(self):
        estimate, _ = ContainerEvent.objects.record_carrier(container=self.container, **self.facts)
        actual, created = ContainerEvent.objects.record_carrier(container=self.container, **{
            **self.facts, "designation": "actual", "source_time": source_time("2026-02-04 21:00", "actual")})
        self.assertTrue(created)
        self.assertNotEqual(estimate.dedupe_key, actual.dedupe_key)
        self.assertFalse(actual.is_public)
