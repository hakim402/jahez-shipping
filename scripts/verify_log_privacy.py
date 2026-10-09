"""Local dev log sentinel check. Report only verdict, never container log bodies."""
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

marker='PHASE7-PRIVATE-LOG-SENTINEL'
request=urllib.request.Request('http://127.0.0.1:18744/en/'+marker+'/?token='+marker)
try:response=urllib.request.urlopen(request,timeout=10)
except urllib.error.HTTPError as exc:response=exc
assert response.status==404 and response.headers['X-Request-ID']
response.close()
result=subprocess.run(['docker','compose','--env-file','.env.dev','-p','jahez-shipping-dev','-f','compose.dev.yml',
    'logs','--since','1m','--no-color','web','worker','beat'],cwd=Path(__file__).resolve().parents[1],check=True,capture_output=True,text=True)
assert marker not in result.stdout+result.stderr,'Private URL/query appeared in Shipping logs.'
assert 'request.complete' in result.stdout,'No application request event was observed.'
print('PASS: actual local private URL/query sentinel is absent from Shipping web/worker/Beat logs; safe correlated request event observed. Raw logs not exported.')
