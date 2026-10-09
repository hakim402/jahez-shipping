import io
import json
import logging
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch
from django.test import SimpleTestCase, TestCase, Client, RequestFactory, override_settings
from apps.core import recovery
from apps.core.privacy import client_address
from apps.core.safe_logging import SafeFormatter
from apps.ai.provider import AIError, generate
from django.urls import path
from apps.core.errors import server_error

def synthetic_error(request):raise RuntimeError('PRIVATE-EXCEPTION-PAYLOAD')
urlpatterns=[path('en/error/',synthetic_error)]
handler500=server_error


class PrivacyTests(SimpleTestCase):
    def test_implicit_readonly_metadata_is_localized_without_changing_english(self):
        from django.utils import translation
        from apps.shipments.models import Shipment
        from apps.ai.models import AIDraft
        with translation.override('ar'):
            self.assertEqual(str(Shipment._meta.get_field('created_at').verbose_name),'تاريخ الإنشاء')
            self.assertEqual(str(AIDraft._meta.get_field('state').verbose_name),'الحالة')
        with translation.override('en'):
            self.assertEqual(str(Shipment._meta.get_field('created_at').verbose_name),'created at')
    def test_forwarding_headers_require_exact_trusted_peer(self):
        request=RequestFactory().get('/',REMOTE_ADDR='192.0.2.1',HTTP_X_REAL_IP='198.51.100.7',HTTP_X_FORWARDED_FOR='203.0.113.3')
        with override_settings(TRUSTED_PROXY_IPS=[]):self.assertEqual(client_address(request),'192.0.2.1')
        with override_settings(TRUSTED_PROXY_IPS=['192.0.2.1']):
            self.assertEqual(client_address(request),'198.51.100.7')
            request.META['HTTP_X_REAL_IP']='198.51.100.7, 203.0.113.3'
            self.assertEqual(client_address(request),'192.0.2.1')

    def test_logging_discards_payload_exception_path_and_untrusted_metadata(self):
        record=logging.LogRecord('jahez.request',logging.ERROR,'PRIVATE-FILE',1,'SECRET %s',('PRIVATE-TOKEN',),None)
        record.exc_text='PRIVATE-TRACE';record.request_id='PRIVATE-ID';record.route='PRIVATE-REF'
        record.status=503;record.duration_ms=12;record.method='POST'
        result=SafeFormatter().format(record)
        self.assertNotIn('PRIVATE',result);self.assertNotIn('SECRET',result)
        self.assertEqual(json.loads(result),{'level':'ERROR','event':'request.complete','status':503,'duration_ms':12,'method':'POST'})

    @override_settings(GROQ_MAX_IMAGES=3)
    def test_image_limit_precedes_sdk_and_cache(self):
        with patch('apps.ai.provider.Groq') as sdk,patch('apps.ai.provider.cache.add') as cache:
            with self.assertRaises(AIError) as error:generate('extraction',{'images':[{}]*4})
        self.assertEqual(error.exception.code,'image_limit');sdk.assert_not_called();cache.assert_not_called()


