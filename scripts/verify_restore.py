"""Offline Django verification of a separate Phase 7 restore. Never opens live /data DB."""
import json
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from apps.core.recovery import verify,allowed
archive,target=map(allowed,sys.argv[1:3]);manifest=verify(archive)
if target==Path('/data') or target==archive or archive in target.parents:raise SystemExit('Isolated target required.')
os.environ.update(DJANGO_SETTINGS_MODULE='config.settings.production',SHIPPING_DATA_DIR=str(target),
    DJANGO_SECRET_KEY='isolated-restore-'+ 'x'*64,DJANGO_ALLOWED_HOSTS='shipping.jahez.online',
    DJANGO_CSRF_TRUSTED_ORIGINS='https://shipping.jahez.online',GROQ_ENABLED='false',GROQ_API_KEY='',TRACK17_ENABLED='false',TRACK17_API_KEY='')
import django
django.setup()
from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.test import Client,override_settings
from apps.shipments.models import Document,Shipment
from apps.core.recovery import sha
assert settings.DATA_DIR==target and not settings.DEBUG
for model in apps.get_models():
    if model._meta.db_table in manifest['records']:assert model.objects.count()==manifest['records'][model._meta.db_table]
for doc in Document.objects.all():assert sha(Path(doc.file.path))==doc.checksum
call_command('migrate',check=True,verbosity=0)
with override_settings(CACHES={'default':{'BACKEND':'django.core.cache.backends.locmem.LocMemCache'}},
    STORAGES={**settings.STORAGES,'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}}):
    client=Client()
    for lang in ('en','ar'):
        assert client.get('/'+lang+'/',secure=True,HTTP_HOST='shipping.jahez.online').status_code==200
        for ship in Shipment.objects.filter(is_demo=True,published=True):
            response=client.post('/'+lang+'/',{'reference':ship.reference},secure=True,HTTP_HOST='shipping.jahez.online')
            assert 'We could not find' in response.content.decode() or 'لم نعثر' in response.content.decode()
print('PASS: isolated restore loads with production Django; all application table counts/private checksums/migrations match manifest; EN/AR pages render, DEMO public lookup suppressed. No source DB change or provider call.')
