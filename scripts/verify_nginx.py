"""Exact Nginx file syntax in an isolated image; synthetic certs are never live evidence."""
import shutil
import subprocess
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
IMAGE='nginx:1.30.5-alpine@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94'
with tempfile.TemporaryDirectory(prefix='jahez-nginx-review-') as directory:
    root=Path(directory);config=root/'nginx';config.mkdir();(config/'snippets').mkdir();cert=root/'cert';cert.mkdir()
    for source,dest in [('jahez-shipping-http.conf','http-extra.conf'),('jahez-shipping-proxy.conf','snippets/jahez-shipping-proxy.conf')]:shutil.copy(ROOT/'deploy/nginx'/source,config/dest)
    (config/'nginx.conf').write_text('pid /tmp/nginx.pid; events {} http { include /etc/nginx/http-extra.conf; include /etc/nginx/shipping.conf; }\n')
    def check():
        return subprocess.run(['docker','run','--rm','--network','none','--entrypoint','nginx','--mount','type=bind,source='+str(config)+',target=/etc/nginx,readonly','--mount','type=bind,source='+str(cert)+',target=/etc/letsencrypt/live/shipping.jahez.online,readonly',IMAGE,'-t'],capture_output=True,text=True)
    shutil.copy(ROOT/'deploy/nginx/shipping-http.conf',config/'shipping.conf');assert check().returncode==0,'HTTP bootstrap syntax failed.'
    shutil.copy(ROOT/'deploy/nginx/shipping-https.conf',config/'shipping.conf');assert check().returncode!=0,'HTTPS must refuse absent certificate files.'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=shipping.jahez.online','-keyout',str(cert/'privkey.pem'),'-out',str(cert/'fullchain.pem')],check=True,capture_output=True)
    assert check().returncode==0,'HTTPS synthetic-cert syntax failed.'
print('PASS: exact HTTP bootstrap Nginx config; HTTPS refuses absent certs; exact HTTPS config parses with disposable self-signed certs. Real VPS/Nginx/Let’s Encrypt issuance/renewal NOT tested or changed.')
