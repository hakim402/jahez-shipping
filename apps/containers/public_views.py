"""Read reviewed saved data only. Never imports/invokes refresh, jobs, browser or Groq."""
import re

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.views.decorators.http import require_GET

from apps.core.views import public_context
from apps.core.privacy import client_address
from .models import Container
from .public_data import validate_snapshot, projection

CODE = re.compile(r"JHZ-[A-Z2-7]{26}\Z")


def private_response(response):
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


@require_GET
def lookup(request, code=None):
    context = public_context("tracking")
    context.update(state="initial", shipment=None, lookup_code="")
    status = 200
    retry = None
    try:
        key = "public-lookup:" + salted_hmac("shipping-lookup-ip", client_address(request)).hexdigest()
        cache.add(key, 0, timeout=300)
        if cache.incr(key) > 30:
            context["state"], status, retry = "limited", 429, "300"
        else:
            values = request.GET.getlist("code") if code is None else [code]
            raw = values[0] if len(values) == 1 else ""
            if code is None and not values:
                raw = None
            normalized = raw.strip().upper() if raw is not None and len(raw) <= 80 else ""
            if raw is None:
                pass
            elif not CODE.fullmatch(normalized):
                context["state"], status = "invalid", 400
            elif code is None or code != normalized:
                return private_response(redirect(f"/{context['lang']}/track/{normalized}/"))
            else:
                data = Container.objects.filter(lookup_code=normalized, is_published=True, archived_at__isnull=True).values_list("public_snapshot", flat=True).first()
                if not data:
                    context["state"], status = "not_found", 404
                else:
                    approved = validate_snapshot(data)
                    context.update(state="found", shipment=projection(approved, context["lang"], timezone.now()), lookup_code=normalized)
                    context["switch_url"] = f"/{context['other_lang']}/track/{normalized}/"
    except (DatabaseError, ValueError, TypeError, ValidationError):
        context.update(state="unavailable", shipment=None, lookup_code="")
        status, retry = 503, "60"
    except Exception:
        # Cache outages fail closed, with no private exception/SQL/provider payload in the page or logs.
        context.update(state="unavailable", shipment=None, lookup_code="")
        status, retry = 503, "60"
    response = private_response(render(request, "public/tracking.html", context, status=status))
    if retry:
        response["Retry-After"] = retry
    return response
