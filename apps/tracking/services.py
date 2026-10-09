"""Durable outbox and fenced, short transactions; no network inside writes."""
import hashlib
import secrets
from datetime import timedelta
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from django.utils.dateparse import parse_datetime
from apps.shipments.models import Shipment, TrackingLeg, TrackingEvent, Status
from apps.shipments.services import audit, snapshot, TERMINAL, RANK
from .models import WebhookReceipt, IntegrationJob
from .adapter import configuration, identifier, ProviderError

ACTIVE = {"pending", "retry", "running"}


def require(user, permission):
    if not user or not user.is_active or not user.is_staff or not user.has_perm("tracking." + permission):
        raise PermissionDenied


def dispatch(job_id):
    # Broker availability cannot undo a durably accepted receipt.
    from .tasks import process_job
    try:
        process_job.apply_async(args=[job_id], retry=False)
    except Exception:
        return False
    return True


def enqueue_after_commit(job):
    transaction.on_commit(lambda: dispatch(job.pk))


@transaction.atomic
def request_leg(leg_id, kind, actor):
    require(actor, "register_reference" if kind == "register" else "refresh_reference")
    if kind not in ("register", "refresh"):
        raise ValidationError(_("Invalid carrier action."))
    leg = TrackingLeg.objects.select_related("shipment").get(pk=leg_id)
    shipment = leg.shipment
    if not actor.has_perm("shipments.view_shipment"):
        raise PermissionDenied
    if shipment.archived_at or shipment.tracking_mode == "manual":
        raise ValidationError(_("Choose an active API/hybrid shipment before requesting carrier work."))
    if shipment.is_demo:
        raise ValidationError(_("Synthetic DEMO references cannot be sent to the live provider."))
    if configuration() != "ready":
        raise ValidationError(_("17TRACK is disabled or its server-side key is missing. Manual tracking still works."))
    try:
        identifier(leg.tracking_number, leg.carrier_identifier)
    except ProviderError:
        raise ValidationError(_("Provide a supported carrier's numeric code and carrier-issued tracking identifier. Bills are not automatically supported.")) from None
    if leg.registration_state == "stopped":
        raise ValidationError(_("Provider tracking stopped. Use manual updates; re-tracking requires a separate reviewed integration."))
    if kind == "register" and leg.registration_state == "registered":
        return None
    if kind == "refresh" and leg.registration_state != "registered":
        raise ValidationError(_("Register this carrier reference before retrieving its stored details."))
    existing = IntegrationJob.objects.filter(leg=leg, state__in=ACTIVE).first()
    if existing:
        return existing
    key = f"{kind}:{leg.pk}"
    job, created = IntegrationJob.objects.get_or_create(dedupe_key=key, defaults={"kind": kind, "leg": leg})
    if not created:
        if kind == "refresh" and job.finished_at and job.finished_at > timezone.now() - timedelta(minutes=15):
            raise ValidationError(_("Wait 15 minutes between requested detail retrievals. Webhooks update stored tracking independently."))
        job.state, job.attempts, job.safe_error = "pending", 0, ""
        job.available_at, job.finished_at, job.last_enqueued_at = timezone.now(), None, None
        job.save()
    if kind == "register":
        leg.registration_state, leg.last_error = "pending", ""
        leg.save(update_fields=["registration_state", "last_error"])
    audit(leg, actor, "carrier." + kind + "_requested")
    enqueue_after_commit(job)
    return job


@transaction.atomic
def accept_receipt(digest, payload, is_demo=False):
    receipt, created = WebhookReceipt.objects.get_or_create(digest=digest, defaults={"event_type": payload["event_type"], "payload": payload, "is_demo": is_demo})
    if created:
        job = IntegrationJob.objects.create(kind="receipt", receipt=receipt, dedupe_key=f"receipt:{receipt.pk}")
        enqueue_after_commit(job)
    return receipt, created


