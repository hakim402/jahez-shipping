from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Max
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from .adapter import configuration
from .models import IntegrationJob, WebhookReceipt
from .services import require, retry_job
from apps.shipments.models import TrackingLeg


ERROR_HELP = {
    "provider_quota": _("Provider quota exhausted. Review the account allocation before retrying."),
    "provider_authentication": _("Provider rejected authentication. Check the server-side key privately."),
    "unsupported_identifier": _("Identifier or carrier is unsupported. Verify a carrier-issued number; use manual tracking for bills."),
    "unsupported_carrier": _("Verify the numeric carrier code against the provider's carrier directory."),
    "provider_rate_limit": _("Provider rate limit reached. A bounded retry is scheduled."),
    "provider_timeout": _("Provider timed out. A bounded retry is scheduled."),
    "rate_store_unavailable": _("Rate-limit storage is unavailable. No provider request was sent."),
    "unknown_or_ineligible_reference": _("Receipt quarantined: no eligible registered reference matches. No shipment was created."),
}


class ImmutableIntegrationAdmin(ModelAdmin):
    actions = None
    list_per_page = 25
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WebhookReceipt)
class ReceiptAdmin(ImmutableIntegrationAdmin):
    list_display = ("id", "event_type", "state_display", "safe_error", "received_at", "processed_at", "is_demo")
    list_filter = ("state", "event_type", "is_demo")
    fields = ("id", "event_type", "state", "safe_error", "received_at", "processed_at", "is_demo")
    readonly_fields = fields


@admin.register(IntegrationJob)
class JobAdmin(ImmutableIntegrationAdmin):
    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request, obj) and request.user.has_perm("shipments.view_shipment")

    list_display = ("id", "kind", "leg", "state_display", "attempts", "safe_error", "available_at", "updated_at")
    list_filter = ("state", "kind")
    fields = ("id", "kind", "leg", "receipt", "state", "attempts", "safe_error", "available_at", "lease_until", "created_at", "updated_at", "finished_at")
    readonly_fields = fields


def integration_health(request):
    if not request.user.has_perm("tracking.view_integrationjob") or not request.user.has_perm("shipments.view_shipment"):
        raise PermissionDenied
    jobs = IntegrationJob.objects.all()
    counts = {state: jobs.filter(state=state).count() for state in ("pending", "running", "retry", "failed")}
    receipts = WebhookReceipt.objects.all()
    recent = list(jobs.select_related("leg", "leg__shipment")[:20])
    for job in recent:
        job.error_help = ERROR_HELP.get(job.safe_error, _("Review the safe diagnostic and retry only when the cause is resolved.")) if job.safe_error else ""
    context = {**admin.site.each_context(request), "title": _("Integration health"), "config_state": configuration(),
        "counts": counts, "recent_jobs": recent,
        "quarantined": receipts.filter(state="quarantined").count() if request.user.has_perm("tracking.view_webhookreceipt") else None,
        "can_view_receipts": request.user.has_perm("tracking.view_webhookreceipt"),
        "last_success": TrackingLeg.objects.filter(shipment__is_demo=False).aggregate(value=Max("last_success"))["value"],
        "can_retry": request.user.has_perm("tracking.retry_jobs"), "business_timezone": settings.BUSINESS_TIME_ZONE,
        "webhook_path": reverse("track17_webhook"), "reconcile_seconds": settings.TRACK17_RECONCILE_SECONDS}
    return TemplateResponse(request, "admin/tracking/health.html", context)


def retry(request, pk):
    require(request.user, "retry_jobs")
    job = get_object_or_404(IntegrationJob, pk=pk)
    if request.method == "POST" and request.POST.get("confirm") == "yes":
        try:
            retry_job(pk, request.user)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, _("Work accepted durably. See integration health for progress."))
        return HttpResponseRedirect(reverse("admin:integration_health"))
    return TemplateResponse(request, "admin/tracking/confirm.html", {**admin.site.each_context(request), "title": _("Confirm retry"), "operation": "retry", "object": job})


_original_urls = admin.site.get_urls

def integration_urls():
    return [path("integration-health/", admin.site.admin_view(integration_health), name="integration_health"), path("integration-job/<int:pk>/retry/", admin.site.admin_view(retry), name="integration_job_retry")] + _original_urls()

admin.site.get_urls = integration_urls