class ResponseSafetyTests(TestCase):
    @override_settings(DEBUG=False,ROOT_URLCONF=__name__)
    def test_unhandled_500_is_generic_and_correlated(self):
        client=Client(raise_request_exception=False)
        response=client.get('/en/error/?token=PRIVATE-CAPABILITY')
        self.assertEqual(response.status_code,500);self.assertNotIn(b'PRIVATE',response.content)
        self.assertTrue(response['X-Request-ID']);self.assertEqual(response['X-Content-Type-Options'],'nosniff')

    @override_settings(DEBUG=False)
    def test_errors_have_generic_bilingual_copy_and_request_ids(self):
        for language in ('en','ar'):
            response=self.client.get('/'+language+'/PRIVATE-CAPABILITY?token=PRIVATE-SECRET')
            self.assertEqual(response.status_code,404)
            self.assertNotIn(b'PRIVATE',response.content)
            self.assertRegex(response['X-Request-ID'],'^[0-9a-f]{16}$')
            self.assertIn(response['X-Request-ID'].encode(),response.content)
            self.assertEqual(response['Cache-Control'],'no-store')
            self.assertIn("frame-ancestors 'none'",response['Content-Security-Policy'])
        response=Client(enforce_csrf_checks=True).post('/en/',{'reference':'PRIVATE-CAPABILITY'})
        self.assertEqual(response.status_code,403);self.assertNotIn(b'PRIVATE',response.content)
        self.assertTrue(response['X-Request-ID'])

    def test_early_throttle_fail_closed_has_headers(self):
        with patch('apps.core.middleware.cache.add',side_effect=ConnectionError('PRIVATE-REDIS')):
            response=self.client.post('/en/admin/login/',{'password':'PRIVATE-PASSWORD'})
        self.assertEqual(response.status_code,503)
        self.assertTrue(response['X-Request-ID']);self.assertEqual(response['Cache-Control'],'no-store')
        self.assertNotIn(b'PRIVATE',response.content)

    def test_maintenance_blocks_writes_jobs_and_readiness_but_liveness_works(self):
        with tempfile.TemporaryDirectory() as folder,override_settings(DATA_DIR=Path(folder)):
            (Path(folder)/'maintenance.lock').write_text('{}')
            response=self.client.post('/ar/',{'reference':'PRIVATE-REF'})
            self.assertEqual(response.status_code,503);self.assertEqual(response['Retry-After'],'60')
            self.assertEqual(response['X-Content-Type-Options'],'nosniff');self.assertEqual(response['X-Frame-Options'],'DENY')
            self.assertEqual(self.client.get('/health/live/').status_code,200)
            self.assertEqual(self.client.get('/health/ready/').status_code,503)
            from apps.ai.services import claim,recover
            from apps.ai.assistant import claim as claim_answer,recover as recover_answers
            from apps.tracking.services import claim_job
            from apps.tracking.tasks import reconcile
            with self.assertNumQueries(0):
                self.assertIsNone(claim(1));self.assertIsNone(claim_answer(1));self.assertIsNone(claim_job(1))
                recover();recover_answers();reconcile()


