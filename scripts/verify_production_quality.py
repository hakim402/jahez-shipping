"""Disposable --network none production-image checks, including existing AI/static checks."""
import runpy
from pathlib import Path
runpy.run_path(str(Path(__file__).with_name('verify_ai_production_image.py')))
from django.conf import settings
from django.core.checks import run_checks,Tags
from django.test import Client
from apps.core.safe_logging import SafeFormatter
import logging
assert not settings.DEBUG and settings.SECURE_SSL_REDIRECT and settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE
assert settings.TRUSTED_PROXY_IPS==[] and not settings.PUBLIC_UI_PREVIEW_ENABLED
assert settings.SECURE_HSTS_SECONDS==0
checks=run_checks(include_deployment_checks=True)
assert {check.id for check in checks}=={'security.W004'},[(c.id,c.msg) for c in checks]
client=Client(enforce_csrf_checks=True)
for lang in ('en','ar'):
    response=client.get('/'+lang+'/PRIVATE-REFERENCE?key=PRIVATE-KEY',secure=True,HTTP_HOST='shipping.jahez.online')
    assert response.status_code==404 and b'PRIVATE' not in response.content and response['X-Request-ID']
    assert "frame-ancestors 'none'" in response['Content-Security-Policy'] and 'no-store' in response['Cache-Control']
    response=client.post('/'+lang+'/',{'reference':'PRIVATE-REFERENCE'},secure=True,HTTP_HOST='shipping.jahez.online')
    assert response.status_code==403 and b'PRIVATE' not in response.content
response=client.get('/en/',HTTP_HOST='shipping.jahez.online');assert response.status_code==301 and response['Location'].startswith('https://')
response=client.get('/en/',secure=True,HTTP_HOST='untrusted.example');assert response.status_code==400 and b'untrusted.example' not in response.content
record=logging.LogRecord('celery',logging.ERROR,'PRIVATE-FILENAME',1,'PRIVATE-PAYLOAD %s',('PRIVATE-KEY',),None)
assert 'PRIVATE' not in SafeFormatter().format(record)
assert not Path('/app/.env.dev').exists() and not Path('/app/.env.prod').exists() and not Path('/app/docs/protected-baseline.json').exists()
print('PASS: offline production quality/security/error/CSRF/host/redirect/static/log privacy checks. Only deployment warning security.W004: HSTS intentionally deferred until real TLS verification; no production service/volume/provider used.')
