from django.utils.translation import gettext_lazy as _
import hashlib
import json
import subprocess
import sys
import uuid
from pathlib import Path
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import transaction
from .models import Document, Shipment
from .services import require, audit


def inspect_upload(upload):
    if upload.size == 0 or upload.size > 5 * 1024 * 1024:
        raise ValidationError(_("Documents must be nonempty and at most 5 MiB."))
    data = upload.read(5 * 1024 * 1024 + 1)
    upload.seek(0)
    try:
        result = subprocess.run([sys.executable, "-m", "apps.shipments.inspect_file"], input=data, capture_output=True, timeout=8, check=True)
        metadata = json.loads(result.stdout)
    except (subprocess.SubprocessError, ValueError):
        raise ValidationError(_("Invalid, encrypted, active, oversized, or unsupported document. Use a plain PDF (up to 40 pages), PNG, or JPEG."))
    allowed = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
    extension = Path(upload.name).suffix.lower()
    if allowed.get(extension) != metadata["mime"] or upload.content_type != metadata["mime"]:
        raise ValidationError(_("File extension, declared MIME type and detected content must agree."))
    metadata["checksum"] = hashlib.sha256(data).hexdigest()
    return metadata


def store_document(shipment, upload, category, metadata, actor, system_demo=False):
    from django.conf import settings
    if not (system_demo and settings.DEBUG and shipment.is_demo):
        require(actor, "add_document")
    if Shipment.objects.get(pk=shipment.pk).archived_at:
        raise ValidationError(_("Archived shipments cannot receive documents."))
    # Inspection and file I/O are outside the SQLite write transaction.
    stored_name = default_storage.save("documents/" + uuid.uuid4().hex + metadata["extension"], upload)
    try:
        with transaction.atomic():
            if Shipment.objects.get(pk=shipment.pk).archived_at:
                raise ValidationError(_("Shipment was archived during upload."))
            document = Document.objects.create(shipment=shipment, category=category, file=stored_name,
                original_filename=Path(upload.name).name[:180], checksum=metadata["checksum"], mime_type=metadata["mime"],
                size=upload.size, page_count=metadata["pages"], uploaded_by=actor)
            audit(document, actor, "document.uploaded", identity="seed_demo" if system_demo else "staff")
            return document
    except Exception:
        default_storage.delete(stored_name)
        raise
