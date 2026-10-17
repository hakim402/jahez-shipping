"""Scoped production maintenance: status, pause, backup, migrate and resume."""
import argparse
import json
from production_tools import scope, call, contract

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('action', choices=('status','pause','backup','migrate','resume'))
parser.add_argument('--confirm-production', action='store_true')
parser.add_argument('--review-dir')
parser.add_argument('--cleanup-backup', help='Explicit old 0.8.1 archive path; data-loss approval required separately.')
args=parser.parse_args()
if not args.review_dir and args.action!='status' and not args.confirm_production:
    raise SystemExit('Production mutation refused without explicit approval and --confirm-production.')
project,compose=scope(args.review_dir)

def one(code):
    return call(compose+['run','--rm','--no-deps','--pull','never','web','python','-c',code],True)

try:
    model=json.loads(call(compose+['config','--format','json'],True));contract(model,project,bool(args.review_dir))
    # This helper cannot safely manage an old four-service release. Use the reviewed transition guide.
    for service in ('worker','beat'):
        if call(['docker','ps','-aq','--filter','label=com.docker.compose.project='+project,
                 '--filter','label=com.docker.compose.service='+service],True).strip():
            raise RuntimeError('Legacy runtime requires transition procedure')
    if args.action=='status':
        call(compose+['ps'])
    elif args.action=='pause':
        code="import os,json; p='/data/maintenance.lock'; fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); os.write(fd,json.dumps({'project':'jahez-shipping','operation':'foundation-release'}).encode()); os.close(fd)"
        call(compose+['exec','-T','web','python','-c',code],True)
        call(compose+['stop','-t','95','web'])
    else:
        if call(['docker','ps','-q','--filter','label=com.docker.compose.project='+project,
                 '--filter','label=com.docker.compose.service=web'],True).strip():raise RuntimeError('Web still running')
        one("import json; from pathlib import Path; assert json.loads(Path('/data/maintenance.lock').read_text())['project']=='jahez-shipping'")
        if args.action=='backup':
            call(compose+['run','--rm','--no-deps','--pull','never','web','python','scripts/backup.py','--quiesced'])
        elif args.action=='migrate':
            flags=[]
            if args.cleanup_backup:flags=['-e','SHIPPING_ALLOW_SCHEMA_CLEANUP=true','-e','SHIPPING_PRE_CLEANUP_ARCHIVE='+args.cleanup_backup]
            call(compose+['run','--rm','--no-deps','--pull','never']+flags+['web','python','manage.py','migrate','--noinput'])
        else:
            call(compose+['run','--rm','--no-deps','--pull','never','web','python','manage.py','migrate','--check'])
            one("from pathlib import Path; Path('/data/maintenance.lock').rename('/data/last-maintenance.json')")
            try:call(compose+['up','-d','--pull','never','--wait','--wait-timeout','120','web'])
            except Exception:
                one("from pathlib import Path; Path('/data/last-maintenance.json').rename('/data/maintenance.lock')")
                call(compose+['stop','-t','95','web']);raise
    print('PASS: scoped foundation release step. No code-only rollback is provided; restore matching database/files/image.')
except Exception:
    raise SystemExit('Release refused/failed. Preserve maintenance evidence and keep writers stopped. Check configuration, backup, schema and legacy-service presence privately.') from None
