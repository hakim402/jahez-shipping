from django.conf import settings
from django.db import connection
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.utils.translation import get_language
from django.views.decorators.http import require_http_methods, require_GET
from redis import Redis
from .copy import COPY

def public_context(page):
    lang = "ar" if get_language() == "ar" else "en"
    return {"c": COPY[lang], "lang": lang, "other_lang": "en" if lang == "ar" else "ar", "direction": "rtl" if lang == "ar" else "ltr", "page": page}

@require_GET
def landing_redirect(request):
    return redirect("/ar/")

@require_http_methods(["GET", "POST"])
def home(request):
    context = public_context("home")
    context["submitted"] = request.method == "POST"
    # This foundation never looks up records or sends provider requests.
    # Do not echo or persist a submitted reference in a preview.
    response = render(request, "public/home.html", context)
    response["Cache-Control"] = "no-store"
    if request.method == "POST":
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
    return JsonResponse({"status": "ready", "integrations": "disabled_in_foundation"})

@require_GET
def robots(request):
    return HttpResponse("User-agent: *\nDisallow: /en/admin/\nDisallow: /ar/admin/\nDisallow: /health/\n", content_type="text/plain")