@transaction.atomic
def claim_job(job_id):
    now = timezone.now()
    job = IntegrationJob.objects.select_related("leg", "receipt").filter(pk=job_id).first()
    if not job or job.state not in ("pending", "retry") or job.available_at > now:
        return None
    if job.leg_id and IntegrationJob.objects.filter(leg_id=job.leg_id, state="running", lease_until__gt=now).exists():
        return None
    if job.attempts >= 5:
        job.state, job.safe_error, job.finished_at = "failed", "retry_exhausted", now
        job.save()
        return None
    job.state, job.lease_token, job.lease_until = "running", secrets.token_hex(16), now + timedelta(seconds=120)
    job.attempts += 1
    job.save(update_fields=["state", "lease_token", "lease_until", "attempts", "updated_at"])
    return job


def fenced(job):
    return IntegrationJob.objects.filter(pk=job.pk, state="running", lease_token=job.lease_token).exists()


def finish(job, state="succeeded", error=""):
    IntegrationJob.objects.filter(pk=job.pk, state="running", lease_token=job.lease_token).update(state=state, safe_error=error, lease_until=None, lease_token="", finished_at=timezone.now(), updated_at=timezone.now())


@transaction.atomic
def record_error(job, error):
    if not fenced(job):
        return
    current = IntegrationJob.objects.get(pk=job.pk)
    if error.code in ("local_rate_limit", "rate_store_unavailable"):
        current.attempts = max(0, current.attempts - 1)
    retry = error.retryable and current.attempts < 5
    current.state = "retry" if retry else "failed"
    current.safe_error, current.lease_until, current.lease_token = error.code, None, ""
    current.available_at = timezone.now() + timedelta(seconds=max(error.retry_after, min(3600, 30 * 2 ** current.attempts)) + secrets.randbelow(16))
    current.finished_at = None if retry else timezone.now()
    current.save()
    if current.leg_id:
        TrackingLeg.objects.filter(pk=current.leg_id).update(last_error=error.code)
    if current.receipt_id and not retry:
        WebhookReceipt.objects.filter(pk=current.receipt_id).update(state="failed", safe_error=error.code)


@transaction.atomic
def retry_job(job_id, actor):
    require(actor, "retry_jobs")
    if not actor.has_perm("tracking.view_integrationjob") or not actor.has_perm("shipments.view_shipment"):
        raise PermissionDenied
    job = IntegrationJob.objects.get(pk=job_id)
    if job.receipt_id and not actor.has_perm("tracking.view_webhookreceipt"):
        raise PermissionDenied
    if job.state != "failed":
        raise ValidationError(_("Only failed work can be retried here."))
    if job.leg_id:
        require(actor, "register_reference" if job.kind == "register" else "refresh_reference")
        leg = job.leg
        if configuration() != "ready" or leg.shipment.archived_at or leg.shipment.is_demo or leg.shipment.tracking_mode == "manual":
            raise ValidationError(_("This reference is not eligible for live work."))
        audit(leg, actor, "carrier.job_retried")
    job.state, job.attempts, job.safe_error = "pending", 0, ""
    job.available_at, job.finished_at, job.last_enqueued_at = timezone.now(), None, None
    job.save()
    if job.receipt_id:
        job.receipt.state, job.receipt.safe_error = "pending", ""
        job.receipt.save(update_fields=["state", "safe_error"])
    enqueue_after_commit(job)


def aggregate_status(shipment, legs):
    if not legs or any(not l.mapped_status or not l.last_provider_event_at for l in legs):
        return "", None
    if any(l.mapped_status == Status.HOLD for l in legs):
        return Status.HOLD, max(l.last_provider_event_at for l in legs if l.mapped_status == Status.HOLD)
    if all(l.mapped_status == Status.DELIVERED for l in legs):
        return (Status.DELIVERED, max(l.last_provider_event_at for l in legs)) if shipment.carrier_coverage_complete else ("", None)
    if len(legs) == 1 and shipment.carrier_coverage_complete and legs[0].mapped_status in (Status.RETURNED, Status.CANCELLED):
        return legs[0].mapped_status, legs[0].last_provider_event_at
    if any(l.mapped_status not in RANK for l in legs):
        return "", None
    leg = min(legs, key=lambda l: RANK[l.mapped_status])
    return leg.mapped_status, min(l.last_provider_event_at for l in legs)


