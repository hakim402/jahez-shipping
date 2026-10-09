"""Private I/O outside write transactions; conversion isolated in a bounded process."""
import hashlib
import json
import subprocess
import sys
from .provider import AIError


def extract_document(document):
    try:
        with document.file.open('rb') as handle:
            data = handle.read(5 * 1024 * 1024 + 1)
        if len(data) != document.size or hashlib.sha256(data).hexdigest() != document.checksum:
            raise AIError('document_changed')
        result = subprocess.run([sys.executable, '-m', 'apps.ai.convert'], input=data, capture_output=True, timeout=15, check=True)
        if len(result.stdout) > 5 * 1024 * 1024:
            raise AIError('document_limit')
        return json.loads(result.stdout)
    except AIError:
        raise
    except Exception:
        raise AIError('document_invalid') from None
