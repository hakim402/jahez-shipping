"""Read-only comparison of DEMO records and private files across app restarts."""
import hashlib
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
import django
django.setup()
from django.conf import settings
from django.db import connection
from apps.shipments.models import Shipment, Document


def manifest():
    rows = [{"pk": s.pk, "revision": s.revision, "status": s.status, "published": s.published,
        "reference_hash": hashlib.sha256(s.reference.encode()).hexdigest(),
        "items": s.items.count(), "events": s.events.count(), "legs": s.legs.count()} for s in Shipment.objects.filter(is_demo=True).order_by("pk")]
    documents = []
    for document in Document.objects.filter(shipment__is_demo=True).order_by("pk"):
        with document.file.open("rb") as f:
            checksum = hashlib.sha256(f.read()).hexdigest()
        assert checksum == document.checksum, "Private document checksum mismatch."
        documents.append({"pk": document.pk, "shipment": document.shipment_id, "checksum": checksum})
    assert rows and documents, "Run seed_demo before this review check."
    return {"shipments": rows, "documents": documents}


path = settings.DATA_DIR / "phase03-persistence-review.json"
if sys.argv[1] == "prepare":
    path.write_text(json.dumps(manifest()))
    path.chmod(0o600)
    print("Synthetic manual-record/private-file baseline saved privately.")
elif sys.argv[1] == "verify":
    assert json.loads(path.read_text()) == manifest(), "Restart changed the review baseline."
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA integrity_check")
        assert cursor.fetchone()[0] == "ok"
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        cursor.execute("PRAGMA busy_timeout")
        busy = cursor.fetchone()[0]
    print(f"PASS: DEMO shipment/item/event relations and private bill checksums survived restart; integrity ok, journal={mode}, busy_timeout={busy}ms.")
else:
    raise SystemExit("Use prepare or verify.")
