"""Optional private explanations: bounded durable jobs, fenced leases, rechecked read tools."""
import secrets
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from apps.shipments.services import audit
from .models import AssistantRun
from .operations import execute, require, source
from .provider import generate, configuration, AIError
from .sources import digest


def authority(user, scope, external=False):
    require(user, scope['tool'])
    if not user.has_perm('ai.view_assistantrun') or (external and not user.has_perm('ai.request_ai')):
        raise PermissionDenied


def dispatch(pk):
    from .tasks import explain_run
    try:
        explain_run.apply_async(args=[pk], retry=False)
    except Exception:
        return False
    return True


def request_explanation(user, scope, expected, consent=False):
    authority(user, scope, True)
    if not consent:
        raise ValidationError(_('Confirm sending only this search metadata to Groq.'))
    result = execute(user, scope)
    if result['scope']['demo']:
        raise ValidationError(_('Synthetic DEMO records are never sent to Groq.'))
    if configuration() != 'ready':
        raise ValidationError(_('Configure Groq before requesting an explanation. Local search remains available.'))
    if digest(result) != expected:
        raise ValidationError(_('Search results changed. Run the local query again before requesting an explanation.'))
    # Source selection is an explicit immutable snapshot; no network under a write transaction.
    with transaction.atomic():
        authority(user, scope, True)
        if digest(execute(user, scope)) != expected:
            raise ValidationError(_('Search results changed. Run the local query again before requesting an explanation.'))
        run, created = AssistantRun.objects.get_or_create(dedupe_key=digest([user.pk,scope,expected]), defaults={
            'requested_by':user,'scope':result['scope'],'result':result,'source_version':expected,
            'expires_at':timezone.now()+timezone.timedelta(days=settings.GROQ_RETENTION_DAYS)})
        if created:
            audit(run,user,'assistant.requested',fields=[scope['tool']])
            transaction.on_commit(lambda:dispatch(run.pk))
    return run


from apps.core.maintenance import pause_claim

@pause_claim
@transaction.atomic
def claim(pk):
    from apps.core.maintenance import active
    if active():return None
    now = timezone.now()
    run = AssistantRun.objects.filter(pk=pk,state__in=['pending','retry'],available_at__lte=now,expires_at__gt=now).first()
    if not run:
        return None
    run.state, run.attempts = 'running', run.attempts+1
    run.lease_token, run.lease_until = secrets.token_hex(16), now+timezone.timedelta(seconds=120)
    run.save(update_fields=['state','attempts','lease_token','lease_until'])
    return run


def current(run, external=False):
    authority(run.requested_by,run.scope,external)
    result = execute(run.requested_by,run.scope)
    if digest(result) != run.source_version:
        raise AIError('source_changed')
    return result


def process(pk):
    run = claim(pk)
    if not run:
        return
    try:
        result = current(run,True)
        if run.scope['demo']:
            raise AIError('demo_outbound_blocked')
        output, model, latency, usage = generate('operational',source(result))
        with transaction.atomic():
            latest = AssistantRun.objects.get(pk=pk)
            if latest.state!='running' or latest.lease_token!=run.lease_token:
                return
            if latest.expires_at<=timezone.now():
                raise AIError('source_changed')
            current(latest,True)  # Fresh user and permissions after the model response.
            latest.output, latest.model, latest.latency_ms, latest.usage = output,model,latency,usage
            latest.state, latest.safe_error, latest.lease_token, latest.lease_until = 'ready','', '',None
            latest.save()
            audit(latest,latest.requested_by,'assistant.ready',identity='groq')
    except Exception as exc:
        error = exc if isinstance(exc,AIError) else AIError('permission_revoked' if isinstance(exc,PermissionDenied) else 'processing_failed')
        with transaction.atomic():
            latest = AssistantRun.objects.get(pk=pk)
            if latest.state!='running' or latest.lease_token!=run.lease_token:
                return
            if error.code in ('local_rate_limit','rate_control_unavailable'):
                latest.attempts=max(0,latest.attempts-1)
            latest.state='retry' if error.retryable and latest.attempts<3 else 'failed'
            latest.available_at=timezone.now()+timezone.timedelta(seconds=min(3600,60*2**latest.attempts)+secrets.randbelow(16))
            latest.safe_error, latest.lease_token, latest.lease_until=error.code,'',None
            latest.save(update_fields=['state','attempts','available_at','safe_error','lease_token','lease_until'])


def recover():
    from apps.core.maintenance import active
    if active():return
    now=timezone.now()
    with transaction.atomic():
        expired=list(AssistantRun.objects.filter(expires_at__lte=now).exclude(state='expired').values_list('pk',flat=True)[:100])
        AssistantRun.objects.filter(pk__in=expired).update(state='expired',result={},output={},scope={},lease_until=None,lease_token='')
        interrupted=AssistantRun.objects.filter(state='running',lease_until__lte=now)
        interrupted.filter(attempts__gte=3).update(state='failed',safe_error='worker_interrupted',lease_token='',lease_until=None)
        interrupted.filter(attempts__lt=3).update(state='retry',available_at=now,safe_error='worker_interrupted',lease_token='',lease_until=None)
        rows=list(AssistantRun.objects.filter(state__in=['pending','retry'],available_at__lte=now,expires_at__gt=now).filter(
            Q(last_enqueued_at__isnull=True)|Q(last_enqueued_at__lte=now-timezone.timedelta(seconds=60))).order_by('available_at')[:25])
        AssistantRun.objects.filter(pk__in=[r.pk for r in rows]).update(last_enqueued_at=now)
        for row in rows:
            transaction.on_commit(lambda pk=row.pk:dispatch(pk))
