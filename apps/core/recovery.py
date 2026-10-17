"""Offline, matching SQLite/private-file recovery points. No archive extraction or secrets."""
import ast
import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path, PurePosixPath


class RecoveryError(Exception):pass


def app_version():
    module=Path(__file__).resolve().parents[2]/'config/settings/base.py'
    for node in ast.parse(module.read_text()).body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='APP_VERSION' for t in node.targets):
            return ast.literal_eval(node.value)
    raise RecoveryError('version_missing')


def allowed(path):
    path=Path(path).absolute()
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):raise RecoveryError('symlink_rejected')
    path=path.resolve()
    if {'jahez-trade-co','JAHEZ-Brand-Kit','jahez-trade-co-shipping-system'} & set(path.parts):raise RecoveryError('protected_project')
    code=Path(__file__).resolve().parents[2]
    if path==code or code in path.parents:raise RecoveryError('code_target_rejected')
    return path


def relative(name):
    value=PurePosixPath(name)
    if not name or value.is_absolute() or '..' in value.parts or '\\' in name or '\x00' in name:
        raise RecoveryError('unsafe_file_path')
    return Path(*value.parts)


def sha(path):
    if path.is_symlink() or not path.is_file():raise RecoveryError('invalid_file')
    h=hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda:handle.read(65536),b''):h.update(chunk)
    return h.hexdigest()


def tree(root):
    if root.is_symlink() or not root.is_dir():raise RecoveryError('invalid_private_directory')
    found=[]
    for path in sorted(root.rglob('*')):
        if path.is_symlink():raise RecoveryError('symlink_rejected')
        if path.is_file():found.append(path)
        elif not path.is_dir():raise RecoveryError('special_file_rejected')
    return found


def connection(path,immutable=False):
    return sqlite3.connect(path.as_uri()+'?mode=ro'+('&immutable=1' if immutable else ''),uri=True,timeout=10)


def database_info(database,private,immutable=False):
    with connection(database,immutable) as db:
        if db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)] or db.execute('PRAGMA foreign_key_check').fetchone():
            raise RecoveryError('database_integrity')
        migrations=db.execute('SELECT app,name FROM django_migrations ORDER BY app,name').fetchall()
        schema=db.execute("SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name").fetchall()
        tables=[name for name,sql in schema if sql.startswith('CREATE TABLE') and name!='sqlite_sequence']
        records={name:db.execute('SELECT count(*) FROM "'+name.replace('"','""')+'"').fetchone()[0] for name in tables}
        if not {'auth_user','django_session','django_migrations','django_content_type','django_admin_log'}.issubset(tables):
            raise RecoveryError('not_foundation_database')
        if any(name.startswith(('shipments_','tracking_','ai_')) for name in tables):
            raise RecoveryError('legacy_schema_requires_matching_old_image')
    return {'migrations':migrations,'schema_sha256':hashlib.sha256(json.dumps(schema).encode()).hexdigest(),'records':records}


def require_quiet(data,acknowledged):
    if not acknowledged:raise RecoveryError('pause_writers_first')
    marker_path=data/'maintenance.lock'
    if marker_path.is_symlink() or not marker_path.is_file() or marker_path.stat().st_size>4096:raise RecoveryError('maintenance_required')
    try:marker=json.loads(marker_path.read_text())
    except Exception:raise RecoveryError('maintenance_required') from None
    if marker.get('project')!='jahez-shipping':raise RecoveryError('maintenance_required')


def secure_tree(root):
    root.chmod(0o700)
    for path in root.rglob('*'):
        if path.is_symlink():raise RecoveryError('symlink_rejected')
        path.chmod(0o700 if path.is_dir() else 0o600)


def backup(data,destination,quiesced=False,label='manual'):
    data,destination=allowed(data),allowed(destination)
    require_quiet(data,quiesced)
    private=data/'private';files=tree(private)
    database=data/'shipping.sqlite3'
    if database.is_symlink() or not database.is_file():raise RecoveryError('missing_database')
    if destination==private or private in destination.parents or destination==data:raise RecoveryError('unsafe_backup_destination')
    destination.mkdir(parents=True,exist_ok=True,mode=0o700)
    needed=database.stat().st_size*2+sum(p.stat().st_size for p in files)
    if shutil.disk_usage(destination).free<needed+1024*1024:raise RecoveryError('insufficient_space')
    ident=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:12]
    staging=destination/('.incomplete-'+ident);staging.mkdir(mode=0o700)
    try:
        with connection(database) as source,sqlite3.connect(staging/'shipping.sqlite3') as target:
            source.backup(target)
            target.execute('PRAGMA journal_mode=DELETE')
        shutil.copytree(private,staging/'private',symlinks=False)
        info=database_info(staging/'shipping.sqlite3',staging/'private',True)
        manifest={'project':'jahez-shipping','format':2,'id':ident,'created_at':datetime.now(timezone.utc).isoformat(),
            'app_version':app_version(),'label':'pre-upgrade' if label=='pre-upgrade' else 'manual',
            **info,'files':{p.relative_to(staging).as_posix():{'sha256':sha(p),'size':p.stat().st_size}
                          for p in [staging/'shipping.sqlite3',*tree(staging/'private')]}}
        (staging/'manifest.json').write_text(json.dumps(manifest,sort_keys=True))
        secure_tree(staging);verify(staging)
        final=destination/ident;staging.rename(final)
        return final
    except Exception:
        # Keep incomplete evidence private; never present it as a recovery point.
        secure_tree(staging)
        raise


