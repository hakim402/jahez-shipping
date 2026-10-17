"""Human-entered admin updates, without provider or model-generated instructions."""
import copy
import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Container, ContainerEvent
from .values import validate_source_time


class SourceTimeWidget(forms.MultiWidget):
    template_name = "containers/widgets/source_time.html"

    def __init__(self, attrs=None):
        super().__init__([
            forms.TextInput(attrs={"dir": "ltr", "class": "jahez-control", "placeholder": "YYYY-MM-DD HH:MM"}),
            forms.TextInput(attrs={"dir": "ltr", "class": "jahez-control", "placeholder": "UTC / Asia/Kabul / +04:30"}),
        ], attrs)

    def decompress(self, value):
        if isinstance(value, dict):
            return [value.get("raw", ""), value.get("source_timezone") or ""]
        return ["", ""]

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        for widget, label in zip(context["widget"]["subwidgets"], (_("Date/time as written"), _("Timezone, only if supplied"))):
            widget["label"] = label
        return context


class SourceTimeField(forms.MultiValueField):
    def __init__(self, *, designation, original=None, **kwargs):
        self.designation = designation
        self.original = original
        super().__init__(fields=[forms.CharField(required=False, max_length=32, strip=False),
                                forms.CharField(required=False, max_length=64)],
                         widget=SourceTimeWidget(), require_all_fields=False, required=False, **kwargs)

    def compress(self, values):
        if not values or not any(values):
            return None
        raw, zone = values
        zone = zone or None
        if self.original and (self.original.get("raw"), self.original.get("source_timezone"), self.original.get("designation")) == (raw, zone, self.designation):
            return copy.deepcopy(self.original)
        precision = next((p for pattern, p in ((r"\d{4}-\d{2}-\d{2}", "date"),
            (r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", "minute"),
            (r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", "second")) if re.fullmatch(pattern, raw)), None)
        result = {"raw": raw, "precision": precision, "designation": self.designation,
                  "source_timezone": zone, "normalized_instant": None}
        validate_source_time(result)
        return result


class ContainerForm(forms.ModelForm):
    expected_revision = forms.IntegerField(widget=forms.HiddenInput, required=False)
    confirm_identity = forms.BooleanField(label=_("Confirm the B/L and selected container"), required=False,
        help_text=_("Check the carrier result before binding. A bound container cannot be reassigned."))
    confirm_publication = forms.BooleanField(label=_("Confirm publication changes"), required=False,
        help_text=_("Check after reviewing to publish current facts and public events. Leave unchecked to save private edits. Required to enable automatic carrier publication."))
    is_archived = forms.BooleanField(label=_("Archived"), required=False,
        help_text=_("Keep completed journeys for reference. Archiving removes customer access when tracking is available."))

    class Meta:
        model = Container
        fields = ["search_reference", "container_number", "equipment_type", "equipment_quantity", "origin_code", "destination_code",
                  "origin_label_en", "origin_label_ar", "destination_label_en", "destination_label_ar", "vessel", "voyage",
                  "manual_status_override", "manual_notes_en", "manual_notes_ar", "is_published", "auto_publish_carrier_updates",
                  "departure_actual", "departure_estimated", "arrival_actual", "arrival_estimated"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original = Container.objects.get(pk=self.instance.pk) if self.instance.pk else None
        self.initial["is_archived"] = bool(self.instance.archived_at)
        self.initial["expected_revision"] = self.instance.revision if self.instance.pk else 0
        if "manual_status_override" in self.fields:
            field = self.fields["manual_status_override"]
            field.choices = [("", _("Use carrier status (clear override)"))] + [(value, label) for value, label in field.choices if value]
        for name in ("departure_actual", "departure_estimated", "arrival_actual", "arrival_estimated"):
            if name in self.fields:
                self.fields[name] = SourceTimeField(designation="actual" if name.endswith("actual") else "estimated",
                    original=getattr(self.instance, name), label=Container._meta.get_field(name).verbose_name,
                    help_text=_("Copy only a verified source date. Leave timezone empty when the carrier does not supply one."))
        for name, field in self.fields.items():
            if name in {"search_reference", "container_number", "equipment_type", "origin_code", "destination_code", "vessel", "voyage"} or name.endswith("_en"):
                field.widget.attrs["dir"] = "ltr"
            elif name.endswith("_ar"):
                field.widget.attrs["dir"] = "rtl"
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs["rows"] = 3

    def clean(self):
        data = super().clean()
        old = self.original
        if old and data.get("expected_revision") != old.revision:
            raise ValidationError(_("This journey changed while the form was open. Reload it before saving."))
        identity_changed = bool(data.get("container_number")) if not old else any(
            name in data and data[name] != getattr(old, name) for name in ("search_reference", "container_number"))
        if identity_changed and not data.get("confirm_identity"):
            self.add_error("confirm_identity", _("Confirm the source identity before saving this change."))
        publishing = data.get("is_published") and (not old or not old.is_published or (old.archived_at and not data.get("is_archived")))
        if publishing and not data.get("confirm_publication"):
            self.add_error("confirm_publication", _("Confirm publication before saving this change."))
        if data.get("auto_publish_carrier_updates") and (not old or not old.auto_publish_carrier_updates) and not data.get("confirm_publication"):
            self.add_error("confirm_publication", _("Confirm publication before saving this change."))
        return data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.archived_at = (instance.archived_at or timezone.now()) if self.cleaned_data.get("is_archived") else None
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class ManualEventForm(forms.ModelForm):
    class Meta:
        model = ContainerEvent
        fields = ["title_en", "title_ar", "detail_en", "detail_ar", "location", "designation", "source_time", "is_public"]

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)
        self.was_public = self.instance.is_public if self.instance.pk else False
        for name in ("title_en", "title_ar"):
            self.fields[name].required = True
        designation = self.data.get(self.add_prefix("designation"), self.instance.designation) if self.is_bound else self.instance.designation
        self.fields["source_time"] = SourceTimeField(designation=designation, original=self.instance.source_time,
            label=_("Source time"), help_text=_("Leave empty for an undated manual update. Dates have no assumed timezone."))
        for name, field in self.fields.items():
            if name.endswith("_ar"):
                field.widget.attrs["dir"] = "rtl"
            elif name.endswith("_en"):
                field.widget.attrs["dir"] = "ltr"
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs["rows"] = 2

    def clean(self):
        data = super().clean()
        self.instance.origin = ContainerEvent.Origin.MANUAL
        if data.get("is_public") and not self.was_public and not (self.request and self.request.POST.get("confirm_publication") in ("on", "true", "1")):
            self.add_error("is_public", _("Use Confirm publication changes above to publish this manual event."))
        if data.get("is_public") and bool(data.get("detail_en")) != bool(data.get("detail_ar")):
            raise ValidationError(_("Provide both English and Arabic details before publishing an event."))
        return data


class ManualEventFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        for form in self.forms:
            identity = form.cleaned_data.get("id")
            if identity and (identity.origin != "manual" or identity.container_id != self.instance.pk):
                raise ValidationError(_("Only this journey's manual events can be edited here."))
