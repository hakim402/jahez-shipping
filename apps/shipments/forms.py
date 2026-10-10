from django.utils.translation import gettext_lazy as _
from django import forms
from django.core.exceptions import ValidationError
from unfold.widgets import UnfoldAdminTextInputWidget, UnfoldAdminTextareaWidget
from .models import Customer, Shipment, ShipmentItem, TrackingLeg, Document, TrackingEvent, Status
from .services import validate_change
from .uploads import inspect_upload
from .form_help import apply_help


class HelpFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_help(self)


class ShipmentForm(HelpFormMixin, forms.ModelForm):
    revision_token = forms.IntegerField(widget=forms.HiddenInput, required=False)
    correction_reason = forms.CharField(required=False, widget=UnfoldAdminTextareaWidget, label=_("Correction / lock release reason"))
    confirm_complete_shipment = forms.BooleanField(required=False, label=_("I confirm every package / leg is delivered"))

    class Meta:
        model = Shipment
        fields = "__all__"

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["revision_token"].initial = self.instance.revision
        self.fields["reference_display"] = forms.CharField(required=False, disabled=True, initial=self.instance.reference, label="Private JAHEZ reference", widget=UnfoldAdminTextInputWidget)

    def clean(self):
        cleaned = super().clean()
        obj = self.instance
        for field, value in cleaned.items():
            if hasattr(obj, field) and field not in ("revision_token", "correction_reason", "reference_display"):
                setattr(obj, field, value)
        old = Shipment.objects.filter(pk=obj.pk).first() if obj.pk else None
        if old and cleaned.get("revision_token") != old.revision:
            raise ValidationError(_("This shipment changed in another session. Reload before saving."))
        if self.user:
            validate_change(obj, old, self.user, cleaned.get("correction_reason", ""))
        if old and old.status != Status.DELIVERED and obj.status == Status.DELIVERED and old.legs.count() > 1 and not cleaned.get("confirm_complete_shipment"):
            raise ValidationError(_("Confirm delivery of every package/leg before marking the entire shipment delivered."))
        return cleaned


class EventForm(HelpFormMixin, forms.ModelForm):
    class Meta:
        model = TrackingEvent
        fields = "__all__"

    def clean(self):
        data = super().clean()
        shipment = data.get("shipment") or getattr(self.instance, "shipment", None)
        if shipment and shipment.archived_at:
            raise ValidationError(_("Restore the shipment before editing its timeline."))
        return data


class DocumentUploadForm(forms.Form):
    shipment = forms.ModelChoiceField(queryset=Shipment.objects.filter(archived_at__isnull=True), label=_("Shipment"))
    category = forms.ChoiceField(choices=Document._meta.get_field("category").choices, label=_("Category"))
    upload = forms.FileField(label=_("Private PDF / PNG / JPEG (up to 5 MiB)"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_help(self)

    def clean_upload(self):
        upload = self.cleaned_data["upload"]
        self.inspection = inspect_upload(upload)
        return upload


class CustomerForm(HelpFormMixin, forms.ModelForm):
    class Meta:
        model = Customer
        fields = "__all__"


class ItemForm(HelpFormMixin, forms.ModelForm):
    class Meta:
        model = ShipmentItem
        fields = "__all__"


class LegForm(HelpFormMixin, forms.ModelForm):
    class Meta:
        model = TrackingLeg
        fields = "__all__"


class DeleteRecordForm(forms.Form):
    token = forms.CharField(widget=forms.HiddenInput)
    reason = forms.CharField(label=_("Reason for deletion"), max_length=1000,
        widget=UnfoldAdminTextareaWidget(attrs={"rows": 3}),
        help_text=_("Explain why the record is no longer needed. This reason stays in staff history."))
    confirm = forms.BooleanField(label=_("I understand that this deletion cannot be undone."))