def apply_payload(payload, is_demo=False):
    """Caller holds the short transaction/fence. Match exact known carrier identity."""
    leg = TrackingLeg.objects.select_related("shipment").filter(carrier_identifier=str(payload["carrier"]), tracking_number=payload["number"]).first()
    if not leg or leg.shipment.archived_at or leg.registration_state not in ("pending", "registered", "stopped") or leg.shipment.is_demo != is_demo:
        return "quarantined", "unknown_or_ineligible_reference"
    shipment = leg.shipment
    now = timezone.now()
    leg.last_received_at = now
    if payload["event_type"] == "TRACKING_STOPPED":
        leg.registration_state, leg.next_reconcile_at = "stopped", None
        leg.save(update_fields=["registration_state", "next_reconcile_at", "last_received_at"])
        audit(leg, None, "carrier.tracking_stopped", identity="17track")
        return "processed", ""
    for item in payload["events"]:
        key = hashlib.sha256(f"{leg.pk}:{item['key']}".encode()).hexdigest()
        with translation.override("en"):
            title_en = str(Status(item["status"]).label) if item["status"] else "Carrier milestone — review required"
        with translation.override("ar"):
            title_ar = str(Status(item["status"]).label) if item["status"] else "مرحلة من الناقل — تتطلب المراجعة"
        event, created = TrackingEvent.objects.get_or_create(provider_event_key=key, defaults={"shipment": shipment, "leg": leg,
            "occurred_at": parse_datetime(item["occurred_at"]) if item["occurred_at"] else None,
            "location": item["location"], "raw_text": item["description"], "provider_time_raw": {"original": item["time_raw"], "time_iso": item["time_iso"]},
            "title_en": title_en, "title_ar": title_ar, "source": "carrier", "mapped_status": item["status"], "provider_identity": f"17track:v2.4:{item['provider']}", "public": False})
        if created:
            audit(event, None, "carrier.event_received", identity="17track")
    sync = parse_datetime(payload["sync_time"]) if payload["sync_time"] else None
    if sync and (not leg.last_success or sync > leg.last_success):
        leg.last_success = sync
    observed = parse_datetime(payload["latest_time"]) if payload["latest_time"] else None
    if observed and (not leg.last_provider_event_at or observed > leg.last_provider_event_at):
        leg.last_provider_event_at, leg.mapped_status, leg.provider_status = observed, payload["status"], payload["provider_status"]
    leg.last_error = "" if sync else "carrier_sync_unconfirmed"
    leg.next_reconcile_at = now + timedelta(seconds=settings.TRACK17_RECONCILE_SECONDS)
    leg.save()
    legs = list(shipment.legs.all())
    status, timestamp = aggregate_status(shipment, legs)
    if shipment.tracking_mode != "manual" and not shipment.status_locked and shipment.status not in TERMINAL and status and timestamp and (not shipment.status_observed_at or timestamp > shipment.status_observed_at):
        # Do not regress ranked progress. Exceptions may flag a later confirmed hold.
        if status == Status.HOLD or shipment.status not in RANK or status not in RANK or RANK[status] >= RANK[shipment.status]:
            before = snapshot(shipment)
            shipment.status, shipment.status_observed_at = status, timestamp
            if status == Status.DELIVERED:
                shipment.delivered_at = timestamp
            shipment.revision += 1
            shipment.save(update_fields=["status", "status_observed_at", "delivered_at", "revision", "updated_at"])
            audit(shipment, None, "carrier.status_updated", before, identity="17track")
    return "processed", ""


