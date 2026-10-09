import os
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-" + "x" * 60)
from .development import *  # noqa: F403
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Test uploads never share the running app's private volume.
import tempfile
_test_private = tempfile.TemporaryDirectory(prefix='jahez-test-private-')
STORAGES = dict(STORAGES)
STORAGES['default'] = {'BACKEND': 'apps.shipments.storage.PrivateStorage', 'OPTIONS': {'location': _test_private.name}}

# Isolated tests never inherit live provider credentials/flags from owner env files.
TRACK17_ENABLED = False
TRACK17_API_KEY = ''
GROQ_ENABLED = False
GROQ_API_KEY = ''
GROQ_TEXT_MODEL = ''
GROQ_VISION_MODEL = ''
