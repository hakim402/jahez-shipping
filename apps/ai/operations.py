"""Fixed read-only ORM tools. No user/model-selected fields, expressions, URLs or code."""
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, Count, Exists, OuterRef
from django.db.models.functions import Trim, Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from apps.shipments.models import Shipment, ShipmentItem, TrackingLeg, Status

TOOLS = {'delayed': _('Delayed shipments'), 'arrived': _('Arrivals in a date range'),
         'status': _('Shipments by status'), 'quality': _('Data quality checks')}
ISSUES = {
    'route': _('Missing bilingual route labels'), 'items': _('No product items recorded'),
    'measurements': _('Invalid quantity, weight or volume'), 'translation': _('Public item missing Arabic labels'),
    'dates': _('Future actual date or delivery before arrival'), 'delivery': _('Delivered status without an actual delivery date'),
    'bill': _('Duplicate bill identifier'), 'order': _('Duplicate order identifier'),
    'carrier': _('API or hybrid shipment without a carrier reference'),
}
TERMINAL = ('delivered', 'returned', 'cancelled')


def require(user, tool):
    if not isinstance(tool,str) or tool not in TOOLS:
        raise ValidationError(_('Choose a supported read-only query.'))
    perms = ['ai.query_shipments', 'shipments.view_shipment']
    if tool == 'quality':
        perms += ['ai.check_quality', 'shipments.view_shipmentitem', 'shipments.view_trackingleg']
    if not user or not user.is_active or not user.is_staff or not all(user.has_perm(p) for p in perms):
        raise PermissionDenied


def question_scope(question, now=None):
    """Deliberately small bilingual grammar. Ambiguous/unsupported requests require clarification."""
    now = now or timezone.now()
    q = ' '.join(question.casefold().strip().rstrip('?؟.').split())
    if q in ('which shipments are delayed', 'show delayed shipments', 'ما الشحنات المتأخرة', 'اعرض الشحنات المتأخرة'):
        return {'tool': 'delayed', 'start': '', 'end': '', 'status': ''}
    if q in ('which shipments arrived this week', 'show arrivals this week', 'ما الشحنات التي وصلت هذا الأسبوع', 'اعرض الشحنات التي وصلت هذا الأسبوع'):
        today = timezone.localtime(now, ZoneInfo(settings.BUSINESS_TIME_ZONE)).date()
        start = today - timedelta(days=today.weekday())
        return {'tool': 'arrived', 'start': start.isoformat(), 'end': (start+timedelta(days=6)).isoformat(), 'status': ''}
    raise ValidationError(_('Please clarify: choose a query and exact dates below. This question is ambiguous or unsupported.'))


