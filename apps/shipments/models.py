import secrets
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def public_reference():
    # 160 random bits. No customer, bill, order or database ID encoded.
    return "JHZ-" + secrets.token_hex(20).upper()


class Status(models.TextChoices):
    CREATED = "created", _("Created")
    WAREHOUSE = "warehouse", _("Received at China warehouse")
    PREPARING = "preparing", _("Preparing shipment")
    DEPARTED = "departed", _("Departed")
    TRANSIT = "in_transit", _("In transit")
    CUSTOMS = "customs", _("Customs clearance")
    ARRIVED = "arrived", _("Arrived at destination")
    OUT = "out_for_delivery", _("Out for delivery")
    DELIVERED = "delivered", _("Delivered")
    HOLD = "on_hold", _("On hold / exception")
    RETURNED = "returned", _("Returned")
    CANCELLED = "cancelled", _("Cancelled")


class Customer(models.Model):
    name = models.CharField(_("Private name"), max_length=160)
    company = models.CharField(_("Company"), max_length=160, blank=True)
    email = models.EmailField(_("Email"), blank=True)
    phone = models.CharField(_("Phone"), max_length=40, blank=True)
    address = models.TextField(_("Private address"), blank=True)
    notes = models.TextField(_("Internal notes"), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Customer")
        verbose_name_plural = _("Customers")
        ordering = ["name"]

    def __str__(self):
        return self.company or self.name


class Shipment(models.Model):
    class Mode(models.TextChoices):
        SEA = "sea", _("Sea freight")
        AIR = "air", _("Air freight")
        ROAD = "road", _("Road freight")
        MULTI = "multimodal", _("Multimodal freight")

    class TrackingMode(models.TextChoices):
        MANUAL = "manual", _("Manual")
        API = "api", _("Carrier tracking")
        HYBRID = "hybrid", _("Manual and carrier tracking")

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, verbose_name=_("Customer"))
    reference = models.CharField(_("Private customer reference"), max_length=44, unique=True, default=public_reference, editable=False)
    internal_order = models.CharField(_("Internal order reference"), max_length=100, blank=True, db_index=True)
    bill_number = models.CharField(_("Private bill number"), max_length=100, blank=True, db_index=True)
    mode = models.CharField(_("Transport mode"), max_length=20, choices=Mode, default=Mode.SEA)
    tracking_mode = models.CharField(_("Tracking mode"), max_length=12, choices=TrackingMode, default=TrackingMode.MANUAL)
    origin_en = models.CharField(_("Approved origin (English)"), max_length=120, blank=True)
    origin_ar = models.CharField(_("Approved origin (Arabic)"), max_length=120, blank=True)
    destination_en = models.CharField(_("Approved destination (English)"), max_length=120, blank=True)
    destination_ar = models.CharField(_("Approved destination (Arabic)"), max_length=120, blank=True)
    status = models.CharField(_("Status"), max_length=24, choices=Status, default=Status.CREATED, db_index=True)
    status_observed_at = models.DateTimeField(null=True, blank=True, editable=False)
    carrier_coverage_complete = models.BooleanField(_("All packages are covered by these carrier references"), default=False)
    eta = models.DateTimeField(_("Confirmed arrival estimate"), null=True, blank=True)
    actual_arrival = models.DateTimeField(_("Actual arrival"), null=True, blank=True)
    delivered_at = models.DateTimeField(_("Actual delivery"), null=True, blank=True)
    confirmed_delay = models.BooleanField(_("Confirmed delay"), default=False)
    delay_reason = models.TextField(_("Private delay reason"), blank=True)
    status_locked = models.BooleanField(_("Lock customer-facing status"), default=False)
    override_reason = models.TextField(_("Private override reason"), blank=True)
    published = models.BooleanField(_("Publish safe tracking summary"), default=False, db_index=True)
    archived_at = models.DateTimeField(_("Archived at"), null=True, blank=True, editable=False, db_index=True)
    is_demo = models.BooleanField(default=False, editable=False)
    internal_notes = models.TextField(_("Internal notes"), blank=True)
    revision = models.PositiveIntegerField(default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Shipment")
        verbose_name_plural = _("Shipments")
        ordering = ["-created_at"]
        permissions = [
            ("publish_shipment", "Publish tracking summaries"),
            ("correct_status", "Correct protected shipment status"),
            ("archive_shipment", "Archive or restore shipments"),
            ("rotate_reference", "Revoke and replace customer references"),
        ]

    def clean(self):
        errors = {}
        if self.confirmed_delay and not self.delay_reason.strip():
            errors["delay_reason"] = _("A confirmed delay requires a reason.")
        if self.status_locked and not self.override_reason.strip():
            errors["override_reason"] = _("A status lock requires a reason.")
        if self.published and not all([self.origin_en.strip(), self.origin_ar.strip(), self.destination_en.strip(), self.destination_ar.strip()]):
            errors["published"] = _("Provide approved bilingual country/region route labels before publication.")
        for field in ("eta", "actual_arrival", "delivered_at"):
            value = getattr(self, field)
            if value and timezone.is_naive(value):
                errors[field] = _("Use a timezone-aware timestamp.")
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"S{self.pk or 'NEW'} · {self.internal_order or self.get_status_display()}"


class ShipmentItem(models.Model):
    shipment = models.ForeignKey(Shipment, on_delete=models.PROTECT, related_name="items", verbose_name=_("Shipment"))
    description_en = models.CharField(_("Product (English)"), max_length=200)
    description_ar = models.CharField(_("Product (Arabic)"), max_length=200, blank=True)
    quantity = models.DecimalField(_("Quantity"), max_digits=12, decimal_places=3, validators=[MinValueValidator(Decimal("0.001"))])
    unit = models.CharField(_("Unit (English)"), max_length=32, default="units")
    unit_ar = models.CharField(_("Unit (Arabic)"), max_length=32, blank=True)
    sku = models.CharField(_("Private SKU"), max_length=80, blank=True)
    cartons = models.PositiveIntegerField(_("Cartons"), null=True, blank=True)
    weight_kg = models.DecimalField(_("Weight (kg)"), max_digits=12, decimal_places=3, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))])
    volume_cbm = models.DecimalField(_("Volume (m³)"), max_digits=12, decimal_places=3, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))])
    public = models.BooleanField(_("Approve for public summary"), default=False)

    class Meta:
        verbose_name = _("Shipment item")
        verbose_name_plural = _("Shipment items")
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0), name="item_positive_quantity")]

    def clean(self):
        if self.public and not (self.description_ar.strip() and self.unit_ar.strip()):
            raise ValidationError(_("Public items require bilingual product and unit labels."))

    def __str__(self):
        return self.description_en


