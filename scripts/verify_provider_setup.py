"""Explicit live, synthetic-only setup checks. No database writes or carrier registration."""
import base64
import io
import json
import os
import sys
import time
import re
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
import django
django.setup()
from django.conf import settings
from apps.ai.provider import AIError, configuration as ai_configuration, generate
from apps.tracking.adapter import ProviderError, configuration as carrier_configuration, outbound_slot
import httpx
from PIL import Image, ImageDraw, ImageFont

if sys.argv[1:] not in (['--live-synthetic-check'], ['--live-synthetic-check', '--only-vision']) or not settings.DEBUG:
    raise SystemExit('Development only; requires --live-synthetic-check. Sends invented text/image to Groq and reads 17TRACK quota; no tracking registration.')

results = {}
vision_only = '--only-vision' in sys.argv

def fetch(name, method, url, headers, payload=None):
    """Fixed callers only; never print headers, raw bodies or exception messages."""
    try:
        with httpx.Client(timeout=httpx.Timeout(15, connect=3), follow_redirects=False, trust_env=False) as client:
            with client.stream(method, url, headers=headers, json=payload) as response:
                status = response.status_code
                if status != 200:
                    results[name] = {'ok': False, 'http_status': status}
                    return None
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 1024 * 1024:
                        results[name] = {'ok': False, 'error': 'response_limit'}
                        return None
        body = json.loads(raw)
        if not isinstance(body, dict):
            raise ValueError()
        return body
    except Exception:
        results[name] = {'ok': False, 'error': 'connection_or_invalid_response'}
        return None

results['configuration'] = {
    'text': ai_configuration(), 'vision': ai_configuration(True),
    'carrier': carrier_configuration(), 'text_model': settings.GROQ_TEXT_MODEL,
    'vision_model': settings.GROQ_VISION_MODEL,
    'text_output_mode': settings.GROQ_TEXT_OUTPUT_MODE,
    'vision_output_mode': settings.GROQ_VISION_OUTPUT_MODE,
    'text_max_tokens': settings.GROQ_MAX_TOKENS,
    'vision_max_tokens': settings.GROQ_VISION_MAX_TOKENS,
}

if not vision_only and carrier_configuration() == 'ready':
    try:
        outbound_slot()
        body = fetch('track17_quota', 'POST', 'https://api.17track.net/track/v2.4/getquota',
                     {'17token': settings.TRACK17_API_KEY, 'Content-Type': 'application/json'}, [])
        if body is not None:
            data = body.get('data')
            ok = type(body.get('code')) is int and body['code'] == 0 and isinstance(data, dict)
            results['track17_quota'] = {'ok': ok, 'provider_code': body.get('code') if type(body.get('code')) is int else None}
            if ok:
                results['track17_quota']['quota'] = {k: data[k] for k in ('quota_total', 'quota_used', 'quota_remain') if type(data.get(k)) is int}
    except ProviderError as exc:
        results['track17_quota'] = {'ok': False, 'error': exc.code}
elif not vision_only:
    results['track17_quota'] = {'ok': False, 'error': carrier_configuration()}

if not vision_only and ai_configuration() == 'ready':
    body = fetch('groq_models', 'GET', 'https://api.groq.com/openai/v1/models',
                 {'Authorization': 'Bearer ' + settings.GROQ_API_KEY})
    if body is not None:
        rows = body.get('data', [])
        ids = {row.get('id') for row in rows if isinstance(row, dict)} if isinstance(rows, list) else set()
        results['groq_models'] = {'ok': bool(ids), 'text_model_listed': settings.GROQ_TEXT_MODEL in ids,
                                  'vision_model_listed': settings.GROQ_VISION_MODEL in ids}
elif not vision_only:
    results['groq_models'] = {'ok': False, 'error': ai_configuration()}

def check_generation(name, kind, source, vision=False):
    if ai_configuration(vision) != 'ready':
        results[name] = {'ok': False, 'error': ai_configuration(vision)}
        return
    try:
        diagnostic = {}
        original_init = httpx.Client.__init__
        def inspect_response(response):
            if response.status_code < 400:
                return
            diagnostic['http_status'] = response.status_code
            diagnostic['rate_headers'] = {k: response.headers[k] for k in
                ('x-ratelimit-limit-tokens', 'x-ratelimit-remaining-tokens', 'retry-after')
                if re.fullmatch(r'\d+(?:\.\d+)?', response.headers.get(k, ''))}
            # Only bounded provider error bodies, no original text/account/organization identifiers.
            length = response.headers.get('content-length', '')
            if length.isdigit() and int(length) <= 8192:
                try:
                    error = response.json() if response.is_stream_consumed else json.loads(response.read())
                    message = error.get('error', {}).get('message', '')
                    for label in ('Limit', 'Used', 'Requested'):
                        match = re.search(r'\b' + label + r'\s+(\d+)', message)
                        if match:
                            diagnostic[label.lower() + '_tokens'] = int(match.group(1))
                    diagnostic['tokens_per_minute_limit'] = 'tokens per minute' in message.lower()
                except Exception:
                    pass
        def instrumented_init(client, **kwargs):
            kwargs['event_hooks'] = {'response': [inspect_response]}
            original_init(client, **kwargs)
        with patch('httpx.Client.__init__', new=instrumented_init):
            output, model, latency, usage = generate(kind, source)
        result = {'ok': True, 'model': model, 'latency_ms': latency, 'usage': usage,
                  'schema_and_citations_validated': True}
        if vision:
            identified = any(row.get('value') == 'SYNTHETIC-CHECK-001' for row in output['fields'] + output['identifiers'])
            result['synthetic_bill_read_correctly'] = identified
            result['ok'] = identified
        else:
            result['bilingual_statements'] = len(output['statements'])
        results[name] = result
    except AIError as exc:
        results[name] = {'ok': False, 'error': exc.code}
        if diagnostic:
            results[name]['safe_diagnostic'] = diagnostic
    except Exception:
        results[name] = {'ok': False, 'error': 'check_failure'}

if not vision_only:
    check_generation('groq_text', 'summary', {'records': [
        {'id': 'synthetic-status', 'text': 'SYNTHETIC TEST ONLY. Invented shipment status: created. Estimated arrival: unknown. No carrier updates.'}
    ], 'images': [], 'warnings': ['Invented setup check, no customer data.']})
    # Respect the application's shared two-second Groq slot even for a fast text response.
    time.sleep(2)

image = Image.new('RGB', (1100, 420), 'white')
draw = ImageDraw.Draw(image)
font = ImageFont.load_default(size=32)
for index, line in enumerate(('SYNTHETIC TEST DOCUMENT', 'Bill: SYNTHETIC-CHECK-001', 'Item: Packing box', 'Quantity: 2 boxes')):
    draw.text((35, 35 + index * 85), line, fill='black', font=font)
buffer = io.BytesIO()
image.save(buffer, format='JPEG', quality=85)
check_generation('groq_vision', 'extraction', {
    'records': [{'id': 'synthetic-page-1', 'text': '', 'scanned': True}],
    'images': [{'id': 'synthetic-page-1', 'jpeg': base64.b64encode(buffer.getvalue()).decode('ascii')}],
    'warnings': ['Invented setup check, no customer data.'],
}, vision=True)

print(json.dumps(results, ensure_ascii=True))
required = ('groq_vision',) if vision_only else ('track17_quota', 'groq_models', 'groq_text', 'groq_vision')
raise SystemExit(0 if all(results.get(name, {}).get('ok') for name in required) else 1)
