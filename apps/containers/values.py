"""Small serializable value rules; no network, defaults from source time or business timezone."""
import base64
import json
import re
import secrets
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class Status(models.TextChoices):
    UNKNOWN = "unknown", _("Needs review")
    PREPARING = "preparing", _("Preparing")
    IN_TRANSIT = "in_transit", _("In transit")
    ARRIVED = "arrived", _("Arrived")
    CUSTOMS = "customs", _("Customs")
    READY = "ready", _("Ready for collection")
    COMPLETED = "completed", _("Completed")
    ON_HOLD = "on_hold", _("On hold")


class Designation(models.TextChoices):
    UNKNOWN = "unknown", _("Unknown")
    ACTUAL = "actual", _("Actual")
    ESTIMATED = "estimated", _("Estimated")


def validate_public_snapshot(value):
    if value == {}:
        return
    from .public_data import validate_snapshot
    try:
        validate_snapshot(value)
    except (ValueError, TypeError) as exc:
        raise ValidationError(_("The reviewed public data is invalid or too large.")) from None


def lookup_code():
    # Sixteen random bytes = 128 bits; never derived from IDs, B/L or customer data.
    return "JHZ-" + base64.b32encode(secrets.token_bytes(16)).decode("ascii").rstrip("=")


def validate_source_time(value):
    """JSON null means absent. An explicit instant is checked, never guessed or generated."""
    if value is None:
        return
    required = {"raw", "precision", "designation", "source_timezone", "normalized_instant"}
    error = _("Use source time text, precision and actual/estimated designation; leave unknown timezone and instant empty.")
    if not isinstance(value, dict) or set(value) != required:
        raise ValidationError(error)
    raw, precision = value["raw"], value["precision"]
    if not isinstance(raw, str) or len(raw) > 32 or value["designation"] not in ("actual", "estimated"):
        raise ValidationError(error)
    formats = {"date": (r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),
               "minute": (r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", "%Y-%m-%d %H:%M"),
               "second": (r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", "%Y-%m-%d %H:%M:%S")}
    if not isinstance(precision, str) or precision not in formats:
        raise ValidationError(error)
    pattern, fmt = formats[precision]
    try:
        if not re.fullmatch(pattern, raw):
            raise ValueError
        local = datetime.strptime(raw, fmt)
        zone = value["source_timezone"]
        tz = None
        if zone is not None:
            if not isinstance(zone, str) or not zone or len(zone) > 64:
                raise ValueError
            if re.fullmatch(r"[+-]\d{2}:\d{2}", zone):
                hours, minutes = int(zone[1:3]), int(zone[4:6])
                if hours > 14 or minutes > 59 or (hours == 14 and minutes):
                    raise ValueError
                tz = timezone(timedelta(minutes=(hours * 60 + minutes) * (-1 if zone[0] == "-" else 1)))
            else:
                tz = ZoneInfo(zone)
        instant = value["normalized_instant"]
        if instant is not None:
            if tz is None or precision == "date" or not isinstance(instant, str) or len(instant) > 40:
                raise ValueError
            parsed = datetime.fromisoformat(instant)
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError
            # Reject a fabricated offset/date/time, including nonexistent local DST clock times.
            observed = parsed.astimezone(tz).replace(tzinfo=None)
            if observed.strftime(fmt) != local.strftime(fmt):
                raise ValueError
            if precision == "minute" and (parsed.second or parsed.microsecond):
                raise ValueError
            if precision == "second" and parsed.microsecond:
                raise ValueError
    except (ValueError, TypeError, ZoneInfoNotFoundError, OverflowError):
        raise ValidationError(error) from None


def validate_evidence(value):
    if value == {}:
        return
    error = _("Keep accepted source evidence within 8 KiB with adapter, fingerprint, observation time and facts only.")
    if not isinstance(value, dict) or set(value) != {"adapter", "source_sha256", "observed_at", "facts"}:
        raise ValidationError(error)
    try:
        if (not isinstance(value["adapter"], str) or len(value["adapter"]) > 64
                or not isinstance(value["source_sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", value["source_sha256"])
                or not isinstance(value["observed_at"], str)
                or not isinstance(value["facts"], dict)):
            raise ValueError
        observed = datetime.fromisoformat(value["observed_at"])
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise ValueError
        if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")) > 8192:
            raise ValueError
    except (TypeError, ValueError, RecursionError, OverflowError):
        raise ValidationError(error) from None
