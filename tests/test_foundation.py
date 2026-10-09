import secrets
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.contrib.staticfiles import finders
from django.urls import reverse
from django.utils import translation

class PublicPreviewTests(TestCase):
    def test_localized_pages_and_language_switches(self):
        for lang, direction, other in [("en", "ltr", "ar"), ("ar", "rtl", "en")]:
            for suffix in ["", "who-we-are/"]:
                with self.subTest(lang=lang, suffix=suffix):
                    r = self.client.get(f"/{lang}/{suffix}")
                    self.assertEqual(r.status_code, 200)
                    self.assertContains(r, f'lang="{lang}" dir="{direction}"')
                    self.assertContains(r, f'/{other}/{suffix}')
                    self.assertContains(r, "noindex,nofollow")
    def test_root_uses_arabic_default(self):
        self.assertRedirects(self.client.get("/"), "/ar/")
    def test_preview_post_does_not_echo_reference(self):
        reference = "PRIVATE-JAHEZ-CAPABILITY-12345"
        r = self.client.post("/en/", {"reference": reference})
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, reference)
        self.assertContains(r, "We could not find that reference.")
        self.assertEqual(r["Cache-Control"], "no-store")
        self.assertEqual(r["X-Robots-Tag"], "noindex, nofollow")
    def test_preview_post_requires_csrf(self):
        c = Client(enforce_csrf_checks=True)
        self.assertEqual(c.post("/en/", {"reference": "private"}).status_code, 403)
    def test_valid_origin_post_with_real_csrf_token(self):
        c = Client(enforce_csrf_checks=True)
        r = c.get("/en/", secure=True)
        self.assertEqual(r["Referrer-Policy"], "same-origin")
        self.assertContains(r, 'name="referrer" content="same-origin"')
        token = c.cookies["jahez_shipping_csrf"].value
        r = c.post("/en/", {"reference": "synthetic-reference", "csrfmiddlewaretoken": token}, secure=True, HTTP_ORIGIN="https://testserver")
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "synthetic-reference")
    def test_untrusted_origins_remain_rejected(self):
        c = Client(enforce_csrf_checks=True)
        c.get("/en/", secure=True)
        token = c.cookies["jahez_shipping_csrf"].value
        for origin in ["null", "https://untrusted.example"]:
            with self.subTest(origin=origin):
                self.assertEqual(c.post("/en/", {"csrfmiddlewaretoken": token}, secure=True, HTTP_ORIGIN=origin).status_code, 403)
    def test_no_private_media_route(self):
        self.assertEqual(self.client.get("/media/customer.pdf").status_code, 404)
        self.assertEqual(self.client.get("/data/shipping.sqlite3").status_code, 404)
    def test_assets_exist(self):
        for name in ["css/site.css", "js/alpine.min.js", "brand/jahez-icon-brand.png", "fonts/Cairo-Regular.ttf", "illustrations/shipping-scene.svg"]:
            self.assertTrue(finders.find(name), name)
    def test_health_and_provider_independence(self):
        self.assertEqual(self.client.get("/health/live/").json()["status"], "ok")
        with patch("apps.core.views.Redis.from_url") as redis:
            self.assertEqual(self.client.get("/health/ready/").status_code, 200)
            redis.return_value.ping.assert_called_once()
        with patch("apps.core.views.Redis.from_url", side_effect=ConnectionError):
            self.assertEqual(self.client.get("/health/ready/").status_code, 503)
    @override_settings(DEBUG=True)
    def test_seed_is_idempotent_and_production_disabled(self):
        call_command("seed_demo")
        call_command("seed_demo")
        self.assertEqual(User.objects.count(), 0)
        with override_settings(DEBUG=False), self.assertRaises(CommandError):
            call_command("seed_demo")
    def test_sqlite_uses_immediate_short_transactions(self):
        self.assertEqual(connection.settings_dict["OPTIONS"]["transaction_mode"], "IMMEDIATE")
        self.assertFalse(connection.settings_dict["ATOMIC_REQUESTS"])

class AdminFoundationTests(TestCase):
    def setUp(self):
        cache.clear()
    def test_unfold_login_in_both_languages(self):
        for lang in ["en", "ar"]:
            r = self.client.get(f"/{lang}/admin/login/")
            self.assertEqual(r.status_code, 200)
            self.assertContains(r, "جاهز للشحن" if lang == "ar" else "JAHEZ Shipping")
            self.assertContains(r, "unfold")
    def test_staff_login_with_csrf_creates_authenticated_session(self):
        password = secrets.token_urlsafe(32)
        user = User.objects.create_user("synthetic-login-check", password=password, is_staff=True)
        c = Client(enforce_csrf_checks=True)
        c.get("/en/admin/login/")
        token = c.cookies["jahez_shipping_csrf"].value
        r = c.post("/en/admin/login/", {"username": user.username, "password": password, "csrfmiddlewaretoken": token, "next": "/en/admin/"}, HTTP_ORIGIN="http://testserver")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(c.session["_auth_user_id"], str(user.pk))
        self.assertContains(c.get("/en/admin/"), "Shipment metrics require view permission.")
    def test_dashboard_requires_staff(self):
        self.assertEqual(self.client.get("/en/admin/").status_code, 302)
        user = User.objects.create_user("viewer", password="temporary-test-password")
        self.client.force_login(user)
        self.assertEqual(self.client.get("/en/admin/").status_code, 302)
    def test_staff_dashboard_is_real_shell_without_fake_metrics(self):
        user = User.objects.create_user("teststaff", is_staff=True)
        self.client.force_login(user)
        r = self.client.get("/en/admin/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Shipment metrics require view permission.")
        self.assertContains(r, "Integrations disabled")
        self.assertNotContains(r, "Manage Users")
        r = self.client.get("/ar/admin/")
        self.assertContains(r, "التكاملات غير متصلة")
    def test_account_management_requires_permissions(self):
        user = User.objects.create_user("staff", is_staff=True)
        self.client.force_login(user)
        self.assertEqual(self.client.get("/en/admin/auth/user/").status_code, 403)
    def test_login_is_bounded(self):
        for _ in range(10):
            self.assertNotEqual(self.client.post("/en/admin/login/", {"username": "absent", "password": "invalid"}).status_code, 429)
        r = self.client.post("/en/admin/login/", {"username": "absent", "password": "invalid"})
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r["Retry-After"], "300")
    def test_login_fails_closed_if_cache_unavailable(self):
        with patch("apps.core.middleware.cache.add", side_effect=ConnectionError):
            self.assertEqual(self.client.post("/en/admin/login/").status_code, 503)
