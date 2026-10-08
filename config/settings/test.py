import os
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-" + "x" * 60)
from .development import *  # noqa: F403
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