class TrackingLeg(models.Model):
    shipment = models.ForeignKey(Shipment, on_delete=models.PROTECT, related_name="legs", verbose_name=_("Shipment"))
    sequence = models.PositiveSmallIntegerField(_("Sequence"), default=1)
    label = models.CharField(_("Private leg label"), max_length=100, blank=True)
    carrier_identifier = models.CharField(_("Carrier identifier"), max_length=80, blank=True)
    tracking_number = models.CharField(_("Private carrier tracking number"), max_length=100)
    registration_state = models.CharField(max_length=24, default="not_connected", editable=False)
    last_success = models.DateTimeField(null=True, blank=True, editable=False)
    last_error = models.CharField(max_length=240, blank=True, editable=False)
    provider_status = models.CharField(max_length=80, blank=True, editable=False)

    last_received_at = models.DateTimeField(null=True, editable=False)
    last_provider_event_at = models.DateTimeField(null=True, editable=False)
    mapped_status = models.CharField(max_length=24, choices=Status, blank=True, editable=False)
    next_reconcile_at = models.DateTimeField(null=True, editable=False)

    class Meta:
        verbose_name = _("Tracking reference")
        verbose_name_plural = _("Tracking references")
        ordering = ["sequence", "pk"]
        constraints = [models.UniqueConstraint(fields=["shipment", "sequence"], name="unique_shipment_leg_sequence"), models.UniqueConstraint(fields=["carrier_identifier", "tracking_number"], condition=~models.Q(carrier_identifier="") & ~models.Q(tracking_number=""), name="unique_carrier_tracking_reference")]

    def clean(self):
        if self.carrier_identifier.isascii() and self.carrier_identifier.isdigit():
            value = int(self.carrier_identifier)
            if not 0 < value < 100000000:
                raise ValidationError({"carrier_identifier": _("Use a positive numeric carrier code from the provider directory.")})
            self.carrier_identifier = str(value)

    def __str__(self):
        return f"Leg {self.sequence} · {self.label}"


