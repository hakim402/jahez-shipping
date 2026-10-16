"""Small scoped helpers. Never print resolved Compose environments or subprocess errors."""
import json
import os
import shlex
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def read_env(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o077:raise ValueError('Environment file must be a private regular file (0600).')
    values={}
    for line in path.read_text().splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        if '=' not in line:raise ValueError('Malformed environment file.')
        name,value=line.split('=',1)
        if name in values or not name.replace('_','').isalnum():raise ValueError('Duplicate or invalid environment field.')
        parts=shlex.split(value,comments=False)
        if len(parts)>1:raise ValueError('Quote environment values containing spaces.')
        values[name]=parts[0] if parts else ''
        if '$' in values[name]:raise ValueError('Environment interpolation is not supported; use literal private values.')
    return values

def scope(review_dir=None):
    if review_dir:
        directory=Path(review_dir).resolve()
        if directory.parent!=(ROOT/'private/cleanup-review').resolve() or not directory.name.startswith('compose-'):
            raise ValueError('Invalid isolated review directory.')
        return 'jahez-shipping-cleanup-review',['docker','compose','--env-file',str(directory/'review.env'),'-p','jahez-shipping-cleanup-review','-f',str(ROOT/'compose.prod.yml'),'-f',str(directory/'review.yml')]
    return 'jahez-shipping-prod',['docker','compose','--env-file',str(ROOT/'.env.prod'),'-p','jahez-shipping-prod','-f',str(ROOT/'compose.prod.yml')]

def call(arguments,capture=False):
    result=subprocess.run(arguments,cwd=ROOT,text=True,capture_output=True)
    if result.returncode:raise RuntimeError('Scoped Shipping command failed; inspect private configuration and safe service diagnostics.')
    if not capture and result.stdout:print(result.stdout,end='')
    return result.stdout

def contract(model,project,review=False):
    if model['name']!=project or set(model['services'])!={'web','redis'}:raise ValueError('Compose service/project contract failed.')
    for name in ('web',):
        svc=model['services'][name]
        if not svc.get('read_only') or svc.get('environment',{}).get('DJANGO_SETTINGS_MODULE')!='config.settings.production':raise ValueError('Production settings/read-only contract failed.')
        if any(v['type']=='bind' for v in svc.get('volumes',[])):raise ValueError('Production source bind mount refused.')
        if not svc.get('healthcheck') or svc.get('stop_grace_period')!='1m35s':raise ValueError('Health/grace contract failed.')
    web=model['services']['web'];ports=web.get('ports',[])
    if review:
        if ports:raise ValueError('Review must have no host ports.')
    elif len(ports)!=1 or ports[0].get('host_ip')!='127.0.0.1' or str(ports[0].get('published'))!='18743':raise ValueError('Production loopback port contract failed.')
    for name in ('redis',):
        if model['services'][name].get('ports'):raise ValueError('Non-web published port refused.')
    for vol in model['volumes'].values():
        if not vol['name'].startswith(project+'_'):raise ValueError('Foreign volume refused.')
    for net in model['networks'].values():
        if not net['name'].startswith(project+'_'):raise ValueError('Foreign network refused.')
