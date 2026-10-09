"""Durable AI work and explicit review. All network/conversion occurs outside writes."""
import secrets
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from apps.shipments.models import Shipment, Document, TrackingEvent, ShipmentItem
from apps.shipments.services import require as require_shipping, save_shipment, save_child, audit
from .models import AIDraft
from .provider import AIError, configuration, generate
from .sources import digest, version, build_history
from .schemas import validate_output
from .documents import extract_document

ACTIVE = ('pending', 'retry', 'running')
REVIEWABLE = ('ready',)


def require(user, permission):
    if not user or not user.is_active or not user.is_staff or not user.has_perm('ai.' + permission):
        raise PermissionDenied
    require_shipping(user, 'view_shipment')


def check_sources(user, draft):
    require(user, 'view_aidraft')
    if draft.document_id:
        require_shipping(user, 'view_document')
        require_shipping(user, 'download_document')
    else:
        require_shipping(user, 'view_trackingevent')
        if not draft.event_id:
            require_shipping(user, 'view_shipmentitem')
            require_shipping(user, 'view_trackingleg')


def dispatch(pk):
    from .tasks import process_draft
    try:
        process_draft.apply_async(args=[pk], retry=False)
    except Exception:
        return False
    return True


def request_draft(shipment_id, kind, actor, document_id=None, event_id=None, consent=False):
    require(actor, 'request_ai')
    require(actor, 'view_aidraft')
    if kind not in AIDraft.Kind.values or not consent:
        raise ValidationError(_('Confirm external AI processing before requesting a draft.'))
    shipment = Shipment.objects.get(pk=shipment_id)
    if shipment.archived_at:
        raise ValidationError(_('Restore the archived shipment before requesting AI work.'))
    if shipment.is_demo:
        raise ValidationError(_('Synthetic DEMO records are never sent to Groq. Use the local AI demonstration.'))
    document = Document.objects.get(pk=document_id, shipment=shipment) if document_id else None
    event = TrackingEvent.objects.get(pk=event_id, shipment=shipment, source='carrier') if event_id else None
    candidate = AIDraft(shipment=shipment, document=document, event=event)
    check_sources(actor, candidate)
    if (kind == 'extraction') != bool(document) or (event and kind != 'message'):
        raise ValidationError(_('Select a matching document or carrier event for this task.'))
    if configuration() != 'ready':
        raise ValidationError(_('Groq is disabled or its private key/text model is missing. Manual operations remain available.'))
    # No file I/O or external requests here; converter runs only in worker after consent.
    source = {'records': [], 'images': [], 'warnings': []} if document else build_history(shipment, event)
    initial_version = version(shipment)
    key = digest([shipment.pk, kind, document.checksum if document else None, event.pk if event else None, initial_version])
    with transaction.atomic():
        current = Shipment.objects.get(pk=shipment.pk)
        if current.archived_at or version(current) != initial_version:
            raise ValidationError(_('Shipment changed while preparing the request. Reload and retry.'))
        previous = AIDraft.objects.filter(shipment=shipment, kind=kind, source_version=initial_version, event=event)
        previous = previous.filter(document__checksum=document.checksum) if document else previous.filter(document__isnull=True)
        previous = previous.order_by('-pk').first()
        if previous and previous.state not in ('rejected', 'expired'):
            return previous
        # Explicit regeneration after rejection/expiry keeps history and deduplicates concurrent requests.
        if previous:
            key = digest([key, previous.pk])
        draft, created = AIDraft.objects.get_or_create(dedupe_key=key, defaults={
            'shipment': shipment, 'document': document, 'event': event, 'kind': kind, 'source': source,
            'source_version': initial_version, 'requested_by': actor,
            'expires_at': timezone.now() + timezone.timedelta(days=settings.GROQ_RETENTION_DAYS)})
        if created:
            audit(draft, actor, 'ai.requested', fields=[kind])
            transaction.on_commit(lambda: dispatch(draft.pk))
    return draft


@transaction.atomic
def claim(pk):
    draft = AIDraft.objects.filter(pk=pk, state__in=('pending', 'retry'), available_at__lte=timezone.now()).first()
    if not draft or draft.expires_at <= timezone.now():
        return None
    draft.state = 'running'
    draft.attempts += 1
    draft.lease_token = secrets.token_hex(16)
    draft.lease_until = timezone.now() + timezone.timedelta(seconds=120)
    draft.save(update_fields=['state', 'attempts', 'lease_token', 'lease_until', 'updated_at'])
    return draft


