from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


STATE_LABELS = {"pending": _("Pending"), "retry": _("Scheduled retry"), "running": _("Running"), "failed": _("Failed"), "succeeded": _("Completed"), "quarantined": _("Quarantined"), "processed": _("Processed")}


class WebhookReceipt(models.Model):
    digest = models.CharField(max_length=64, unique=True, editable=False)
    event_type = models.CharField(max_length=24, editable=False)
    payload = models.JSONField(default=dict, editable=False)
    state = models.CharField(max_length=16, default="pending", editable=False)
    safe_error = models.CharField(max_length=64, blank=True, editable=False)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, editable=False)
    is_demo = models.BooleanField(default=False, editable=False)

    class Meta:
        verbose_name = _("Webhook receipt")
        verbose_name_plural = _("Webhook receipts")
        ordering = ["-received_at"]

    def state_display(self):
        return STATE_LABELS.get(self.state, self.state)

    def __str__(self):
        return f"Receipt {self.pk} · {self.state}"


class IntegrationJob(models.Model):
    class Kind(models.TextChoices):
        REGISTER = "register", _("Register reference")
        REFRESH = "refresh", _("Retrieve stored carrier details")
        RECEIPT = "receipt", _("Process webhook receipt")

    kind = models.CharField(max_length=16, choices=Kind, editable=False)
    dedupe_key = models.CharField(max_length=100, unique=True, editable=False)
    leg = models.ForeignKey("shipments.TrackingLeg", on_delete=models.PROTECT, null=True, editable=False)
    receipt = models.OneToOneField(WebhookReceipt, on_delete=models.PROTECT, null=True, editable=False)
    state = models.CharField(max_length=16, default="pending", editable=False, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0, editable=False)
    available_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    lease_until = models.DateTimeField(null=True, editable=False)
    lease_token = models.CharField(max_length=32, blank=True, editable=False)
    last_enqueued_at = models.DateTimeField(null=True, editable=False)
    safe_error = models.CharField(max_length=64, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    finished_at = models.DateTimeField(null=True, editable=False)

    class Meta:
        verbose_name = _("Integration job")
        verbose_name_plural = _("Integration jobs")
        ordering = ["-created_at"]
        permissions = [("register_reference", "Register carrier references"), ("refresh_reference", "Refresh carrier references"), ("retry_jobs", "Retry failed integration work")]
        indexes = [models.Index(fields=["state", "available_at"])]

    def state_display(self):
        return STATE_LABELS.get(self.state, self.state)

    def __str__(self):
        return f"Job {self.pk} · {self.kind} · {self.state}"
