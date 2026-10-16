"""Integration assertion run only on /review synthetic fixture with current candidate source."""
import os,sys,json,hashlib
from pathlib import Path
sys.path.insert(0,'/app')
baseline=json.loads(Path('/review/baseline.json').read_text())
os.environ.update(DJANGO_SETTINGS_MODULE='config.settings.development',SHIPPING_DATA_DIR='/review/legacy',
 DJANGO_SECRET_KEY=baseline['secret'],GROQ_ENABLED='false')
import django;django.setup()
from django.core.management import call_command
from django.db import connection
from apps.core.transition import LEGACY_TABLES
from django.contrib.auth import authenticate
from django.contrib.auth.models import User,Permission,Group
from django.contrib.sessions.models import Session
from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
before=set(connection.introspection.table_names());assert set(LEGACY_TABLES)<=before
try:call_command('migrate',verbosity=0)
except RuntimeError as error:assert 'Cleanup refused' in str(error)
else:raise AssertionError('Populated migration must refuse missing approval/backup')
assert set(LEGACY_TABLES)<=set(connection.introspection.table_names())
os.environ.update(SHIPPING_ALLOW_SCHEMA_CLEANUP='true',SHIPPING_PRE_CLEANUP_ARCHIVE=baseline['archive'])
# Reject a stale backup even when the operator flag is provided.
connection.cursor().execute("UPDATE shipments_customer SET name='SYNTHETIC CHANGED AFTER BACKUP'")
try:call_command('migrate',verbosity=0)
except RuntimeError as error:assert 'Cleanup refused' in str(error)
else:raise AssertionError('Stale recovery point must refuse')
connection.cursor().execute("UPDATE shipments_customer SET name='SYNTHETIC LEGACY CUSTOMER'")
call_command('migrate',verbosity=0)
assert not set(LEGACY_TABLES)&set(connection.introspection.table_names())
user=authenticate(username='synthetic-transition-admin',password=baseline['password'])
assert user and user.pk==baseline['user_id'] and user.password==baseline['password_hash']
assert Session.objects.get(session_key=baseline['session_key']).get_decoded()['synthetic-preserved']=='yes'
assert user.groups.get().permissions.filter(codename='view_user').exists()
assert not ContentType.objects.filter(app_label__in=('shipments','tracking','ai')).exists()
assert not Permission.objects.filter(content_type__app_label__in=('shipments','tracking','ai')).exists()
assert LogEntry.objects.count()==1 and LogEntry.objects.get().content_type_id is None
assert hashlib.sha256(Path('/review/legacy/private/documents/synthetic.pdf').read_bytes()).hexdigest()==baseline['document_sha256']
call_command('makemigrations',check=True,dry_run=True,verbosity=0)
from django.db.migrations.exceptions import IrreversibleError
try:call_command('migrate','shipments','0003_fileremoval_alter_auditentry_shipment_and_more',verbosity=0)
except IrreversibleError:pass
else:raise AssertionError('Retirement must not reverse to empty tables')
assert not set(LEGACY_TABLES)&set(connection.introspection.table_names())
from apps.core.recovery import backup,restore,verify
archive=backup('/review/legacy','/review/reduced-backups',True);manifest=verify(archive)
assert manifest['records']['auth_user']==1
restore(archive,'/review/reduced-restored')
from apps.core.recovery import database_info
assert database_info(Path('/review/reduced-restored/shipping.sqlite3'),Path('/review/reduced-restored/private'),True)['records']==manifest['records']
Path('/review/reduced-archive.txt').write_text(str(archive))
print('PASS: unsafe/stale-backup cleanup refused; all 12 legacy tables deleted only in disposable DB; admin/hash/group/session/admin log/private file preserved; reduced backup/isolated restore verified.')
