"""Old-image-only recovery proof; never runs on a persistent owner database."""
import os,sys,json,hashlib
from pathlib import Path
sys.path.insert(0,'/app')
b=json.loads(Path('/review/baseline.json').read_text())
from apps.core.recovery import verify,restore
verify(b['archive']);restore(b['archive'],'/review/legacy-restored')
os.environ.update(DJANGO_SETTINGS_MODULE='config.settings.development',SHIPPING_DATA_DIR='/review/legacy-restored',
 DJANGO_SECRET_KEY=b['secret'],GROQ_ENABLED='false',TRACK17_ENABLED='false')
import django;django.setup()
from django.conf import settings
assert settings.APP_VERSION=='0.8.1'
from django.contrib.auth import authenticate
from django.contrib.sessions.models import Session
from django.apps import apps
for label in ('shipments.Customer','shipments.Shipment','shipments.ShipmentItem','shipments.TrackingLeg','shipments.TrackingEvent','shipments.Document','shipments.AuditEntry','shipments.FileRemoval','tracking.WebhookReceipt','tracking.IntegrationJob','ai.AIDraft','ai.AssistantRun'):
 assert apps.get_model(label).objects.count()==1,label
user=authenticate(username='synthetic-transition-admin',password=b['password'])
assert user and user.password==b['password_hash']
assert Session.objects.get(session_key=b['session_key']).get_decoded()['synthetic-preserved']=='yes'
assert hashlib.sha256(Path('/review/legacy-restored/private/documents/synthetic.pdf').read_bytes()).hexdigest()==b['document_sha256']
from django.core.management import call_command
call_command('migrate',check=True,verbosity=0)
print('PASS: restored old matching backup under immutable 0.8.1 image; all 12 legacy rows, admin/hash/session and private file recovered in a separate disposable directory.')
