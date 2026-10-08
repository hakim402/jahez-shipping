from django.conf import settings
from django.db import connection
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.utils.translation import get_language
from django.views.decorators.http import require_http_methods, require_GET
from redis import Redis
from .copy import COPY
from .forms import TrackingReferenceForm
from .preview import PREVIEW_STATES, synthetic_result


def public_context(page):
    lang = "ar" if get_language() == "ar" else "en"
    c = COPY[lang]
    path = f"/{lang}/" + ("who-we-are/" if page == "about" else "")
    return {
        "c": c, "lang": lang, "other_lang": "en" if lang == "ar" else "ar",
        "direction": "rtl" if lang == "ar" else "ltr", "page": page,
        "preview_enabled": settings.DEBUG and settings.PUBLIC_UI_PREVIEW_ENABLED,
        "page_description": c["about_meta"] if page == "about" else c["intro"],
        "canonical_url": "https://shipping.jahez.online" + path,
    }


@require_GET
def landing_redirect(request):
    return redirect("/ar/")


@require_http_methods(["GET", "POST"])
def home(request):
    context = public_context("home")
    state = None
    demo = False
    if request.method == "POST":
        selected = request.POST.get("preview_state")
        if selected is not None and context["preview_enabled"] and selected in PREVIEW_STATES:
            state = selected
            demo = True
        elif selected is not None:
            # Production must not select fixtures, even when request/env is tampered with.
            state = "unavailable"
        else:
            form = TrackingReferenceForm(request.POST)
            state = "unavailable" if form.is_valid() else "invalid"
    context.update({
        "state": state, "is_demo": demo, "submitted": request.method == "POST",
        "invalid": state == "invalid",
        "preview_states": [(s, context["c"]["state_" + s]) for s in PREVIEW_STATES],
    })
    if demo and state in ("found", "no_updates"):
        context["result"] = synthetic_result(context["lang"], no_updates=state == "no_updates")
    if state and state not in ("found", "no_updates"):
        prefix = {"initial": "initial", "submitting": "loading", "invalid": "invalid", "not_found": "not_found", "rate_limited": "limited", "unavailable": "unavailable"}[state]
        context["state_title"] = context["c"][prefix + "_title"]
        context["state_body"] = context["c"]["invalid_message" if state == "invalid" else prefix + "_body"]
    # Never echo/store the requested capability or send an external provider call.
    response = render(request, "public/home.html", context)
    response["Cache-Control"] = "no-store"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


@require_GET
def about(request):
    return render(request, "public/about.html", public_context("about"))


@require_GET
def liveness(request):
    return JsonResponse({"status": "ok", "service": "jahez-shipping", "version": settings.APP_VERSION})


@require_GET
def readiness(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2).ping()
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ready", "integrations": "disabled_in_public_preview"})


@require_GET
def robots(request):
    return HttpResponse("User-agent: *\nDisallow: /en/admin/\nDisallow: /ar/admin/\nDisallow: /health/\n", content_type="text/plain")
