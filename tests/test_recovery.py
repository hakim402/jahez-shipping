import json
import sqlite3
import tempfile
from pathlib import Path
from django.test import SimpleTestCase
from apps.core import recovery

class ReducedRecoveryTests(SimpleTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='jahez-recovery-test-')
        self.root=Path(self.temp.name).resolve();self.data=self.root/'data';self.data.mkdir()
        self.private=self.data/'private';self.private.mkdir();(self.private/'retained.bin').write_bytes(b'SYNTHETIC retained private bytes')
        with sqlite3.connect(self.data/'shipping.sqlite3') as db:
            db.executescript('CREATE TABLE django_migrations(app TEXT,name TEXT); INSERT INTO django_migrations VALUES ("sessions","0001_initial"); CREATE TABLE auth_user(id INTEGER PRIMARY KEY,password TEXT); INSERT INTO auth_user VALUES (1,"SYNTHETIC HASH"); CREATE TABLE django_session(id INTEGER); CREATE TABLE django_content_type(id INTEGER); CREATE TABLE django_admin_log(id INTEGER);')
        (self.data/'maintenance.lock').write_text(json.dumps({'project':'jahez-shipping'}))
    def tearDown(self):self.temp.cleanup()
    def archive(self):return recovery.backup(self.data,self.root/'backups',True)

    def test_backup_restore_hashes_and_auth_counts(self):
        archive=self.archive();manifest=recovery.verify(archive)
        self.assertEqual(manifest['format'],2);self.assertEqual(manifest['records']['auth_user'],1)
        target=self.root/'restored';recovery.restore(archive,target)
        self.assertEqual((target/'private/retained.bin').read_bytes(),(self.private/'retained.bin').read_bytes())
        self.assertEqual(archive.stat().st_mode&0o777,0o700)
        self.assertTrue(all(p.stat().st_mode&0o777==0o600 for p in recovery.tree(archive)))
        with sqlite3.connect(target/'shipping.sqlite3') as db:self.assertEqual(db.execute('SELECT password FROM auth_user').fetchone()[0],'SYNTHETIC HASH')

    def test_quiescence_corruption_and_legacy_schema_fail_closed(self):
        with self.assertRaises(recovery.RecoveryError):recovery.backup(self.data,self.root/'backups',False)
        archive=self.archive();(archive/'private/retained.bin').write_bytes(b'TAMPERED')
        with self.assertRaises(recovery.RecoveryError):recovery.verify(archive)
        with sqlite3.connect(self.data/'shipping.sqlite3') as db:db.execute('CREATE TABLE shipments_customer(id INTEGER)')
        with self.assertRaises(recovery.RecoveryError):self.archive()

    def test_exact_target_and_version_refusal_preserve_original(self):
        archive=self.archive();before=(self.data/'shipping.sqlite3').read_bytes()
        with self.assertRaises(recovery.RecoveryError):recovery.restore(archive,self.data,True,'/wrong-target',True)
        self.assertEqual((self.data/'shipping.sqlite3').read_bytes(),before)
        manifest=json.loads((archive/'manifest.json').read_text());manifest['app_version']='0.8.1';(archive/'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaises(recovery.RecoveryError):recovery.verify(archive)

    def test_symlink_and_public_private_storage_url_refused(self):
        link=self.private/'unsafe';link.symlink_to(self.root)
        with self.assertRaises(recovery.RecoveryError):self.archive()
        from apps.core.storage import PrivateStorage
        with self.assertRaises(ValueError):PrivateStorage(location=self.private).url('retained.bin')
