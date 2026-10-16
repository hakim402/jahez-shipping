"""Verify a separate reduced-schema restore; no real env/providers or source DB opened."""
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from apps.core.recovery import verify,allowed,database_info
archive,target=map(allowed,sys.argv[1:3]);manifest=verify(archive)
if target==Path('/data') or target==archive or archive in target.parents or target in archive.parents:raise SystemExit('Separate isolated target required.')
info=database_info(target/'shipping.sqlite3',target/'private',True)
assert info['records']==manifest['records'] and info['schema_sha256']==manifest['schema_sha256']
os.environ.update(DJANGO_SETTINGS_MODULE='config.settings.production',SHIPPING_DATA_DIR=str(target),
 DJANGO_SECRET_KEY='isolated-restore-'+'x'*64,DJANGO_ALLOWED_HOSTS='shipping.jahez.online',
 DJANGO_CSRF_TRUSTED_ORIGINS='https://shipping.jahez.online',GROQ_ENABLED='false',GROQ_API_KEY='')
import django;django.setup()
from django.core.management import call_command
from django.test import Client,override_settings
call_command('migrate',check=True,verbosity=0)
with override_settings(CACHES={'default':{'BACKEND':'django.core.cache.backends.locmem.LocMemCache'}}):
 for lang in ('en','ar'):
  assert Client().get('/'+lang+'/',secure=True,HTTP_HOST='shipping.jahez.online').status_code==200
print('PASS: isolated reduced-schema restore, auth/table counts, schema/migrations and bilingual pages. No external calls.')