class TrackingEvent(models.Model):
    shipment = models.ForeignKey(Shipment, on_delete=models.PROTECT, related_name="events", verbose_name=_("Shipment"))
    leg = models.ForeignKey(TrackingLeg, on_delete=models.PROTECT, null=True, blank=True, verbose_name=_("Tracking reference"))
    occurred_at = models.DateTimeField(_("Occurrence time"), default=timezone.now, null=True, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    location = models.CharField(_("Private location"), max_length=160, blank=True)
    raw_text = models.TextField(_("Private source text"), blank=True)
    title_en = models.CharField(_("Approved title (English)"), max_length=160)
    title_ar = models.CharField(_("Approved title (Arabic)"), max_length=160, blank=True)
    body_en = models.TextField(_("Approved detail (English)"), blank=True)
    body_ar = models.TextField(_("Approved detail (Arabic)"), blank=True)
    source = models.CharField(max_length=12, choices=[("manual", _("JAHEZ manual update")), ("carrier", _("Carrier-provided update"))], default="manual", editable=False)
    mapped_status = models.CharField(_("Milestone status"), max_length=24, choices=Status, default=Status.CREATED, blank=True)
    public = models.BooleanField(_("Publish this event"), default=False)
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, editable=False)
    provider_identity = models.CharField(max_length=80, blank=True, editable=False)
    provider_event_key = models.CharField(max_length=64, null=True, unique=True, editable=False)
    provider_time_raw = models.JSONField(default=dict, editable=False)

    class Meta:
        verbose_name = _("Tracking event")
        verbose_name_plural = _("Tracking events")
        ordering = ["occurred_at", "pk"]
        indexes = [models.Index(fields=["shipment", "public", "occurred_at"])]

    def clean(self):
        if self.leg_id and self.leg.shipment_id != self.shipment_id:
            raise ValidationError({"leg": _("The tracking reference must belong to this shipment.")})
        if self.public and not (self.title_ar.strip() and bool(self.body_en.strip()) == bool(self.body_ar.strip())):
            raise ValidationError(_("Published events require bilingual titles and matching detail translations."))
        if (self.source == "manual" and self.occurred_at is None) or (self.occurred_at and (timezone.is_naive(self.occurred_at) or self.occurred_at > timezone.now() + timezone.timedelta(minutes=5))):
            raise ValidationError({"occurred_at": _("Use an aware occurrence time, not a future milestone.")})

    def __str__(self):
        return self.title_en


class Document(models.Model):
    shipment = models.ForeignKey(Shipment, on_delete=models.PROTECT, related_name="documents", verbose_name=_("Shipment"))
    category = models.CharField(_("Category"), max_length=24, choices=[("bill", _("Shipping bill")), ("invoice", _("Invoice")), ("packing", _("Packing list")), ("other", _("Other"))], default="bill")
    file = models.FileField(upload_to="documents/%Y/%m", editable=False)
    original_filename = models.CharField(max_length=180, editable=False)
    checksum = models.CharField(max_length=64, editable=False)
    mime_type = models.CharField(max_length=40, editable=False)
    size = models.PositiveIntegerField(editable=False)
    page_count = models.PositiveSmallIntegerField(default=1, editable=False)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, editable=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Private document")
        verbose_name_plural = _("Private documents")
        permissions = [("download_document", "Download private shipment documents")]

    def __str__(self):
        return f"{self.get_category_display()} · S{self.shipment_id}"


class AuditEntry(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, editable=False)
    identity = models.CharField(max_length=80, default="staff", editable=False)
    shipment = models.ForeignKey(Shipment, on_delete=models.SET_NULL, null=True, related_name="audit_entries", editable=False)
    object_type = models.CharField(max_length=40, editable=False)
    object_id = models.CharField(max_length=40, editable=False)
    action = models.CharField(max_length=80, editable=False)
    changes = models.JSONField(default=dict, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Audit entry")
        verbose_name_plural = _("Audit entries")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} · {self.object_type} {self.object_id}"


class FileRemoval(models.Model):
    """Private cleanup outbox; survives a storage failure after record deletion."""
    storage_name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()


from apps.core.model_labels import localize_generated_labels
localize_generated_labels([Customer,Shipment,ShipmentItem,TrackingLeg,TrackingEvent,Document,AuditEntry])
