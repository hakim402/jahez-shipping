from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from apps.shipments.models import Status
from .forms import RequestForm, ReviewForm, SourceSelectionForm
from .models import AIDraft
from .provider import configuration
from . import services

ERRORS = {
    'image_limit': _('Too many scanned images for this model. Split the document into at most three images per request.'),
    'disabled': _('Groq is disabled.'), 'missing_key': _('Groq private key is missing.'), 'missing_model': _('The required text or vision model is missing.'), 'invalid_mode': _('Invalid output mode'),
    'document_changed': _('Document integrity changed. Review its private file.'), 'document_invalid': _('Document conversion failed. AI accepts plain documents up to five pages within its resource limits.'),
    'document_limit': _('Document exceeds AI processing limits.'), 'source_limit': _('Source exceeds AI processing limits.'),
    'source_changed': _('Source changed. Request a new draft.'), 'permission_revoked': _('Staff permission is no longer available.'),
    'invalid_output': _('Model returned invalid data or unsupported source citations.'), 'incomplete_output': _('Model did not return a complete draft.'),
    'provider_unavailable': _('Groq is temporarily unavailable.'), 'provider_rate_limit': _('Groq account rate limit reached.'),
    'provider_configuration': _('Check the private Groq key, model access and output mode.'), 'provider_failure': _('Groq request failed safely.'),
    'response_limit': _('Groq response exceeded safe limits.'), 'local_rate_limit': _('Waiting for the local AI rate limit.'),
    'rate_control_unavailable': _('Shared AI rate control is unavailable.'), 'worker_interrupted': _('Interrupted worker; durable recovery handles eligible work.'),
    'demo_outbound_blocked': _('Synthetic DEMO records are never sent to Groq.'), 'processing_failed': _('AI processing failed safely. Review before retrying.'),
}


def visible(queryset, user):
    if not user.has_perm('shipments.view_shipment'):
        return queryset.none()
    if not all(user.has_perm('shipments.'+p) for p in ('view_document','download_document')):
        queryset = queryset.filter(document__isnull=True)
    if not user.has_perm('shipments.view_trackingevent'):
        queryset = queryset.filter(kind='extraction')
    if not all(user.has_perm('shipments.'+p) for p in ('view_shipmentitem','view_trackingleg')):
        queryset = queryset.exclude(document__isnull=True, event__isnull=True)
    return queryset


