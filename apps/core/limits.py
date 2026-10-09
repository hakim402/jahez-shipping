import hashlib
from django.core.cache import cache


def lookup_limit(request):
    # Do not key/cache the submitted tracking capability. Forwarding headers untrusted.
    address = hashlib.sha256(request.META.get("REMOTE_ADDR", "unknown").encode()).hexdigest()
    key = "public-lookup:" + address
    try:
        cache.add(key, 0, timeout=300)
        attempts = cache.incr(key)
    except Exception:
        return "unavailable"
    return "rate_limited" if attempts > 30 else None
