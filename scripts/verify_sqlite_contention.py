"""Disposable file-backed admin/webhook/AI-job contention. Never touches /data or providers."""
import hashlib
import io
import json
import multiprocessing as mp
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def setup(folder):
    os.environ.update(DJANGO_SETTINGS_MODULE='config.settings.development',SHIPPING_DATA_DIR=folder,
        DJANGO_SECRET_KEY='disposable-contention-'+ 'x'*64,DJANGO_ALLOWED_HOSTS='testserver',
        GROQ_ENABLED='false',GROQ_API_KEY='',TRACK17_ENABLED='false',TRACK17_API_KEY='')
    import django
    django.setup()
    import logging
    logging.getLogger('jahez.request').disabled=True


def contender(folder,role,barrier,queue):
    setup(folder)
    from django.db import transaction,connections
    from django.contrib.auth.models import User
    from django.test import Client,override_settings
    from django.utils import timezone
    from apps.shipments.models import Shipment
    from apps.shipments.services import save_shipment
    from apps.ai.models import AIDraft
    from apps.ai.services import claim
    durations=[];failures=[]
    barrier.wait(timeout=30)
    with override_settings(CACHES={'default':{'BACKEND':'django.core.cache.backends.locmem.LocMemCache'}},TRACK17_ENABLED=True,TRACK17_API_KEY='SYNTHETIC-CONTENTION-ONLY'):
        for number in range(20):
            started=time.monotonic()
            try:
                if role=='admin':
                    with transaction.atomic():
                        ship=Shipment.objects.get(internal_order='SYNTHETIC-CONTENTION')
                        ship.internal_notes='SYNTHETIC admin write '+str(number)
                        save_shipment(ship,User.objects.get(username='SYNTHETIC-contender'),ship.revision)
                elif role=='webhook':
                    body=json.loads((Path(__file__).resolve().parents[1]/'tests/fixtures/tracking/updated.json').read_text())
                    event=body['data']['track_info']['latest_event']
                    event['description']='SYNTHETIC concurrent receipt '+str(number)
                    event['time_utc']=(timezone.now()-timezone.timedelta(minutes=1)).isoformat()
                    body['data']['track_info']['tracking']['providers'][0]['events']=[event]
                    raw=json.dumps(body).encode();sign=hashlib.sha256(raw+b'/SYNTHETIC-CONTENTION-ONLY').hexdigest()
                    with patch('apps.tracking.services.dispatch',return_value=False):
                        response=Client().post('/webhooks/17track/',raw,content_type='application/json',HTTP_SIGN=sign)
                    if response.status_code!=200:raise RuntimeError('unexpected_http_status')
                else:
                    draft=AIDraft.objects.get(dedupe_key=hashlib.sha256(('SYNTHETIC-'+str(number)).encode()).hexdigest())
                    claimed=claim(draft.pk)
                    if not claimed or claim(draft.pk):raise RuntimeError('duplicate_claim')
                    with transaction.atomic():
                        changed=AIDraft.objects.filter(pk=claimed.pk,state='running',lease_token=claimed.lease_token).update(state='failed',safe_error='synthetic_check',lease_token='',lease_until=None)
                        if changed!=1:raise RuntimeError('fence_failed')
            except Exception as exc:
                failures.append('database_locked' if 'locked' in str(exc).lower() else type(exc).__name__)
            durations.append(round((time.monotonic()-started)*1000,2))
    connections.close_all();queue.put({'role':role,'durations_ms':durations,'failures':failures})


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='jahez-contention-') as folder:
        setup(folder)
        from django.core.management import call_command
        from django.contrib.auth.models import User,Group
        from django.db import transaction,connection,connections
        from django.utils import timezone
        from django.test import override_settings
        from apps.shipments.models import Customer,Shipment,TrackingLeg,TrackingEvent,AuditEntry
        from apps.ai.models import AIDraft
        from apps.tracking.models import WebhookReceipt,IntegrationJob
        from apps.tracking.tasks import process_job
        call_command('migrate',verbosity=0);call_command('setup_roles',stdout=io.StringIO())
        actor=User.objects.create(username='SYNTHETIC-contender',is_staff=True)
        actor.groups.add(Group.objects.get(name='Shipping Operations'))
        ship=Shipment.objects.create(customer=Customer.objects.create(name='SYNTHETIC'),internal_order='SYNTHETIC-CONTENTION',tracking_mode='hybrid')
        TrackingLeg.objects.create(shipment=ship,tracking_number='DEMO-CARRIER-0001',carrier_identifier='3011',registration_state='registered')
        for number in range(20):AIDraft.objects.create(shipment=ship,kind='summary',dedupe_key=hashlib.sha256(('SYNTHETIC-'+str(number)).encode()).hexdigest(),source_version='synthetic',expires_at=timezone.now()+timezone.timedelta(days=1))
        connections.close_all()
        context=mp.get_context('spawn');barrier=context.Barrier(4);queue=context.Queue()
        workers=[context.Process(target=contender,args=(folder,role,barrier,queue)) for role in ('admin','webhook','ai_job')]
        for worker in workers:worker.start()
        # A known held write ensures this exercises busy waiting rather than lucky sequential startup.
        with transaction.atomic():
            Shipment.objects.filter(pk=ship.pk).update(internal_notes='SYNTHETIC held write')
            barrier.wait(timeout=30);time.sleep(0.2)
        results=[queue.get(timeout=90) for _ in workers]
        for worker in workers:
            worker.join(timeout=10)
            assert worker.exitcode==0,'Contender failed.'
        assert all(not r['failures'] for r in results),results
        assert AuditEntry.objects.filter(action='shipment.updated').count()==20
        assert WebhookReceipt.objects.count()==20 and IntegrationJob.objects.count()==20
        assert AIDraft.objects.filter(state='failed',attempts=1).count()==20
        with override_settings(TRACK17_ENABLED=True,TRACK17_API_KEY='SYNTHETIC-CONTENTION-ONLY'):
            for job in IntegrationJob.objects.all():process_job(job.pk)
        assert WebhookReceipt.objects.filter(state='processed').count()==20 and TrackingEvent.objects.count()==20
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA integrity_check');assert cursor.fetchone()[0]=='ok'
            cursor.execute('PRAGMA journal_mode');assert cursor.fetchone()[0]=='wal'
            cursor.execute('PRAGMA busy_timeout');assert cursor.fetchone()[0]>=20000
            cursor.execute('PRAGMA foreign_key_check');assert not cursor.fetchall()
        report={r['role']:{'operations':20,'errors':len(r['failures']),'median_ms':round(statistics.median(r['durations_ms']),2),
            'p95_ms':sorted(r['durations_ms'])[18],'max_ms':max(r['durations_ms'])} for r in results}
        print('PASS: isolated WAL/20s IMMEDIATE contention; 3 separate processes, 60 operations, zero lost writes/duplicate claims; signed receipt jobs processed; integrity/foreign keys OK.')
        print(json.dumps(report,sort_keys=True))
