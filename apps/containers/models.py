"""Two shared-journey business models. Provider work belongs in the explicit refresh service."""
import hashlib
import json
import secrets
import uuid

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models, transaction
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _, get_language

from apps.integrations.sealegend import ADAPTER, WEBSITE, ERROR_CODES
from .values import Designation, Status, lookup_code, validate_evidence, validate_source_time, validate_public_snapshot

CODE_VALIDATOR = RegexValidator(r"\AJHZ-[A-Z2-7]{26}\Z", _("Use the generated JAHEZ lookup code."))
REFERENCE_VALIDATOR = RegexValidator(r"\A[A-Z0-9][A-Z0-9-]{5,39}\Z", _("Use a carrier search reference of 6 to 40 uppercase letters, digits or hyphens."))
NUMBER_VALIDATOR = RegexValidator(r"\A(?:[A-Z]{4}[0-9]{7})?\Z", _("Use four uppercase letters and seven digits, or leave the container unbound."))
HASH_VALIDATOR = RegexValidator(r"\A[0-9a-f]{64}\Z", _("Use a SHA-256 fingerprint."))
FAILURES = sorted(ERROR_CODES | {"ambiguous_container", "unknown_status", "invalid_extraction", "concurrent_change", "ai_unavailable"})


class Container(models.Model):
    journey_key = models.UUIDField(_("Journey key"), default=uuid.uuid4, editable=False,
        help_text=_("Internal journey grouping; use a new key for a later journey, even with the same container."))
    search_reference = models.CharField(_("B/L or search reference"), max_length=40, validators=[REFERENCE_VALIDATOR])
    container_number = models.CharField(_("Container number"), max_length=11, blank=True, default="", validators=[NUMBER_VALIDATOR],
        help_text=_("Leave empty until the carrier identifies one container or an administrator selects it."))
    source_adapter = models.CharField(_("Source adapter"), max_length=64, choices=[(ADAPTER, "Sea Legend")], default=ADAPTER)
    source_website = models.URLField(_("Source website"), max_length=200, default=WEBSITE, choices=[(WEBSITE, "Sea Legend")])
    equipment_type = models.CharField(_("Equipment type"), max_length=32, blank=True)
    equipment_quantity = models.PositiveSmallIntegerField(_("Equipment quantity"), null=True, blank=True, validators=[MinValueValidator(1)])
    origin_code = models.CharField(_("Origin code"), max_length=16, blank=True)
    destination_code = models.CharField(_("Destination code"), max_length=16, blank=True)
    origin_label_en = models.CharField(_("Origin label (English)"), max_length=200, blank=True)
    origin_label_ar = models.CharField(_("Origin label (Arabic)"), max_length=200, blank=True)
    destination_label_en = models.CharField(_("Destination label (English)"), max_length=200, blank=True)
    destination_label_ar = models.CharField(_("Destination label (Arabic)"), max_length=200, blank=True)
    vessel = models.CharField(_("Vessel"), max_length=200, blank=True)
    voyage = models.CharField(_("Voyage"), max_length=80, blank=True)
    raw_status = models.CharField(_("Raw carrier status"), max_length=256, blank=True)
    carrier_status = models.CharField(_("Carrier status"), max_length=20, choices=Status.choices, default=Status.UNKNOWN)
    departure_actual = models.JSONField(_("Actual departure"), null=True, blank=True, validators=[validate_source_time])
    departure_estimated = models.JSONField(_("Estimated departure"), null=True, blank=True, validators=[validate_source_time])
    arrival_actual = models.JSONField(_("Actual arrival"), null=True, blank=True, validators=[validate_source_time])
    arrival_estimated = models.JSONField(_("Estimated arrival"), null=True, blank=True, validators=[validate_source_time])
    manual_notes_en = models.TextField(_("Manual notes (English)"), max_length=2000, blank=True)
    manual_notes_ar = models.TextField(_("Manual notes (Arabic)"), max_length=2000, blank=True)
    manual_status_override = models.CharField(_("Manual status override"), max_length=20, choices=Status.choices, null=True, blank=True, default=None,
        help_text=_("Empty uses the carrier status. Manual notes remain independent of carrier updates."))
    is_published = models.BooleanField(_("Published"), default=False)
    auto_publish_carrier_updates = models.BooleanField(_("Automatically publish validated carrier updates"), default=False,
        help_text=_("Only updates an already published journey after validation. Manual notes and unreviewed translations stay private."))
    public_snapshot = models.JSONField(_("Reviewed public data"), default=dict, blank=True, editable=False, validators=[validate_public_snapshot])
    archived_at = models.DateTimeField(_("Archived at"), null=True, blank=True)
    lookup_code = models.CharField(_("JAHEZ lookup code"), max_length=30, default=lookup_code, unique=True, editable=False, validators=[CODE_VALIDATOR])
    last_refresh_attempt_at = models.DateTimeField(_("Last refresh attempt"), null=True, blank=True)
    last_refresh_success_at = models.DateTimeField(_("Last successful refresh"), null=True, blank=True)
    last_failure_code = models.CharField(_("Refresh failure code"), max_length=32, blank=True, choices=[(c, c) for c in FAILURES])
    source_fingerprint = models.CharField(_("Source fingerprint"), max_length=64, blank=True, validators=[HASH_VALIDATOR])
    source_evidence = models.JSONField(_("Accepted source evidence"), default=dict, blank=True, validators=[validate_evidence])
    revision = models.PositiveBigIntegerField(_("Revision"), default=0, editable=False)
    refresh_claim = models.UUIDField(_("Refresh claim"), null=True, blank=True, editable=False)
    refresh_claim_expires_at = models.DateTimeField(_("Refresh claim expiry"), null=True, blank=True, editable=False)
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated at"), auto_now=True)

    class Meta:
        verbose_name = _("Container")
        verbose_name_plural = _("Containers")
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(fields=["journey_key", "source_adapter", "search_reference", "container_number"], name="container_journey_identity"),
            models.CheckConstraint(condition=Q(equipment_quantity__isnull=True) | Q(equipment_quantity__gte=1), name="container_positive_quantity"),
            models.CheckConstraint(condition=(Q(refresh_claim__isnull=True, refresh_claim_expires_at__isnull=True) | Q(refresh_claim__isnull=False, refresh_claim_expires_at__isnull=False)), name="container_claim_pair"),
        ]

    def __str__(self):
        return self.lookup_code

    @property
    def display_status(self):
        return self.manual_status_override or self.carrier_status

    @property
    def needs_review(self):
        return self.carrier_status == Status.UNKNOWN

    def tracking_path(self, language="en"):
        # Reserved link only. The result route stays disabled until Phase 6.
        if language not in ("en", "ar"):
            raise ValueError("unsupported_language")
        return f"/{language}/track/{self.lookup_code}/"

    def clear_manual_status_override(self):
        self.manual_status_override = None
        self.save(update_fields=["manual_status_override"])

    def bind_container(self, available_numbers, *, selected_number=None):
        """Bind only a sole source identity or an explicit selection; never save implicitly."""
        if (not isinstance(available_numbers, (list, tuple)) or not available_numbers
                or len(available_numbers) > 100 or any(not isinstance(n, str) for n in available_numbers)):
            raise ValidationError(_("A valid list of carrier container identities is required."))
        numbers = set(available_numbers)
        for number in numbers:
            NUMBER_VALIDATOR(number)
            if not number:
                raise ValidationError(_("A valid list of carrier container identities is required."))
        if selected_number is not None and (not isinstance(selected_number, str) or selected_number not in numbers):
            raise ValidationError(_("Select a container present in the carrier result."))
        if self.container_number:
            if self.container_number not in numbers or (selected_number and selected_number != self.container_number):
                raise ValidationError(_("The carrier container does not match the bound journey."))
            return self.container_number
        if selected_number is None:
            if len(numbers) != 1:
                raise ValidationError(_("More than one container was found. An explicit selection is required."))
            selected_number = next(iter(numbers))
        self.container_number = selected_number
        return selected_number

    def clean(self):
        super().clean()
        if self.manual_status_override == "":
            self.manual_status_override = None
        errors = {}
        for field in ("departure_actual", "departure_estimated", "arrival_actual", "arrival_estimated"):
            value = getattr(self, field)
            if value is not None:
                validate_source_time(value)
                expected = "actual" if field.endswith("actual") else "estimated"
                if value["designation"] != expected:
                    errors[field] = _("The source time designation must match this field.")
        if self.source_evidence != {}:
            validate_evidence(self.source_evidence)
            if (self.source_evidence["adapter"] != self.source_adapter
                    or self.source_evidence["source_sha256"] != self.source_fingerprint):
                errors["source_evidence"] = _("Evidence must match the configured adapter and source fingerprint.")
        if self.pk and not self._state.adding:
            old = type(self).objects.get(pk=self.pk)
            if old.lookup_code != self.lookup_code or old.journey_key != self.journey_key:
                errors["lookup_code"] = _("Journey and lookup identities cannot be changed.")
            if old.container_number and any(getattr(old, f) != getattr(self, f) for f in ("container_number", "search_reference", "source_adapter", "source_website")):
                errors["container_number"] = _("Bound source identities cannot be reassigned. Register a separate journey.")
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Validate ordinary writes and version local edits for refresh claim/CAS checks.
        with transaction.atomic():
            self.full_clean()
            adding = self._state.adding
            if not adding:
                self.revision = F("revision") + 1
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {"revision", "updated_at"}
            super().save(*args, **kwargs)
            if not adding:
                self.refresh_from_db(fields=["revision"])


