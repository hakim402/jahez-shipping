"""Explicit human approval and narrowly gated automatic carrier-only snapshot updates."""
import json
from django.db import transaction
from django.utils import timezone

from .models import Container
from .public_data import Facts, validate_snapshot, MAX_EVENTS, MAX_PUBLIC_BYTES
from .values import Status

FACT_FIELDS = tuple(name for name in Facts.model_fields if name != "status")
AUTO_FIELDS = set(FACT_FIELDS) - {"origin_label_ar", "destination_label_ar", "container_number"}


def known_event(event):
    return event.raw_status in ("KH", "DG") and event.designation in ("actual", "estimated") and event.source_time is not None


def event_data(event, *, automatic=False):
    return {"key": event.dedupe_key, "origin": event.origin, "title_en": event.title_en, "title_ar": event.title_ar,
            "detail_en": "" if automatic else event.detail_en, "detail_ar": "" if automatic else event.detail_ar,
            "location": event.location, "source_time": event.source_time, "designation": event.designation}


def ordered_events(events):
    dated = sorted(events, key=lambda e: (e["source_time"] is None, (e["source_time"] or {}).get("raw", ""), e["key"]))
    # Retain undated notes and the most recent source-clock entries within the bounded snapshot.
    return dated[-MAX_EVENTS:]


def bounded(data):
    while len(json.dumps(data, ensure_ascii=False).encode()) > MAX_PUBLIC_BYTES and data["events"]:
        data["events"].pop(0)
        data["limited"] = True
    validate_snapshot(data)
    return data


@transaction.atomic
def publish_reviewed(container):
    """Only called after explicit admin confirmation, after parent/inline validation/saves."""
    current = Container.objects.get(pk=container.pk)
    if not current.is_published or current.archived_at:
        return
    # Confirmation approves the displayed known dated carrier milestones; unknown mappings stay private.
    for event in current.events.filter(origin="carrier", raw_status__in=("KH", "DG"), source_time__isnull=False).iterator():
        if known_event(event) and not event.is_public:
            event.is_public = True
            event.save(update_fields=["is_public"])
    events = list(current.events.filter(is_public=True).order_by("-source_time__raw", "-pk")[:MAX_EVENTS + 1])
    facts = {name: getattr(current, name) for name in FACT_FIELDS}
    facts["status"] = current.display_status
    data = {"version": 1, "facts": facts,
            "events": ordered_events([event_data(e) for e in events]),
            "manual_status": bool(current.manual_status_override),
            "checked_at": current.last_refresh_success_at.isoformat() if current.last_refresh_success_at else None,
            "reviewed_at": timezone.now().isoformat(), "limited": len(events) > MAX_EVENTS}
    current.public_snapshot = bounded(data)
    current.save(update_fields=["public_snapshot"])


def auto_publish(current, source_fields, accepted_events):
    """Caller holds the Phase 4 atomic write/claim check. No standalone or public invocation."""
    if not current.is_published or current.archived_at or not current.auto_publish_carrier_updates or not current.public_snapshot:
        return
    previous = validate_snapshot(current.public_snapshot)
    approved_override = previous.facts.status if previous.manual_status else None
    if current.manual_status_override != approved_override:
        return  # An unreviewed manual status must not alter the public snapshot indirectly.
    data = previous.model_dump()
    for field, value in source_fields.items():
        if field in AUTO_FIELDS:
            data["facts"][field] = value
    data["facts"]["container_number"] = current.container_number
    # Advance only from actual facts in this response, never private/manual retained dates.
    if not previous.manual_status:
        if source_fields.get("arrival_actual"):
            data["facts"]["status"] = Status.ARRIVED.value
        elif source_fields.get("departure_actual") and previous.facts.status != Status.ARRIVED:
            data["facts"]["status"] = Status.IN_TRANSIT.value
    merged = {e["key"]: e for e in data["events"]}
    for event in accepted_events:
        if not known_event(event):
            return
        merged[event.dedupe_key] = event_data(event, automatic=True)
    data["limited"] = data["limited"] or len(merged) > MAX_EVENTS
    data["events"] = ordered_events(list(merged.values()))
    data["checked_at"] = current.last_refresh_success_at.isoformat()
    data = bounded(data)
    for event in accepted_events:
        if not event.is_public:
            event.is_public = True
            event.save(update_fields=["is_public"])
    current.public_snapshot = data
    current.save(update_fields=["public_snapshot"])


def withdraw_manual_events(current):
    """Removing an event's public flag withdraws it without publishing other private edits."""
    if not current.public_snapshot or not current.is_published:
        return
    data = validate_snapshot(current.public_snapshot).model_dump()
    retained = set(current.events.filter(origin="manual", is_public=True).values_list("dedupe_key", flat=True))
    events = [e for e in data["events"] if e["origin"] != "manual" or e["key"] in retained]
    if len(events) != len(data["events"]):
        data["events"] = events
        current.public_snapshot = data
        current.save(update_fields=["public_snapshot"])
