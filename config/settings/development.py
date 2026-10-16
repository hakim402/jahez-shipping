from .base import *  # noqa: F403
DEBUG = True
STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Django serves source static assets in development; WhiteNoise is production-only.
MIDDLEWARE = [m for m in MIDDLEWARE if m != "whitenoise.middleware.WhiteNoiseMiddleware"]
