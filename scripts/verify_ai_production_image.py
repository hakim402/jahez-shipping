"""Run only in a --network none disposable production-image container, no mounted data."""
import os
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
root=Path(tempfile.mkdtemp(prefix='jahez-offline-production-'))
os.environ.update(DJANGO_SETTINGS_MODULE='config.settings.production',DJANGO_SECRET_KEY='offline-synthetic-only-'+ 'x'*64,DJANGO_ALLOWED_HOSTS='shipping.jahez.online',DJANGO_CSRF_TRUSTED_ORIGINS='https://shipping.jahez.online',SHIPPING_DATA_DIR=str(root),TRACK17_ENABLED='false',TRACK17_API_KEY='',GROQ_ENABLED='false',GROQ_API_KEY='')
import django
django.setup()
from django.conf import settings
from django.core.management import call_command, CommandError
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.test import Client, override_settings
from django.utils import timezone
from apps.shipments.models import Customer, Shipment, Document
from apps.core.management.commands.seed_demo import sample_pdf
from apps.ai.management.commands.seed_ai_demo import extraction_fixture,scanned_pdf
from apps.ai.documents import extract_document
from apps.ai.models import AIDraft
from apps.ai.sources import version,digest
from apps.ai.provider import generate
from unittest.mock import patch
import hashlib
import json
import httpx

assert not settings.DEBUG
call_command('migrate',verbosity=0)
with override_settings(CACHES={'default':{'BACKEND':'django.core.cache.backends.locmem.LocMemCache'}}):
    ship=Shipment.objects.create(customer=Customer.objects.create(name='SYNTHETIC PRIVATE CUSTOMER'),published=True,origin_en='China',origin_ar='الصين',destination_en='UAE',destination_ar='الإمارات')
    for name,data in [('DEMO.pdf',sample_pdf()),('DEMO-scan.pdf',scanned_pdf())]:
        stored=default_storage.save('documents/'+name,ContentFile(data))
        doc=Document.objects.create(shipment=ship,file=stored,original_filename=name,checksum=hashlib.sha256(data).hexdigest(),size=len(data),mime_type='application/pdf')
        source=extract_document(doc)
        if 'scan' in name:
            assert source['images'] and source['records'][0]['scanned']
        else:
            assert not source['images'] and 'Bill: DEMO-BILL-001' in source['records'][0]['text']
            original_init=httpx.Client.__init__
            requests=[]
            def handler(request):
                requests.append(request)
                return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(extraction_fixture())}}],'usage':{'total_tokens':30}},request=request)
            def init(client,**kwargs):
                kwargs['transport']=httpx.MockTransport(handler);original_init(client,**kwargs)
            with override_settings(GROQ_ENABLED=True,GROQ_API_KEY='SYNTHETIC-ONLY',GROQ_TEXT_MODEL='SYNTHETIC'),patch('httpx.Client.__init__',new=init):
                output,model,latency,usage=generate('extraction',source)
            assert requests[0].url.path=='/openai/v1/chat/completions' and usage['total_tokens']==30
            AIDraft.objects.create(shipment=ship,document=doc,kind='extraction',state='ready',dedupe_key=digest(['offline']),source={**source,'images':[]},source_version=version(ship),output=output,expires_at=timezone.now()+timezone.timedelta(days=30))
    client=Client()
    for lang in ('en','ar'):
        response=client.post('/'+lang+'/',{'reference':ship.reference},secure=True,HTTP_HOST='shipping.jahez.online')
        assert response.status_code==200 and 'no-store' in response['Cache-Control']
        assert b'SYNTHETIC PRIVATE CUSTOMER' not in response.content and b'DEMO-BILL-001' not in response.content
    try:call_command('seed_ai_demo',verbosity=0)
    except CommandError:pass
    else:raise AssertionError('Production seed must be refused.')
    from django.templatetags.static import static
    assert '/static/' in static('css/admin.css')
    assert not ship.items.exists() and ship.bill_number==''
    from types import SimpleNamespace
    from apps.ai.operations import execute
    staff=SimpleNamespace(is_staff=True,is_active=True,has_perm=lambda permission:True)
    matches=execute(staff,{'tool':'status','status':'created'})
    assert matches['count']==1 and len(matches['rows'])==1
    assert 'SYNTHETIC PRIVATE CUSTOMER' not in str(matches) and 'DEMO-BILL-001' not in str(matches)
    from apps.ai.models import AssistantRun
    assert AssistantRun.objects.count()==0
print('PASS: offline production migrations/manifest, actual digital/scan conversion, SDK mock transport, private/public EN-AR separation, DEMO guard and bounded operational query projection. No accounts, live provider requests or live service/volume created.')
