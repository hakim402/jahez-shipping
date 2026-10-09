"""Invented local proposals, digital/scanned inputs, no provider or account creation."""
import io
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from apps.shipments.models import Shipment, TrackingEvent
from apps.shipments.uploads import inspect_upload, store_document
from apps.core.management.commands.seed_demo import sample_pdf
from apps.ai.models import AIDraft
from apps.ai.documents import extract_document
from apps.ai.schemas import validate_output
from apps.ai.sources import build_history, digest, version


def extraction_fixture():
    return {'fields':[{'field':'bill_number','value':'DEMO-BILL-001','source_ids':['page:1'],'source_snippet':'Bill: DEMO-BILL-001'}],
        'identifiers':[{'kind':'bill','value':'DEMO-BILL-001','source_ids':['page:1'],'source_snippet':'Bill: DEMO-BILL-001'}],
        'items':[{'description_source':'DEMO reusable drinkware','description_en':'DEMO reusable drinkware','description_ar':'أكواب تجريبية','quantity':'120','unit':'units','unit_ar':'قطعة','source_ids':['page:1'],'source_snippet':'Quantity: 120 units'}],
        'missing_or_uncertain':['Carrier-issued tracking number is not provided.', 'Arrival estimate is unknown.'],
        'warnings':['SYNTHETIC local fixture, not an AI-generated extraction.']}


def scanned_pdf():
    from PIL import Image, ImageDraw
    image = Image.new('RGB', (1200,1600), 'white')
    draw=ImageDraw.Draw(image)
    for i,line in enumerate(['SYNTHETIC DEMO SCANNED INVOICE','Invoice: DEMO-SCAN-002','Product: DEMO packing boxes','Quantity: 24 boxes','No carrier tracking number or ETA provided.']):
        draw.text((80,150+i*90), line, fill='black', font_size=30)
    output=io.BytesIO();image.save(output,'PDF');image.close()
    return output.getvalue()


class Command(BaseCommand):
    help='Seed labeled private AI review fixtures and bounded digital/scanned PDF conversion; development only.'
    def handle(self,*args,**options):
        if not settings.DEBUG:
            raise CommandError('AI demonstration is development-only.')
        call_command('seed_demo',stdout=self.stdout)
        customer=Shipment.objects.get(internal_order='DEMO-MANUAL',is_demo=True).customer
        shipment, _=Shipment.objects.get_or_create(internal_order='DEMO-AI',is_demo=True,defaults={'customer':customer,'internal_notes':'Invented local AI workflow; private by default.'})
        for name, data in [('DEMO-digital-bill.pdf',sample_pdf()),('DEMO-scanned-invoice.pdf',scanned_pdf())]:
            if not shipment.documents.filter(original_filename=name).exists():
                upload=SimpleUploadedFile(name,data,content_type='application/pdf')
                store_document(shipment,upload,'bill' if 'digital' in name else 'invoice',inspect_upload(upload),None,system_demo=True)
        event,_=TrackingEvent.objects.get_or_create(shipment=shipment,title_en='DEMO goods received',defaults={'title_ar':'استلام بضائع تجريبية','body_en':'Synthetic local event. Arrival estimate unknown.','body_ar':'حدث تجريبي محلي. موعد الوصول غير معروف.','public':False})
        initial_version=version(shipment)
        for document in shipment.documents.order_by('pk'):
            marker=digest(['seed_ai_demo',shipment.pk,document.checksum,initial_version])
            if AIDraft.objects.filter(dedupe_key=marker).exists():
                continue
            source=extract_document(document)
            source['images']=[]
            source['warnings'].append('SYNTHETIC local conversion and proposal review only.')
            output=extraction_fixture()
            if 'scanned' in document.original_filename:
                output={'fields':[], 'identifiers':[{'kind':'invoice','value':'DEMO-SCAN-002','source_ids':['page:1'],'source_snippet':'Invoice: DEMO-SCAN-002'}], 'items':[{'description_source':'DEMO packing boxes','description_en':'DEMO packing boxes','description_ar':'صناديق تعبئة تجريبية','quantity':'24','unit':'boxes','unit_ar':'صندوق','source_ids':['page:1'],'source_snippet':'Quantity: 24 boxes'}], 'missing_or_uncertain':['Bill, carrier reference and arrival estimate are unknown.'], 'warnings':['SYNTHETIC manually supplied scan proposal. Verify visually; no OCR/model call was made.']}
            validate_output('extraction',output,source)
            AIDraft.objects.create(shipment=shipment,document=document,kind='extraction',state='ready',source=source,output=output,source_version=initial_version,dedupe_key=marker,is_demo=True,model='SYNTHETIC-LOCAL-FIXTURE',expires_at=timezone.now()+timezone.timedelta(days=settings.GROQ_RETENTION_DAYS))
        for kind in ('summary','message'):
            marker=digest(['seed_ai_demo',shipment.pk,kind,initial_version])
            if AIDraft.objects.filter(dedupe_key=marker).exists():
                continue
            source=build_history(shipment)
            output={'statements':[{'english':'DEMO goods received. Arrival estimate is unknown.','arabic':'تم استلام البضائع التجريبية. موعد الوصول غير معروف.','source_ids':[f'event:{event.pk}','shipment']}], 'warnings':['SYNTHETIC local writing fixture; staff must verify its cited sources.']}
            validate_output(kind,output,source)
            AIDraft.objects.create(shipment=shipment,kind=kind,state='ready',source=source,output=output,source_version=initial_version,dedupe_key=marker,is_demo=True,model='SYNTHETIC-LOCAL-FIXTURE',expires_at=timezone.now()+timezone.timedelta(days=settings.GROQ_RETENTION_DAYS))
        self.stdout.write(self.style.SUCCESS('DEMO-AI: four private local drafts ready; digital extraction and scan rendering verified. No Groq/17TRACK requests, user account, publication or customer message sent.'))