class RecoveryTests(SimpleTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='jahez-recovery-test-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.data=self.root/'data';self.data.mkdir()
        self.private=self.data/'private';self.private.mkdir()
        document=self.private/'documents/demo.pdf';document.parent.mkdir();document.write_bytes(b'SYNTHETIC PRIVATE DOCUMENT')
        self.db=sqlite3.connect(self.data/'shipping.sqlite3')
        self.addCleanup(self.db.close)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('CREATE TABLE django_migrations(app TEXT,name TEXT); INSERT INTO django_migrations VALUES ("shipments","synthetic"); CREATE TABLE shipments_document(file TEXT,checksum TEXT,size INTEGER);')
        self.db.execute('INSERT INTO shipments_document VALUES (?,?,?)',('documents/demo.pdf',recovery.sha(document),document.stat().st_size));self.db.commit()
        (self.data/'maintenance.lock').write_text(json.dumps({'project':'jahez-shipping'}))

    def archive(self):return recovery.backup(self.data,self.root/'backups',True)

    def test_online_backup_includes_wal_private_files_and_isolated_restore(self):
        self.assertTrue((self.data/'shipping.sqlite3-wal').exists())
        archive=self.archive();manifest=recovery.verify(archive)
        self.assertEqual(manifest['documents'],1)
        self.assertEqual(archive.stat().st_mode&0o777,0o700)
        for path in recovery.tree(archive):self.assertEqual(path.stat().st_mode&0o777,0o600)
        target=self.root/'restored';result=recovery.restore(archive,target)
        self.assertEqual(result['documents'],1);self.assertFalse(result['rollback_retained'])
        self.assertEqual(recovery.sha(target/'private/documents/demo.pdf'),recovery.sha(self.private/'documents/demo.pdf'))

    def test_quiescence_missing_files_corruption_version_and_symlinks_refused(self):
        with self.assertRaises(recovery.RecoveryError):recovery.backup(self.data,self.root/'backups')
        marker=self.data/'maintenance.lock';marker.unlink()
        external=self.root/'external-marker';external.write_text(json.dumps({'project':'jahez-shipping'}));marker.symlink_to(external)
        with self.assertRaises(recovery.RecoveryError):self.archive()
        marker.unlink();marker.write_text(json.dumps({'project':'jahez-shipping'}))
        archive=self.archive();document=archive/'private/documents/demo.pdf';document.write_bytes(b'CORRUPT')
        with self.assertRaises(recovery.RecoveryError):recovery.verify(archive)
        document.unlink();document.symlink_to(self.private/'documents/demo.pdf')
        with self.assertRaises(recovery.RecoveryError):recovery.verify(archive)
        document.unlink();document.write_bytes(b'SYNTHETIC PRIVATE DOCUMENT')
        manifest=json.loads((archive/'manifest.json').read_text());manifest['app_version']='other-version'
        (archive/'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaises(recovery.RecoveryError):recovery.restore(archive,self.root/'restored')
        (self.private/'documents/demo.pdf').unlink()
        with self.assertRaises(recovery.RecoveryError):self.archive()

    def test_existing_target_requires_exact_confirmation_and_retains_rollback(self):
        archive=self.archive();target=self.root/'restored';recovery.restore(archive,target)
        with self.assertRaises(recovery.RecoveryError):recovery.restore(archive,target,True,'wrong',True)
        (target/'maintenance.lock').write_text(json.dumps({'project':'jahez-shipping'}))
        result=recovery.restore(archive,target,True,str(target),True)
        self.assertTrue(result['rollback_retained'])
        self.assertEqual(len(list(target.glob('.pre-restore-*/shipping.sqlite3'))),1)

    def test_failed_replace_returns_original_database_and_files(self):
        archive=self.archive();target=self.root/'restored';recovery.restore(archive,target)
        (target/'maintenance.lock').write_text(json.dumps({'project':'jahez-shipping'}))
        original=recovery.sha(target/'shipping.sqlite3');real=recovery.database_info
        def validate(database,*args):
            if database==target/'shipping.sqlite3' and list(target.glob('.pre-restore-*')):raise recovery.RecoveryError('synthetic_install_failure')
            return real(database,*args)
        with patch('apps.core.recovery.database_info',side_effect=validate):
            with self.assertRaises(recovery.RecoveryError):recovery.restore(archive,target,True,str(target),True)
        self.assertEqual(recovery.sha(target/'shipping.sqlite3'),original)
        real(target/'shipping.sqlite3',target/'private',True)
        self.assertTrue((target/'maintenance.lock').exists())

    def test_damaged_target_needs_extra_explicit_flag_and_is_retained(self):
        archive=self.archive();target=self.root/'restored';recovery.restore(archive,target)
        (target/'maintenance.lock').write_text(json.dumps({'project':'jahez-shipping'}))
        (target/'shipping.sqlite3').write_bytes(b'SYNTHETIC CORRUPTED DATABASE')
        with self.assertRaises(recovery.RecoveryError):recovery.restore(archive,target,True,str(target),True)
        result=recovery.restore(archive,target,True,str(target),True,allow_damaged_target=True)
        self.assertTrue(result['rollback_retained'])
        self.assertEqual(next(target.glob('.pre-restore-*/shipping.sqlite3')).read_bytes(),b'SYNTHETIC CORRUPTED DATABASE')
        recovery.database_info(target/'shipping.sqlite3',target/'private',True)

    def test_paths_and_explicit_retention_preserve_unverified_evidence(self):
        for name in ('../escape','/absolute','bad\\path'):
            with self.assertRaises(recovery.RecoveryError):recovery.relative(name)
        with self.assertRaises(recovery.RecoveryError):recovery.allowed(Path(__file__).resolve().parents[1]/'data')
        archive=self.archive();manifest=json.loads((archive/'manifest.json').read_text());manifest['created_at']='2000-01-01T00:00:00+00:00'
        (archive/'manifest.json').write_text(json.dumps(manifest))
        incomplete=archive.parent/'.incomplete-evidence';incomplete.mkdir()
        invalid=archive.parent/'invalid';invalid.mkdir()
        self.assertEqual(recovery.prune(archive.parent,14),1)
        self.assertTrue(incomplete.exists());self.assertTrue(invalid.exists())
