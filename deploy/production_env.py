"""Stdlib startup/preflight validation; importing it never initializes Django/Celery."""
import ipaddress
import re
from pathlib import PurePosixPath
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from urllib.parse import urlsplit

class EnvironmentError(ValueError):pass

def validate(values):
    problems=[]
    def bad(name):problems.append(name)
    key=values.get('DJANGO_SECRET_KEY','')
    if len(key)<50 or len(set(key))<10 or key.startswith(('dev-','REPLACE_','GENERATE_','YOUR_')) or any(c.isspace() for c in key):bad('DJANGO_SECRET_KEY')
    if values.get('DJANGO_SETTINGS_MODULE','config.settings.production')!='config.settings.production':bad('DJANGO_SETTINGS_MODULE')
    if values.get('DJANGO_DEBUG','false').lower() not in ('false','0'):bad('DJANGO_DEBUG')
    hosts=[h.strip() for h in values.get('DJANGO_ALLOWED_HOSTS','').split(',') if h.strip()]
    if hosts!=['shipping.jahez.online']:bad('DJANGO_ALLOWED_HOSTS')
    origins=[h.strip() for h in values.get('DJANGO_CSRF_TRUSTED_ORIGINS','').split(',') if h.strip()]
    if origins!=['https://shipping.jahez.online']:bad('DJANGO_CSRF_TRUSTED_ORIGINS')
    data=PurePosixPath(values.get('SHIPPING_DATA_DIR',''))
    if not data.is_absolute() or str(data)=='/' or 'app' in data.parts or 'root' in data.parts or '..' in data.parts or {'jahez-trade-co','JAHEZ-Brand-Kit','jahez-trade-co-shipping-system'}&set(data.parts):bad('SHIPPING_DATA_DIR')
    for name,default,db in [('CACHE_REDIS_URL','redis://redis:6379/1','/1')]:
        try:
            url=urlsplit(values.get(name,default))
            if url.scheme!='redis' or url.hostname!='redis' or url.port not in (None,6379) or url.path!=db or url.username or url.password or url.query or url.fragment:bad(name)
        except ValueError:bad(name)
    for flag in ('GROQ_ENABLED',):
        if values.get(flag,'false').lower() not in ('true','false'):bad(flag)
    for flag,key_name,models in [('GROQ_ENABLED','GROQ_API_KEY',('GROQ_TEXT_MODEL','GROQ_VISION_MODEL'))]:
        if values.get(flag,'false').lower()=='true':
            key=values.get(key_name,'')
            if not key.strip() or key.startswith(('REPLACE_','YOUR_')):bad(key_name)
            for model in models:
                if not values.get(model,'').strip():bad(model)
    for name in ('GROQ_TEXT_OUTPUT_MODE','GROQ_VISION_OUTPUT_MODE'):
        if values.get(name,'schema' if 'TEXT' in name else 'json') not in ('schema','json'):bad(name)
    for name,default,low,high in [('SHIPPING_BIND_PORT','18743',18743,18743),('SHIPPING_HSTS_SECONDS','0',0,31536000),('GROQ_MAX_TOKENS','4096',64,8192),('GROQ_VISION_MAX_TOKENS','512',64,8192)]:
        try:
            if not low<=int(values.get(name,default))<=high:bad(name)
        except ValueError:bad(name)
    try:ZoneInfo(values.get('SHIPPING_BUSINESS_TIME_ZONE','Asia/Kabul'))
    except (ValueError,ZoneInfoNotFoundError):bad('SHIPPING_BUSINESS_TIME_ZONE')
    try:
        for ip in values.get('SHIPPING_TRUSTED_PROXY_IPS','').split(','):
            if ip.strip():ipaddress.ip_address(ip.strip())
    except ValueError:bad('SHIPPING_TRUSTED_PROXY_IPS')
    image=values.get('SHIPPING_IMAGE','jahez-shipping:0.9.0')
    if not (re.fullmatch(r'sha256:[0-9a-f]{64}',image) or re.fullmatch(r'[a-zA-Z0-9./_-]+(?::[0-9]+)?(?:@[s]ha256:[0-9a-f]{64}|:[0-9]+\.[0-9]+\.[0-9]+)',image)):bad('SHIPPING_IMAGE')
    if problems:raise EnvironmentError('Invalid production fields: '+', '.join(sorted(set(problems))))
