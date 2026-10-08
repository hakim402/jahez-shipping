import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from django.templatetags.static import static
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parents[2]
APP_VERSION = "0.2.0"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if len(SECRET_KEY) < 50 or SECRET_KEY.startswith(("REPLACE_", "GENERATE_")):
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must contain at least 50 characters. Generate a private environment file with scripts/init_dev_env.py.")
DEBUG = False
ALLOWED_HOSTS = [s.strip() for s in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",") if s.strip()]
INSTALLED_APPS = ["unfold", "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles", "apps.core.apps.CoreConfig"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "whitenoise.middleware.WhiteNoiseMiddleware", "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.locale.LocaleMiddleware", "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware", "apps.core.middleware.AdminLoginThrottleMiddleware", "django.contrib.messages.middleware.MessageMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware"]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True, "OPTIONS": {"context_processors": ["django.template.context_processors.request", "django.template.context_processors.i18n", "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages"]}}]
WSGI_APPLICATION = "config.wsgi.application"
DATA_DIR = Path(os.environ.get("SHIPPING_DATA_DIR", str(BASE_DIR / "data")))
PRIVATE_ROOT = DATA_DIR / "private"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": DATA_DIR / "shipping.sqlite3", "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE", "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;"}, "ATOMIC_REQUESTS": False}}
AUTH_PASSWORD_VALIDATORS = [{"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"}, {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}}, {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"}, {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"}]
LANGUAGE_CODE = "ar"
LANGUAGES = [("en", "English"), ("ar", "العربية")]
TIME_ZONE = "UTC"
BUSINESS_TIME_ZONE = os.environ.get("SHIPPING_BUSINESS_TIME_ZONE", "Asia/Kabul")
USE_I18N = True
USE_TZ = True
LOCALE_PATHS = [BASE_DIR / "locale"]
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": PRIVATE_ROOT}}, "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": os.environ.get("CACHE_REDIS_URL", "redis://redis:6379/1"), "KEY_PREFIX": "jahez_shipping", "OPTIONS": {"socket_connect_timeout": 2, "socket_timeout": 2}}}
CELERY_BROKER_URL = REDIS_URL
CELERY_TASK_IGNORE_RESULT = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_WORKER_CONCURRENCY = 1
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_SOFT_TIME_LIMIT = 60
CELERY_TASK_TIME_LIMIT = 90
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULE = {}
TRACK17_ENABLED = os.environ.get("TRACK17_ENABLED", "false").lower() == "true"
GROQ_ENABLED = os.environ.get("GROQ_ENABLED", "false").lower() == "true"
# Provider implementations are intentionally outside Phase 1.
FOUNDATION_PREVIEW = True
PUBLIC_UI_PREVIEW_ENABLED = False
CSRF_TRUSTED_ORIGINS = [s.strip() for s in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "http://localhost:18744,http://127.0.0.1:18744").split(",") if s.strip()]
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_NAME = "jahez_shipping_session"
CSRF_COOKIE_NAME = "jahez_shipping_csrf"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
DATA_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
UNFOLD = {
    "SITE_TITLE": _("JAHEZ Shipping"), "SITE_HEADER": "JAHEZ Shipping", "SITE_SUBHEADER": _("Operations workspace"), "SITE_VERSION": APP_VERSION,
    "SITE_URL": "/", "SITE_ICON": {"light": lambda request: static("brand/jahez-icon-brand.png"), "dark": lambda request: static("brand/jahez-icon-white.png")},
    "SITE_FAVICONS": [{"rel": "icon", "type": "image/png", "href": lambda request: static("brand/jahez-icon-brand.png")}],
    "ENVIRONMENT": "apps.core.admin.environment", "DASHBOARD_CALLBACK": "apps.core.admin.dashboard",
    "LOGIN": {"image": lambda request: static("illustrations/shipping-scene.svg")},
    "SHOW_LANGUAGES": True, "STYLES": [lambda request: static("css/admin.css")],
    "COLORS": {"primary": {"50": "#F4F1FF", "100": "#EDE6FF", "200": "#D9CBFF", "300": "#BBA3FF", "400": "#9979FF", "500": "#7B57FC", "600": "#6842E5", "700": "#5734C9", "800": "#4527A8", "900": "#351E80", "950": "#21114D"}},
    "SIDEBAR": {"show_all_applications": False, "navigation": [{"title": _("Workspace"), "items": [{"title": _("Dashboard"), "icon": "dashboard", "link": reverse_lazy("admin:index")}, {"title": _("View tracking preview"), "icon": "travel_explore", "link": "/en/"}]}, {"title": _("Access management"), "items": [{"title": _("Users"), "icon": "group", "link": reverse_lazy("admin:auth_user_changelist"), "permission": lambda request: request.user.has_perm("auth.view_user")}, {"title": _("Groups"), "icon": "shield", "link": reverse_lazy("admin:auth_group_changelist"), "permission": lambda request: request.user.has_perm("auth.view_group")}]}]},
}
