import json
import logging
import secrets
from unittest.mock import patch
from django.apps import apps
from django.contrib import admin
from django.contrib.auth.models import Group, Permission, User
from django.core.cache import cache
from django.core.management import call_command, get_commands
from django.contrib.staticfiles import finders
from django.db import connection
from django.test import Client, TestCase, SimpleTestCase, override_settings
from apps.core.safe_logging import SafeFormatter

class FoundationTests(TestCase):
    def setUp(self):cache.clear()

    def test_schema_admin_and_commands_have_no_business_features(self):
        self.assertFalse(any(t.startswith(('shipments_','tracking_','ai_')) for t in connection.introspection.table_names()))
        self.assertEqual({m._meta.label for m in admin.site._registry},{'auth.User','auth.Group'})
        self.assertFalse([m for m in apps.get_models() if m._meta.app_label in ('shipments','tracking','ai')])
        commands=get_commands()
        for name in ('seed_demo','seed_tracking_demo','seed_ai_demo','seed_search_demo'):self.assertNotIn(name,commands)
        call_command('setup_roles');self.assertEqual(User.objects.count(),0)

    @override_settings(SHIPPING_WHATSAPP_NUMBER='+971 (50) 123-4567')
    def test_public_bilingual_empty_state_branding_whatsapp_and_static(self):
        for lang,dir in (('en','ltr'),('ar','rtl')):
            for suffix in ('','who-we-are/'):
                r=self.client.get('/'+lang+'/'+suffix)
                self.assertEqual(r.status_code,200);self.assertContains(r,'dir="'+dir+'"')
                self.assertContains(r,'https://wa.me/971501234567');self.assertContains(r,'jahez.online')
            r=self.client.get('/'+lang+'/')
            self.assertContains(r,'disabled');self.assertNotContains(r,'type="submit"')
            self.assertNotContains(r,'JHZ-DEMO');self.assertNotContains(r,'stored_result')
            self.assertContains(r,'Container tracking is being prepared' if lang=='en' else 'نعمل على تجهيز تتبع الحاويات')
        for name in ('css/site.css','js/alpine.min.js','images/majed-saleem-600.webp','fonts/Cairo-Regular.ttf'):
            self.assertTrue(finders.find(name),name)

    @override_settings(SHIPPING_WHATSAPP_NUMBER='invalid-private-number')
    def test_invalid_contact_hidden_and_public_post_is_not_a_lookup(self):
        r=self.client.get('/en/');self.assertNotContains(r,'wa.me/');self.assertNotContains(r,'invalid-private-number')
        with patch('apps.integrations.groq.create_client') as provider:
            r=self.client.post('/en/',{'reference':'SYNTHETIC-PRIVATE-REFERENCE'})
            self.assertEqual(r.status_code,405);self.assertNotIn(b'SYNTHETIC-PRIVATE-REFERENCE',r.content);provider.assert_not_called()

    def test_admin_auth_session_csrf_permissions_and_minimal_navigation(self):
        password=secrets.token_urlsafe(32)
        user=User.objects.create_user('synthetic-staff',password=password,is_staff=True)
        group=Group.objects.create(name='Retained group');permission=Permission.objects.get(codename='view_user')
        group.permissions.add(permission);user.groups.add(group)
        c=Client(enforce_csrf_checks=True)
        for lang in ('en','ar'):
            self.assertContains(c.get('/'+lang+'/admin/login/'),'unfold')
        token=c.cookies['jahez_shipping_csrf'].value
        self.assertEqual(c.post('/en/admin/login/',{'username':user.username,'password':password,'csrfmiddlewaretoken':token},HTTP_ORIGIN='https://invalid.test').status_code,403)
        r=c.post('/en/admin/login/',{'username':user.username,'password':password,'csrfmiddlewaretoken':token},HTTP_ORIGIN='http://testserver')
        self.assertEqual(r.status_code,302);self.assertEqual(c.session['_auth_user_id'],str(user.pk))
        for lang in ('en','ar'):
            r=c.get('/'+lang+'/admin/');self.assertEqual(r.status_code,200)
            self.assertContains(r,'Container tracking preparation' if lang=='en' else 'تجهيز تتبع الحاويات')
            for forbidden in ('/admin/shipments/','/admin/ai/','integration-health','recent_shipments'):self.assertNotContains(r,forbidden)
        self.assertEqual(c.get('/en/admin/auth/user/').status_code,200)
        self.assertEqual(c.get('/en/admin/auth/group/').status_code,403)
        for path in ('/webhooks/17track/','/en/admin/shipments/shipment/','/en/admin/ai/aidraft/workspace/','/en/admin/integration-health/','/media/private.pdf','/data/shipping.sqlite3'):
            self.assertEqual(c.get(path).status_code,404,path)

    def test_login_shared_counter_and_failure_closed(self):
        for _ in range(10):self.assertNotEqual(self.client.post('/en/admin/login/',{}).status_code,429)
        self.assertEqual(self.client.post('/en/admin/login/',{}).status_code,429)
        with patch('apps.core.middleware.cache.add',side_effect=ConnectionError):
            self.assertEqual(self.client.post('/ar/admin/login/',{}).status_code,503)

    def test_health_checks_remaining_schema_cache_only(self):
        with patch('apps.integrations.groq.create_client') as provider:
            self.assertEqual(self.client.get('/health/live/').status_code,200)
            self.assertEqual(self.client.get('/health/ready/').json(),{'status':'ready'});provider.assert_not_called()
        with patch('apps.core.views.cache.add',side_effect=ConnectionError):self.assertEqual(self.client.get('/health/ready/').status_code,503)
        with patch('django.db.migrations.executor.MigrationExecutor.migration_plan',return_value=[object()]):
            self.assertEqual(self.client.get('/health/ready/').status_code,503)

    def test_privacy_headers_generic_errors_and_proxy_identity(self):
        r=self.client.get('/en/PRIVATE-NAME?key=PRIVATE-KEY')
        self.assertEqual(r.status_code,404);self.assertNotIn(b'PRIVATE',r.content)
        for key in ('X-Request-ID','Content-Security-Policy','X-Frame-Options','Referrer-Policy'):self.assertIn(key,r)
        self.assertEqual(r['Cache-Control'],'no-store')
        from apps.core.privacy import client_address
        from django.test import RequestFactory
        request=RequestFactory().get('/',REMOTE_ADDR='192.0.2.1',HTTP_X_REAL_IP='198.51.100.1')
        with override_settings(TRUSTED_PROXY_IPS=[]):self.assertEqual(client_address(request),'192.0.2.1')
        with override_settings(TRUSTED_PROXY_IPS=['192.0.2.1']):self.assertEqual(client_address(request),'198.51.100.1')

