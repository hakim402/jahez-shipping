import json
import sqlite3
import tempfile
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
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
        recovery.verify_restored_private_files(target,manifest)
        self.assertEqual((target/'private/retained.bin').read_bytes(),(self.private/'retained.bin').read_bytes())
        self.assertEqual(archive.stat().st_mode&0o777,0o700)
        self.assertTrue(all(p.stat().st_mode&0o777==0o600 for p in recovery.tree(archive)))
        with sqlite3.connect(target/'shipping.sqlite3') as db:self.assertEqual(db.execute('SELECT password FROM auth_user').fetchone()[0],'SYNTHETIC HASH')

    def test_restored_private_files_reject_corruption_missing_extra_and_symlinks(self):
        archive=self.archive();manifest=recovery.verify(archive)
        for damage in ('corrupt','missing','extra','symlink','missing_directory'):
            with self.subTest(damage=damage):
                target=self.root/('restored-'+damage);recovery.restore(archive,target)
                file=target/'private/retained.bin'
                if damage=='corrupt':
                    original=file.read_bytes();file.write_bytes(bytes([original[0]^1])+original[1:])
                elif damage=='missing':file.unlink()
                elif damage=='extra':(target/'private/unexpected.bin').write_bytes(b'SYNTHETIC extra')
                elif damage=='symlink':
                    file.unlink();file.symlink_to(self.private/'retained.bin')
                else:shutil.rmtree(target/'private')
                with self.assertRaises(recovery.RecoveryError):recovery.verify_restored_private_files(target,manifest)
                result=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/verify_restore.py'),str(archive),str(target)],capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0)
                self.assertNotIn('PASS:',result.stdout)
                self.assertIn('RecoveryError',result.stderr)

    def test_corrupted_restore_copy_refuses_before_replacing_original(self):
        archive=self.archive();before=(self.data/'shipping.sqlite3').read_bytes()
        original=(self.private/'retained.bin').read_bytes()
        copytree=shutil.copytree
        def corrupt_copy(source,destination,*args,**kwargs):
            result=copytree(source,destination,*args,**kwargs)
            file=Path(destination)/'retained.bin'
            file.write_bytes(bytes([original[0]^1])+original[1:])
            return result
        with patch('apps.core.recovery.shutil.copytree',side_effect=corrupt_copy):
            with self.assertRaisesRegex(recovery.RecoveryError,'restored_file_checksum_mismatch'):
                recovery.restore(archive,self.data,True,str(self.data),True)
        self.assertEqual((self.data/'shipping.sqlite3').read_bytes(),before)
        self.assertEqual((self.private/'retained.bin').read_bytes(),original)

    def test_quiescence_corruption_and_legacy_schema_fail_closed(self):
        with self.assertRaises(recovery.RecoveryError):recovery.backup(self.data,self.root/'backups',False)
        archive=self.archive();(archive/'private/retained.bin').write_bytes(b'TAMPERED')
        with self.assertRaises(recovery.RecoveryError):recovery.verify(archive)
        with sqlite3.connect(self.data/'shipping.sqlite3') as db:db.execute('CREATE TABLE shipments_customer(id INTEGER)')
        with self.assertRaises(recovery.RecoveryError):self.archive()

    def test_valid_sqlite_row_corruption_fails_verifier_and_preserves_original_target(self):
        archive=self.archive();manifest=recovery.verify(archive)
        target=self.root/'row-corrupt';recovery.restore(archive,target)
        with sqlite3.connect(target/'shipping.sqlite3') as db:
            db.execute("UPDATE auth_user SET password='SYNTHETIC DIFFERENT HASH'")
        # Counts, schema and SQLite integrity still agree; exact backup bytes must not.
        self.assertEqual(recovery.database_info(target/'shipping.sqlite3',target/'private')['records'],manifest['records'])
        with self.assertRaisesRegex(recovery.RecoveryError,'restored_database_checksum_mismatch'):
            recovery.verify_restored_database(target,manifest)
        result=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/verify_restore.py'),str(archive),str(target)],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0);self.assertNotIn('PASS:',result.stdout)
        before=(self.data/'shipping.sqlite3').read_bytes()
        private_before=(self.private/'retained.bin').read_bytes()
        copy2=shutil.copy2
        def corrupt_copy(source,destination,*args,**kwargs):
            result=copy2(source,destination,*args,**kwargs)
            if Path(destination).name=='shipping.sqlite3':
                with sqlite3.connect(destination) as db:
                    db.execute("UPDATE auth_user SET password='SYNTHETIC DIFFERENT HASH'")
            return result
        with patch('apps.core.recovery.shutil.copy2',side_effect=corrupt_copy):
            with self.assertRaisesRegex(recovery.RecoveryError,'restored_database_checksum_mismatch'):
                recovery.restore(archive,self.data,True,str(self.data),True)
        self.assertEqual((self.data/'shipping.sqlite3').read_bytes(),before)
        self.assertEqual((self.private/'retained.bin').read_bytes(),private_before)

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
