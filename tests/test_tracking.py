import copy
import hashlib
import io
import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock
from django.conf import settings
from django.contrib.auth.models import User, Group
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, SimpleTestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from apps.shipments.models import Customer, Shipment, TrackingLeg, TrackingEvent, Status, AuditEntry
from apps.shipments.services import save_shipment, save_child
from apps.tracking.adapter import ProviderError, request, outcome, configuration
from apps.tracking.models import WebhookReceipt, IntegrationJob
from apps.tracking.payloads import normalize, parse_webhook, PayloadError
from apps.tracking.services import accept_receipt, request_leg, claim_job, process_receipt, recover_pending, schedule_reconciliation, retry_job, apply_response
from apps.tracking.tasks import process_job

FIXTURES = Path(settings.BASE_DIR) / 'tests/fixtures/tracking'
KEY = 'SYNTHETIC-TEST-KEY-ONLY'


def fixture():
    return json.loads((FIXTURES/'updated.json').read_text())


def signature(raw):
    return hashlib.sha256(raw+b'/'+KEY.encode()).hexdigest()


@override_settings(TRACK17_ENABLED=True, TRACK17_API_KEY=KEY)
class CarrierPipelineTests(TestCase):
    def setUp(self):
        cache.clear()
        call_command('setup_roles',stdout=io.StringIO())
        self.ops=User.objects.create_user('DEMO-tracking-ops',is_staff=True)
        self.ops.groups.add(Group.objects.get(name='Shipping Operations'))
        self.reader=User.objects.create_user('DEMO-tracking-reader',is_staff=True)
        self.reader.groups.add(Group.objects.get(name='Shipping Read Only'))
        self.customer=Customer.objects.create(name='PRIVATE-PROVIDER-CUSTOMER')
        self.shipment=Shipment.objects.create(customer=self.customer,tracking_mode='hybrid',published=True,origin_en='China',origin_ar='الصين',destination_en='UAE',destination_ar='الإمارات')
        self.leg=TrackingLeg.objects.create(shipment=self.shipment,carrier_identifier='3011',tracking_number='DEMO-CARRIER-0001',registration_state='registered')

    def webhook(self,body=None,raw=None,sign=None,client=None):
        raw=raw or json.dumps(body or fixture(),ensure_ascii=False).encode()
        return (client or self.client).post('/webhooks/17track/',raw,content_type='application/json',HTTP_SIGN=sign or signature(raw))

    def ingest(self,body=None):
        raw=json.dumps(body or fixture(),ensure_ascii=False).encode()
        receipt,_=accept_receipt(hashlib.sha256(raw).hexdigest(),parse_webhook(raw))
        process_job(IntegrationJob.objects.get(receipt=receipt).pk)
        receipt.refresh_from_db()
        return receipt

    def status_payload(self,status='Delivered',stamp=None):
        body=fixture()
        item=body['data']['track_info']['latest_event']
        item['time_utc']=(stamp or timezone.now()-timedelta(minutes=1)).isoformat()
        item['stage']=status
        item['sub_status']=status+'_Other'
        body['data']['track_info']['latest_status']={'status':status,'sub_status':status+'_Other'}
        body['data']['track_info']['tracking']['providers'][0]['events']=[copy.deepcopy(item)]
        return body

    def test_raw_body_signature_and_durable_acknowledgement(self):
        raw=json.dumps(fixture(),indent=3,ensure_ascii=False).encode()
        reserialized=json.dumps(json.loads(raw),separators=(',',':'),ensure_ascii=False).encode()
        self.assertEqual(self.webhook(raw=raw,sign=signature(reserialized)).status_code,401)
        c=Client(enforce_csrf_checks=True)
        with patch('apps.tracking.services.dispatch',return_value=False),self.captureOnCommitCallbacks(execute=True):
            r=self.webhook(raw=raw,client=c)
        self.assertEqual(r.status_code,200)
        self.assertEqual(WebhookReceipt.objects.count(),1)
        self.assertEqual(IntegrationJob.objects.get().state,'pending')
        self.assertEqual(self.webhook(raw=raw).status_code,200)
        self.assertEqual(WebhookReceipt.objects.count(),1)
        self.assertEqual(IntegrationJob.objects.count(),1)
        self.assertNotContains(r,'DEMO-CARRIER')

    def test_invalid_signatures_and_malformed_signed_payloads(self):
        for value in ('0'*64,'missing','A'*63):
            self.assertEqual(self.webhook(sign=value).status_code,401)
        for raw in (b'[]',b'{"event":"TRACKING_UPDATED","data":{}}',b'not JSON'):
            self.assertEqual(self.webhook(raw=raw).status_code,400)
        self.assertEqual(WebhookReceipt.objects.count(),0)
        self.assertEqual(self.client.get('/webhooks/17track/').status_code,405)

    def test_webhook_bounds_type_and_storage_failure(self):
        self.assertEqual(self.webhook(raw=b'x'*(512*1024+1)).status_code,413)
        self.assertEqual(self.client.post('/webhooks/17track/',b'{}',content_type='text/plain').status_code,415)
        from django.db import OperationalError
        with patch('apps.tracking.views.accept_receipt',side_effect=OperationalError('PRIVATE-DB-DETAIL')):
            r=self.webhook()
        self.assertEqual(r.status_code,503)
        self.assertNotContains(r,'PRIVATE-DB-DETAIL',status_code=503)

    @override_settings(TRACK17_ENABLED=False)
    def test_disabled_provider_does_not_break_manual_or_accept_webhook(self):
        self.assertEqual(self.webhook().status_code,503)
        self.assertEqual(self.client.post('/en/',{'reference':self.shipment.reference}).status_code,200)
        self.assertEqual(WebhookReceipt.objects.count(),0)
        with self.assertRaises(ValidationError):
            request_leg(self.leg.pk,'refresh',self.ops)

    @override_settings(TRACK17_API_KEY='')
    def test_missing_key_is_honest_and_no_network(self):
        self.assertEqual(configuration(),'missing_key')
        with patch('apps.tracking.adapter.http.client.HTTPSConnection') as conn:
            with self.assertRaises(ProviderError):
                request('register',[{'number':'DEMO-1234','carrier':3011}])
            conn.assert_not_called()

    def test_normalization_drops_contacts_addresses_and_urls(self):
        body=fixture()
        body['data']['phone_number']='PRIVATE-PHONE'
        body['data']['track_info']['shipping_info']={'recipient_address':{'street':'PRIVATE-STREET'}}
        body['data']['track_info']['tracking']['providers'][0]['provider']['homepage']='https://untrusted.invalid/'
        receipt=self.ingest(body)
        self.assertNotIn('PRIVATE-',json.dumps(receipt.payload))
        self.assertNotIn('homepage',json.dumps(receipt.payload))
        self.assertEqual(receipt.state,'processed')
        self.assertEqual(TrackingEvent.objects.get().source,'carrier')
        self.assertFalse(TrackingEvent.objects.get().public)

    def test_duplicate_events_and_out_of_order_status_do_not_regress(self):
        first=self.status_payload('Delivered')
        self.shipment.carrier_coverage_complete=True
        self.shipment.save()
        self.ingest(first)
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.status,Status.DELIVERED)
        count=TrackingEvent.objects.count()
        changed=copy.deepcopy(first);changed['data']['tag']='ignored extra field'
        self.ingest(changed)
        self.assertEqual(TrackingEvent.objects.count(),count)
        self.ingest(self.status_payload('InTransit',timezone.now()-timedelta(days=5)))
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.status,Status.DELIVERED)
        self.assertTrue(AuditEntry.objects.filter(action='carrier.status_updated').exists())

    def test_manual_mode_and_override_preserve_status_but_ingest_history(self):
        for mode,locked in [('manual',False),('hybrid',True)]:
            self.shipment.tracking_mode=mode;self.shipment.status_locked=locked;self.shipment.status=Status.WAREHOUSE
            self.shipment.save()
            self.ingest(self.status_payload('InTransit',timezone.now()-timedelta(minutes=2 if locked else 3)))
            self.shipment.refresh_from_db()
            self.assertEqual(self.shipment.status,Status.WAREHOUSE)
        self.assertEqual(TrackingEvent.objects.count(),2)

    def test_manual_correction_watermark_blocks_older_provider_status(self):
        self.shipment.status=Status.ARRIVED
        save_shipment(self.shipment,self.ops,self.shipment.revision)
        self.ingest(self.status_payload('OutForDelivery',timezone.now()-timedelta(days=1)))
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.status,Status.ARRIVED)

    def test_multileg_delivered_requires_all_legs_and_coverage(self):
        other=TrackingLeg.objects.create(shipment=self.shipment,sequence=2,carrier_identifier='3011',tracking_number='DEMO-SECOND-0002',registration_state='registered')
        self.shipment.carrier_coverage_complete=True;self.shipment.save()
        self.ingest(self.status_payload())
        self.shipment.refresh_from_db();self.assertNotEqual(self.shipment.status,Status.DELIVERED)
        body=self.status_payload();body['data']['number']=other.tracking_number
        self.ingest(body)
        self.shipment.refresh_from_db();self.assertEqual(self.shipment.status,Status.DELIVERED)
        self.assertIsNotNone(self.shipment.delivered_at)

    def test_incomplete_coverage_never_auto_completes_even_one_leg(self):
        self.ingest(self.status_payload())
        self.shipment.refresh_from_db();self.assertNotEqual(self.shipment.status,Status.DELIVERED)

    def test_unknown_or_archived_reference_is_quarantined(self):
        body=fixture();body['data']['number']='UNKNOWN-SYNTHETIC-001'
        receipt=self.ingest(body)
        self.assertEqual(receipt.state,'quarantined')
        self.assertEqual(Shipment.objects.count(),1)
        self.assertEqual(TrackingEvent.objects.count(),0)
        self.shipment.archived_at=timezone.now();self.shipment.save()
        self.assertEqual(self.ingest().state,'quarantined')

    def test_unknown_time_retained_without_invented_timestamp_or_status(self):
        body=fixture()
        event=body['data']['track_info']['latest_event']
        event['time_utc']=None;event['time_iso']='2026-10-08T17:00:00'
        event['time_raw']['timezone']=None
        body['data']['track_info']['tracking']['providers'][0]['events']=[event]
        self.ingest(body)
        event=TrackingEvent.objects.get()
        self.assertIsNone(event.occurred_at)
        self.assertEqual(event.provider_time_raw['original']['date'],'2026-10-08')
        self.shipment.refresh_from_db();self.assertEqual(self.shipment.status,Status.CREATED)
        event.public=True;save_child(event,self.ops)
        self.assertContains(self.client.post('/en/',{'reference':self.shipment.reference}),'Exact event time not confirmed')

    def test_carrier_event_review_can_publish_but_not_edit_history(self):
        self.ingest()
        event=TrackingEvent.objects.get();event.public=True;event.title_en='Approved carrier milestone';event.title_ar='مرحلة معتمدة'
        save_child(event,self.ops)
        r=self.client.post('/en/',{'reference':self.shipment.reference})
        self.assertContains(r,'Approved carrier milestone')
        self.assertContains(r,'Carrier-provided update')
        self.assertNotContains(r,'SYNTHETIC carrier milestone')
        event.raw_text='forged'
        with self.assertRaises(ValidationError):save_child(event,self.ops)
        with self.assertRaises(PermissionDenied):save_child(TrackingEvent.objects.get(),self.reader)

    def test_public_sync_time_and_stale_notice_never_change_delay(self):
        body=fixture();provider=body['data']['track_info']['tracking']['providers'][0]
        provider['latest_sync_time']=(timezone.now()-timedelta(days=2)).isoformat()
        self.ingest(body)
        r=self.client.post('/en/',{'reference':self.shipment.reference})
        self.assertContains(r,'older than 24 hours')
        self.shipment.refresh_from_db();self.assertFalse(self.shipment.confirmed_delay)
        self.assertIsNone(self.shipment.eta)

    def test_unknown_status_sync_failure_and_future_time_do_not_invent_state(self):
        body=fixture();info=body['data']['track_info']
        info['latest_status']={'status':'FutureProviderStatus','sub_status':'Unknown'}
        info['latest_event']['time_utc']=(timezone.now()+timedelta(days=3)).isoformat()
        info['latest_event']['time_iso']=None
        info['tracking']['providers'][0]['latest_sync_status']='Failure'
        self.ingest(body)
        self.leg.refresh_from_db();self.shipment.refresh_from_db()
        self.assertIsNone(self.leg.last_success)
        self.assertIsNone(self.leg.last_provider_event_at)
        self.assertEqual(self.shipment.status,Status.CREATED)
        self.assertEqual(self.leg.last_error,'carrier_sync_unconfirmed')
        self.assertFalse(self.shipment.confirmed_delay)

    def test_outbound_request_runs_outside_the_job_write_transaction(self):
        from django.db import connection
        depth=len(connection.atomic_blocks)
        job=request_leg(self.leg.pk,'refresh',self.ops)
        def retrieve(*args,**kwargs):
            self.assertEqual(len(connection.atomic_blocks),depth)
            return {'accepted':[fixture()['data']],'rejected':[]}
        with patch('apps.tracking.tasks.adapter.request',side_effect=retrieve):process_job(job.pk)
        job.refresh_from_db();self.assertEqual(job.state,'succeeded')

    def test_retry_permissions_and_receipt_payload_absent_from_admin(self):
        receipt=self.ingest()
        job=IntegrationJob.objects.get(receipt=receipt)
        job.state='failed';job.save()
        with self.assertRaises(PermissionDenied):retry_job(job.pk,self.reader)
        self.client.force_login(self.reader)
        r=self.client.get(reverse('admin:tracking_webhookreceipt_change',args=[receipt.pk]))
        self.assertEqual(r.status_code,200)
        self.assertNotContains(r,'SYNTHETIC carrier milestone')
        self.assertNotContains(r,self.leg.tracking_number)
        self.assertEqual(self.client.post(reverse('admin:integration_job_retry',args=[job.pk]),{'confirm':'yes'}).status_code,403)

    def test_registration_dedup_and_individual_business_rejection(self):
        self.leg.registration_state='not_connected';self.leg.save()
        first=request_leg(self.leg.pk,'register',self.ops)
        self.assertEqual(request_leg(self.leg.pk,'register',self.ops).pk,first.pk)
        data=json.loads((FIXTURES/'registration-partial.json').read_text())['data']
        self.assertTrue(outcome(data,'DEMO-CARRIER-0001','3011',True).accepted)
        self.assertFalse(outcome(data,'DEMO-REJECTED-0002','3011',True).accepted)
        with patch('apps.tracking.tasks.adapter.request',return_value=data):process_job(first.pk)
        self.leg.refresh_from_db();self.assertEqual(self.leg.registration_state,'registered')
        first.refresh_from_db();self.assertEqual(first.state,'succeeded')
        with patch('apps.tracking.tasks.adapter.request') as call:
            process_job(first.pk);call.assert_not_called()
        self.assertIsNone(request_leg(self.leg.pk,'register',self.ops))

    def test_registration_rejection_does_not_treat_http_200_as_success(self):
        self.leg.registration_state='not_connected';self.leg.save()
        job=request_leg(self.leg.pk,'register',self.ops)
        data={'accepted':[],'rejected':[{'number':self.leg.tracking_number,'carrier':3011,'error':{'code':-18019903,'message':'PRIVATE-PROVIDER-ERROR'}}]}
        with patch('apps.tracking.tasks.adapter.request',return_value=data):process_job(job.pk)
        job.refresh_from_db();self.leg.refresh_from_db()
        self.assertEqual(job.state,'failed');self.assertEqual(self.leg.registration_state,'rejected')
        self.assertEqual(job.safe_error,'unsupported_identifier')
        self.assertNotIn('PRIVATE',self.leg.last_error)

    def test_refresh_ingests_details_and_stops_for_terminal_or_stopped(self):
        job=request_leg(self.leg.pk,'refresh',self.ops)
        with patch('apps.tracking.tasks.adapter.request',return_value={'accepted':[fixture()['data']],'rejected':[]}):process_job(job.pk)
        self.assertEqual(TrackingEvent.objects.count(),1)
        body=json.loads((FIXTURES/'stopped.json').read_text())
        self.ingest(body)
        self.leg.refresh_from_db();self.assertEqual(self.leg.registration_state,'stopped')
        self.assertIsNone(self.leg.next_reconcile_at)
        self.assertEqual(schedule_reconciliation(),0)
        with self.assertRaises(ValidationError):request_leg(self.leg.pk,'register',self.ops)

    def test_retry_backoff_and_exhaustion_keep_business_status(self):
        job=request_leg(self.leg.pk,'refresh',self.ops)
        before=self.shipment.status
        for n in range(5):
            IntegrationJob.objects.filter(pk=job.pk).update(available_at=timezone.now()-timedelta(seconds=1))
            with patch('apps.tracking.tasks.adapter.request',side_effect=ProviderError('provider_rate_limit',True,600)):process_job(job.pk)
            job.refresh_from_db()
            self.assertGreaterEqual(job.available_at,timezone.now()+timedelta(seconds=599))
        self.assertEqual(job.state,'failed');self.assertEqual(job.attempts,5)
        self.shipment.refresh_from_db();self.assertEqual(self.shipment.status,before)
        self.assertFalse(self.shipment.confirmed_delay)
        retry_job(job.pk,self.ops);job.refresh_from_db();self.assertEqual(job.attempts,0)
        self.assertEqual(job.state,'pending')

    def test_broker_submission_failure_recovered_from_durable_pending_work(self):
        with patch('apps.tracking.tasks.process_job.apply_async',side_effect=ConnectionError('PRIVATE-REDIS')),self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.webhook().status_code,200)
        job=IntegrationJob.objects.get()
        with patch('apps.tracking.services.dispatch',return_value=True) as dispatch,self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(recover_pending(),1)
        dispatch.assert_called_once_with(job.pk)
        process_job(job.pk)
        self.assertEqual(WebhookReceipt.objects.get().state,'processed')

    def test_expired_worker_lease_and_stale_fence_are_safe(self):
        self.webhook();job=IntegrationJob.objects.get();old=claim_job(job.pk)
        self.assertIsNone(claim_job(job.pk))
        IntegrationJob.objects.filter(pk=job.pk).update(lease_until=timezone.now()-timedelta(seconds=1))
        recover_pending();fresh=claim_job(job.pk)
        self.assertNotEqual(old.lease_token,fresh.lease_token)
        process_receipt(old);self.assertEqual(TrackingEvent.objects.count(),0)
        process_receipt(fresh);self.assertEqual(TrackingEvent.objects.count(),1)

    def test_reconciliation_is_bounded_deduplicated_and_no_public_api_call(self):
        self.leg.next_reconcile_at=timezone.now()-timedelta(hours=7);self.leg.save()
        with patch('apps.tracking.tasks.adapter.request') as call:
            self.assertEqual(schedule_reconciliation(limit=1),1)
            self.assertEqual(schedule_reconciliation(limit=1),0)
            self.client.post('/en/',{'reference':self.shipment.reference})
            call.assert_not_called()
        self.shipment.status=Status.DELIVERED;self.shipment.save()
        IntegrationJob.objects.all().update(state='succeeded')
        self.leg.next_reconcile_at=timezone.now()-timedelta(days=1);self.leg.save()
        self.assertEqual(schedule_reconciliation(),0)

    def test_permanent_refresh_failure_requires_operator_review(self):
        self.leg.next_reconcile_at=timezone.now()-timedelta(days=1);self.leg.save()
        IntegrationJob.objects.create(kind='refresh',leg=self.leg,dedupe_key=f'refresh:{self.leg.pk}',state='failed',safe_error='provider_authentication')
        self.assertEqual(schedule_reconciliation(),0)
        job=IntegrationJob.objects.get();self.assertEqual(job.state,'failed')

    def test_stopped_notification_during_registration_is_not_overwritten(self):
        self.leg.registration_state='not_connected';self.leg.save()
        job=request_leg(self.leg.pk,'register',self.ops)
        claimed=claim_job(job.pk)
        body=json.loads((FIXTURES/'stopped.json').read_text());self.ingest(body)
        from apps.tracking.adapter import Outcome
        apply_response(claimed,Outcome(True))
        self.leg.refresh_from_db();job.refresh_from_db()
        self.assertEqual(self.leg.registration_state,'stopped')
        self.assertEqual(job.state,'quarantined')

    def test_readonly_permissions_admin_health_and_actions(self):
        self.client.force_login(self.reader)
        for language in ('en','ar'):
            r=self.client.get('/'+language+'/admin/integration-health/')
            self.assertEqual(r.status_code,200)
            self.assertNotContains(r,KEY)
        for action in ('register','refresh'):
            path=reverse('admin:tracking_leg_action',args=[self.leg.pk,action])
            self.assertEqual(self.client.post(path,{'confirm':'yes'}).status_code,403)
        with self.assertRaises(PermissionDenied):request_leg(self.leg.pk,'refresh',self.reader)
        empty=User.objects.create_user('DEMO-no-tracking-role',is_staff=True)
        self.client.force_login(empty)
        self.assertEqual(self.client.get('/en/admin/integration-health/').status_code,403)

    def test_consequential_actions_require_confirmation_post_and_csrf(self):
        c=Client(enforce_csrf_checks=True);c.force_login(self.ops)
        path=reverse('admin:tracking_leg_action',args=[self.leg.pk,'refresh'])
        self.assertEqual(c.get(path).status_code,200)
        self.assertEqual(IntegrationJob.objects.count(),0)
        self.assertEqual(c.post(path,{'confirm':'yes'}).status_code,403)
        self.client.force_login(self.ops)
        self.client.post(path,{})
        self.assertEqual(IntegrationJob.objects.count(),0)
        self.client.post(path,{'confirm':'yes'})
        self.assertEqual(IntegrationJob.objects.count(),1)

    def test_global_reference_uniqueness_and_registered_identity_retention(self):
        with self.assertRaises(IntegrityError),transaction.atomic():
            TrackingLeg.objects.create(shipment=self.shipment,sequence=2,carrier_identifier='3011',tracking_number=self.leg.tracking_number)
        self.leg.tracking_number='DEMO-CHANGED-0001'
        with self.assertRaises(ValidationError):save_child(self.leg,self.ops)

    def test_seed_carrier_demo_is_explicit_private_and_production_disabled(self):
        with override_settings(DEBUG=True),patch('apps.tracking.adapter.request') as outbound:
            call_command('seed_tracking_demo',stdout=io.StringIO())
            call_command('seed_tracking_demo',stdout=io.StringIO())
            outbound.assert_not_called()
        demo=Shipment.objects.get(internal_order='DEMO-CARRIER',is_demo=True)
        self.assertFalse(demo.published)
        self.assertEqual(TrackingEvent.objects.filter(shipment=demo).count(),1)
        from django.core.management.base import CommandError
        with override_settings(DEBUG=False),self.assertRaises(CommandError):call_command('seed_tracking_demo')


