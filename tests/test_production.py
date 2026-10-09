import secrets
import json
import tempfile
from pathlib import Path
from django.test import SimpleTestCase
from deploy.production_env import validate,EnvironmentError

class ProductionEnvironmentTests(SimpleTestCase):
    def values(self):return {'DJANGO_SECRET_KEY':secrets.token_urlsafe(64),'DJANGO_ALLOWED_HOSTS':'shipping.jahez.online','DJANGO_CSRF_TRUSTED_ORIGINS':'https://shipping.jahez.online','SHIPPING_DATA_DIR':'/data'}
    def test_disabled_integrations_require_no_keys_and_live_flags_require_configuration(self):
        values=self.values();validate(values)
        for flag in ('TRACK17_ENABLED','GROQ_ENABLED'):
            with self.subTest(flag=flag),self.assertRaises(EnvironmentError):validate({**values,flag:'true'})
    def test_insecure_settings_fail_with_field_names_and_no_value_leak(self):
        values=self.values()
        for key,value in [('DJANGO_SECRET_KEY','PRIVATE-'+ 'x'*20),('DJANGO_ALLOWED_HOSTS','*'),('DJANGO_CSRF_TRUSTED_ORIGINS','http://shipping.jahez.online'),('SHIPPING_DATA_DIR','/app'),('REDIS_URL','redis://PRIVATE:SECRET@untrusted/0'),('SHIPPING_IMAGE','jahez-shipping:latest'),('GROQ_ENABLED','maybe'),('SHIPPING_BIND_PORT','8000'),('SHIPPING_TRUSTED_PROXY_IPS','10.0.0.0/8')]:
            with self.subTest(key=key),self.assertRaises(EnvironmentError) as caught:validate({**values,key:value})
            self.assertIn(key,str(caught.exception));self.assertNotIn('PRIVATE',str(caught.exception));self.assertNotIn('SECRET@',str(caught.exception))

    def test_nginx_error_datagram_is_discarded_before_private_file_logging(self):
        from deploy.nginx_error_log import safe_record,append
        payload=b'<132>nginx: PRIVATE-URL?token=PRIVATE-KEY customer PRIVATE-NAME'
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'error.jsonl';append(path,safe_record(payload))
            text=path.read_text();self.assertNotIn('PRIVATE',text)
            self.assertEqual(json.loads(text)['severity'],4);self.assertEqual(path.stat().st_mode&0o777,0o600)
