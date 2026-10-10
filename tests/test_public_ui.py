"""Phase 2: synthetic-fixture isolation, validation, and public-page semantics."""
from unittest.mock import patch
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.contrib.staticfiles import finders
from apps.core.preview import PREVIEW_STATES


@override_settings(DEBUG=True, PUBLIC_UI_PREVIEW_ENABLED=True)
class PublicDesignTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_all_synthetic_states_in_both_languages(self):
        for lang in ('en', 'ar'):
            for state in PREVIEW_STATES:
                with self.subTest(lang=lang, state=state):
                    response = self.client.post(f'/{lang}/', {'preview_state': state})
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.context['is_demo'])
                    self.assertEqual(response.context['state'], state)
                    self.assertContains(response, 'مثال تجريبي · ليس شحنة حقيقية' if lang == 'ar' else 'SYNTHETIC EXAMPLE · NOT A REAL SHIPMENT')
                    self.assertEqual(response['Cache-Control'], 'no-store')
                    self.assertEqual(response['X-Robots-Tag'], 'noindex, nofollow')
    def test_example_reference_alone_never_looks_up_a_fixture(self):
        with patch('apps.core.views.synthetic_result') as fixture:
            response = self.client.post('/en/', {'reference': 'JHZ-DEMO-7K4P8Q2'})
            self.assertEqual(response.context['state'], 'not_found')
            self.assertFalse(response.context['is_demo'])
            fixture.assert_not_called()
            self.assertNotContains(response, 'Reusable drinkware')
    def test_invalid_reference_is_not_echoed(self):
        for reference in ('', 'abc', '<script>alert(1)</script>', 'name with spaces', 'X' * 81):
            with self.subTest(reference=reference):
                response = self.client.post('/en/', {'reference': reference})
                self.assertEqual(response.context['state'], 'invalid')
                self.assertContains(response, 'aria-invalid="true"')
                if reference:
                    self.assertNotContains(response, reference)
    def test_unknown_preview_state_never_selects_a_fixture(self):
        with patch('apps.core.views.synthetic_result') as fixture:
            response = self.client.post('/en/', {'preview_state': '../../private'})
            self.assertEqual(response.context['state'], 'unavailable')
            fixture.assert_not_called()
    def test_get_parameters_do_not_select_results(self):
        response = self.client.get('/en/', {'preview_state': 'found', 'reference': 'private-reference'})
        self.assertIsNone(response.context['state'])
        self.assertNotContains(response, 'Reusable drinkware')
        self.assertNotContains(response, 'private-reference')
    def test_result_has_sources_unknown_eta_and_chronological_events(self):
        response = self.client.post('/en/', {'preview_state': 'found'})
        self.assertContains(response, 'Awaiting a confirmed estimate')
        self.assertContains(response, 'JAHEZ manual update')
        self.assertContains(response, 'Carrier-provided update')
        self.assertContains(response, 'Illustrative stale carrier data')
        timestamps = [event['occurred_at'] for event in response.context['result']['events']]
        self.assertEqual(timestamps, sorted(timestamps))
        self.assertEqual(len(timestamps), 4)
        self.assertNotContains(response, 'supplierId')
        self.assertNotContains(response, 'invoice.pdf')
    def test_no_updates_has_no_timeline_or_confirmed_eta(self):
        response = self.client.post('/en/', {'preview_state': 'no_updates'})
        self.assertEqual(response.context['result']['events'], [])
        self.assertContains(response, 'Updates will follow')
        self.assertContains(response, 'Awaiting a confirmed estimate')
        self.assertNotContains(response, 'Carrier-provided update')
    def test_demo_post_requires_csrf(self):
        c = Client(enforce_csrf_checks=True)
        self.assertEqual(c.post('/en/', {'preview_state': 'found'}).status_code, 403)
    def test_faqs_use_native_keyboard_accessible_details(self):
        response = self.client.get('/en/')
        self.assertContains(response, 'class="faq-list"')
        faq_markup = response.content.decode().split('<div class="faq-list">', 1)[1].split('</section>', 1)[0]
        self.assertEqual(faq_markup.count('<summary>'), 6)
        self.assertContains(response, 'id="reference"')
        self.assertContains(response, 'aria-describedby="tracking-help tracking-error"')
        self.assertContains(response, 'novalidate')  # server fallback remains functional
    def test_company_copy_is_complete_and_unverified_claims_are_labeled(self):
        for lang in ('en', 'ar'):
            response = self.client.get(f'/{lang}/who-we-are/')
            self.assertContains(response, 'ceo-section')
            self.assertContains(response, 'Majed Saleem')
            self.assertContains(response, 'class="portrait-label"')
            self.assertContains(response, 'images/majed-saleem-1200.webp')
            self.assertNotContains(response, '<blockquote>')  # no unauthenticated CEO quotation
            self.assertNotContains(response, 'Temporary portrait placeholder')
            self.assertContains(response, 'loading="lazy"')
            self.assertContains(response, 'https://jahez.online/' + lang + '/services')
            self.assertNotContains(response, 'Phase 1 company-page shell')
            self.assertNotContains(response, '500+')
    def test_company_page_metadata_is_page_specific(self):
        response = self.client.get('/en/who-we-are/')
        self.assertContains(response, 'Learn how JAHEZ supports China-focused sourcing')
        self.assertContains(response, 'https://shipping.jahez.online/en/who-we-are/')
        self.assertContains(response, 'hreflang="ar"')
    def test_assets_are_self_hosted(self):
        for name in ('js/site.js', 'illustrations/warehouse-scene.svg', 'illustrations/portrait-placeholder.svg', 'illustrations/service-icons.svg'):
            self.assertTrue(finders.find(name), name)


class ProductionFixtureIsolationTests(SimpleTestCase):
    def test_debug_false_overrides_even_an_enabled_preview_setting(self):
        with override_settings(DEBUG=False, PUBLIC_UI_PREVIEW_ENABLED=True), patch('apps.core.views.synthetic_result') as fixture:
            for state in PREVIEW_STATES:
                response = self.client.post('/en/', {'preview_state': state})
                self.assertFalse(response.context['is_demo'])
                self.assertFalse(response.context['preview_enabled'])
                self.assertNotContains(response, 'SYNTHETIC EXAMPLE')
                self.assertNotContains(response, 'Reusable drinkware')
                self.assertNotContains(response, 'name="preview_state"')
            fixture.assert_not_called()
    def test_setting_false_disables_fixtures_in_debug_too(self):
        with override_settings(DEBUG=True, PUBLIC_UI_PREVIEW_ENABLED=False), patch('apps.core.views.synthetic_result') as fixture:
            response = self.client.post('/ar/', {'preview_state': 'found'})
            self.assertFalse(response.context['is_demo'])
            self.assertNotContains(response, 'name="preview_state"')
            fixture.assert_not_called()
