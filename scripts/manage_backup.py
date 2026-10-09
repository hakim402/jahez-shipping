"""Scoped Docker quiescence wrapper; preserves volumes and resumes the same Shipping services."""
import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--environment',choices=['dev','prod'],default='dev')
parser.add_argument('--confirm-production',action='store_true')
parser.add_argument('--label',choices=['manual','pre-upgrade'],default='manual')
parser.add_argument('--retention-days',type=int,default=14)
parser.add_argument('--prune',action='store_true')
parser.add_argument('--export-dir',help='Explicit private mounted destination in the container; not proof it is off-server.')
args=parser.parse_args()
if args.environment=='prod' and not args.confirm_production:
    raise SystemExit('Production backup requires explicit --confirm-production; this pauses only Shipping writers.')
project='jahez-shipping-'+args.environment
compose=['docker','compose','--env-file','.env.'+args.environment,'-p',project,'-f','compose.'+args.environment+'.yml']
token=uuid.uuid4().hex

def run(parts,capture=False):
    return subprocess.run(parts,cwd=root,check=True,text=True,capture_output=capture)

enabled=False
try:
    code="from pathlib import Path; import json,os; p=Path('/data/maintenance.lock'); fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); os.write(fd,json.dumps({'project':'jahez-shipping','operation':'backup','token':'"+token+"'}).encode()); os.close(fd)"
    run(compose+['exec','-T','web','python','-c',code],True);enabled=True
    run(compose+['stop','-t','95','web','worker','beat'])
    for service in ('web','worker','beat'):
        active=run(['docker','ps','--filter','label=com.docker.compose.project='+project,
            '--filter','label=com.docker.compose.service='+service,'--format','{{.ID}}'],True).stdout.strip()
        if active:raise RuntimeError('Other Shipping writers are running; pause one-off jobs first.')
    command=compose+['run','--rm','--no-deps','--pull','never','web','python','scripts/backup.py','--quiesced','--label',args.label,'--retention-days',str(args.retention_days)]
    if args.prune:command+=['--prune']
    if args.export_dir:command+=['--export-dir',args.export_dir]
    run(command)
except Exception:
    print('Scoped backup failed or was refused. Incomplete archives are not recovery points; inspect private storage and service health.',file=sys.stderr)
    raise SystemExit(1) from None
finally:
    if enabled:
        code="from pathlib import Path; import json; p=Path('/data/maintenance.lock'); assert json.loads(p.read_text()).get('token')=='"+token+"'; p.unlink()"
        try:
            run(compose+['run','--rm','--no-deps','--pull','never','web','python','-c',code],True)
            run(compose+['up','-d','--pull','never','web','worker','beat'])
        except Exception:
            print('Shipping cleanup/resume failed. Inspect only this project; keep maintenance until its marker ownership and service state are verified.',file=sys.stderr)
            raise SystemExit(1) from None