def normalize(scope):
    if not isinstance(scope, dict) or set(scope) - {'tool','start','end','status','demo','as_of'}:
        raise ValidationError(_('Unsupported query parameters.'))
    tool = scope.get('tool')
    if not isinstance(tool,str) or tool not in TOOLS or type(scope.get('demo', False)) is not bool:
        raise ValidationError(_('Choose a supported read-only query.'))
    if scope.get('demo') and not settings.DEBUG:
        raise ValidationError(_('Synthetic search is available only in development.'))
    start, end = scope.get('start', ''), scope.get('end', '')
    if bool(start) != bool(end) or (tool == 'arrived' and not start):
        raise ValidationError(_('Provide both start and end dates for this query.'))
    try:
        if start:
            if not all(isinstance(v, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', v) for v in (start,end)):
                raise ValueError()
            first, last = date.fromisoformat(start), date.fromisoformat(end)
            if last < first or (last-first).days > 365 or first.year<2 or last.year>9998:
                raise ValueError()
        as_of = datetime.fromisoformat(scope['as_of']) if scope.get('as_of') else timezone.now()
        if timezone.is_naive(as_of) or as_of > timezone.now()+timedelta(minutes=5):
            raise ValueError()
    except (ValueError, TypeError, OverflowError):
        raise ValidationError(_('Use an ordered ISO date range of at most 366 days and an aware query time.')) from None
    status = scope.get('status', '')
    if (tool == 'status' and status not in Status.values) or (tool != 'status' and status):
        raise ValidationError(_('Select a valid status for the status query only.'))
    return {'tool': tool, 'start': start, 'end': end, 'status': status, 'demo': scope.get('demo',False), 'as_of': as_of.isoformat()}


def base_query(scope):
    rows = Shipment.objects.filter(archived_at__isnull=True, is_demo=scope['demo'])
    if scope['start']:
        zone = ZoneInfo(settings.BUSINESS_TIME_ZONE)
        start = datetime.combine(date.fromisoformat(scope['start']), time.min, zone)
        # Half-open local boundaries account for DST; do not add 24h to UTC timestamps.
        end = datetime.combine(date.fromisoformat(scope['end'])+timedelta(days=1), time.min, zone)
        field = 'actual_arrival' if scope['tool'] == 'arrived' else 'created_at'
        rows = rows.filter(**{field+'__gte':start, field+'__lt':end})
    return rows


def delayed(rows, scope):
    now = datetime.fromisoformat(scope['as_of'])
    return rows.exclude(status__in=TERMINAL).filter(Q(confirmed_delay=True) | Q(eta__lt=now))


def arrived(rows, scope):
    # Actual arrival field only. Status/events alone cannot establish the actual date.
    return rows.filter(actual_arrival__isnull=False)


def by_status(rows, scope):
    return rows.filter(status=scope['status'])


def quality(rows, scope):
    # Correlated subqueries include all eligible rows in this chosen scope, not just the displayed page.
    duplicates = base_query(scope)
    def duplicate(field):
        return duplicates.annotate(key=Lower(Trim(field))).exclude(key='').filter(key=OuterRef('norm_'+field)).values('key').annotate(n=Count('pk')).filter(n__gt=1)
    future = datetime.fromisoformat(scope['as_of'])+timedelta(minutes=5)
    from django.db.models import F
    rows = rows.annotate(**{name+'_trim':Trim(name) for name in ('origin_en','origin_ar','destination_en','destination_ar')},
        norm_bill_number=Lower(Trim('bill_number')), norm_internal_order=Lower(Trim('internal_order')),
        issue_items=~Exists(ShipmentItem.objects.filter(shipment_id=OuterRef('pk'))),
        issue_measurements=Exists(ShipmentItem.objects.filter(shipment_id=OuterRef('pk')).filter(Q(quantity__lte=0)|Q(weight_kg__lt=0)|Q(volume_cbm__lt=0))),
        issue_translation=Exists(ShipmentItem.objects.filter(shipment_id=OuterRef('pk'),public=True).annotate(a=Trim('description_ar'),u=Trim('unit_ar')).filter(Q(a='')|Q(u=''))),
        issue_bill=Exists(duplicate('bill_number')), issue_order=Exists(duplicate('internal_order')),
        has_carrier=Exists(TrackingLeg.objects.filter(shipment_id=OuterRef('pk'))))
    conditions = {
        'route': Q(origin_en_trim='')|Q(origin_ar_trim='')|Q(destination_en_trim='')|Q(destination_ar_trim=''),
        'items': Q(issue_items=True), 'measurements':Q(issue_measurements=True), 'translation':Q(issue_translation=True),
        'dates': Q(actual_arrival__gt=future)|Q(delivered_at__gt=future)|Q(delivered_at__lt=F('actual_arrival')),
        'delivery': Q(status='delivered',delivered_at__isnull=True), 'bill':Q(issue_bill=True), 'order':Q(issue_order=True),
        'carrier': Q(tracking_mode__in=['api','hybrid'],has_carrier=False),
    }
    rows = rows.annotate(**{'flag_'+name:condition for name,condition in conditions.items()})
    any_issue = Q(pk__in=[])
    for name in ISSUES:
        any_issue |= Q(**{'flag_'+name:True})
    return rows.filter(any_issue)


ALLOWLIST = {'delayed':delayed, 'arrived':arrived, 'status':by_status, 'quality':quality}


@transaction.atomic
def execute(user, scope):
    scope = normalize(scope)
    require(user, scope['tool'])  # Repeated on every call, including background/source revalidation.
    rows = ALLOWLIST[scope['tool']](base_query(scope), scope)
    count = rows.count()
    # Only explicit projection, no contacts, references, filenames, raw carrier text or arbitrary labels.
    fields = ['pk','status','eta','actual_arrival','delivered_at','updated_at']
    if scope['tool']=='quality':
        fields += ['flag_'+name for name in ISSUES]
    result_rows = []
    for row in rows.order_by('pk').values(*fields)[:25]:
        flags = [name for name in ISSUES if row.get('flag_'+name)] if scope['tool']=='quality' else []
        result_rows.append({'id':'shipment:'+str(row['pk']), 'pk':row['pk'], 'status':row['status'],
            'eta':row['eta'].isoformat() if row['eta'] else None,
            'actual_arrival':row['actual_arrival'].isoformat() if row['actual_arrival'] else None,
            'delivered_at':row['delivered_at'].isoformat() if row['delivered_at'] else None,
            'updated_at':row['updated_at'].isoformat(), 'issues':flags})
    return {'scope':scope, 'count':count, 'shown':len(result_rows), 'truncated':count>25, 'rows':result_rows,
            'timezone':settings.BUSINESS_TIME_ZONE, 'date_field':'actual_arrival' if scope['tool']=='arrived' else 'created_at',
            'issue_counts':{name:rows.filter(**{'flag_'+name:True}).count() for name in ISSUES} if scope['tool']=='quality' else {}}


def source(result):
    return {'records':[{'id':'scope', 'text':{'scope':result['scope'], 'exact_count':result['count'], 'shown':result['shown'],
        'truncated':result['truncated'],'timezone':result['timezone'],'issue_counts':result['issue_counts']}}] +
        [{'id':row['id'], 'text':row} for row in result['rows']], 'images':[],
        'warnings':['Read-only database snapshot; count is exact, displayed rows capped at 25. No ETA inferred. Explanation is a private suggestion.']}
