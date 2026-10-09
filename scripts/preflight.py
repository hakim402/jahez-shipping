"""Read-only production config/secret/port checks; no broad environment/config output."""
import argparse
import json
import socket
import sys
sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parents[1]))
from deploy.production_env import validate
from production_tools import read_env,scope,call,contract,ROOT
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--review-dir');parser.add_argument('--running',action='store_true',help='Skip free-port check for an already running Shipping production instance.')
args=parser.parse_args()
try:
    project,compose=scope(args.review_dir)
    values=read_env(compose[3]);validate(values)
    if values.get('SHIPPING_DATA_DIR')!='/data':raise ValueError('Compose runtime must use its dedicated /data volume.')
    model=json.loads(call(compose+['config','--format','json'],True));contract(model,project,bool(args.review_dir))
    if not args.review_dir and not args.running:
        with socket.socket() as sock:sock.bind(('127.0.0.1',18743))
    print('PASS: private production env, secure settings, pinned image, scoped Compose/services/volumes, loopback port and health/grace contracts. No secret values displayed.')
except Exception as error:
    # Validation errors are field-name-only; OS/subprocess errors remain generic.
    from deploy.production_env import EnvironmentError
    print(str(error) if isinstance(error,EnvironmentError) else 'Preflight refused: inspect private file permissions/configuration, Docker availability and port ownership.',file=sys.stderr)
    raise SystemExit(1) from None
