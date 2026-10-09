"""Bounded v2.4 normalization; drop addresses, contacts and provider URLs."""
import hashlib
import json
from datetime import timezone as utc_timezone
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from apps.shipments.models import Status
from .adapter import identifier, ProviderError


class PayloadError(ValueError):
    pass


STATUS_MAP = {"InfoReceived": Status.PREPARING, "InTransit": Status.TRANSIT, "AvailableForPickup": Status.ARRIVED, "OutForDelivery": Status.OUT, "Delivered": Status.DELIVERED, "Expired": Status.HOLD, "DeliveryFailure": Status.HOLD, "Exception": Status.HOLD}
SUB_MAP = {"InTransit_Departure": Status.DEPARTED, "InTransit_Arrival": Status.ARRIVED, "InTransit_CustomsProcessing": Status.CUSTOMS, "InTransit_CustomsRequiringInformation": Status.HOLD, "Exception_Returned": Status.RETURNED, "Exception_Cancel": Status.CANCELLED}


EVENT_STAGE_MAP = {"PickedUp": Status.TRANSIT, "Departure": Status.DEPARTED, "Arrival": Status.ARRIVED, "Returning": Status.HOLD, "Returned": Status.RETURNED}


def mapped(status, sub="", event_stage=False):
    if event_stage and status in EVENT_STAGE_MAP:
        return str(EVENT_STAGE_MAP[status])
    if status not in STATUS_MAP:
        return ""
    if sub in SUB_MAP and not sub.startswith(status + "_"):
        return ""
    return str(SUB_MAP.get(sub, STATUS_MAP[status]))


def text(value, limit):
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > limit:
        raise PayloadError("invalid_text")
    return value


def known_time(value):
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        dt = parse_datetime(value)
    except (ValueError, TypeError, OverflowError):
        return None
    if not dt or timezone.is_naive(dt) or dt > timezone.now() + timezone.timedelta(minutes=5):
        return None
    return dt.astimezone(utc_timezone.utc).isoformat()


def event(raw, provider):
    if not isinstance(raw, dict):
        raise PayloadError("invalid_event")
    original = raw.get("time_raw") or {}
    if not isinstance(original, dict):
        raise PayloadError("invalid_time")
    original = {k: text(original.get(k), 64) for k in ("date", "time", "timezone")}
    status = text(raw.get("stage"), 64)
    sub = text(raw.get("sub_status"), 80)
    result = {"occurred_at": known_time(raw.get("time_utc")) or known_time(raw.get("time_iso")), "time_raw": original,
        "time_iso": text(raw.get("time_iso"), 100), "status": mapped(status, sub, event_stage=True), "stage": status,
        "sub_status": sub, "description": text(raw.get("description"), 4000), "location": text(raw.get("location"), 160), "provider": provider}
    result["key"] = hashlib.sha256(json.dumps(result, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return result


def normalize(data, event_type="TRACKING_UPDATED"):
    if not isinstance(data, dict) or event_type not in ("TRACKING_UPDATED", "TRACKING_STOPPED"):
        raise PayloadError("invalid_contract")
    try:
        ident = identifier(data.get("number"), data.get("carrier"))
    except ProviderError:
        raise PayloadError("invalid_identifier") from None
    result = {**ident, "event_type": event_type, "events": [], "latest_time": None, "status": "", "provider_status": "", "sync_time": None}
    if event_type == "TRACKING_STOPPED":
        return result
    info = data.get("track_info")
    if not isinstance(info, dict):
        raise PayloadError("missing_track_info")
    latest = info.get("latest_status") or {}
    if not isinstance(latest, dict):
        raise PayloadError("invalid_status")
    status, sub = text(latest.get("status"), 64), text(latest.get("sub_status"), 80)
    result.update(status=mapped(status, sub), provider_status=status)
    latest_event = info.get("latest_event")
    if latest_event:
        result["latest_time"] = event(latest_event, ident["carrier"])["occurred_at"]
    tracking = info.get("tracking") or {}
    if not isinstance(tracking, dict):
        raise PayloadError("invalid_tracking")
    providers = tracking.get("providers", [])
    if not isinstance(providers, list) or len(providers) > 10:
        raise PayloadError("too_many_providers")
    sync_times = []
    for provider in providers:
        if not isinstance(provider, dict):
            raise PayloadError("invalid_provider")
        provider_info = provider.get("provider") or {}
        if not isinstance(provider_info, dict):
            raise PayloadError("invalid_provider")
        code = provider_info.get("key", ident["carrier"])
        if not isinstance(code, int) or isinstance(code, bool):
            raise PayloadError("invalid_provider")
        if provider.get("latest_sync_status") == "Success":
            value = known_time(provider.get("latest_sync_time"))
            if value:
                sync_times.append(value)
        events = provider.get("events", [])
        if not isinstance(events, list) or len(events) + len(result["events"]) > 500:
            raise PayloadError("too_many_events")
        result["events"].extend(event(e, code) for e in events)
    result["sync_time"] = min(sync_times) if providers and len(sync_times) == len(providers) else None
    return result


def parse_webhook(raw):
    try:
        body = json.loads(raw)
        if not isinstance(body, dict):
            raise PayloadError("invalid_contract")
        return normalize(body.get("data"), body.get("event"))
    except (ValueError, RecursionError, TypeError, KeyError) as exc:
        raise PayloadError("invalid_payload") from exc
