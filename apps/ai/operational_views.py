from django import forms
from django.contrib import admin
from django.core import signing
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from apps.shipments.models import Status
from . import operations, assistant
from .models import AssistantRun
from .sources import digest
from .admin import ERRORS


class QueryForm(forms.Form):
    question=forms.CharField(label=_('Optional operational question'),max_length=200,required=False,
        help_text=_('Examples: Which shipments are delayed? Which shipments arrived this week? Other questions need explicit filters.'))
    tool=forms.ChoiceField(label=_('Read-only query'),choices=list(operations.TOOLS.items()))
    status=forms.ChoiceField(label=_('Status for status query'),choices=[('',_('Choose status'))]+list(Status.choices),required=False)
    start=forms.DateField(label=_('Start date'),required=False,widget=forms.DateInput(attrs={'type':'date'}))
    end=forms.DateField(label=_('End date (inclusive)'),required=False,widget=forms.DateInput(attrs={'type':'date'}))
    demo=forms.BooleanField(label=_('Search only synthetic DEMO records'),required=False)

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if not settings.DEBUG:
            self.fields.pop('demo')

    def clean(self):
        values=super().clean()
        if self.errors:
            return values
        scope={k:values.get(k,False if k=='demo' else '') for k in ('tool','status','start','end','demo')}
        for key in ('start','end'):
            scope[key]=scope[key].isoformat() if scope[key] else ''
        if values.get('question'):
            scope.update(operations.question_scope(values['question']))
        values['scope']=operations.normalize(scope)
        return values


def decorate(result):
    if not result:
        return None
    return {**result,'tool_label':operations.TOOLS[result['scope']['tool']],
        'issue_totals':[(operations.ISSUES[k],v) for k,v in result['issue_counts'].items() if v],
        'rows':[{**row,'status_label':Status(row['status']).label,
                 'issue_labels':[operations.ISSUES[k] for k in row['issues']]} for row in result['rows']]}


def response(request,**context):
    result=TemplateResponse(request,'admin/ai/assistant.html',{**admin.site.each_context(request),
        'title':_('Operational assistant'),**context})
    result['Cache-Control']='no-store, private'
    result['X-Robots-Tag']='noindex, nofollow'
    return result


def workspace(request):
    operations.require(request.user,'delayed')
    if request.method not in ('GET','POST'):
        return HttpResponseNotAllowed(['GET','POST'])
    form=QueryForm(request.POST if request.method=='POST' and request.POST.get('action')=='search' else None)
    result=None;token='';error=''
    if request.method=='POST' and request.POST.get('action')=='explain':
        try:
            selected=signing.loads(request.POST.get('scope_token',''),salt='assistant-scope',max_age=600)
            if selected['actor']!=request.user.pk:
                raise signing.BadSignature()
            run=assistant.request_explanation(request.user,selected['scope'],selected['version'],consent=request.POST.get('consent')=='on')
        except (signing.BadSignature,KeyError,TypeError):
            error=_('Search selection expired or is invalid. Run a new local query.')
        except ValidationError as exc:
            error=' '.join(exc.messages)
        else:
            return HttpResponseRedirect(reverse('admin:ai_assistant_result',args=[run.pk]))
    elif request.method=='POST' and request.POST.get('action')=='search' and form.is_valid():
        result=operations.execute(request.user,form.cleaned_data['scope'])
        token=signing.dumps({'actor':request.user.pk,'scope':result['scope'],'version':digest(result)},salt='assistant-scope')
    return response(request,form=form,result=decorate(result),scope_token=token,error=error,
        can_explain=request.user.has_perm('ai.request_ai') and request.user.has_perm('ai.view_assistantrun'))


def detail(request,pk):
    if request.method!='GET':
        return HttpResponseNotAllowed(['GET'])
    run=get_object_or_404(AssistantRun.objects.filter(requested_by=request.user),pk=pk)
    from django.utils import timezone
    if run.expires_at<=timezone.now():
        run.state='expired'  # Hide immediately; scheduled retention purges the stored content.
    operations.require(request.user,'delayed')
    if not request.user.has_perm('ai.view_assistantrun'):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    result=None;stale=False
    if run.state!='expired':
        try:
            result=assistant.current(run)
        except assistant.AIError:
            stale=True
    # No saved question/customer data; source revalidation also hides archived/changed snapshots.
    output=run.output if not stale and run.state=='ready' else {}
    statements=[{**statement,'links':[{'id':c,'pk':int(c.split(':')[1]) if c.startswith('shipment:') else None} for c in statement['source_ids']]} for statement in output.get('statements',[])]
    return response(request,run=run,result=decorate(result),stale=stale,statements=statements,
        safe_error=ERRORS.get(run.safe_error,_('Explanation is not available.')) if run.safe_error else '')
