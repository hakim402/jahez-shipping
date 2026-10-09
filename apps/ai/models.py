from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class AIDraft(models.Model):
    class Kind(models.TextChoices):
        EXTRACTION = 'extraction', _('Document extraction')
        SUMMARY = 'summary', _('Shipment summary')
        MESSAGE = 'message', _('Customer message / carrier translation')

    class State(models.TextChoices):
        PENDING = 'pending', _('Pending')
        RUNNING = 'running', _('Running')
        RETRY = 'retry', _('Retry scheduled')
        FAILED = 'failed', _('Failed')
        READY = 'ready', _('Awaiting review')
        APPLIED = 'applied', _('Applied privately')
        ACCEPTED = 'accepted', _('Approved private text')
        REJECTED = 'rejected', _('Rejected')
        EXPIRED = 'expired', _('Expired')

    shipment = models.ForeignKey('shipments.Shipment', on_delete=models.PROTECT, related_name='ai_drafts')
    document = models.ForeignKey('shipments.Document', null=True, on_delete=models.PROTECT)
    event = models.ForeignKey('shipments.TrackingEvent', null=True, on_delete=models.PROTECT)
    kind = models.CharField(max_length=16, choices=Kind)
    state = models.CharField(max_length=16, choices=State, default=State.PENDING, db_index=True)
    dedupe_key = models.CharField(max_length=64, unique=True, editable=False)
    # Private data: never served by public tracking or serialized into ordinary logs.
    source = models.JSONField(default=dict, editable=False)
    output = models.JSONField(default=dict, editable=False)
    source_version = models.CharField(max_length=64, editable=False)
    model = models.CharField(max_length=120, blank=True, editable=False)
    attempts = models.PositiveSmallIntegerField(default=0, editable=False)
    available_at = models.DateTimeField(default=timezone.now, editable=False)
    lease_until = models.DateTimeField(null=True, editable=False)
    lease_token = models.CharField(max_length=32, blank=True, editable=False)
    last_enqueued_at = models.DateTimeField(null=True, editable=False)
    safe_error = models.CharField(max_length=40, blank=True, editable=False)
    latency_ms = models.PositiveIntegerField(null=True, editable=False)
    usage = models.JSONField(default=dict, editable=False)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    reviewed_at = models.DateTimeField(null=True, editable=False)
    accepted_changes = models.JSONField(default=dict, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(editable=False)
    is_demo = models.BooleanField(default=False, editable=False)

    class Meta:
        verbose_name = _('AI draft')
        verbose_name_plural = _('AI drafts')
        ordering = ['-created_at']
        indexes = [models.Index(fields=['state', 'available_at'])]
        permissions = [('request_ai', 'Request external AI processing'), ('review_ai', 'Review private AI drafts'), ('apply_extraction', 'Apply reviewed document fields'), ('retry_ai', 'Retry failed AI work')]

    def __str__(self):
        return f'AI {self.pk} · S{self.shipment_id} · {self.get_kind_display()}'


class AssistantRun(models.Model):
    """Private explanation outbox; no mutation payload or document/customer relation."""
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    scope = models.JSONField(default=dict, editable=False)
    result = models.JSONField(default=dict, editable=False)
    source_version = models.CharField(max_length=64, editable=False)
    output = models.JSONField(default=dict, editable=False)
    state = models.CharField(max_length=16, default='pending', choices=[
        ('pending', _('Pending')), ('running', _('Running')), ('retry', _('Retry scheduled')),
        ('ready', _('Explanation ready')), ('failed', _('Failed')), ('expired', _('Expired'))], db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0, editable=False)
    available_at = models.DateTimeField(default=timezone.now, editable=False)
    lease_until = models.DateTimeField(null=True, editable=False)
    lease_token = models.CharField(max_length=32, blank=True, editable=False)
    last_enqueued_at = models.DateTimeField(null=True, editable=False)
    safe_error = models.CharField(max_length=40, blank=True, editable=False)
    model = models.CharField(max_length=120, blank=True, editable=False)
    latency_ms = models.PositiveIntegerField(null=True, editable=False)
    usage = models.JSONField(default=dict, editable=False)
    dedupe_key = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(editable=False)

    class Meta:
        default_permissions = ('view',)
        permissions = [('query_shipments', 'Run read-only operational queries'),
                       ('check_quality', 'Run read-only data quality checks')]
        ordering = ['-created_at']
        indexes = [models.Index(fields=['state', 'available_at'])]

    def __str__(self):
        return f'Assistant {self.pk}'