def process(pk):
    draft = claim(pk)
    if not draft:
        return
    try:
        local_demo = draft.is_demo and draft.shipment.is_demo and settings.DEBUG
        if (draft.is_demo or draft.shipment.is_demo) and not local_demo:
            raise AIError('demo_outbound_blocked')
        if not local_demo:
            check_sources(draft.requested_by, draft)
            require(draft.requested_by, 'request_ai')
        if draft.shipment.archived_at or version(draft.shipment) != draft.source_version:
            raise AIError('source_changed')
        source = extract_document(draft.document) if draft.document else draft.source
        if local_demo:
            # Explicit seeded proposals only; same converter/validation/job lifecycle, no provider.
            output = validate_output(draft.kind, draft.output, source)
            model, latency, usage = 'SYNTHETIC-LOCAL-FIXTURE', 0, {}
            source['warnings'].append('SYNTHETIC real-worker conversion/validation; no Groq request.')
        else:
            output, model, latency, usage = generate(draft.kind, source)
        # Discard temporary image base64; citations retain source text and page IDs privately.
        source = {**source, 'images': []}
        with transaction.atomic():
            current = AIDraft.objects.get(pk=pk)
            if current.state != 'running' or current.lease_token != draft.lease_token:
                return
            if not local_demo:
                check_sources(current.requested_by, current)
                require(current.requested_by, 'request_ai')
            if version(current.shipment) != current.source_version or current.shipment.archived_at:
                raise AIError('source_changed')
            current.source, current.output, current.model = source, output, model
            current.latency_ms, current.usage, current.state = latency, usage, 'ready'
            current.safe_error, current.lease_token, current.lease_until = '', '', None
            current.save()
            audit(current, current.requested_by, 'ai.ready', identity='synthetic_local' if local_demo else 'groq')
    except Exception as exc:
        error = exc if isinstance(exc, AIError) else AIError('permission_revoked' if isinstance(exc, PermissionDenied) else 'processing_failed')
        with transaction.atomic():
            current = AIDraft.objects.get(pk=pk)
            if current.state != 'running' or current.lease_token != draft.lease_token:
                return
            defer = error.code in ('local_rate_limit', 'rate_control_unavailable')
            if defer:
                current.attempts = max(0, current.attempts - 1)
            current.state = 'retry' if error.retryable and current.attempts < 3 else 'failed'
            current.available_at = timezone.now() + timezone.timedelta(seconds=min(3600, 60 * 2 ** current.attempts) + secrets.randbelow(16))
            current.safe_error, current.lease_token, current.lease_until = error.code, '', None
            current.save(update_fields=['state', 'attempts', 'available_at', 'safe_error', 'lease_token', 'lease_until', 'updated_at'])


def reviewable(draft, actor):
    require(actor, 'review_ai')
    check_sources(actor, draft)
    if draft.state != 'ready' or draft.expires_at <= timezone.now():
        raise ValidationError(_('This draft is no longer awaiting review.'))
    if draft.is_demo and not settings.DEBUG:
        raise ValidationError(_('DEMO drafts cannot be applied in production.'))
    if draft.shipment.archived_at or version(draft.shipment) != draft.source_version:
        raise ValidationError(_('This draft is stale. Request a new draft from the current records.'))


@transaction.atomic
def apply_extraction(pk, actor, reviewed, selected_fields, selected_items):
    require(actor, 'apply_extraction')
    require_shipping(actor, 'change_shipment')
    draft = AIDraft.objects.select_related('shipment').get(pk=pk)
    reviewable(draft, actor)
    if draft.kind != 'extraction':
        raise ValidationError(_('Only an extraction draft can apply operational fields.'))
    if AIDraft.objects.filter(shipment=draft.shipment, kind='extraction', state='applied', document__checksum=draft.document.checksum).exclude(pk=draft.pk).exists():
        raise ValidationError(_('An extraction from this document was already applied. Review the existing records.'))
    try:
        result = validate_output('extraction', reviewed, draft.source)
    except Exception:
        raise ValidationError(_('Invalid reviewed data or source citations.')) from None
    names = {f['field'] for f in result['fields']}
    if not set(selected_fields) <= names or any(type(i) is not int or i < 0 or i >= len(result['items']) for i in selected_items) or len(set(selected_items)) != len(selected_items):
        raise ValidationError(_('Invalid field or item selection.'))
    if not selected_fields and not selected_items:
        raise ValidationError(_('Select at least one field or item to apply.'))
    shipment = Shipment.objects.get(pk=draft.shipment_id)
    for field in result['fields']:
        if field['field'] in selected_fields:
            if getattr(shipment, field['field']).strip() and getattr(shipment, field['field']) != field['value']:
                raise ValidationError(_('Existing shipment fields are retained. Make intentional corrections through the shipment editor.'))
            if field['field'] in ('bill_number', 'internal_order') and Shipment.objects.exclude(pk=shipment.pk).filter(**{field['field']: field['value']}).exists():
                raise ValidationError(_('This identifier already belongs to another shipment. Review the likely duplicate.'))
            setattr(shipment, field['field'], field['value'])
    if selected_fields:
        save_shipment(shipment, actor, shipment.revision, selected_fields)
    if selected_items:
        require_shipping(actor, 'add_shipmentitem')
    for index in selected_items:
        item = result['items'][index]
        if shipment.items.filter(description_en=item['description_en'], quantity=item['quantity'], unit=item['unit']).exists():
            raise ValidationError(_('A matching item already exists. Review the likely duplicate.'))
        save_child(ShipmentItem(shipment=shipment, **{k: item[k] for k in ('description_en', 'description_ar', 'quantity', 'unit', 'unit_ar')}, public=False), actor, fields=['ai_review'])
    draft.output = result
    draft.accepted_changes = {'fields': list(selected_fields), 'item_indices': list(selected_items)}
    finish_review(draft, actor, 'applied')
    audit(draft, actor, 'ai.applied', fields=list(selected_fields))
    return draft


