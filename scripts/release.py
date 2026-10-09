"""Explicit paused Shipping release workflow. Failed steps keep writers paused."""
import argparse
import json
from production_tools import scope,call
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('action',choices=['pause','backup','migrate','resume','rollback-check','status'])
parser.add_argument('--confirm-production',action='store_true');parser.add_argument('--review-dir')
args=parser.parse_args()
if not args.review_dir and args.action!='status' and not args.confirm_production:raise SystemExit('Mutating production release steps require --confirm-production; Phase 9 approval still required.')
project,compose=scope(args.review_dir)

def one(code):return call(compose+['run','--rm','--no-deps','--pull','never','web','python','-c',code],True)
def quiet():
    for svc in ('web','worker','beat'):
        if call(['docker','ps','--filter','label=com.docker.compose.project='+project,'--filter','label=com.docker.compose.service='+svc,'--format','{{.ID}}'],True).strip():raise RuntimeError('Writers still active.')
def marked():
    return one("import json; from pathlib import Path; m=json.loads(Path('/data/maintenance.lock').read_text()); assert m['project']=='jahez-shipping' and m['operation']=='release'; print('marked')")
schema_code="import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.production'); import django; django.setup(); import hashlib,json; from django.db import connection; c=connection.cursor(); c.execute(\"SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name\"); print(hashlib.sha256(json.dumps(c.fetchall()).encode()).hexdigest())"
try:
    if args.action=='pause':
        container=call(compose+['ps','-q','web'],True).strip();assert container
        old_image=call(['docker','inspect','--format','{{.Image}}',container],True).strip()
        schema=call(compose+['exec','-T','web','python','-c',schema_code],True).strip()
        code="import os,json,uuid; from pathlib import Path; p=Path('/data/maintenance.lock'); fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); os.write(fd,json.dumps({'project':'jahez-shipping','operation':'release','token':uuid.uuid4().hex,'old_image':"+repr(old_image)+",'schema':"+repr(schema)+"}).encode()); os.close(fd)"
        call(compose+['exec','-T','web','python','-c',code],True)
        call(compose+['stop','-t','95','web','worker','beat']);quiet()
        print('PASS: only Shipping writers paused; release marker retains old image/schema. Keep marker until migration/restore checks pass.')
    elif args.action=='status':
        call(compose+['ps']);print('Release marker inspection requires its private volume; no token/environment dumped.')
    else:
        quiet();marked()
        if args.action=='backup':
            model=json.loads(call(compose+['config','--format','json'],True))
            target=call(['docker','image','inspect','--format','{{.Id}}',model['services']['web']['image']],True).strip()
            one("import json; from pathlib import Path; m=json.loads(Path('/data/maintenance.lock').read_text()); assert m['old_image']=="+repr(target))
            call(compose+['run','--rm','--no-deps','--pull','never','web','python','scripts/backup.py','--quiesced','--label','pre-upgrade'])
        elif args.action=='migrate':
            call(compose+['run','--rm','--no-deps','--pull','never','web','python','manage.py','migrate','--noinput'])
            call(compose+['run','--rm','--no-deps','--pull','never','web','python','manage.py','check','--deploy','--fail-level','ERROR'])
            print('PASS: one-off migration/system checks; writers remain paused.')
        elif args.action=='rollback-check':
            current=one(schema_code).strip()
            image=one("import json; from pathlib import Path; m=json.loads(Path('/data/maintenance.lock').read_text()); assert m['schema']=="+repr(current)+"; print(m['old_image'])").strip()
            print('Rollback SHIPPING_IMAGE: '+image)
            print('PASS: schema matches before upgrade. Use the marker old_image SHA as SHIPPING_IMAGE, check migrations, then resume. If schema changed, restore the matching recovery point instead.')
        elif args.action=='resume':
            model=json.loads(call(compose+['config','--format','json'],True))
            target=call(['docker','image','inspect','--format','{{.Id}}',model['services']['web']['image']],True).strip()
            current=one(schema_code).strip()
            one("import json; from pathlib import Path; m=json.loads(Path('/data/maintenance.lock').read_text()); assert m['old_image']!="+repr(target)+" or m['schema']=="+repr(current))
            call(compose+['run','--rm','--no-deps','--pull','never','web','python','manage.py','migrate','--check'])
            one("import json; from pathlib import Path; p=Path('/data/maintenance.lock'); m=json.loads(p.read_text()); assert m['operation']=='release'; p.rename(Path('/data/last-release.json'))")
            try:
                call(compose+['up','-d','--pull','never','--wait','--wait-timeout','120','web'])
                call(compose+['up','-d','--pull','never','--wait','--wait-timeout','120','worker','beat'])
            except Exception:
                one("from pathlib import Path; p=Path('/data/last-release.json'); p.rename(Path('/data/maintenance.lock'))")
                call(compose+['stop','-t','95','web','worker','beat']);raise
            print('PASS: Shipping web ready and one worker/Beat healthy; release metadata retained privately.')
except Exception:
    raise SystemExit('Release step refused/failed. Keep Shipping writers paused; inspect safe diagnostics and the private maintenance marker. No unrelated project touched.') from None
