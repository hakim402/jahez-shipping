"""Explicit refresh: short claim, provider work outside DB transactions, atomic CAS save."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
import json
import os
import signal
import subprocess
import sys
import time
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, transaction, OperationalError, IntegrityError
from django.db.models import F, Q
from django.utils import timezone

from .models import Container, ContainerEvent, FAILURES
from .pipeline import Candidate, Labels, RefreshError, fingerprint
from .values import Status, validate_evidence
from .tracking import active_journeys

# 18s killable provider group + bounded database waits leaves margin under Gunicorn 30s / proxy 45s.
PROVIDER_SECONDS = 18
CLAIM_SECONDS = 27
GROQ_SETTINGS = ("GROQ_ENABLED", "GROQ_API_KEY", "GROQ_TEXT_MODEL", "GROQ_TEXT_OUTPUT_MODE", "GROQ_MAX_TOKENS")
STAGES = {"KH": ("Departure", "المغادرة"), "DG": ("Arrival", "الوصول")}


@dataclass(frozen=True)
class RefreshResult:
    ok: bool
    code: str
    changed: bool = False
    ai_used: bool = False


@contextmanager
def short_database_wait():
    if connection.vendor != "sqlite":
        yield
        return
    with connection.cursor() as cursor:
        old = cursor.execute("PRAGMA busy_timeout").fetchone()[0]
        cursor.execute("PRAGMA busy_timeout=750")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f"PRAGMA busy_timeout={int(old)}")


def run_provider(snapshot):
    labels = snapshot.source_evidence.get("facts", {}).get("labels", {})
    payload = {"reference": snapshot.search_reference, "number": snapshot.container_number,
               "labels": labels, "groq": {k: getattr(settings, k) for k in GROQ_SETTINGS}}
    proc = subprocess.Popen([sys.executable, "-m", "apps.containers.refresh_worker"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    try:
        output, _ = proc.communicate(json.dumps(payload).encode(), timeout=PROVIDER_SECONDS)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise RefreshError("timeout") from None
    if proc.returncode or len(output) > 262144:
        raise RefreshError("invalid_extraction")
    try:
        result = json.loads(output)
        if result.get("ok") is not True:
            raise RefreshError(result.get("code") if result.get("code") in FAILURES else "invalid_extraction")
        return result["result"]
    except RefreshError:
        raise
    except (ValueError, KeyError, TypeError):
        raise RefreshError("invalid_extraction") from None


def _claim(pk, *, active_only=False):
    now, token = timezone.now(), uuid.uuid4()
    with transaction.atomic():
        eligible = Container.objects.filter(pk=pk, archived_at__isnull=True)
        if active_only:
            eligible = active_journeys(eligible)
        won = eligible.filter(
            Q(refresh_claim__isnull=True) | Q(refresh_claim_expires_at__lte=now)).update(
                refresh_claim=token, refresh_claim_expires_at=now + timedelta(seconds=CLAIM_SECONDS),
                last_refresh_attempt_at=now, revision=F("revision") + 1)
        if not won:
            if eligible.exists():
                raise RefreshError("concurrent_change")
            return None
        return Container.objects.get(pk=pk)


def _failure(snapshot, code):
    code = code if code in FAILURES else "invalid_extraction"
    # Another request may have edited/archived the row; record conflict without changing its facts.
    with transaction.atomic():
        current = Container.objects.filter(pk=snapshot.pk, refresh_claim=snapshot.refresh_claim).first()
        if current is None:
            return RefreshResult(False, "concurrent_change")
        if current.revision != snapshot.revision:
            code = "concurrent_change"
        Container.objects.filter(pk=current.pk, refresh_claim=snapshot.refresh_claim).update(
            refresh_claim=None, refresh_claim_expires_at=None, last_failure_code=code, revision=F("revision") + 1)
    return RefreshResult(False, code)


def _source_fields(candidate, selected):
    route = candidate.route
    fields = {}
    # This endpoint's equipment count is B/L-wide, not necessarily a per-container count.
    if len(candidate.containers) == 1:
        for name in ("equipment_type", "equipment_quantity"):
            if getattr(candidate, name) is not None:
                fields[name] = getattr(candidate, name)
    for field, value in (("origin_code", route.pol), ("destination_code", route.pod)):
        if value:
            fields[field] = value
    for prefix, port, status in (("departure", route.pol, "KH"), ("arrival", route.pod, "DG")):
        milestones = [m for m in selected.milestones if port and m.location_code == port and m.raw_status == status]
        for kind in ("actual", "estimated"):
            times = {fingerprint(getattr(m, kind).model_dump()): getattr(m, kind).model_dump() for m in milestones if getattr(m, kind)}
            if len(times) > 1:
                # Revisited ports lack a stable leg ID in this interface; never choose by array order.
                raise RefreshError("invalid_extraction")
            if times:
                fields[f"{prefix}_{kind}"] = next(iter(times.values()))
        if prefix == "departure":
            vessels = {(m.vessel, m.voyage) for m in milestones if m.vessel and m.voyage}
            if len(vessels) == 1:
                fields["vessel"], fields["voyage"] = next(iter(vessels))
    return fields


def _save(snapshot, prepared, deadline):
    candidate = Candidate.model_validate(prepared["candidate"])
    if candidate.search_reference != snapshot.search_reference or candidate.adapter != snapshot.source_adapter or candidate.website != snapshot.source_website:
        raise RefreshError("identity_mismatch")
    identities = [c.container_number for c in candidate.containers]
    selected_number = prepared["selected"]
    if selected_number not in identities or (not snapshot.container_number and len(identities) != 1) or (snapshot.container_number and snapshot.container_number != selected_number):
        raise RefreshError("identity_mismatch" if snapshot.container_number else "ambiguous_container")
    selected = next(c for c in candidate.containers if c.container_number == selected_number)
    fields = _source_fields(candidate, selected)
    labels = prepared["labels"]
    if not isinstance(labels, dict) or len(labels) > 8:
        raise RefreshError("invalid_extraction")
    Labels.model_validate({"labels": [{"source": k, "ar": v} for k, v in labels.items()]})
    source_names = {m.location_label for m in selected.milestones}
    if set(labels) - source_names:
        raise RefreshError("invalid_extraction")
    for prefix, port in (("origin", candidate.route.pol), ("destination", candidate.route.pod)):
        names = {m.location_label for m in selected.milestones if port and m.location_code == port and m.location_label}
        if len(names) == 1:
            name = next(iter(names))
            if len(name) <= 200:
                fields[prefix + "_label_en"] = name
                if name in labels:
                    fields[prefix + "_label_ar"] = labels[name]
    observed = timezone.now()
    evidence = {"adapter": candidate.adapter, "source_sha256": candidate.source_sha256, "observed_at": observed.isoformat(),
                "facts": {"container": selected_number, "reference": candidate.search_reference, "fields": fields,
                          "milestones_sha256": fingerprint(selected.model_dump()), "milestones_count": len(selected.milestones), "labels": labels}}
    validate_evidence(evidence)
    with transaction.atomic():
        # SQLite IMMEDIATE obtains the writer lock before reading. The conditional write also checks ownership/version.
        current = Container.objects.get(pk=snapshot.pk)
        if (current.refresh_claim != snapshot.refresh_claim or current.revision != snapshot.revision
                or current.archived_at or current.refresh_claim_expires_at <= observed):
            raise RefreshError("concurrent_change")
        if time.monotonic() >= deadline:
            raise RefreshError("timeout")
        won = Container.objects.filter(pk=current.pk, revision=snapshot.revision, refresh_claim=snapshot.refresh_claim,
            archived_at__isnull=True, refresh_claim_expires_at__gt=observed).update(revision=F("revision") + 1)
        if not won:
            raise RefreshError("concurrent_change")
        current.bind_container(identities, selected_number=selected_number)
        # A route change can be a new voyage under the same reference: don't merge retained dates across it.
        for name in ("origin_code", "destination_code"):
            if getattr(current, name) and fields.get(name) and getattr(current, name) != fields[name]:
                raise RefreshError("identity_mismatch")
        for name, value in fields.items():
            setattr(current, name, value)
        # Only retrieved, route-matched actual facts advance the carrier stage. Manually copied dates
        # are independent; omissions preserve the last accepted stage rather than regress it.
        if fields.get("arrival_actual"):
            current.carrier_status, current.raw_status = Status.ARRIVED, "DG"
        elif fields.get("departure_actual") and current.carrier_status != Status.ARRIVED:
            current.carrier_status, current.raw_status = Status.IN_TRANSIT, "KH"
        review = (not selected.milestones or any(m.raw_status not in STAGES or not (m.actual or m.estimated) for m in selected.milestones)
                  or current.carrier_status == Status.UNKNOWN)
        changed = current.source_fingerprint != candidate.source_sha256
        current.source_fingerprint, current.source_evidence = candidate.source_sha256, evidence
        current.last_refresh_success_at = observed
        current.last_failure_code = "unknown_status" if review else ""
        current.refresh_claim = current.refresh_claim_expires_at = None
        current.save(update_fields=set(fields) | {"container_number", "carrier_status", "raw_status", "source_fingerprint", "source_evidence", "last_refresh_success_at", "last_failure_code", "refresh_claim", "refresh_claim_expires_at"})
        estimate_slots = {}
        accepted_events = []
        for milestone in selected.milestones:
            if milestone.estimated:
                slot = (milestone.raw_status, milestone.location_code)
                value_hash = fingerprint(milestone.estimated.model_dump())
                if slot in estimate_slots and estimate_slots[slot] != value_hash:
                    raise RefreshError("invalid_extraction")
                estimate_slots[slot] = value_hash
            kinds = ("actual", "estimated") if milestone.actual or milestone.estimated else ("unknown",)
            for kind in kinds:
                value = getattr(milestone, kind, None)
                if value is None and kind != "unknown":
                    continue
                if not milestone.raw_status or not milestone.location_code:
                    raise RefreshError("invalid_extraction")
                en, ar = "Carrier update — review required", "تحديث من الناقل — يتطلب المراجعة"
                if milestone.raw_status == "KH" and kind != "unknown":
                    en, ar = ("Actual departure", "مغادرة فعلية") if kind == "actual" else ("Estimated departure", "مغادرة متوقعة")
                elif milestone.raw_status == "DG" and kind != "unknown":
                    en, ar = ("Actual arrival", "وصول فعلي") if kind == "actual" else ("Estimated arrival", "وصول متوقع")
                event, _ = ContainerEvent.objects.record_carrier(container=current, raw_status=milestone.raw_status,
                    raw_text=milestone.raw_text or "", location_code=milestone.location_code, location=milestone.location_label or "",
                    source_time=value.model_dump() if value else None, designation=kind, title_en=en, title_ar=ar)
                accepted_events.append(event)
                if time.monotonic() >= deadline:
                    raise RefreshError("timeout")
        if not review:
            from .publication import auto_publish
            auto_publish(current, fields, accepted_events)
            if time.monotonic() >= deadline:
                raise RefreshError("timeout")
        return RefreshResult(True, "unknown_status" if review else "updated" if changed else "unchanged", changed, prepared["ai_used"])


def refresh_container(pk, *, active_only=False):
    """Only explicit authorized callers; public views never invoke this service."""
    if connection.in_atomic_block:
        # Providers must not be called from a request/admin write transaction.
        raise RuntimeError("refresh_requires_autocommit")
    snapshot = None
    deadline = time.monotonic() + 24
    with short_database_wait():
        try:
            snapshot = _claim(pk, active_only=active_only)
            if snapshot is None:
                return RefreshResult(True, "skipped") if active_only else RefreshResult(False, "unavailable")
            prepared = run_provider(snapshot)
            return _save(snapshot, prepared, deadline)
        except RefreshError as exc:
            code = exc.code
        except (ValidationError, ValueError, KeyError, TypeError, IntegrityError):
            code = "invalid_extraction"
        except OperationalError:
            code = "concurrent_change"
        except Exception:
            code = "unavailable"
        if snapshot is not None:
            try:
                return _failure(snapshot, code)
            except OperationalError:
                pass  # Bounded failure; persisted claim expires, last-good data remains intact.
        return RefreshResult(False, code)
