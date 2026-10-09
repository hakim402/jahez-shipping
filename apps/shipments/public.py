"""Explicit allowlist projection. Never pass operational models to public templates."""
from zoneinfo import ZoneInfo
from django.conf import settings
from django.utils import timezone
from .models import Shipment


def translated(obj, name, lang):
    return getattr(obj, name + "_" + lang) or getattr(obj, name + "_en")


def public_summary(shipment, lang):
    zone = ZoneInfo(settings.BUSINESS_TIME_ZONE)
    def date(value):
        return timezone.localtime(value, zone) if value else None
    events = [{"occurred_at": date(e.occurred_at), "title": translated(e, "title", lang),
        "body": translated(e, "body", lang), "source": e.source} for e in shipment.events.filter(public=True).order_by("occurred_at", "pk")]
    items = [{"description": translated(i, "description", lang), "quantity": i.quantity,
        "unit": i.unit_ar if lang == "ar" else i.unit, "cartons": i.cartons} for i in shipment.items.filter(public=True)]
    # Capability itself stays out of result HTML; the customer already entered it.
    return {"mode": shipment.get_mode_display(), "status": shipment.get_status_display(),
        "origin": translated(shipment, "origin", lang), "destination": translated(shipment, "destination", lang),
        "eta": date(shipment.eta), "actual_arrival": date(shipment.actual_arrival), "delivered_at": date(shipment.delivered_at),
        "events": events, "items": items, "no_updates": not events,
        "last_update": events[-1]["occurred_at"] if events else None,
        "created_at": date(shipment.created_at), "timezone": settings.BUSINESS_TIME_ZONE,
        "manual": shipment.tracking_mode == "manual", "is_demo": shipment.is_demo}


def find_public(reference, lang):
    query = Shipment.objects.filter(reference=reference.strip().upper(), published=True, archived_at__isnull=True)
    if not settings.DEBUG:
        query = query.filter(is_demo=False)
    shipment = query.first()
    return public_summary(shipment, lang) if shipment else None
