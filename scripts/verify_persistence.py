#!/usr/bin/env python3
"""App-scoped development proof of SQLite and private-file restart persistence."""
import json
import os
import sys
from pathlib import Path
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import django
django.setup()
from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore
from django.db import connection

if not settings.DEBUG:
    raise SystemExit('This synthetic persistence check is development-only.')
marker = settings.PRIVATE_ROOT / 'foundation-persistence-check.json'
mode = sys.argv[1] if len(sys.argv) > 1 else ''
if mode == 'prepare':
    if marker.exists():
        raise SystemExit('Existing check marker kept intact. Verify/clean it before preparing again.')
    session = SessionStore()
    session['foundation_test'] = 'synthetic-restart-proof'
    session.save()
    with marker.open('x') as file:
        json.dump({'session': session.session_key, 'content': 'synthetic-restart-proof'}, file)
    marker.chmod(0o600)
    print('Prepared synthetic SQLite session and private-file marker. No customer/admin data created.')
elif mode == 'verify':
    proof = json.loads(marker.read_text())
    session = SessionStore(session_key=proof['session'])
    assert proof['content'] == 'synthetic-restart-proof'
    assert session.get('foundation_test') == 'synthetic-restart-proof'
    with connection.cursor() as cursor:
        cursor.execute('PRAGMA journal_mode')
        journal = cursor.fetchone()[0]
        cursor.execute('PRAGMA busy_timeout')
        timeout = cursor.fetchone()[0]
    assert journal.lower() == 'wal', journal
    assert timeout == 20000, timeout
    print(f'PASS: SQLite session and private-file content persisted. journal={journal}; busy_timeout={timeout}ms.')
elif mode == 'cleanup':
    proof = json.loads(marker.read_text())
    session = SessionStore(session_key=proof['session'])
    assert session.get('foundation_test') == 'synthetic-restart-proof'
    session.delete()
    marker.unlink()
    print('Removed only the synthetic check session and its private marker.')
else:
    raise SystemExit('Usage: python scripts/verify_persistence.py prepare|verify|cleanup')
