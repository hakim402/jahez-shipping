"""Migration-only safeguard for retirement of the 0.8.1 schema, never a product API."""
import hashlib
import json
import os
from pathlib import Path
from .recovery import allowed, connection, tree, sha, relative

LEGACY_TABLES = (
    'shipments_customer', 'shipments_shipment', 'shipments_shipmentitem',
    'shipments_trackingleg', 'shipments_trackingevent', 'shipments_document',
    'shipments_auditentry', 'shipments_fileremoval', 'tracking_webhookreceipt',
    'tracking_integrationjob', 'ai_aidraft', 'ai_assistantrun',
)


def row_digest(cursor, table):
    quoted='"'+table.replace('"','""')+'"'
    columns=[row[1] for row in cursor.execute('PRAGMA table_info('+quoted+')').fetchall()]
    selection=','.join('quote("'+name.replace('"','""')+'")' for name in columns)
    cursor.execute('SELECT '+selection+' FROM '+quoted+' ORDER BY rowid')
    digest=hashlib.sha256()
    for row in cursor:
        digest.update(repr(tuple(row)).encode());digest.update(b'\n')
    return digest.hexdigest()


def require_legacy_backup(apps, schema_editor):
    """Empty fresh installs pass. Any existing account/data requires matching recovery evidence."""
    db=schema_editor.connection
    cursor=db.cursor()
    has_data=any(cursor.execute('SELECT 1 FROM "'+table+'" LIMIT 1').fetchone()
                 for table in (*LEGACY_TABLES,'auth_user','auth_group','auth_permission','django_content_type','django_session','django_admin_log'))
    if not has_data:
        return
    try:
        if os.environ.get('SHIPPING_ALLOW_SCHEMA_CLEANUP')!='true':
            raise ValueError()
        archive=allowed(os.environ['SHIPPING_PRE_CLEANUP_ARCHIVE'])
        manifest_path=archive/'manifest.json'
        if manifest_path.is_symlink() or manifest_path.stat().st_size>5*1024*1024:raise ValueError()
        manifest=json.loads(manifest_path.read_text())
        if manifest.get('project')!='jahez-shipping' or manifest.get('format')!=1 or manifest.get('app_version')!='0.8.1':raise ValueError()
        files=manifest['files']
        if {p.relative_to(archive).as_posix() for p in tree(archive)}-{'manifest.json'}!=set(files):raise ValueError()
        for name,metadata in files.items():
            part=relative(name)
            if name!='shipping.sqlite3' and part.parts[0]!='private':raise ValueError()
            file=archive/part
            if file.stat().st_size!=metadata['size'] or sha(file)!=metadata['sha256']:raise ValueError()
        source_data=Path(db.settings_dict['NAME']).parent
        marker=source_data/'maintenance.lock'
        if marker.is_symlink() or json.loads(marker.read_text()).get('project')!='jahez-shipping':raise ValueError()
        with connection(archive/'shipping.sqlite3',True) as old:
            if old.execute('PRAGMA integrity_check').fetchall()!=[('ok',)] or old.execute('PRAGMA foreign_key_check').fetchone():raise ValueError()
            tables=[name for (name,) in old.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            if not set(LEGACY_TABLES).issubset(tables):raise ValueError()
            old_schema=old.execute("SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name").fetchall()
            live_schema=db.cursor().execute("SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name").fetchall()
            if old_schema!=live_schema or hashlib.sha256(json.dumps(old_schema).encode()).hexdigest()!=manifest['schema_sha256']:raise ValueError()
            for table in tables:
                if row_digest(old.cursor(),table)!=row_digest(db.cursor(),table):raise ValueError()
            for name,checksum,size in old.execute('SELECT file,checksum,size FROM shipments_document'):
                path=archive/'private'/relative(name)
                if path.stat().st_size!=size or sha(path)!=checksum:raise ValueError()
        current_private=source_data/'private'
        expected={name[len('private/'):] for name in files if name.startswith('private/')}
        if {p.relative_to(current_private).as_posix() for p in tree(current_private)}!=expected:raise ValueError()
        for name in expected:
            if sha(current_private/name)!=files['private/'+name]['sha256']:raise ValueError()
    except Exception:
        raise RuntimeError('Cleanup refused: require explicit cleanup authorization, a Shipping maintenance marker and a verified matching 0.8.1 database/private-file backup. Keep all writers stopped; restore with the old image to recover data.') from None


def remove_retired_permissions(apps, schema_editor):
    # Required auth/content types and ordinary admin history stay. SET_NULL retains log rows.
    apps.get_model('contenttypes','ContentType').objects.using(schema_editor.connection.alias).filter(
        app_label__in=('shipments','tracking','ai')).delete()
