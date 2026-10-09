import hashlib
import secrets
from django.core.cache import cache
from django.http import HttpResponse
from django.utils.translation import get_language
from django.utils import timezone
from django.conf import settings
from zoneinfo import ZoneInfo


class BusinessTimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.zone = ZoneInfo(settings.BUSINESS_TIME_ZONE)

    def __call__(self, request):
        timezone.activate(self.zone)
        try:
            return self.get_response(request)
        finally:
            timezone.deactivate()

class AdminLoginThrottleMiddleware:
    """Shared per-IP bound on login POSTs; fail closed when Redis is unavailable.

    In production REMOTE_ADDR is the proxy: using the shared proxy-wide limit is
    conservative until verified proxy/IP handling is added in Phase 7/8.
    Do not trust a caller-supplied X-Forwarded-For value.
    """
    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        request.correlation_id = secrets.token_hex(8)
        if request.method == "POST" and request.path.endswith("/admin/login/"):
            address = hashlib.sha256(request.META.get("REMOTE_ADDR", "unknown").encode()).hexdigest()
            key = "admin-login:" + address
            ar = get_language() == "ar"
            try:
                cache.add(key, 0, timeout=300)
                attempts = cache.incr(key)
            except Exception:
                response = HttpResponse("خدمة تسجيل الدخول غير متاحة مؤقتًا." if ar else "Login is temporarily unavailable. Please try again shortly.", status=503)
                response["Cache-Control"] = "no-store"
                return response
            if attempts > 10:
                response = HttpResponse("محاولات كثيرة. حاول بعد خمس دقائق." if ar else "Too many login attempts. Try again in five minutes.", status=429)
                response["Retry-After"] = "300"
                response["Cache-Control"] = "no-store"
                return response
        response = self.get_response(request)
        response["X-Request-ID"] = request.correlation_id
        if "/admin/" in request.path:
            response["X-Robots-Tag"] = "noindex, nofollow"
        return response
