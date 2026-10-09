"""Private hash-only Phase 6 review baseline; no uploads, results or capabilities exported."""
import os
import sys
import hashlib
import json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.development')
import django
django.setup()
from django.conf import settings
from django.db import connection
from apps.shipments.models import Shipment, ShipmentItem, TrackingLeg, TrackingEvent, Document
from apps.ai.models import AIDraft, AssistantRun
from apps.ai.sources import digest

if not settings.DEBUG:
    raise SystemExit('Development-only persistence review.')
marker=Path(settings.DATA_DIR)/'phase06-persistence-review.json'

def snapshot():
    if AssistantRun.objects.filter(state__in=['pending','running','retry']).exists():
        raise SystemExit('Wait for active assistant work before preparing/verifying the baseline.')
    data={}
    for model in (Shipment,ShipmentItem,TrackingLeg,TrackingEvent,Document,AIDraft):
        rows=model.objects.filter(**({'is_demo':True} if model is Shipment else {'shipment__is_demo':True})).order_by('pk')
        data[model._meta.label]={'count':rows.count(),'sha256':digest(list(rows.values()))}
    data['assistant']=digest(list(AssistantRun.objects.order_by('pk').values()))
    files=[]
    for document in Document.objects.filter(shipment__is_demo=True).order_by('pk'):
        with document.file.open('rb') as handle:
            checksum=hashlib.sha256(handle.read(5*1024*1024+1)).hexdigest()
        assert checksum==document.checksum
        files.append([document.pk,checksum])
    data['files']=files
    return data

operation=sys.argv[1] if len(sys.argv)>1 else ''
if operation=='prepare':
    if marker.exists():raise SystemExit('Baseline exists; preserve it and use verify.')
    marker.write_text(json.dumps(snapshot()));marker.chmod(0o600)
    print('Private hash-only Phase 6 baseline recorded. Recreate Shipping, then verify.')
elif operation=='verify':
    assert snapshot()==json.loads(marker.read_text()),'Reviewed sources or records changed since baseline.'
    with connection.cursor() as cursor:
        cursor.execute('PRAGMA integrity_check');assert cursor.fetchone()[0]=='ok'
        cursor.execute('PRAGMA journal_mode');assert cursor.fetchone()[0].lower()=='wal'
        cursor.execute('PRAGMA busy_timeout');assert cursor.fetchone()[0]>=20000
    print('PASS: private assistant result, DEMO shipments/items/events/legs, reviewed AI drafts and private document files survived Shipping recreation; SQLite integrity/WAL/timeout verified.')
else:raise SystemExit('Use prepare or verify.')