def finish_review(draft, actor, state):
    draft.state, draft.reviewed_by, draft.reviewed_at = state, actor, timezone.now()
    draft.save(update_fields=['state', 'reviewed_by', 'reviewed_at', 'output', 'accepted_changes', 'updated_at'])


@transaction.atomic
def accept_writing(pk, actor, reviewed):
    draft = AIDraft.objects.get(pk=pk)
    reviewable(draft, actor)
    if draft.kind not in ('summary', 'message'):
        raise ValidationError(_('Use the extraction review form for operational fields.'))
    try:
        draft.output = validate_output(draft.kind, reviewed, draft.source)
    except Exception:
        raise ValidationError(_('Invalid reviewed text or source citations.')) from None
    draft.accepted_changes = {'private_text_approved': True}
    finish_review(draft, actor, 'accepted')
    audit(draft, actor, 'ai.text_approved')
    return draft


@transaction.atomic
def reject(pk, actor):
    require(actor, 'review_ai')
    draft = AIDraft.objects.get(pk=pk)
    check_sources(actor, draft)
    if draft.state != 'ready':
        raise ValidationError(_('Only a draft awaiting review can be rejected.'))
    finish_review(draft, actor, 'rejected')
    audit(draft, actor, 'ai.rejected')


@transaction.atomic
def retry(pk, actor):
    require(actor, 'retry_ai')
    require(actor, 'request_ai')
    draft = AIDraft.objects.get(pk=pk)
    check_sources(actor, draft)
    if draft.state != 'failed' or draft.expires_at <= timezone.now() or version(draft.shipment) != draft.source_version or draft.shipment.archived_at:
        raise ValidationError(_('Only a current failed draft can be retried.'))
    if draft.is_demo or draft.shipment.is_demo:
        raise ValidationError(_('DEMO processing stays local.'))
    if configuration() != 'ready':
        raise ValidationError(_('Configure Groq before retrying.'))
    draft.state, draft.attempts, draft.available_at, draft.requested_by = 'pending', 0, timezone.now(), actor
    draft.save(update_fields=['state', 'attempts', 'available_at', 'requested_by', 'updated_at'])
    audit(draft, actor, 'ai.retried')
    transaction.on_commit(lambda: dispatch(pk))


def recover():
    now = timezone.now()
    with transaction.atomic():
        # Retain audit/decision metadata; erase private contents when retention ends.
        AIDraft.objects.filter(expires_at__lte=now).exclude(state='expired').update(state='expired', source={}, output={}, accepted_changes={}, lease_token='', lease_until=None)
        expired = AIDraft.objects.filter(state='running', lease_until__lte=now)
        expired.filter(attempts__gte=3).update(state='failed', safe_error='worker_interrupted', lease_token='', lease_until=None)
        expired.filter(attempts__lt=3).update(state='retry', available_at=now, safe_error='worker_interrupted', lease_token='', lease_until=None)
        rows = list(AIDraft.objects.filter(state__in=('pending', 'retry'), available_at__lte=now).filter(Q(last_enqueued_at__isnull=True) | Q(last_enqueued_at__lte=now-timezone.timedelta(seconds=60))).order_by('available_at')[:25])
        AIDraft.objects.filter(pk__in=[r.pk for r in rows]).update(last_enqueued_at=now)
        for row in rows:
            transaction.on_commit(lambda pk=row.pk: dispatch(pk))
