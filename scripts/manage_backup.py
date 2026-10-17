"""Back up the two-service production runtime; keep web paused on failure."""
import argparse
import subprocess
import sys
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--confirm-production',action='store_true')
args=parser.parse_args()
if not args.confirm_production:raise SystemExit('Production backup requires owner approval and --confirm-production. No service changed.')
root=Path(__file__).resolve().parents[1]
for action in ('pause','backup','resume'):
    if subprocess.run([sys.executable,'scripts/release.py',action,'--confirm-production'],cwd=root).returncode:
        raise SystemExit('Backup failed; writers remain paused. Inspect private evidence before resuming.')