@transaction.atomic
def process_receipt(job):
    if not fenced(job):
        return
    receipt = WebhookReceipt.objects.get(pk=job.receipt_id)
    if receipt.state in ("processed", "quarantined"):
        finish(job, "quarantined" if receipt.state == "quarantined" else "succeeded", receipt.safe_error)
        return
    if receipt.is_demo and not settings.DEBUG:
        state, error = "quarantined", "demo_disabled"
    else:
        state, error = apply_payload(receipt.payload, receipt.is_demo)
    receipt.state, receipt.safe_error, receipt.processed_at = state, error, timezone.now()
    receipt.save(update_fields=["state", "safe_error", "processed_at"])
    finish(job, "quarantined" if state == "quarantined" else "succeeded", error)


@transaction.atomic
def apply_response(job, outcome, normalized=None):
    if not fenced(job):
        return
    leg = TrackingLeg.objects.select_related("shipment").get(pk=job.leg_id)
    if leg.shipment.archived_at or leg.shipment.is_demo:
        finish(job, "quarantined", "reference_no_longer_eligible")
        return
    if not outcome.accepted:
        leg.last_error = outcome.code
        if job.kind == "register" or outcome.code == "not_registered":
            leg.registration_state = "rejected"
        leg.save(update_fields=["last_error", "registration_state"])
        finish(job, "failed", outcome.code)
        audit(leg, None, "carrier.number_rejected", identity="17track")
        return
    if job.kind == "register":
        if leg.registration_state == "stopped":
            finish(job, "quarantined", "stopped_during_registration")
            return
        leg.registration_state, leg.last_error = "registered", ""
        leg.next_reconcile_at = timezone.now()
        leg.save(update_fields=["registration_state", "last_error", "next_reconcile_at"])
        audit(leg, None, "carrier.reference_registered", identity="17track")
    elif normalized:
        apply_payload(normalized)
    finish(job)


@transaction.atomic
def recover_pending(limit=50):
    now = timezone.now()
    expired = list(IntegrationJob.objects.filter(state="running", lease_until__lt=now).order_by("pk")[:limit])
    for job in expired:
        job.state, job.safe_error = ("retry", "lease_expired") if job.attempts < 5 else ("failed", "retry_exhausted")
        job.lease_until, job.lease_token, job.available_at = None, "", now
        job.save(update_fields=["state", "safe_error", "lease_until", "lease_token", "available_at", "updated_at"])
    due = list(IntegrationJob.objects.filter(state__in=("pending", "retry"), available_at__lte=now).filter(Q(last_enqueued_at__isnull=True) | Q(last_enqueued_at__lt=now - timedelta(seconds=60))).order_by("available_at", "pk")[:limit])
    for job in due:
        job.last_enqueued_at = now
        job.save(update_fields=["last_enqueued_at"])
        enqueue_after_commit(job)
    return len(due)


@transaction.atomic
def schedule_reconciliation(limit=10):
    if configuration() != "ready":
        return 0
    now = timezone.now()
    legs = TrackingLeg.objects.filter(registration_state="registered", next_reconcile_at__lte=now, shipment__archived_at__isnull=True, shipment__is_demo=False).exclude(shipment__tracking_mode="manual").exclude(shipment__status__in=TERMINAL).exclude(mapped_status__in=TERMINAL).order_by("next_reconcile_at")[:limit]
    count = 0
    for leg in legs:
        if IntegrationJob.objects.filter(leg=leg, state__in=ACTIVE).exists():
            continue
        job, created = IntegrationJob.objects.get_or_create(dedupe_key=f"refresh:{leg.pk}", defaults={"kind": "refresh", "leg": leg})
        if not created:
            if job.state == "failed" and job.safe_error in {"provider_authentication", "unsupported_identifier", "unsupported_carrier", "not_registered", "number_rejected", "invalid_response", "invalid_provider_payload", "provider_http_rejected"}:
                continue
            job.state, job.attempts, job.safe_error = "pending", 0, ""
            job.available_at, job.finished_at, job.last_enqueued_at = now, None, None
            job.save()
        leg.next_reconcile_at = now + timedelta(seconds=settings.TRACK17_RECONCILE_SECONDS)
        leg.save(update_fields=["next_reconcile_at"])
        enqueue_after_commit(job)
        count += 1
    return count
