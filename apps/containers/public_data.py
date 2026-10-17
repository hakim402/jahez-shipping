"""Strict stored approval contract and deliberate public projection. No ORM/providers."""
from datetime import datetime, timezone
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from .values import Status, validate_source_time

MAX_PUBLIC_BYTES = 262144
MAX_EVENTS = 100
Text = Annotated[str, Field(max_length=200)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PublicTime(Strict):
    raw: Annotated[str, Field(max_length=32)]
    precision: Literal["date", "minute", "second"]
    designation: Literal["actual", "estimated"]
    source_timezone: str | None
    normalized_instant: str | None

    @model_validator(mode="after")
    def valid(self):
        validate_source_time(self.model_dump())
        return self


class Facts(Strict):
    container_number: Annotated[str, Field(pattern=r"^(?:[A-Z]{4}[0-9]{7})?$")]
    equipment_type: Annotated[str, Field(max_length=32)]
    equipment_quantity: Annotated[int, Field(ge=1, le=32767)] | None
    origin_code: Annotated[str, Field(max_length=16)]
    destination_code: Annotated[str, Field(max_length=16)]
    origin_label_en: Text
    origin_label_ar: Text
    destination_label_en: Text
    destination_label_ar: Text
    vessel: Text
    voyage: Annotated[str, Field(max_length=80)]
    departure_actual: PublicTime | None
    departure_estimated: PublicTime | None
    arrival_actual: PublicTime | None
    arrival_estimated: PublicTime | None
    status: Literal["unknown", "preparing", "in_transit", "arrived", "customs", "ready", "completed", "on_hold"]

    @model_validator(mode="after")
    def designations(self):
        for name in ("departure_actual", "departure_estimated", "arrival_actual", "arrival_estimated"):
            value = getattr(self, name)
            if value and value.designation != ("actual" if name.endswith("actual") else "estimated"):
                raise ValueError("designation")
        return self


class ApprovedEvent(Strict):
    # Private merge identity, deliberately stripped from the customer projection.
    key: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    origin: Literal["carrier", "manual"]
    title_en: Text
    title_ar: Text
    detail_en: Annotated[str, Field(max_length=2000)]
    detail_ar: Annotated[str, Field(max_length=2000)]
    location: Annotated[str, Field(max_length=256)]
    source_time: PublicTime | None
    designation: Literal["actual", "estimated", "unknown"]

    @model_validator(mode="after")
    def designation_matches(self):
        if self.source_time and self.source_time.designation != self.designation:
            raise ValueError("designation")
        return self


def checked_instant(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("invalid_check_time")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("invalid_check_time")
    return parsed


class Snapshot(Strict):
    version: Literal[1]
    facts: Facts
    events: Annotated[list[ApprovedEvent], Field(max_length=MAX_EVENTS)]
    manual_status: bool
    checked_at: str | None
    reviewed_at: str
    limited: bool

    @model_validator(mode="after")
    def times_and_keys(self):
        checked_instant(self.checked_at)
        if checked_instant(self.reviewed_at) is None:
            raise ValueError("review_time_required")
        if len({e.key for e in self.events}) != len(self.events):
            raise ValueError("duplicate_event")
        return self


def validate_snapshot(value):
    if len(json.dumps(value, ensure_ascii=False).encode()) > MAX_PUBLIC_BYTES:
        raise ValueError("public_snapshot_too_large")
    return Snapshot.model_validate(value)


def projection(snapshot, language, now):
    """Only display values leave this module; no keys, model, evidence or source identifiers."""
    ar = language == "ar"
    facts = snapshot.facts
    def text(name):
        return getattr(facts, name + ("_ar" if ar else "_en")) or getattr(facts, name + ("_en" if ar else "_ar"))
    def time_value(value):
        return {"raw": value.raw, "designation": value.designation, "precision": value.precision,
                "zone": value.source_timezone} if value else None
    checked = checked_instant(snapshot.checked_at)
    return {
        "container_number": facts.container_number, "equipment_type": facts.equipment_type,
        "equipment_quantity": facts.equipment_quantity, "origin": text("origin_label") or facts.origin_code,
        "destination": text("destination_label") or facts.destination_code,
        "vessel": facts.vessel, "voyage": facts.voyage, "status": str(Status(facts.status).label),
        "departure_actual": time_value(facts.departure_actual), "departure_estimated": time_value(facts.departure_estimated),
        "arrival_actual": time_value(facts.arrival_actual), "arrival_estimated": time_value(facts.arrival_estimated),
        "events": [{"title": (e.title_ar or e.title_en) if ar else (e.title_en or e.title_ar),
                    "detail": (e.detail_ar or e.detail_en) if ar else (e.detail_en or e.detail_ar),
                    "location": e.location, "origin": e.origin, "time": time_value(e.source_time)} for e in snapshot.events],
        "checked": checked.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if checked else "",
        "stale": bool(checked and (now - checked).total_seconds() >= 30 * 3600), "limited": snapshot.limited,
    }