@admin.register(AIDraft)
class DraftAdmin(ModelAdmin):
    actions = None
    list_per_page = 25
    list_display = ('id', 'shipment', 'kind', 'state', 'model', 'attempts', 'created_at', 'reviewed_at')
    list_filter = ('kind', 'state', 'is_demo')
    search_fields = ('shipment__internal_order',)

    def get_queryset(self, request):
        return visible(super().get_queryset(request).select_related('shipment'), request.user)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def change_view(self, request, object_id, form_url='', extra_context=None):
        if request.method != 'GET':
            raise PermissionDenied
        return HttpResponseRedirect(reverse('admin:ai_review', args=[object_id]))

    def get_urls(self):
        from . import operational_views
        return [path('workspace/', self.admin_site.admin_view(self.workspace), name='ai_workspace'),
            path('assistant/', self.admin_site.admin_view(operational_views.workspace), name='ai_assistant'),
            path('assistant/<int:pk>/', self.admin_site.admin_view(operational_views.detail), name='ai_assistant_result'),
            path('request/', self.admin_site.admin_view(self.request_draft), name='ai_request'),
            path('<int:pk>/review/', self.admin_site.admin_view(self.review), name='ai_review'),
            path('<int:pk>/retry/', self.admin_site.admin_view(self.retry), name='ai_retry')] + super().get_urls()

    def context(self, request, title, **kwargs):
        return {**self.admin_site.each_context(request), 'title': title, **kwargs}

    def response(self, request, template, context):
        response = TemplateResponse(request, template, context)
        response['Cache-Control'] = 'no-store, private'
        response['X-Robots-Tag'] = 'noindex, nofollow'
        return response

    def workspace(self, request):
        services.require(request.user, 'view_aidraft')
        rows = self.get_queryset(request)
        counts = [(label, rows.filter(state=state).count()) for state, label in [('pending', _('Pending')), ('running', _('Running')), ('ready', _('Awaiting review')), ('failed', _('Failed'))]]
        return self.response(request, 'admin/ai/workspace.html', self.context(request, _('AI Workspace'),
            rows=rows[:20], counts=counts, configuration={'ready': _('Configured — live verification pending'), 'disabled': _('Disabled'), 'missing_key': _('Missing key'), 'missing_model': _('Missing model'), 'invalid_mode': _('Invalid output mode')}[configuration()], vision_configuration={'ready': _('Configured — live verification pending'), 'disabled': _('Disabled'), 'missing_key': _('Missing key'), 'missing_model': _('Missing model'), 'invalid_mode': _('Invalid output mode')}[configuration(True)],
            can_request=request.user.has_perm('ai.request_ai')))

    def request_draft(self, request):
        services.require(request.user, 'request_ai')
        services.require(request.user, 'view_aidraft')
        initial = {'shipment': request.GET.get('shipment'), 'kind': request.GET.get('kind', 'summary'), 'document': request.GET.get('document')}
        form = RequestForm(request.POST or None, user=request.user, initial=initial)
        if request.method == 'POST' and form.is_valid():
            values = form.cleaned_data
            try:
                draft = services.request_draft(values['shipment'].pk, values['kind'], request.user,
                    document_id=values['document'].pk if values['document'] else None,
                    event_id=values['event'].pk if values['event'] else None, consent=values['consent'])
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, _('AI request saved durably. Review its progress and sources here.'))
                return HttpResponseRedirect(reverse('admin:ai_review', args=[draft.pk]))
        return self.response(request, 'admin/ai/request.html', self.context(request, _('Request an AI draft'), form=form, source_selection=SourceSelectionForm(request.GET or None, auto_id="source_%s")))

    def review(self, request, pk):
        services.require(request.user, 'view_aidraft')
        draft = get_object_or_404(self.get_queryset(request), pk=pk)
        services.check_sources(request.user, draft)
        stale = services.version(draft.shipment) != draft.source_version or bool(draft.shipment.archived_at)
        can_review = request.user.has_perm('ai.review_ai') and draft.state == 'ready' and not stale
        if draft.kind == 'extraction':
            can_review = can_review and request.user.has_perm('ai.apply_extraction') and request.user.has_perm('shipments.change_shipment')
        form = ReviewForm(request.POST or None, draft=draft) if can_review else None
        if request.method == 'POST':
            if not can_review:
                # Rejection remains possible for a stale ready draft, preserving decision history.
                if request.POST.get('decision') == 'reject' and request.POST.get('confirm') and draft.state == 'ready':
                    services.reject(pk, request.user)
                    return HttpResponseRedirect(reverse('admin:ai_review', args=[pk]))
                raise PermissionDenied
            if form.is_valid():
                try:
                    if form.cleaned_data['decision'] == 'reject':
                        services.reject(pk, request.user)
                    else:
                        output, fields, items = form.reviewed_output()
                        if draft.kind == 'extraction':
                            services.apply_extraction(pk, request.user, output, fields, items)
                        else:
                            services.accept_writing(pk, request.user, output)
                except ValidationError as exc:
                    form.add_error(None, exc)
                else:
                    messages.success(request, _('Review saved. Approved text stays private; no customer message was sent.'))
                    return HttpResponseRedirect(reverse('admin:ai_review', args=[pk]))
        source_rows = []
        for record in draft.source.get('records', []):
            link = None
            if record['id'].startswith('page:') and draft.document_id:
                link = reverse('admin:shipments_document_download', args=[draft.document_id])
            elif record['id'].startswith('event:'):
                link = reverse('admin:shipments_trackingevent_change', args=[int(record['id'].split(':')[1])])
            elif record['id'].startswith('item:'):
                link = reverse('admin:shipments_shipmentitem_change', args=[int(record['id'].split(':')[1])])
            elif record['id'] == 'shipment':
                link = reverse('admin:shipments_shipment_change', args=[draft.shipment_id])
            source_rows.append({'id': record['id'], 'record': record, 'url': link,
                'status_label': dict(Status.choices).get(record.get('status'), ''), 'origin_label': ' / '.join(v for v in record.get('origin',[]) if v) or _('Unknown'), 'destination_label': ' / '.join(v for v in record.get('destination',[]) if v) or _('Unknown')})
        return self.response(request, 'admin/ai/review.html', self.context(request, _('Review AI draft'), draft=draft, form=form,
            source_rows=source_rows, proposed_items=draft.output.get('items', []), proposed_fields=[{**field, 'label': {'internal_order':_('Internal order reference'),'bill_number':_('Private bill number'),'origin_en':_('Approved origin (English)'),'origin_ar':_('Approved origin (Arabic)'),'destination_en':_('Approved destination (English)'),'destination_ar':_('Approved destination (Arabic)')}[field['field']]} for field in draft.output.get('fields',[])], stale=stale, stale_warning=stale and draft.state in ('ready','failed'), safe_error=ERRORS.get(draft.safe_error, ''),
            can_reject=request.user.has_perm('ai.review_ai') and draft.state == 'ready',
            can_retry=request.user.has_perm('ai.retry_ai') and request.user.has_perm('ai.request_ai') and draft.state=='failed' and not draft.is_demo and not stale))

    def retry(self, request, pk):
        services.require(request.user, 'retry_ai')
        draft = get_object_or_404(self.get_queryset(request), pk=pk)
        services.check_sources(request.user, draft)
        if request.method == 'POST' and request.POST.get('confirm') == 'yes':
            try:
                services.retry(pk, request.user)
            except ValidationError as exc:
                messages.error(request, ' '.join(exc.messages))
            return HttpResponseRedirect(reverse('admin:ai_review', args=[pk]))
        return self.response(request, 'admin/ai/retry.html', self.context(request, _('Retry AI processing'), draft=draft))