class ProviderAndConfigTests(SimpleTestCase):
    def test_client_disabled_and_mocked_transport_only(self):
        from apps.integrations.groq import create_client,configuration,ProviderUnavailable
        self.assertEqual(configuration(),'disabled')
        with self.assertRaises(ProviderUnavailable):create_client()
        import httpx
        seen=[]
        def handler(request):
            seen.append(request);return httpx.Response(200,json={'object':'list','data':[]})
        with override_settings(GROQ_ENABLED=True,GROQ_API_KEY='synthetic-only-key',GROQ_TEXT_MODEL='synthetic-model',GROQ_TEXT_OUTPUT_MODE='schema'):
            with create_client(transport=httpx.MockTransport(handler)) as client:client.models.list()
        self.assertEqual(len(seen),1);self.assertEqual(str(seen[0].url),'https://api.groq.com/openai/v1/models')

    def test_production_values_and_error_logging_do_not_leak(self):
        from deploy.production_env import validate,EnvironmentError
        values={'DJANGO_SECRET_KEY':secrets.token_urlsafe(64),'DJANGO_ALLOWED_HOSTS':'shipping.jahez.online','DJANGO_CSRF_TRUSTED_ORIGINS':'https://shipping.jahez.online','SHIPPING_DATA_DIR':'/data'}
        validate(values)
        for name,value in (('DJANGO_SECRET_KEY','PRIVATE-KEY'),('DJANGO_ALLOWED_HOSTS','*'),('CACHE_REDIS_URL','redis://PRIVATE@other/1'),('GROQ_ENABLED','maybe')):
            with self.assertRaises(EnvironmentError) as error:validate({**values,name:value})
            self.assertIn(name,str(error.exception));self.assertNotIn('PRIVATE',str(error.exception))
        record=logging.LogRecord('httpx',logging.ERROR,'PRIVATE-FILE',1,'PRIVATE-KEY',(),None)
        self.assertNotIn('PRIVATE',SafeFormatter().format(record))