@override_settings(TRACK17_ENABLED=True, TRACK17_API_KEY=KEY)
class AdapterContractTests(SimpleTestCase):
    def setUp(self):cache.clear()

    def connection(self,status=200,body=None,headers=None):
        conn=MagicMock();response=conn.getresponse.return_value
        response.status=status;response.read.return_value=json.dumps(body or {'code':0,'data':{'accepted':[],'rejected':[]}}).encode()
        response.getheader.side_effect=lambda key,default=None:(headers or {}).get(key,default)
        return conn

    def test_fixed_https_host_path_token_and_no_redirect(self):
        conn=self.connection()
        with patch('apps.tracking.adapter.http.client.HTTPSConnection',return_value=conn) as factory:
            request('register',[{'number':'DEMO-001','carrier':3011}])
        self.assertEqual(factory.call_args.args[0],'api.17track.net')
        self.assertEqual(conn.request.call_args.args[:2],('POST','/track/v2.4/register'))
        self.assertEqual(conn.request.call_args.kwargs['headers']['17token'],KEY)
        cache.clear()
        with patch('apps.tracking.adapter.http.client.HTTPSConnection',return_value=self.connection(302)):
            with self.assertRaises(ProviderError) as error:request('register',[{'number':'DEMO-001','carrier':3011}])
        self.assertEqual(error.exception.code,'provider_http_rejected')

    def test_timeouts_rate_limits_authentication_and_bounded_response(self):
        for status,code in [(429,'provider_rate_limit'),(503,'provider_unavailable'),(401,'provider_authentication')]:
            cache.clear()
            with patch('apps.tracking.adapter.http.client.HTTPSConnection',return_value=self.connection(status,headers={'Retry-After':'600'})):
                with self.assertRaises(ProviderError) as error:request('gettrackinfo',[{'number':'DEMO-001','carrier':3011}])
            self.assertEqual(error.exception.code,code)
        cache.clear();conn=self.connection();conn.request.side_effect=TimeoutError('PRIVATE-TIMEOUT')
        with patch('apps.tracking.adapter.http.client.HTTPSConnection',return_value=conn),self.assertRaises(ProviderError) as error:request('gettrackinfo',[{'number':'DEMO-001','carrier':3011}])
        self.assertEqual(str(error.exception),'provider_timeout')
        cache.clear();conn=self.connection();conn.getresponse.return_value.read.return_value=b'x'*(1024*1024+1)
        with patch('apps.tracking.adapter.http.client.HTTPSConnection',return_value=conn),self.assertRaises(ProviderError):request('gettrackinfo',[{'number':'DEMO-001','carrier':3011}])

    def test_shared_rate_limit_and_failure_prevent_outbound_requests(self):
        conn=self.connection()
        with patch('apps.tracking.adapter.http.client.HTTPSConnection',return_value=conn) as factory:
            request('register',[{'number':'DEMO-001','carrier':3011}])
            with self.assertRaises(ProviderError) as error:request('register',[{'number':'DEMO-002','carrier':3011}])
            self.assertEqual(error.exception.code,'local_rate_limit');self.assertEqual(factory.call_count,1)
        with patch('apps.tracking.adapter.cache.add',side_effect=ConnectionError('PRIVATE-CACHE')),patch('apps.tracking.adapter.http.client.HTTPSConnection') as factory:
            with self.assertRaises(ProviderError) as error:request('register',[{'number':'DEMO-001','carrier':3011}])
            self.assertEqual(error.exception.code,'rate_store_unavailable');factory.assert_not_called()

    def test_invalid_contract_identifier_unknown_time_and_event_bounds(self):
        for carrier in ('not-a-carrier',0,True):
            with self.assertRaises(ProviderError):request('register',[{'number':'DEMO-001','carrier':carrier}])
        body=fixture();body['data']['track_info']['tracking']['providers'][0]['events']*=501
        with self.assertRaises(PayloadError):parse_webhook(json.dumps(body).encode())
        with self.assertRaises(PayloadError):normalize({'accepted':[fixture()['data']]})

    def test_official_event_stages_and_unknown_or_inconsistent_main_status(self):
        from apps.tracking.payloads import mapped
        body=fixture();event=body['data']['track_info']['tracking']['providers'][0]['events'][0]
        event['stage']='Departure';event['sub_status']='InTransit_Departure'
        self.assertEqual(normalize(body['data'])['events'][0]['status'],Status.DEPARTED)
        self.assertEqual(mapped('FutureStatus','InTransit_Departure'),'')
        self.assertEqual(mapped('Delivered','Exception_Cancel'),'')

    def test_already_registered_is_idempotent_and_unknown_business_errors_are_safe(self):
        data={'accepted':[],'rejected':[{'number':'DEMO-001','carrier':3011,'error':{'code':-18019901,'message':'PRIVATE-ERROR'}}]}
        self.assertTrue(outcome(data,'DEMO-001',3011,True).accepted)
        self.assertFalse(outcome(data,'DEMO-001',3011,False).accepted)
        data['rejected'][0]['error']['code']=-18019908
        with self.assertRaises(ProviderError) as error:outcome(data,'DEMO-001',3011,True)
        self.assertEqual(error.exception.code,'provider_quota')
