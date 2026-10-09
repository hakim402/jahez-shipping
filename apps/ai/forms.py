from django import forms
from django.utils.translation import gettext_lazy as _
from apps.shipments.models import Shipment, Document, TrackingEvent
from .models import AIDraft


class SourceSelectionForm(forms.Form):
    shipment = forms.ModelChoiceField(label=_('Shipment'), queryset=Shipment.objects.filter(archived_at__isnull=True))
    kind = forms.ChoiceField(label=_('Task'), choices=AIDraft.Kind.choices)


class DocumentChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.get_category_display()} · {obj.original_filename}"


class RequestForm(forms.Form):
    shipment = forms.ModelChoiceField(label=_('Shipment'), queryset=Shipment.objects.filter(archived_at__isnull=True))
    kind = forms.ChoiceField(label=_('Task'), choices=AIDraft.Kind.choices)
    document = DocumentChoiceField(label=_('Private document for extraction'), queryset=Document.objects.none(), required=False)
    event = forms.ModelChoiceField(label=_('Carrier event to translate (optional)'), queryset=TrackingEvent.objects.none(), required=False)
    consent = forms.BooleanField(label=_('I authorize sending the selected document or minimal shipment history to Groq for this task.'))

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        candidate = self.data.get('shipment') or self.initial.get('shipment')
        if str(candidate).isdigit():
            if user.has_perm('shipments.download_document') and user.has_perm('shipments.view_document'):
                self.fields['document'].queryset = Document.objects.filter(shipment_id=candidate, shipment__archived_at__isnull=True)
            if user.has_perm('shipments.view_trackingevent'):
                self.fields['event'].queryset = TrackingEvent.objects.filter(shipment_id=candidate, source='carrier', shipment__archived_at__isnull=True)


class ReviewForm(forms.Form):
    decision = forms.ChoiceField(label=_('Review decision'), choices=[('accept', _('Approve selected changes / private text')), ('reject', _('Reject draft'))])
    confirm = forms.BooleanField(label=_('I checked the cited sources and reviewed these changes.'))

    def __init__(self, *args, **kwargs):
        self.draft = kwargs.pop('draft')
        super().__init__(*args, **kwargs)
        result = self.draft.output
        if self.draft.kind == 'extraction':
            for i, proposal in enumerate(result.get('fields', [])):
                self.fields[f'field_select_{i}'] = forms.BooleanField(label=_('Apply field: ') + str({'internal_order':_('Internal order reference'),'bill_number':_('Private bill number'),'origin_en':_('Approved origin (English)'),'origin_ar':_('Approved origin (Arabic)'),'destination_en':_('Approved destination (English)'),'destination_ar':_('Approved destination (Arabic)')}[proposal['field']]), required=False)
                self.fields[f'field_value_{i}'] = forms.CharField(label=_('Reviewed value'), max_length=100 if proposal['field'] in ('internal_order', 'bill_number') else 120, initial=proposal['value'], required=False)
            for i, item in enumerate(result.get('items', [])):
                self.fields[f'item_select_{i}'] = forms.BooleanField(label=_('Add private item: ') + item['description_source'], required=False)
                for key in ('description_en', 'description_ar', 'quantity', 'unit', 'unit_ar'):
                    self.fields[f'item_{i}_{key}'] = forms.CharField(label={'description_en': _('Product (English)'), 'description_ar': _('Product (Arabic)'), 'quantity': _('Quantity'), 'unit': _('Unit (English)'), 'unit_ar': _('Unit (Arabic)')}[key], max_length={'description_en':200,'description_ar':200,'quantity':16,'unit':32,'unit_ar':32}[key], initial=item[key], required=False)
        else:
            for i, statement in enumerate(result.get('statements', [])):
                self.fields[f'en_{i}'] = forms.CharField(label=_('Reviewed English statement'), max_length=2000, widget=forms.Textarea(attrs={'rows':3}), initial=statement['english'])
                self.fields[f'ar_{i}'] = forms.CharField(label=_('Reviewed Arabic statement'), max_length=2000, widget=forms.Textarea(attrs={'rows':3,'dir':'rtl'}), initial=statement['arabic'])

    def reviewed_output(self):
        import copy
        result = copy.deepcopy(self.draft.output)
        fields, items = [], []
        if self.draft.kind == 'extraction':
            for i, proposal in enumerate(result['fields']):
                if self.cleaned_data[f'field_select_{i}']:
                    fields.append(proposal['field'])
                    proposal['value'] = self.cleaned_data[f'field_value_{i}']
            for i, item in enumerate(result['items']):
                if self.cleaned_data[f'item_select_{i}']:
                    items.append(i)
                    for key in ('description_en','description_ar','quantity','unit','unit_ar'):
                        item[key] = self.cleaned_data[f'item_{i}_{key}']
        else:
            for i, statement in enumerate(result['statements']):
                statement['english'] = self.cleaned_data[f'en_{i}']
                statement['arabic'] = self.cleaned_data[f'ar_{i}']
        return result, fields, items
