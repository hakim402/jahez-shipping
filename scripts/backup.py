"""Manual/quiesced backup or verification. No secret values or manifest filenames printed."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from apps.core.recovery import backup,verify,prune
from apps.core.recovery import allowed,secure_tree
import shutil
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--data-dir',default='/data')
parser.add_argument('--destination',default='/data/backups')
parser.add_argument('--quiesced',action='store_true',help='Assert web and all other writers have been stopped.')
parser.add_argument('--label',choices=['manual','pre-upgrade'],default='manual')
parser.add_argument('--verify')
parser.add_argument('--prune',action='store_true',help='Explicitly purge verified backups older than retention.')
parser.add_argument('--retention-days',type=int,default=14)
parser.add_argument('--export-dir',help='Explicit private mounted destination; configure encryption/access separately.')
args=parser.parse_args()
try:
    if args.verify:
        result=verify(args.verify);print('PASS: backup files, SQLite integrity/foreign keys, schema and retained private files verified.')
    else:
        path=backup(args.data_dir,args.destination,args.quiesced,args.label)
        print('Backup complete: '+path.name)
        if args.export_dir:
            destination=allowed(args.export_dir)
            destination.mkdir(parents=True,exist_ok=True,mode=0o700)
            if destination==path or path in destination.parents or destination in path.parents:raise ValueError()
            copied=destination/path.name
            shutil.copytree(path,copied);secure_tree(copied);verify(copied)
            print('Configured export copy verified. Its off-server status/encryption require operator verification.')
        if args.prune:print('Expired verified backups removed: '+str(prune(args.destination,args.retention_days)))
except Exception:
    print('Backup/verification refused or failed. Inspect private paths, maintenance/quiescence, capacity and app version; no incomplete archive is a recovery point.',file=sys.stderr)
    raise SystemExit(1) from None
