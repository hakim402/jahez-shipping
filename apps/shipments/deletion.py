"""Confirmed single-record deletion with retained audit and protected relations."""
import hashlib
import json
from decimal import Decimal
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models.deletion import PROTECT, ProtectedError
from django.utils.translation import gettext_lazy as _
from .models import Customer, Shipment, ShipmentItem, TrackingLeg, TrackingEvent, Document, FileRemoval
from .services import audit, require, snapshot

DELETABLE = (Customer, Shipment, ShipmentItem, TrackingLeg, TrackingEvent, Document)
SALT = "jahez.shipping.delete-record"


def fingerprint(obj):
    values = {}
    for field in obj._meta.concrete_fields:
        value = field.get_prep_value(field.value_from_object(obj))
        values[field.attname] = str(value.normalize()) if isinstance(value, Decimal) else str(value)
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def confirmation_token(obj, user):
    return signing.dumps({"model": obj._meta.label_lower, "pk": obj.pk,
                          "user": user.pk, "version": fingerprint(obj)}, salt=SALT)


def deletion_problem(obj):
    if not isinstance(obj, DELETABLE):
        return _("This history record is retained and cannot be deleted.")
    if isinstance(obj, Shipment) and (not obj.archived_at or obj.published):
        return _("Archive this shipment before deleting it. Archiving hides tracking and can be undone.")
    if isinstance(obj, TrackingEvent) and obj.source != "manual":
        return _("Carrier history cannot be deleted. Unpublish the update if it should not be shown.")
    if isinstance(obj, TrackingLeg) and obj.registration_state in ("pending", "registered", "stopped"):
        return _("This carrier reference is retained because registration has already started.")
    for relation in obj._meta.related_objects:
        if relation.on_delete is PROTECT and relation.related_model._default_manager.filter(
                **{relation.field.attname: obj.pk}).exists():
            return _("This record is linked to other records. Keep it, or remove eligible linked records first.")
    return ""


@transaction.atomic
def delete_record(model, pk, actor, token, reason):
    if model not in DELETABLE:
        raise PermissionDenied
    require(actor, "view_" + model._meta.model_name)
    require(actor, "delete_" + model._meta.model_name)
    obj = model.objects.select_for_update().get(pk=pk)
    if getattr(obj, "shipment_id", None):
        require(actor, "view_shipment")
    try:
        expected = signing.loads(token, salt=SALT, max_age=1800)
    except signing.BadSignature:
        raise ValidationError(_("This confirmation expired. Open the delete page again.")) from None
    if expected != {"model": obj._meta.label_lower, "pk": obj.pk, "user": actor.pk, "version": fingerprint(obj)}:
        raise ValidationError(_("This record changed. Review it again before deleting."))
    if not reason.strip():
        raise ValidationError(_("Enter a reason for deleting this record."))
    problem = deletion_problem(obj)
    if problem:
        raise ValidationError(problem)
    if getattr(obj, "public", False):
        require(actor, "publish_shipment")
    entry = audit(obj, actor, obj._meta.model_name + ".deleted", before=snapshot(obj))
    entry.changes["reason"] = reason.strip()[:1000]
    entry.save(update_fields=["changes"])
    if isinstance(obj, Document):
        FileRemoval.objects.get_or_create(storage_name=obj.file.name)
    try:
        obj.delete()
    except ProtectedError:
        raise ValidationError(_("This record is linked to other records. Keep it, or remove eligible linked records first.")) from None
    if model is Document:
        transaction.on_commit(clean_file_removals)


def clean_file_removals(limit=10):
    from apps.core.maintenance import active
    if active():
        return
    storage = Document._meta.get_field("file").storage
    for removal in FileRemoval.objects.order_by("pk")[:limit]:
        try:
            storage.delete(removal.storage_name)
        except Exception:
            # Retain the private outbox row for scheduled retry; never log file names.
            continue
        removal.delete()
