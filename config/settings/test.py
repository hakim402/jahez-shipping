import os
import tempfile
from pathlib import Path
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-" + "x" * 60)
from .development import *
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
_test_data = tempfile.TemporaryDirectory(prefix="jahez-foundation-test-")
DATA_DIR = Path(_test_data.name)
PRIVATE_ROOT = DATA_DIR / "private"
DATABASES["default"]["NAME"] = DATA_DIR / "shipping.sqlite3"
STORAGES = {**STORAGES, "default": {"BACKEND": "apps.core.storage.PrivateStorage", "OPTIONS": {"location": PRIVATE_ROOT}}}
GROQ_ENABLED = False
GROQ_API_KEY = ""
GROQ_TEXT_MODEL = ""
GROQ_VISION_MODEL = ""
LOGGING["loggers"]["jahez.request"]["handlers"] = ["silent"]
