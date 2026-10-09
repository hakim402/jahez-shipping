"""Compare synthetic Phase 4 records/private bill across local app recreation."""
import hashlib
import json
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.development')
import django
django.setup()
from django.conf import settings
from django.db import connection
from django.db.models import Q
from apps.shipments.models import Shipment,Document
from apps.tracking.models import WebhookReceipt,IntegrationJob

if not settings.DEBUG:
    raise SystemExit('Synthetic persistence review is restricted to development.')


def manifest():
    shipments=[]
    for s in Shipment.objects.filter(is_demo=True).order_by('pk'):
        shipments.append({'id':s.pk,'status':s.status,'revision':s.revision,'published':s.published,'reference_hash':hashlib.sha256(s.reference.encode()).hexdigest(),
            'items':s.items.count(),'legs':s.legs.count(),'events':list(s.events.order_by('pk').values('pk','public','source','provider_event_key'))})
    receipts=list(WebhookReceipt.objects.filter(is_demo=True).order_by('pk').values('pk','digest','state'))
    jobs=list(IntegrationJob.objects.filter(Q(receipt__is_demo=True)|Q(leg__shipment__is_demo=True)).order_by('pk').values('pk','kind','state','attempts','receipt_id','leg_id'))
    assert shipments and receipts and jobs,'Run the labeled carrier demo/recovery review first.'
    assert all(j['state'] in ('succeeded','quarantined') for j in jobs),'Finish pending DEMO review jobs before preparing a stable baseline.'
    documents=[]
    for d in Document.objects.filter(shipment__is_demo=True).order_by('pk'):
        with d.file.open('rb') as file:checksum=hashlib.sha256(file.read()).hexdigest()
        assert checksum==d.checksum
        documents.append({'id':d.pk,'sha256':checksum})
    assert documents
    return {'shipments':shipments,'receipts':receipts,'jobs':jobs,'documents':documents}


path=settings.DATA_DIR/'phase04-persistence-review.json'
if sys.argv[1]=='prepare':
    path.write_text(json.dumps(manifest()))
    path.chmod(0o600)
    print('Phase 4 synthetic records and private-file baseline saved privately.')
elif sys.argv[1]=='verify':
    assert json.loads(path.read_text())==manifest(),'Synthetic records or private files changed after the baseline.'
    with connection.cursor() as cursor:
        cursor.execute('PRAGMA integrity_check');assert cursor.fetchone()[0]=='ok'
        cursor.execute('PRAGMA journal_mode');journal=cursor.fetchone()[0]
        cursor.execute('PRAGMA busy_timeout');busy=cursor.fetchone()[0]
    print(f'PASS: synthetic shipment publication/reference hashes, carrier events/receipts/jobs and private bill checksums survived recreation; SQLite integrity ok, {journal}, timeout={busy}ms.')
else:
    raise SystemExit('Use prepare or verify.')
