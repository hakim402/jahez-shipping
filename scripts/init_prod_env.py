"""Create a new independent private production env; never overwrite or display secrets."""
import argparse
import os
import secrets
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',default='.env.prod');args=parser.parse_args()
root=Path(__file__).resolve().parents[1];target=Path(args.output).absolute()
text=(root/'.env.prod.example').read_text().replace('REPLACE_WITH_INDEPENDENT_RANDOM_SECRET_AT_LEAST_50_CHARACTERS',secrets.token_urlsafe(64))
try:
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as handle:handle.write(text)
except FileExistsError:raise SystemExit('Existing environment preserved; no secret rotated.') from None
print('Created independent production environment (0600); integrations disabled. Secret not displayed.')
