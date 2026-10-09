import hashlib
import io
import json
from pathlib import Path
from unittest.mock import patch
from django.conf import settings
from django.contrib.auth.models import User,Group
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase,override_settings
from django.utils import timezone
from apps.shipments.models import Customer,Shipment,TrackingEvent,TrackingLeg,Status
from apps.shipments.services import save_shipment,save_child
from apps.shipments.uploads import inspect_upload,store_document
from apps.core.management.commands.seed_demo import sample_pdf
from apps.ai.management.commands.seed_ai_demo import extraction_fixture
from apps.ai import services
from apps.ai.models import AIDraft
from apps.tracking.models import IntegrationJob
from apps.tracking.tasks import process_job


@override_settings(GROQ_ENABLED=True,GROQ_API_KEY='SYNTHETIC-ONLY',GROQ_TEXT_MODEL='SYNTHETIC',TRACK17_ENABLED=True,TRACK17_API_KEY='SYNTHETIC-ONLY')
class EndToEndTests(TestCase):
    def test_creation_manual_signed_mock_carrier_review_and_private_public_lookup(self):
        call_command('setup_roles',stdout=io.StringIO())
        actor=User.objects.create_user('SYNTHETIC-flow',is_staff=True)
        actor.groups.add(Group.objects.get(name='Shipping Operations'))
        customer=Customer.objects.create(name='PRIVATE-CUSTOMER',phone='PRIVATE-PHONE')
        ship=Shipment(customer=customer,internal_order='PRIVATE-ORDER',tracking_mode='hybrid',
            origin_en='China',origin_ar='الصين',destination_en='UAE',destination_ar='الإمارات',published=True)
        save_shipment(ship,actor)
        ship.status=Status.WAREHOUSE;save_shipment(ship,actor,ship.revision)
        manual=TrackingEvent(shipment=ship,title_en='Received at warehouse',title_ar='تم الاستلام في المستودع',public=True)
        save_child(manual,actor)
        leg=TrackingLeg(shipment=ship,carrier_identifier='3011',tracking_number='DEMO-CARRIER-0001',registration_state='registered')
        save_child(leg,actor)
        body=json.loads((Path(settings.BASE_DIR)/'tests/fixtures/tracking/updated.json').read_text())
        event=body['data']['track_info']['latest_event'];event['time_utc']=timezone.now().isoformat()
        event['time_iso']=event['time_utc'];event['description']='PRIVATE-CARRIER-RAW'
        body['data']['track_info']['tracking']['providers'][0]['events']=[event]
        raw=json.dumps(body).encode();sign=hashlib.sha256(raw+b'/SYNTHETIC-ONLY').hexdigest()
        with patch('apps.tracking.services.dispatch',return_value=False):
            response=self.client.post('/webhooks/17track/',raw,content_type='application/json',HTTP_SIGN=sign)
        self.assertEqual(response.status_code,200)
        job=IntegrationJob.objects.get();process_job(job.pk);process_job(job.pk)
        ship.refresh_from_db();self.assertEqual(ship.status,Status.TRANSIT)
        self.assertEqual(ship.events.filter(source='carrier').count(),1)
        self.assertIsNone(ship.eta);self.assertIsNone(ship.delivered_at)
        upload=SimpleUploadedFile('SYNTHETIC.pdf',sample_pdf(),content_type='application/pdf')
        doc=store_document(ship,upload,'bill',inspect_upload(upload),actor)
        self.assertEqual(Path(doc.file.path).stat().st_mode&0o777,0o600)
        with patch('apps.ai.services.dispatch',return_value=False):
            draft=services.request_draft(ship.pk,'extraction',actor,document_id=doc.pk,consent=True)
        with patch('apps.ai.services.generate',return_value=(extraction_fixture(),'SYNTHETIC',1,{})):
            services.process(draft.pk)
        draft.refresh_from_db();self.assertEqual(draft.state,'ready')
        services.apply_extraction(draft.pk,actor,draft.output,['bill_number'],[0])
        draft.refresh_from_db();ship.refresh_from_db()
        self.assertEqual(draft.state,'applied');self.assertEqual(ship.status,Status.TRANSIT)
        self.assertEqual(ship.items.count(),1);self.assertFalse(ship.items.get().public)
        for language in ('en','ar'):
            response=self.client.post('/'+language+'/',{'reference':ship.reference})
            self.assertEqual(response.status_code,200)
            for private in ('PRIVATE-CUSTOMER','PRIVATE-PHONE','PRIVATE-ORDER','PRIVATE-CARRIER-RAW',ship.bill_number,'DEMO-CARRIER-0001'):
                self.assertNotIn(private.encode(),response.content)
            self.assertIn((manual.title_ar if language=='ar' else manual.title_en).encode(),response.content)
            self.assertEqual(response['Cache-Control'],'no-store')
        self.assertEqual(self.client.get('/en/admin/shipments/document/'+str(doc.pk)+'/download/').status_code,302)
