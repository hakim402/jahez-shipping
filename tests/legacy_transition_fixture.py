"""Test-only fixture executed inside the immutable 0.8.1 image, never current product code."""
import os
import sys
sys.path.insert(0,"/app")
import json
import secrets
import hashlib
from pathlib import Path
os.environ.update(DJANGO_SETTINGS_MODULE='config.settings.development',SHIPPING_DATA_DIR='/review/legacy',
 DJANGO_SECRET_KEY='synthetic-transition-'+secrets.token_urlsafe(64),GROQ_ENABLED='false',TRACK17_ENABLED='false')
import django;django.setup()
from django.conf import settings
assert settings.APP_VERSION=='0.8.1'
from django.apps import apps
from django.core.management import call_command
from django.contrib.auth.models import User,Group,Permission
from django.contrib.sessions.backends.db import SessionStore
from django.utils import timezone
call_command('migrate',verbosity=0)
password=secrets.token_urlsafe(32)
user=User.objects.create_superuser('synthetic-transition-admin','',password)
group=Group.objects.create(name='Synthetic retained group');group.permissions.add(Permission.objects.get(codename='view_user'));user.groups.add(group)
session=SessionStore();session['synthetic-preserved']='yes';session.save()
customer=apps.get_model('shipments','Customer').objects.create(name='SYNTHETIC LEGACY CUSTOMER')
shipment=apps.get_model('shipments','Shipment').objects.create(customer=customer,internal_order='SYNTHETIC-LEGACY',origin_en='Test port',destination_en='Other test port')
item=apps.get_model('shipments','ShipmentItem').objects.create(shipment=shipment,description_en='Synthetic goods',quantity=1)
leg=apps.get_model('shipments','TrackingLeg').objects.create(shipment=shipment,tracking_number='SYNTHETIC-ONLY',carrier_identifier=1)
event=apps.get_model('shipments','TrackingEvent').objects.create(shipment=shipment,leg=leg,title_en='Synthetic milestone',occurred_at=timezone.now())
# The old backup validates this real private file checksum, not a fake document record.
content=b'%PDF-1.4\n% SYNTHETIC legacy recovery fixture only\n';path=Path('/review/legacy/private/documents/synthetic.pdf');path.parent.mkdir(parents=True);path.write_bytes(content)
document=apps.get_model('shipments','Document').objects.create(shipment=shipment,file='documents/synthetic.pdf',size=len(content),checksum=hashlib.sha256(content).hexdigest(),original_filename='synthetic.pdf',mime_type='application/pdf')
apps.get_model('shipments','AuditEntry').objects.create(shipment=shipment,actor=user,action='synthetic.transition')
apps.get_model('shipments','FileRemoval').objects.create(storage_name='synthetic-not-a-real-file')
receipt=apps.get_model('tracking','WebhookReceipt').objects.create(digest='0'*64,event_type='synthetic',payload={})
apps.get_model('tracking','IntegrationJob').objects.create(kind='receipt',receipt=receipt,leg=leg,dedupe_key='synthetic-transition')
apps.get_model('ai','AIDraft').objects.create(shipment=shipment,document=document,event=event,kind='extraction',dedupe_key='synthetic-draft',source_version='synthetic',expires_at=timezone.now(),requested_by=user)
apps.get_model('ai','AssistantRun').objects.create(dedupe_key='synthetic-assistant',source_version='synthetic',expires_at=timezone.now(),requested_by=user)
from django.contrib.admin.models import LogEntry,ADDITION
from django.contrib.contenttypes.models import ContentType
LogEntry.objects.log_actions(user_id=user.pk,queryset=[shipment],action_flag=ADDITION,change_message='Synthetic transition history')
marker=Path('/review/legacy/maintenance.lock');marker.write_text(json.dumps({'project':'jahez-shipping','operation':'transition-test'}));marker.chmod(0o600)
from apps.core.recovery import backup,verify
archive=backup('/review/legacy','/review/legacy/backups',True,'pre-upgrade');verify(archive)
baseline={'secret':settings.SECRET_KEY,'password':password,'user_id':user.pk,'password_hash':user.password,'session_key':session.session_key,'archive':str(archive),'document_sha256':hashlib.sha256(content).hexdigest()}
p=Path('/review/baseline.json');p.write_text(json.dumps(baseline));p.chmod(0o600)
print('PASS: isolated old image created all 12 synthetic business rows, admin/group/session/log and verified matching private-file backup.')
