import os
from django.core.exceptions import ImproperlyConfigured
from .base import *  # noqa: F403

if SECRET_KEY.startswith("dev-"):
    raise ImproperlyConfigured("Production cannot use a development secret.")
if not os.environ.get("DJANGO_ALLOWED_HOSTS") or not os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS"):
    raise ImproperlyConfigured("Production requires explicit allowed hosts and trusted HTTPS origins.")
if "*" in ALLOWED_HOSTS or any(h in ("localhost", "127.0.0.1") for h in ALLOWED_HOSTS):
    raise ImproperlyConfigured("Production hosts must be explicit production hostnames.")
if any(not origin.startswith("https://") for origin in CSRF_TRUSTED_ORIGINS):
    raise ImproperlyConfigured("Production trusted origins must use HTTPS.")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^health/live/$", r"^health/ready/$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 0  # Activate only after Phase 9 verifies TLS.
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
