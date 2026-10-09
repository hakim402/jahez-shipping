"""Hash-only local DEMO persistence baseline. Never exports source/ref/credentials."""
import json
import hashlib
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.development')
import django
django.setup()
from django.conf import settings
from django.db import connection
from apps.shipments.models import Shipment, Document, ShipmentItem, TrackingEvent, TrackingLeg
from apps.ai.models import AIDraft
from apps.ai.sources import digest
from apps.tracking.models import IntegrationJob, WebhookReceipt

if not settings.DEBUG:
    raise SystemExit('Development-only synthetic persistence review.')
marker=Path(settings.DATA_DIR)/'phase05-persistence-review.json'
operation=sys.argv[1] if len(sys.argv)>1 else ''

def snapshot():
    if AIDraft.objects.filter(shipment__is_demo=True,state__in=('pending','retry','running')).exists():
        raise SystemExit('Wait for active DEMO AI work before taking a stable baseline.')
    data={}
    for model in (Shipment, Document, ShipmentItem, TrackingEvent, TrackingLeg,AIDraft):
        rows=model.objects.filter(**({'is_demo':True} if model is Shipment else {'shipment__is_demo':True})).order_by('pk')
        data[model._meta.label]={'count':rows.count(),'sha256':digest(list(rows.values()))}
    data['carrier_jobs']=digest(list(IntegrationJob.objects.filter(leg__shipment__is_demo=True).order_by('pk').values()))
    data['carrier_receipts']=digest(list(WebhookReceipt.objects.filter(is_demo=True).order_by('pk').values()))
    file_checks=[]
    for document in Document.objects.filter(shipment__is_demo=True).order_by('pk'):
        with document.file.open('rb') as handle:
            sha=hashlib.sha256(handle.read(5*1024*1024+1)).hexdigest()
        assert sha==document.checksum
        file_checks.append([document.pk,sha])
    data['private_files']=file_checks
    return data

if operation=='prepare':
    if marker.exists():raise SystemExit('Baseline exists; use verify without overwriting history.')
    marker.write_text(json.dumps(snapshot()));marker.chmod(0o600)
    print('Private hash-only DEMO baseline recorded; recreate this app, then verify.')
elif operation=='verify':
    assert snapshot()==json.loads(marker.read_text()), 'Synthetic records/files changed since baseline.'
    with connection.cursor() as cursor:
        cursor.execute('PRAGMA integrity_check');assert cursor.fetchone()[0]=='ok'
        cursor.execute('PRAGMA journal_mode');assert cursor.fetchone()[0].lower()=='wal'
        cursor.execute('PRAGMA busy_timeout');assert cursor.fetchone()[0]>=20000
    print('PASS: AI sources/output/review decisions, operational references/items/events/legs, carrier history and private bill files survived recreation. SQLite integrity/WAL/timeout verified.')
else:raise SystemExit('Use prepare or verify.')
