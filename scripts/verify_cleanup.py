"""Synthetic cleanup/migration/recovery/production review. Never mounts owner env/data."""
import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path
from production_tools import ROOT, scope, call, contract
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--image',default='jahez-shipping-cleanup:0.9.0')
parser.add_argument('--old-image',default='sha256:60dd55dc3c2f781c9ea2f10d75729b05fbed21f783cc34e6f746e4fe63db4db3')
args=parser.parse_args()
base=ROOT/'private/cleanup-review';base.mkdir(parents=True,exist_ok=True)
directory=Path(tempfile.mkdtemp(prefix='compose-',dir=base));directory.chmod(0o700)
review=directory/'review';review.mkdir(mode=0o700)
env=directory/'review.env';override=directory/'review.yml'
text=(ROOT/'.env.prod.example').read_text().replace('REPLACE_WITH_INDEPENDENT_RANDOM_SECRET_AT_LEAST_50_CHARACTERS',secrets.token_urlsafe(64)).replace('SHIPPING_IMAGE=jahez-shipping:0.9.0','SHIPPING_IMAGE='+args.image)
text+='\nSHIPPING_ENV_FILE='+json.dumps(str(env))+'\n';env.write_text(text);env.chmod(0o600)
os.environ.update(SHIPPING_ENV_FILE=str(env),SHIPPING_IMAGE=args.image,SHIPPING_WEB_MEMORY='768m',SHIPPING_REDIS_MEMORY='256m')
override.write_text('services:\n  web:\n    ports: !reset []\n')
project,compose=scope(directory)
if call(['docker','ps','-aq','--filter','label=com.docker.compose.project='+project],True).strip():raise SystemExit('Existing review resources preserved; do not run concurrent verifiers.')
model=json.loads(call(compose+['config','--format','json'],True));contract(model,project,True)
uid=str(os.getuid())+':'+str(os.getgid())

def fixture(image,name):
    # Mount only this synthetic review tree and one explicit test file, never owner env/source/private paths.
    mount=['--mount','type=bind,src='+str(review)+',dst=/review',
           '--mount','type=bind,src='+str(ROOT/'tests'/name)+',dst=/fixture.py,readonly']
    call(['docker','run','--rm','--network','none','--user',uid]+mount+[image,'python','/fixture.py'])

try:
    call([sys.executable,'scripts/preflight.py','--review-dir',str(directory)])
    fixture(args.old_image,'legacy_transition_fixture.py')
    fixture(args.image,'verify_transition_candidate.py')
    fixture(args.old_image,'verify_legacy_restore.py')
    call(['docker','run','--rm','--network','none',args.image,'python','-m','pip','check'])
    no_retired="import importlib.util; assert not any(importlib.util.find_spec(m) for m in ('celery','kombu','billiard','pypdf','pypdfium2','PIL')); print('PASS: retired job/document dependencies absent from candidate runtime.')"
    call(['docker','run','--rm','--network','none',args.image,'python','-c',no_retired])
    call(compose+['up','-d','--pull','never','--wait','--wait-timeout','120','redis'])
    call(compose+['run','--rm','--no-deps','--pull','never','web','python','manage.py','migrate','--noinput'])
    call(compose+['run','--rm','--no-deps','--pull','never','web','python','manage.py','check','--deploy','--fail-level','ERROR'])
    call(compose+['up','-d','--pull','never','--wait','--wait-timeout','120','web'])
    check="""import urllib.request,re,os,json
from pathlib import Path
h={'Host':'shipping.jahez.online','X-Forwarded-Proto':'https'}
for lang in ('en','ar'):
 r=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8000/'+lang+'/',headers=h));html=r.read().decode()
 assert r.status==200 and r.headers['X-Request-ID'] and 'name="code"' in html and 'type="submit"' in html
 css=re.search(r'href="(/static/css/site[^"]+)"',html).group(1);assert re.search(r'/site[.][0-9a-f]+[.]css',css)
 assert urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8000'+css,headers=h)).status==200
assert os.getuid()==10001 and not Path('/app/.env.dev').exists() and not Path('/app/.env.prod').exists()
try:Path('/app/cleanup-write-probe').write_text('synthetic')
except OSError as e:assert e.errno==30
else:raise AssertionError('Writable root')
import django;django.setup()
from django.db import connection
assert not any(t.startswith(('shipments_','tracking_','ai_')) for t in connection.introspection.table_names())
from django.core.cache import cache
assert cache.get('synthetic-shared-counter')==2
from django.contrib.auth.models import User
assert User.objects.filter(username='synthetic-production-admin').exists()
p=Path('/data/private/synthetic-retained.bin');assert p.read_bytes()==b'SYNTHETIC PERSISTENCE'
print('PASS: production-mode fresh clean schema, EN/AR/code form/hashed assets, nonroot/readonly root, shared Redis counters and retained synthetic data.')
"""
    first="import django; django.setup(); from django.core.cache import cache; cache.set('synthetic-shared-counter',1,900); from django.contrib.auth.models import User; User.objects.create_superuser('synthetic-production-admin','',None); from pathlib import Path; Path('/data/private/synthetic-retained.bin').write_bytes(b'SYNTHETIC PERSISTENCE')"
    second="import django; django.setup(); from django.core.cache import cache; assert cache.incr('synthetic-shared-counter')==2"
    call(compose+['exec','-T','web','python','-c',first]);call(compose+['exec','-T','web','python','-c',second])
    call(compose+['exec','-T','web','python','-c',check])
    for action in ('pause','backup','resume'):
        call([sys.executable,'scripts/release.py',action,'--review-dir',str(directory)])
    call(compose+['up','-d','--pull','never','--force-recreate','--wait','--wait-timeout','120','web'])
    call(compose+['exec','-T','web','python','-c',check])
    restore="from pathlib import Path; from apps.core.recovery import verify,restore; a=next(Path('/data/backups').glob('[0-9]*')); m=verify(a); assert m['records']['auth_user']==1; restore(a,'/data/isolated-restore'); print('PASS: reduced production-mode backup and isolated auth/private-file restore.')"
    call(compose+['exec','-T','web','python','-c',restore])
    (directory/'result.json').write_text(json.dumps({'passed':True,'image':args.image,'old_image':args.old_image,'project':project}))
    print('PASS: cleanup candidate/fresh/legacy/old-image recovery/production recreation. Private synthetic evidence retained: '+str(directory))
finally:
    # Exact reviewed project names only; never prune or remove owner resources.
    call(compose+['down','--remove-orphans'])
    for volume in model['volumes'].values():
        found=subprocess.run(['docker','volume','inspect',volume['name']],capture_output=True).returncode==0
        if found:call(['docker','volume','rm',volume['name']])
