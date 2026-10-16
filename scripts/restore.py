import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from apps.core.recovery import restore
parser=argparse.ArgumentParser(description='Restore a verified Shipping recovery point into an isolated empty directory, or explicitly confirmed paused Shipping data.')
parser.add_argument('--backup',required=True)
parser.add_argument('--target',required=True)
parser.add_argument('--replace',action='store_true')
parser.add_argument('--confirm-target',default='',help='Exact absolute existing target; required before replacing it.')
parser.add_argument('--quiesced',action='store_true')
parser.add_argument('--allow-damaged-target',action='store_true',help='Explicit recovery over an invalid Shipping DB/document mapping; retain damaged originals.')
args=parser.parse_args()
print('Restore target: '+str(Path(args.target).absolute()))
try:
    result=restore(args.backup,args.target,args.replace,args.confirm_target,args.quiesced,args.allow_damaged_target)
    print('PASS: restored matching database/files verified; files='+str(result['files'])+'; prior target retained='+str(result['rollback_retained']))
except Exception:
    print('Restore refused or failed. Keep writers paused; inspect private target/rollback/staging and backup validation. No source archive was modified.',file=sys.stderr)
    raise SystemExit(1) from None
