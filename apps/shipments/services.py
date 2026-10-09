"""Permission-aware, short transactions for manual operational writes."""
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from .models import AuditEntry, Shipment, TrackingLeg, Status, public_reference

TERMINAL = {Status.DELIVERED, Status.RETURNED, Status.CANCELLED}
RANK = {s: i for i, s in enumerate([Status.CREATED, Status.WAREHOUSE, Status.PREPARING, Status.DEPARTED, Status.TRANSIT, Status.CUSTOMS, Status.ARRIVED, Status.OUT, Status.DELIVERED])}
SAFE_AUDIT = {"status", "published", "public", "status_locked", "mode", "tracking_mode", "eta", "actual_arrival", "delivered_at", "confirmed_delay", "archived_at", "quantity", "cartons", "mapped_status", "occurred_at", "sequence", "category"}


def require(user, permission):
    if not user or not user.is_active or not user.is_staff or not user.has_perm("shipments." + permission):
        raise PermissionDenied


def snapshot(obj):
    return {f.name: str(getattr(obj, f.name)) for f in obj._meta.fields if f.name in SAFE_AUDIT}


def audit(obj, actor, action, before=None, fields=None, identity="staff"):
    shipment = obj if isinstance(obj, Shipment) else getattr(obj, "shipment", None)
    return AuditEntry.objects.create(
        actor=actor, identity=identity, shipment=shipment, object_type=obj._meta.model_name,
        object_id=str(obj.pk), action=action,
        changes={"before": before or {}, "after": snapshot(obj), "fields": fields or []},
    )


def transition_problem(old, new, old_time=None, new_time=None):
    if old == new:
        return None
    if old in TERMINAL:
        return "A terminal status requires an explicit correction reason."
    if old_time and new_time and new_time < old_time:
        return "An older milestone cannot replace the current status without a correction."
    if old in RANK and new in RANK and RANK[new] < RANK[old]:
        return "A backward status change requires an explicit correction reason."
    return None


def validate_change(obj, old, user, correction_reason=""):
    if old and old.archived_at:
        raise ValidationError(_("Restore the archived shipment before editing it."))
    if obj.published != (old.published if old else False):
        require(user, "publish_shipment")
    if obj.published:
        require(user, "publish_shipment")
    problem = transition_problem(old.status, obj.status) if old else None
    if problem or (old and old.status_locked and old.status != obj.status) or (old and old.status_locked and not obj.status_locked):
        require(user, "correct_status")
        if not correction_reason.strip():
            raise ValidationError(problem or "Changing or releasing a locked status requires a correction reason.")
    if old and old.status_locked != obj.status_locked:
        require(user, "correct_status")
    if obj.carrier_coverage_complete != (old.carrier_coverage_complete if old else False):
        require(user, "correct_status")


@transaction.atomic
def save_shipment(obj, actor, expected_revision=None, fields=None, correction_reason="", confirm_complete_shipment=False):
    old = Shipment.objects.filter(pk=obj.pk).first() if obj.pk else None
    require(actor, "change_shipment" if old else "add_shipment")
    validate_change(obj, old, actor, correction_reason)
    if old and old.status != Status.DELIVERED and obj.status == Status.DELIVERED and old.legs.count() > 1 and not confirm_complete_shipment:
        raise ValidationError(_("Confirm delivery of every package/leg before marking the entire shipment delivered."))
    obj.full_clean()
    if old:
        if expected_revision is None or expected_revision != old.revision:
            raise ValidationError(_("This shipment changed in another session. Reload before saving."))
        updated = Shipment.objects.filter(pk=old.pk, revision=expected_revision).update(revision=F("revision") + 1)
        if updated != 1:
            raise ValidationError(_("Concurrent change detected. Reload before saving."))
        obj.revision = old.revision + 1
    if (old and old.status != obj.status) or (not old and obj.status != Status.CREATED):
        obj.status_observed_at = timezone.now()
    obj.save()
    entry = audit(obj, actor, "shipment.updated" if old else "shipment.created", snapshot(old) if old else {}, fields)
    if correction_reason.strip():
        # Reasons are staff-only. Never serialize to public tracking.
        entry.changes["correction_reason"] = correction_reason.strip()[:1000]
        entry.save(update_fields=["changes"])
    return obj


@transaction.atomic
def save_child(obj, actor, fields=None):
    require(actor, ("change_" if obj.pk else "add_") + obj._meta.model_name)
    shipment = Shipment.objects.get(pk=obj.shipment_id)
    if shipment.archived_at:
        raise ValidationError(_("Archived shipments cannot be edited."))
    old = type(obj).objects.filter(pk=obj.pk).first() if obj.pk else None
    if hasattr(obj, "public") and (obj.public or obj.public != (old.public if old else False)):
        require(actor, "publish_shipment")
    if hasattr(obj, "source"):
        if old and old.source != "manual":
            immutable = ("shipment_id", "leg_id", "occurred_at", "location", "raw_text", "source", "mapped_status", "provider_identity", "provider_event_key", "provider_time_raw")
            if any(getattr(obj, f) != getattr(old, f) for f in immutable):
                raise ValidationError(_("Provider history cannot be edited as a manual event."))
            obj.source, obj.creator = old.source, old.creator
        else:
            obj.source = "manual"
            obj.creator = old.creator if old else actor
    if isinstance(obj, TrackingLeg) and old and old.registration_state in ("pending", "registered", "stopped"):
        if any(getattr(obj, f) != getattr(old, f) for f in ("shipment_id", "carrier_identifier", "tracking_number")):
            raise ValidationError(_("Registered carrier identifiers are retained. Add a new tracking reference instead."))
    obj.full_clean()
    obj.save()
    audit(obj, actor, obj._meta.model_name + (".updated" if old else ".created"), snapshot(old) if old else {}, fields)
    return obj


@transaction.atomic
def archive_shipment(shipment, actor, restore=False):
    require(actor, "archive_shipment")
    old = Shipment.objects.get(pk=shipment.pk)
    before = snapshot(old)
    old.archived_at = None if restore else timezone.now()
    if not restore:
        old.published = False
    old.revision += 1
    old.save(update_fields=["archived_at", "published", "revision", "updated_at"])
    audit(old, actor, "shipment.restored" if restore else "shipment.archived", before)


@transaction.atomic
def rotate_shipment_reference(shipment, actor):
    require(actor, "rotate_reference")
    old = Shipment.objects.get(pk=shipment.pk)
    old.reference = public_reference()
    old.revision += 1
    old.save(update_fields=["reference", "revision", "updated_at"])
    audit(old, actor, "shipment.reference_revoked")  # no capability in audit/logs


def delayed_q(now=None):
    return Q(confirmed_delay=True) | Q(eta__lt=now or timezone.now())


def active_shipments():
    return Shipment.objects.filter(archived_at__isnull=True)


def delayed_shipments():
    return active_shipments().exclude(status__in=TERMINAL).filter(delayed_q())
