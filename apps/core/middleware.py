import hashlib
import secrets
import logging
import time
from django.core.cache import cache
from django.http import HttpResponse
from django.utils.translation import get_language
from django.utils import timezone
from django.conf import settings
from zoneinfo import ZoneInfo
from .privacy import client_address
from .maintenance import active


class RequestSafetyMiddleware:
    def __init__(self,get_response):self.get_response=get_response
    def __call__(self,request):
        request.correlation_id=secrets.token_hex(8)
        started=time.monotonic()
        if active() and not request.path.startswith(('/health/','/static/')):
            from .errors import error_response
            response=error_response(request,503,'maintenance')
            response['Retry-After']='60'
        else:
            response=self.get_response(request)
        response['X-Request-ID']=request.correlation_id
        response.setdefault('X-Content-Type-Options','nosniff')
        response.setdefault('X-Frame-Options','DENY')
        response.setdefault('Referrer-Policy','same-origin')
        private=('/admin/' in request.path or request.path.startswith(('/health/',)))
        if private or request.method=='POST' or response.status_code>=400:
            if 'no-store' not in response.get('Cache-Control',''):
                response['Cache-Control']='no-store'
            response['X-Robots-Tag']='noindex, nofollow'
        if not request.path.startswith('/static/') and 'Content-Security-Policy' not in response:
            response['Content-Security-Policy']="default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
        route='health' if request.path.startswith('/health/') else 'admin' if '/admin/' in request.path else 'public' if request.path in ('/en/','/ar/') else 'other'
        logging.getLogger('jahez.request').info('complete',extra={'request_id':request.correlation_id,
            'method':request.method,'route':route,'status':response.status_code,'duration_ms':int((time.monotonic()-started)*1000)})
        return response


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

    Only an explicitly allowlisted peer may supply one valid X-Real-IP address.
    Do not trust a caller-supplied X-Forwarded-For value.
    """
    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        if request.method == "POST" and request.path.endswith("/admin/login/"):
            address = hashlib.sha256(client_address(request).encode()).hexdigest()
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