class EventManager(models.Manager):
    def record_carrier(self, *, container, **facts):
        """Idempotent carrier event write; publication and manual fields stay outside this boundary."""
        allowed = {"source_event_id", "source_leg", "location_code", "location", "raw_status", "raw_text",
                   "source_time", "designation", "title_en", "title_ar", "detail_en", "detail_ar"}
        if set(facts) - allowed:
            raise ValueError("unsupported_carrier_fields")
        candidate = self.model(container=container, origin="carrier", **facts)
        candidate.full_clean(validate_unique=False, validate_constraints=False)
        return self.update_or_create(container=container, origin="carrier", dedupe_key=candidate.dedupe_key, defaults=facts)


class ContainerEvent(models.Model):
    class Origin(models.TextChoices):
        CARRIER = "carrier", _("Carrier")
        MANUAL = "manual", _("Manual")

    container = models.ForeignKey(Container, verbose_name=_("Container"), on_delete=models.PROTECT, related_name="events")
    origin = models.CharField(_("Origin"), max_length=7, choices=Origin.choices, default=Origin.MANUAL)
    source_event_id = models.CharField(_("Source event ID"), max_length=128, blank=True)
    source_leg = models.CharField(_("Source leg"), max_length=128, blank=True,
        help_text=_("Stable source leg identity when a journey revisits a location; never a retrieval time."))
    location_code = models.CharField(_("Location code"), max_length=16, blank=True)
    location = models.CharField(_("Source location"), max_length=256, blank=True)
    raw_status = models.CharField(_("Raw source status"), max_length=256, blank=True)
    raw_text = models.TextField(_("Raw source text"), max_length=2000, blank=True)
    designation = models.CharField(_("Actual or estimated"), max_length=9, choices=Designation.choices, default=Designation.UNKNOWN)
    source_time = models.JSONField(_("Source time"), null=True, blank=True, validators=[validate_source_time])
    title_en = models.CharField(_("Title (English)"), max_length=200, blank=True)
    title_ar = models.CharField(_("Title (Arabic)"), max_length=200, blank=True)
    detail_en = models.TextField(_("Detail (English)"), max_length=2000, blank=True)
    detail_ar = models.TextField(_("Detail (Arabic)"), max_length=2000, blank=True)
    is_public = models.BooleanField(_("Public event"), default=False)
    dedupe_key = models.CharField(_("Deduplication key"), max_length=64, blank=True, editable=False, validators=[HASH_VALIDATOR])
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated at"), auto_now=True)

    objects = EventManager()

    class Meta:
        verbose_name = _("Container event")
        verbose_name_plural = _("Container events")
        ordering = ["created_at", "pk"]
        constraints = [models.UniqueConstraint(fields=["container", "origin", "dedupe_key"], name="container_event_identity")]

    def __str__(self):
        title = (self.title_ar or self.title_en) if get_language() == "ar" else (self.title_en or self.title_ar)
        return title or str(self.get_origin_display())

    def compute_dedupe_key(self):
        if self.origin == self.Origin.MANUAL:
            return self.dedupe_key or secrets.token_hex(32)
        if self.source_event_id:
            identity = ["id", self.source_event_id, self.designation]
        else:
            if not self.raw_status or not self.location_code:
                raise ValidationError(_("Carrier events require a source ID or stable status and location codes."))
            identity = ["facts", self.raw_status, self.location_code, self.source_leg, self.designation]
            if self.designation == Designation.ACTUAL:
                if self.source_time is None:
                    raise ValidationError(_("An actual carrier event without a source ID requires a source time."))
                identity += [self.source_time, self.raw_text]
            # An estimate is the milestone slot: its changing date/text is not a new identity.
        canonical = [self.origin, self.container.source_adapter, identity]
        return hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def clean(self):
        super().clean()
        if self.source_time is not None:
            validate_source_time(self.source_time)
            if self.source_time["designation"] != self.designation:
                raise ValidationError({"source_time": _("The source time designation must match this field.")})
        if self.container_id:
            self.dedupe_key = self.compute_dedupe_key()
        if self.pk and not self._state.adding:
            old = type(self).objects.get(pk=self.pk)
            if (old.container_id, old.origin, old.dedupe_key) != (self.container_id, self.origin, self.dedupe_key):
                raise ValidationError(_("Event origin, container and milestone identity cannot be changed."))

    def save(self, *args, **kwargs):
        self.full_clean()
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"dedupe_key", "updated_at"}
        super().save(*args, **kwargs)
