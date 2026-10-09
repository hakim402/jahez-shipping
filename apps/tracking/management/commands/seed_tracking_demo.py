"""Explicit local fixture: never dispatches an outbound provider request."""
import hashlib
import json
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.db import transaction
from apps.shipments.models import Shipment, TrackingLeg, Status
from apps.shipments.services import audit
from apps.tracking.models import IntegrationJob
from apps.tracking.payloads import parse_webhook
from apps.tracking.services import accept_receipt
from apps.tracking.tasks import process_job
from pathlib import Path


class Command(BaseCommand):
    help = "Create an explicit synthetic carrier review on a separate DEMO shipment; development only, no provider calls."
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Synthetic carrier review is restricted to development.")
        call_command("seed_demo", stdout=self.stdout)
        with transaction.atomic():
            customer = Shipment.objects.get(internal_order="DEMO-MANUAL", is_demo=True).customer
            shipment, created = Shipment.objects.get_or_create(internal_order="DEMO-CARRIER", is_demo=True, defaults={"customer": customer, "tracking_mode": "hybrid", "status": Status.CREATED, "origin_en": "Mainland China", "origin_ar": "الصين", "destination_en": "United Arab Emirates", "destination_ar": "الإمارات العربية المتحدة", "internal_notes": "SYNTHETIC carrier fixture — no live 17TRACK data.", "published": False})
            leg, _ = TrackingLeg.objects.get_or_create(shipment=shipment, sequence=1, defaults={"carrier_identifier": "3011", "tracking_number": "DEMO-CARRIER-FIXTURE-0001", "registration_state": "registered", "label": "DEMO recorded provider fixture"})
            if created:
                audit(shipment, None, "demo.carrier_created", identity="seed_tracking_demo")
        raw = (Path(settings.BASE_DIR) / "tests/fixtures/tracking/updated.json").read_bytes()
        payload = parse_webhook(raw)
        payload["number"] = leg.tracking_number
        # Suppress on_commit queue submission: execute this labeled fixture explicitly.
        from unittest.mock import patch
        with patch("apps.tracking.services.dispatch", return_value=True):
            receipt, _ = accept_receipt(hashlib.sha256(b"demo:" + raw).hexdigest(), payload, is_demo=True)
        job = IntegrationJob.objects.get(receipt=receipt)
        if job.state in ("pending", "retry"):
            process_job(job.pk)
        self.stdout.write(self.style.SUCCESS("SYNTHETIC carrier receipt/job processed locally. DEMO-CARRIER and its carrier events remain private until reviewed/published. No live provider request or user account created."))
