"""Explicit DEMO durable recovery/persistence on local volume. Never sends provider data."""
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.development')
import django
django.setup()
from django.conf import settings
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone
from unittest.mock import patch
from apps.ai.models import AIDraft
from apps.ai.services import dispatch, recover
from apps.ai.sources import version, digest
from apps.shipments.models import Shipment

marker=Path(settings.DATA_DIR)/'phase05-recovery-review.json'
if not settings.DEBUG:
    raise SystemExit('Development-only recovery review.')
operation=sys.argv[1] if len(sys.argv)>1 else ''
if operation=='prepare':
    if marker.exists():
        raise SystemExit('Baseline already exists; use dispatch/verify without resetting review history.')
    call_command('seed_ai_demo')
    shipment=Shipment.objects.get(internal_order='DEMO-AI',is_demo=True)
    original=AIDraft.objects.filter(shipment=shipment,kind='extraction',document__original_filename='DEMO-scanned-invoice.pdf').latest('created_at')
    before=version(shipment)
    with patch('apps.ai.tasks.process_draft.apply_async',side_effect=RuntimeError('Synthetic publication failure')):
        with transaction.atomic():
            draft=AIDraft.objects.create(shipment=shipment,document=original.document,kind='extraction',state='pending',source=original.source,output=original.output,source_version=before,dedupe_key=digest(['phase05-recovery',before]),is_demo=True,model='SYNTHETIC-LOCAL-FIXTURE',expires_at=timezone.now()+timezone.timedelta(days=30),available_at=timezone.now()+timezone.timedelta(seconds=90))
            transaction.on_commit(lambda: dispatch(draft.pk))
    marker.write_text(json.dumps({'draft':draft.pk,'version':before,'document_checksum':original.document.checksum}));marker.chmod(0o600)
    print('PASS: private DEMO AI work committed despite simulated broker publication failure. No provider request. Recreate worker, then dispatch/verify.')
elif operation=='dispatch':
    baseline=json.loads(marker.read_text())
    AIDraft.objects.filter(pk=baseline['draft'],state='pending').update(available_at=timezone.now())
    recover()
    print('DEMO recovery dispatched through the real dedicated broker/worker.')
elif operation=='verify':
    baseline=json.loads(marker.read_text());draft=AIDraft.objects.get(pk=baseline['draft'])
    assert draft.state=='ready', 'Wait for real worker processing before verifying.'
    assert draft.is_demo and draft.model=='SYNTHETIC-LOCAL-FIXTURE'
    assert draft.document.checksum==baseline['document_checksum']
    assert version(draft.shipment)==baseline['version']
    assert not draft.shipment.published and not draft.source.get('images')
    assert draft.output['items'][0]['quantity']=='24'
    assert not draft.reviewed_at and draft.attempts==1
    print('PASS: real Celery worker converted/validated a synthetic scan, retained its draft/source and changed no operational/public records. No Groq request.')
else:
    raise SystemExit('Use prepare, dispatch or verify.')
