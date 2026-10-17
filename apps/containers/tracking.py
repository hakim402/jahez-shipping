"""Shared daily selection and read-only admin attention rules; no provider calls."""
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext

from .models import Container
from .values import Status

STALE_AFTER = timedelta(hours=30)


def active_journeys(queryset=None):
    queryset = Container.objects.all() if queryset is None else queryset
    return queryset.filter(archived_at__isnull=True).exclude(
        manual_status_override=Status.COMPLETED).exclude(carrier_status=Status.COMPLETED)


def attention_query(now=None):
    return (Q(last_refresh_success_at__isnull=True)
            | Q(last_refresh_success_at__lte=(now or timezone.now()) - STALE_AFTER)
            | ~Q(last_failure_code=""))


def attention_text(obj, now=None):
    now = now or timezone.now()
    if obj.archived_at:
        return gettext("Archived — daily checks skipped")
    if Status.COMPLETED in (obj.manual_status_override, obj.carrier_status):
        return gettext("Completed — daily checks skipped")
    if obj.refresh_claim and obj.refresh_claim_expires_at and obj.refresh_claim_expires_at > now:
        return gettext("Checking carrier")
    if obj.last_failure_code == "unknown_status":
        return gettext("Carrier stages need review")
    if obj.last_failure_code:
        return gettext("Last check failed — retry or verify manual facts")
    if not obj.last_refresh_success_at:
        return gettext("Not checked yet")
    if obj.last_refresh_success_at <= now - STALE_AFTER:
        return gettext("Stale — last successful check is over 30 hours old")
    return gettext("Up to date")
