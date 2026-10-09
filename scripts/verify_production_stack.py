"""Synthetic Phase 8 full Compose review; fixed independent names, no host ports/providers."""
import argparse
import hashlib
import json
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path
from production_tools import ROOT,scope,call,contract
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--keep',action='store_true',help='Retain synthetic review containers/volumes for inspection; still no host port.');args=parser.parse_args()
directory=Path(tempfile.mkdtemp(prefix='jahez-phase08-',dir='/private/tmp' if Path('/private/tmp').exists() else '/tmp'));directory.chmod(0o700)
env=directory/'review.env';override=directory/'review.yml'
text=(ROOT/'.env.prod.example').read_text().replace('REPLACE_WITH_INDEPENDENT_RANDOM_SECRET_AT_LEAST_50_CHARACTERS',secrets.token_urlsafe(64))
text+='\nSHIPPING_ENV_FILE='+str(env)+'\n';env.write_text(text);env.chmod(0o600)
override.write_text('services:\n  web:\n    ports: !reset []\n')
project,compose=scope(directory)
if call(['docker','ps','-aq','--filter','label=com.docker.compose.project='+project],True).strip():raise SystemExit('Existing review project preserved; inspect it before rerunning.')
completed=False
validated=False
try:
    model=json.loads(call(compose+['config','--format','json'],True));contract(model,project,True)
    validated=True
    call(['python3','scripts/preflight.py','--review-dir',str(directory)])
    bad=subprocess.run(['docker','run','--rm','--network','none','--env-file',str(env),'-e','DJANGO_SECRET_KEY=PRIVATE-INVALID-SECRET',model['services']['web']['image'],'python','manage.py','check'],capture_output=True,text=True)
    assert bad.returncode and 'DJANGO_SECRET_KEY' in bad.stderr and 'PRIVATE-INVALID-SECRET' not in bad.stderr
    print('PASS: production startup rejects an insecure secret with field-only diagnostics.')
    call(compose+['up','-d','--pull','never','--wait','--wait-timeout','120','redis'])
    call(compose+['run','--rm','--no-deps','--pull','never','web','python','manage.py','migrate','--noinput'])
    call(compose+['run','--rm','--no-deps','--pull','never','web','python','manage.py','setup_roles'])
    call(compose+['up','-d','--pull','never','--wait','--wait-timeout','120','web','worker','beat'])
    fixture="""import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.production'); import django; django.setup()
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from apps.shipments.models import Shipment,Customer,Document
from apps.core.management.commands.seed_demo import sample_pdf
from apps.ai.sources import digest
import json,hashlib
from pathlib import Path
assert not settings.DEBUG and not settings.TRACK17_ENABLED and not settings.GROQ_ENABLED and os.getuid()==10001
customer=Customer.objects.create(name='SYNTHETIC PHASE08 PRIVATE CUSTOMER')
ship=Shipment.objects.create(customer=customer,internal_order='SYNTHETIC-PACKAGING',published=True,origin_en='China',origin_ar='الصين',destination_en='UAE',destination_ar='الإمارات')
data=sample_pdf();name=default_storage.save('documents/SYNTHETIC.pdf',ContentFile(data))
Document.objects.create(shipment=ship,file=name,original_filename='SYNTHETIC.pdf',size=len(data),checksum=hashlib.sha256(data).hexdigest(),mime_type='application/pdf')
p=Path('/data/phase08-baseline.json');p.write_text(json.dumps({'shipment':ship.pk,'reference':ship.reference,'documents':Document.objects.count(),'file':name,'checksum':hashlib.sha256(data).hexdigest()}));p.chmod(0o600)
print('Synthetic production-mode shipment/private PDF baseline created; no account or provider call.')
"""
    call(compose+['exec','-T','web','python','-c',fixture])
    check="""import json,urllib.request,urllib.error,http.cookiejar,hashlib,re,os
from pathlib import Path
b=json.loads(Path('/data/phase08-baseline.json').read_text());headers={'Host':'shipping.jahez.online','X-Forwarded-Proto':'https'}
jar=http.cookiejar.CookieJar();opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
for lang in ('en','ar'):
 r=opener.open(urllib.request.Request('http://127.0.0.1:8000/'+lang+'/',headers=headers));html=r.read().decode();assert r.status==200 and r.headers['X-Request-ID']
 assert 'SYNTHETIC PHASE08 PRIVATE CUSTOMER' not in html
 css=re.search(r'href="(/static/css/site[^\"]+\\.css)"',html).group(1);assert opener.open(urllib.request.Request('http://127.0.0.1:8000'+css,headers=headers)).status==200
assert hashlib.sha256((Path('/data/private')/b['file']).read_bytes()).hexdigest()==b['checksum']
import django;django.setup()
from apps.shipments.models import Shipment,Document
ship=Shipment.objects.get(pk=b['shipment']);assert ship.reference==b['reference'] and ship.published and Document.objects.count()==b['documents']
try:Path('/app/phase08-write-probe').write_text('synthetic')
except OSError as error:assert error.errno==30
else:raise AssertionError('Production root is writable')
assert not Path('/app/.env.prod').exists() and os.getuid()==10001
print('PASS: production-mode EN/AR HTTP, correlation, hashed CSS, nonroot/private-file persistence; no host port or account.')
"""
    call(compose+['exec','-T','web','python','-c',check])
    call(['python3','scripts/release.py','pause','--review-dir',str(directory)])
    call(['python3','scripts/release.py','backup','--review-dir',str(directory)])
    call(['python3','scripts/release.py','migrate','--review-dir',str(directory)])
    # Deliberately change ONLY this disposable DB's schema to exercise rollback safety.
    def alter(statement):
        code='import sqlite3; c=sqlite3.connect("/data/shipping.sqlite3"); c.execute('+repr(statement)+'); c.commit(); c.close()'
        call(compose+['run','--rm','--no-deps','--pull','never','web','python','-c',code])
    alter('CREATE TABLE SYNTHETIC_PHASE08_SCHEMA_FAILURE (id integer)')
    for action in ('rollback-check','resume'):
        refusal=subprocess.run(['python3','scripts/release.py',action,'--review-dir',str(directory)],capture_output=True,text=True)
        assert refusal.returncode and 'Keep Shipping writers paused' in refusal.stderr
    assert not call(['docker','ps','-q','--filter','label=com.docker.compose.project='+project,'--filter','label=com.docker.compose.service=web'],True).strip()
    alter('DROP TABLE SYNTHETIC_PHASE08_SCHEMA_FAILURE')
    print('PASS: changed-schema rollback/resume refused and web remained paused; temporary fixture removed.')
    call(['python3','scripts/release.py','rollback-check','--review-dir',str(directory)])
    call(['python3','scripts/release.py','resume','--review-dir',str(directory)])
    call(compose+['up','-d','--pull','never','--force-recreate','--wait','--wait-timeout','120','web','worker','beat'])
    call(compose+['exec','-T','web','python','-c',check])
    restore="""from pathlib import Path
from apps.core.recovery import restore,verify
archives=list(Path('/data/backups').glob('[0-9]*'));assert len(archives)==1
manifest=verify(archives[0]);assert manifest['documents']==1
restore(archives[0],Path('/data/isolated-restore'))
print('PASS: quiesced production-mode backup/isolated restore; one synthetic private document, schema/files verified.')
"""
    call(compose+['exec','-T','web','python','-c',restore]);completed=True
    print('PASS: isolated full production Compose boot/migrations/health/recreation/release/backup/restore. No real production/dev data or server changed.')
finally:
    if not args.keep and validated:
        # Only fixed synthetic project labels and the exact names validated above can be removed.
        call(compose+['down','--remove-orphans'])
        for name in model['volumes'].values():
            exists=subprocess.run(['docker','volume','inspect','--format','{{.Name}}',name['name']],capture_output=True).returncode==0
            if exists:call(['docker','volume','rm',name['name']])
        import shutil
        shutil.rmtree(directory)
    elif completed:print('Synthetic review resources retained privately: '+str(directory))
