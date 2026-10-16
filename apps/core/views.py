"""Saved public branding only. No tracking lookup, retrieval or provider requests."""
import re
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import get_language
from django.views.decorators.http import require_GET
from .copy import COPY


def public_context(page):
    lang = "ar" if get_language() == "ar" else "en"
    number = re.sub(r"[\s()-]", "", settings.SHIPPING_WHATSAPP_NUMBER).removeprefix("+")
    if not re.fullmatch(r"[1-9][0-9]{6,14}", number):
        number = ""
    path = f"/{lang}/" + ("who-we-are/" if page == "about" else "")
    return {
        "c": COPY[lang], "lang": lang, "other_lang": "en" if lang == "ar" else "ar",
        "direction": "rtl" if lang == "ar" else "ltr", "page": page,
        "page_description": COPY[lang]["about_meta"] if page == "about" else COPY[lang]["intro"],
        "canonical_url": "https://shipping.jahez.online" + path,
        "whatsapp_number": number, "whatsapp_url": f"https://wa.me/{number}" if number else "",
        "tracking_empty": "Container tracking is being prepared. Please contact JAHEZ for an update." if lang == "en" else "نعمل على تجهيز تتبع الحاويات. يرجى التواصل مع جاهز للحصول على آخر المستجدات.",
    }


@require_GET
def landing_redirect(request):
    return redirect("/ar/")


@require_GET
def home(request):
    response = render(request, "public/home.html", public_context("home"))
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
    from .maintenance import active
    if active():
        return JsonResponse({"status": "maintenance"}, status=503)
    try:
        from django.db.migrations.executor import MigrationExecutor
        # Refuse readiness until the reduced schema is actually installed.
        executor = MigrationExecutor(connection)
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            raise RuntimeError("schema_pending")
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM django_session LIMIT 1")
            cursor.fetchone()
        if not cache.add("health:cache-probe", "ready", timeout=30):
            if cache.get("health:cache-probe") != "ready":
                raise RuntimeError("cache_unavailable")
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ready"})


@require_GET
def robots(request):
    return HttpResponse("User-agent: *\nDisallow: /en/admin/\nDisallow: /ar/admin/\nDisallow: /health/\n", content_type="text/plain")
