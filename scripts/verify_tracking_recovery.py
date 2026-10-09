"""Development-only durable DEMO receipt recovery through real local Celery."""
import hashlib
import io
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
import django
django.setup()
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone
from apps.tracking.adapter import configuration
from apps.tracking.models import IntegrationJob, WebhookReceipt
from apps.tracking.payloads import parse_webhook
from apps.tracking.services import accept_receipt
from apps.tracking.tasks import reconcile
from apps.shipments.models import Shipment, TrackingEvent

if not settings.DEBUG or configuration() != "disabled":
    raise SystemExit("Run only in development with 17TRACK disabled; no live provider request permitted.")
path = settings.DATA_DIR / "phase04-recovery-review.json"
action = sys.argv[1]
if action == "prepare":
    if path.exists():
        raise SystemExit("Recovery baseline already exists; use dispatch or verify.")
    call_command("seed_tracking_demo", stdout=io.StringIO())
    body = json.loads((settings.BASE_DIR / "tests/fixtures/tracking/updated.json").read_text())
    shipment = Shipment.objects.get(internal_order="DEMO-CARRIER", is_demo=True)
    body["data"]["number"] = shipment.legs.get(sequence=1).tracking_number
    item = body["data"]["track_info"]["latest_event"]
    item["description"] = "SYNTHETIC durable queue recovery review — not live carrier data."
    item["time_utc"] = (timezone.now() - timezone.timedelta(minutes=2)).isoformat()
    item["time_iso"] = item["time_utc"]
    from django.utils.dateparse import parse_datetime
    occurred = parse_datetime(item["time_utc"])
    item["time_raw"] = {"date": occurred.strftime("%Y-%m-%d"), "time": occurred.strftime("%H:%M:%S"), "timezone": "+00:00"}
    body["data"]["track_info"]["tracking"]["providers"][0]["events"] = [item]
    raw = json.dumps(body, ensure_ascii=False).encode()
    # Deliberately simulate submission failure after the actual SQLite commit.
    with patch("apps.tracking.tasks.process_job.apply_async", side_effect=ConnectionError("synthetic broker submission failure")):
        receipt, _ = accept_receipt(hashlib.sha256(b"demo-recovery:" + raw).hexdigest(), parse_webhook(raw), is_demo=True)
    job = IntegrationJob.objects.get(receipt=receipt)
    assert job.state == "pending"
    path.write_text(json.dumps({"job": job.pk, "receipt": receipt.pk, "shipment": shipment.pk}))
    path.chmod(0o600)
    print("PASS: SQLite durably retained DEMO work after deliberately simulated broker submission failure. No live provider call.")
elif action == "dispatch":
    assert path.exists()
    # This task travels through the real dedicated Redis/Celery path.
    reconcile.apply_async(retry=False)
    print("Recovery task dispatched to the real local Shipping broker/worker.")
elif action == "verify":
    baseline = json.loads(path.read_text())
    job = IntegrationJob.objects.get(pk=baseline["job"])
    receipt = WebhookReceipt.objects.get(pk=baseline["receipt"])
    assert job.state == "succeeded", "Wait for local worker/Beat recovery, then verify."
    assert receipt.state == "processed" and receipt.is_demo
    event = TrackingEvent.objects.get(shipment_id=baseline["shipment"], raw_text="SYNTHETIC durable queue recovery review — not live carrier data.")
    assert not event.public and event.source == "carrier"
    print("PASS: Real local Redis/Celery recovery processed the durable DEMO receipt; carrier event private; no external provider verification implied.")
else:
    raise SystemExit("Use prepare, dispatch or verify.")