def verify(archive):
    archive=allowed(archive)
    if not archive.is_dir():raise RecoveryError('missing_archive')
    manifest_path=archive/'manifest.json'
    if manifest_path.is_symlink() or manifest_path.stat().st_size>5*1024*1024:raise RecoveryError('invalid_manifest')
    manifest=json.loads(manifest_path.read_text())
    if manifest.get('project')!='jahez-shipping' or manifest.get('format')!=2 or manifest.get('app_version')!=app_version():
        raise RecoveryError('incompatible_backup')
    if not isinstance(manifest.get('files'),dict) or 'shipping.sqlite3' not in manifest['files']:raise RecoveryError('invalid_manifest')
    actual={p.relative_to(archive).as_posix() for p in tree(archive)}-{'manifest.json'}
    if actual!=set(manifest['files']):raise RecoveryError('file_set_mismatch')
    for name,meta in manifest['files'].items():
        rel=relative(name)
        if name!='shipping.sqlite3' and (not rel.parts or rel.parts[0]!='private'):raise RecoveryError('unexpected_file')
        p=archive/rel
        if p.stat().st_size!=meta['size'] or sha(p)!=meta['sha256']:raise RecoveryError('checksum_mismatch')
    info=database_info(archive/'shipping.sqlite3',archive/'private',True)
    if info['schema_sha256']!=manifest['schema_sha256'] or info['records']!=manifest.get('records',info['records']) or [list(x) for x in info['migrations']]!=manifest['migrations']:
        raise RecoveryError('schema_or_documents_mismatch')
    return manifest


def verify_restored_private_files(target,manifest):
    """Check retained bytes against the verified archive, not just database metadata."""
    target=allowed(target)
    private=target/'private'
    expected={name:meta for name,meta in manifest['files'].items() if name.startswith('private/')}
    actual={'private/'+p.relative_to(private).as_posix() for p in tree(private)}
    if actual!=set(expected):raise RecoveryError('restored_file_set_mismatch')
    for name,meta in expected.items():
        file=target/relative(name)
        if file.stat().st_size!=meta['size'] or sha(file)!=meta['sha256']:
            raise RecoveryError('restored_file_checksum_mismatch')


def verify_restored_database(target,manifest):
    """Verify the exact quiesced backup bytes before opening the restored DB for writes."""
    database=allowed(target)/'shipping.sqlite3'
    expected=manifest['files']['shipping.sqlite3']
    if database.stat().st_size!=expected['size'] or sha(database)!=expected['sha256']:
        raise RecoveryError('restored_database_checksum_mismatch')


def restore(archive,target,replace=False,confirm_target='',quiesced=False,allow_damaged_target=False):
    manifest=verify(archive);archive=allowed(archive);target=allowed(target)
    if target==archive or archive in target.parents or target in archive.parents:raise RecoveryError('unsafe_restore_target')
    exists=target.exists() and any(target.iterdir())
    if exists:
        if not replace or confirm_target!=str(target):raise RecoveryError('exact_target_confirmation_required')
        require_quiet(target,quiesced)
        try:database_info(target/'shipping.sqlite3',target/'private')
        except (RecoveryError,sqlite3.DatabaseError):
            if not allow_damaged_target:raise RecoveryError('damaged_target_requires_explicit_flag') from None
            # Operator explicitly chose recovery over a damaged Shipping dataset; retain it verbatim.
            if (target/'shipping.sqlite3').is_symlink() or not (target/'shipping.sqlite3').is_file():raise RecoveryError('invalid_target_database')
            tree(target/'private')
    else:target.mkdir(parents=True,exist_ok=True,mode=0o700)
    token=uuid.uuid4().hex
    staging=target/('.restore-stage-'+token);staging.mkdir(mode=0o700)
    shutil.copy2(archive/'shipping.sqlite3',staging/'shipping.sqlite3')
    shutil.copytree(archive/'private',staging/'private')
    secure_tree(staging);database_info(staging/'shipping.sqlite3',staging/'private',True)
    verify_restored_database(staging,manifest)
    verify_restored_private_files(staging,manifest)
    rollback=target/('.pre-restore-'+token)
    moved=[]
    if exists:rollback.mkdir(mode=0o700)
    try:
        for name in ('shipping.sqlite3','shipping.sqlite3-wal','shipping.sqlite3-shm','private'):
            original=target/name
            if original.exists():original.rename(rollback/name);moved.append(name)
        for name in ('shipping.sqlite3','private'):(staging/name).rename(target/name)
        database_info(target/'shipping.sqlite3',target/'private',True)
        verify_restored_database(target,manifest)
        verify_restored_private_files(target,manifest)
        (target/'restored-manifest.json').write_text(json.dumps({'archive_id':manifest['id'],'app_version':manifest['app_version']}))
        (target/'restored-manifest.json').chmod(0o600)
        staging.rmdir()
    except Exception:
        # Keep writes paused; preserve both old and partially restored files for operator recovery.
        for name in reversed(moved):
            installed=target/name
            if installed.exists():installed.rename(staging/('failed-'+name))
            (rollback/name).rename(target/name)
        raise
    return {'files':len(manifest['files']),'rollback_retained':exists}


def prune(destination,days):
    destination=allowed(destination)
    if not 1<=days<=365:raise RecoveryError('invalid_retention')
    cutoff=datetime.now(timezone.utc)-timedelta(days=days);removed=0
    for path in destination.iterdir():
        if not path.is_dir() or path.name.startswith('.'):continue
        try:manifest=verify(path)
        except Exception:continue
        created=datetime.fromisoformat(manifest['created_at'])
        if created<cutoff:shutil.rmtree(path);removed+=1
    return removed
