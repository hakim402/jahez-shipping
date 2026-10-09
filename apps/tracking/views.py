import hashlib
import hmac
import re
from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.db import DatabaseError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .adapter import configuration
from .payloads import parse_webhook, PayloadError
from .services import accept_receipt

MAX_BODY = 512 * 1024


@csrf_exempt
@require_POST
def webhook(request):
    def response(status, state):
        result = JsonResponse({"state": state}, status=status)
        result["Cache-Control"] = "no-store"
        result["X-Robots-Tag"] = "noindex, nofollow"
        return result
    if configuration() != "ready":
        return response(503, "disabled")
    length = request.META.get("CONTENT_LENGTH", "")
    if length and (not length.isdigit() or int(length) > MAX_BODY):
        return response(413, "too_large")
    if request.content_type != "application/json":
        return response(415, "json_required")
    try:
        raw = request.body
    except RequestDataTooBig:
        return response(413, "too_large")
    if len(raw) > MAX_BODY:
        return response(413, "too_large")
    signature = request.headers.get("sign", "")
    expected = hashlib.sha256(raw + b"/" + settings.TRACK17_API_KEY.encode("utf-8")).hexdigest()
    if not re.fullmatch(r"[0-9a-fA-F]{64}", signature) or not hmac.compare_digest(expected, signature.lower()):
        return response(401, "invalid_signature")
    try:
        payload = parse_webhook(raw)
    except PayloadError:
        return response(400, "invalid_payload")
    try:
        accept_receipt(hashlib.sha256(raw).hexdigest(), payload)
    except DatabaseError:
        return response(503, "storage_unavailable")
    # 17TRACK requires HTTP 200, including deduplicated durably accepted work.
    return response(200, "accepted")
