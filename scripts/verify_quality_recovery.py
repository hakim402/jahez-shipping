"""Private Phase 7 markers; real local broker recovery, synthetic work, no provider requests."""
import hashlib
import json
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.update(DJANGO_SETTINGS_MODULE='config.settings.development',GROQ_ENABLED='false',GROQ_API_KEY='',TRACK17_ENABLED='false',TRACK17_API_KEY='')
import django
django.setup()
from django.conf import settings
from django.db import connection
from django.utils import timezone
from redis import Redis
from apps.shipments.models import Shipment,ShipmentItem,TrackingEvent,TrackingLeg,Document
from apps.ai.models import AIDraft,AssistantRun
from apps.ai.sources import digest,version,build_history
from apps.ai.services import dispatch,recover
from apps.tracking.models import IntegrationJob,WebhookReceipt
from apps.tracking.payloads import parse_webhook
from apps.tracking.services import accept_receipt
from apps.tracking.tasks import reconcile,process_job

if not settings.DEBUG or settings.DATA_DIR!=Path('/data'):raise SystemExit('Development volume only.')
marker=settings.DATA_DIR/'phase07-redis-recovery.json'
persistence=settings.DATA_DIR/'phase07-persistence-review.json'
operation=sys.argv[1]

def snapshot():
    data={model._meta.label:{'count':model.objects.count(),'sha256':digest(list(model.objects.order_by('pk').values()))}
          for model in (Shipment,ShipmentItem,TrackingEvent,TrackingLeg,Document,AIDraft,AssistantRun)}
    for doc in Document.objects.all():
        with doc.file.open('rb') as handle:assert hashlib.sha256(handle.read(5*1024*1024+1)).hexdigest()==doc.checksum
    return data

if operation=='prepare-outage':
    if marker.exists():raise SystemExit('Phase 7 baseline exists; preserve it and use dispatch/verify.')
    try:Redis.from_url(settings.REDIS_URL,socket_connect_timeout=1,socket_timeout=1).ping()
    except Exception:pass
    else:raise SystemExit('Stop only Shipping Redis/worker/Beat before preparing the outage test.')
    carrier=Shipment.objects.get(internal_order='DEMO-CARRIER',is_demo=True)
    body=json.loads((settings.BASE_DIR/'tests/fixtures/tracking/updated.json').read_text())
    body['data']['number']=carrier.legs.get(sequence=1).tracking_number
    item=body['data']['track_info']['latest_event'];item['description']='SYNTHETIC Phase 7 Redis outage — private carrier history'
    item['time_utc']=(timezone.now()-timezone.timedelta(minutes=10)).isoformat();item['time_iso']=item['time_utc']
    body['data']['track_info']['tracking']['providers'][0]['events']=[item]
    raw=json.dumps(body).encode()
    receipt,_=accept_receipt(hashlib.sha256(raw).hexdigest(),parse_webhook(raw),is_demo=True)
    job=IntegrationJob.objects.get(receipt=receipt);assert job.state=='pending'
    ship=Shipment.objects.get(internal_order='DEMO-AI',is_demo=True);before=version(ship)
    draft=AIDraft.objects.create(shipment=ship,kind='summary',dedupe_key=digest(['phase07-real-redis-outage',before]),
        source=build_history(ship),source_version=before,is_demo=True,
        output={'statements':[{'english':'Arrival estimate is unknown.','arabic':'موعد الوصول غير معروف.','source_ids':['shipment']}],'warnings':[]},
        expires_at=timezone.now()+timezone.timedelta(days=30))
    assert not dispatch(draft.pk),'Expected a real broker publication failure.'
    marker.write_text(json.dumps({'draft':draft.pk,'job':job.pk,'receipt':receipt.pk,'source_version':before}));marker.chmod(0o600)
    print('PASS: actual Redis outage left committed receipt/AI work pending in SQLite; publication really failed; no mocked broker/provider.')
elif operation=='dispatch':
    assert marker.exists();reconcile.apply_async(retry=False);recover()
    print('Durable recovery dispatched through real Shipping Redis/Celery.')
elif operation=='check-outage':
    import urllib.request,urllib.error
    for route,body,expected in [('/health/ready/',None,503),('/health/live/',None,200),('/en/',None,200),('/en/admin/login/',b'username=SYNTHETIC',503)]:
        request=urllib.request.Request('http://127.0.0.1:8000'+route,data=body)
        try:response=urllib.request.urlopen(request,timeout=10)
        except urllib.error.HTTPError as exc:response=exc
        assert response.status==expected and response.headers['X-Request-ID']
        if expected==503:assert 'no-store' in response.headers['Cache-Control']
        response.close()
    print('PASS: real Redis outage yields readiness/login 503 with correlation/no-store; liveness and public GET still 200. No credentials submitted.')
elif operation=='verify':
    baseline=json.loads(marker.read_text());draft=AIDraft.objects.get(pk=baseline['draft']);job=IntegrationJob.objects.get(pk=baseline['job'])
    assert draft.state=='ready' and draft.is_demo and draft.model=='SYNTHETIC-LOCAL-FIXTURE'
    assert version(draft.shipment)==baseline['source_version'] and not draft.shipment.published
    assert job.state=='succeeded' and job.receipt.state=='processed' and job.receipt.is_demo
    assert TrackingEvent.objects.filter(raw_text='SYNTHETIC Phase 7 Redis outage — private carrier history',public=False).count()==1
    process_job(job.pk);from apps.ai.services import process;process(draft.pk)
    draft.refresh_from_db();assert draft.attempts==1
    print('PASS: real recovered worker processed both durable DEMO jobs once; duplicates no-op; AI changed no operational/public record; carrier event private.')
elif operation=='prepare-persistence':
    if persistence.exists():raise SystemExit('Baseline exists; preserve it and use verify-persistence.')
    assert not AIDraft.objects.filter(state__in=['pending','running','retry']).exists()
    persistence.write_text(json.dumps(snapshot()));persistence.chmod(0o600)
    print('Phase 7 private hash/count/file baseline recorded for container recreation.')
elif operation=='verify-persistence':
    assert snapshot()==json.loads(persistence.read_text())
    with connection.cursor() as cursor:
        cursor.execute('PRAGMA integrity_check');assert cursor.fetchone()[0]=='ok'
        cursor.execute('PRAGMA foreign_key_check');assert not cursor.fetchall()
    print('PASS: all operational records, AI reviews/assistant runs, private files and public capabilities survived Shipping container recreation; integrity/foreign keys OK.')
else:raise SystemExit('Use prepare-outage, check-outage, dispatch, verify, prepare-persistence or verify-persistence.')
