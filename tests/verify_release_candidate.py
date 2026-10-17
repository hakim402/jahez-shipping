"""Installed-image synthetic acceptance; only the isolated release verifier invokes this."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from unittest.mock import patch

sys.path.insert(0,"/app")
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("mode",choices=("journey","http","outage","restore"))
args=parser.parse_args()
data=Path(os.environ.get("SHIPPING_DATA_DIR","/data"))
assert data==Path("/data") and os.getuid()==10001


def save(name,value):
    p=data/name;p.write_text(json.dumps(value,indent=2));p.chmod(0o600)


def rows(path):
    with sqlite3.connect("file:"+str(path)+"?mode=ro",uri=True) as db:
        tables=[x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {name:sorted(db.execute('SELECT * FROM "'+name.replace('"','""')+'"').fetchall(),key=repr) for name in tables}


if args.mode=="journey":
    import django;django.setup()
    from datetime import timedelta
    from django.contrib.auth.models import User
    from django.contrib.sessions.backends.db import SessionStore
    from django.utils import timezone
    from tests.release_journey import exercise
    from apps.containers.models import Container,ContainerEvent
    from apps.containers.publication import publish_reviewed
    from apps.core.recovery import sha
    proof=exercise("shipping.jahez.online")
    archived=Container.objects.get(pk=proof["container_id"])
    paths={}
    for state in ("fresh","stale","empty"):
        obj=Container.objects.create(search_reference="DEMOXY654321",container_number="DEMO7654321",
            equipment_type="40HC",equipment_quantity=1,origin_code="AAAAA",destination_code="BBBBB",
            origin_label_en="DEMO ORIGIN",origin_label_ar="ميناء تجريبي أ",
            destination_label_en="DEMO DESTINATION",destination_label_ar="ميناء تجريبي ب",
            vessel="DEMO VESSEL",voyage="DEMO-001",carrier_status="preparing" if state=="empty" else "in_transit",
            departure_actual=None if state=="empty" else archived.departure_actual,
            arrival_estimated=None if state=="empty" else archived.arrival_estimated,
            last_refresh_success_at=None if state=="empty" else timezone.now()-timedelta(hours=31 if state=="stale" else 0),
            manual_notes_en="PRIVATE-RELEASE-PREVIEW",is_published=True)
        if state!="empty":
            ContainerEvent.objects.create(container=obj,origin="carrier",raw_status="KH",location_code="AAAAA",
                location="DEMO ORIGIN",source_time=obj.departure_actual,designation="actual",
                title_en="Actual departure — DEMO",title_ar="مغادرة فعلية — تجريبي")
            ContainerEvent.objects.create(container=obj,title_en="DEMO office update",title_ar="تحديث مكتب تجريبي",
                detail_en="Reviewed synthetic journey for release acceptance.",detail_ar="رحلة تجريبية لمراجعة الإصدار.",is_public=True)
        publish_reviewed(obj)
        paths[state]={"code":obj.lookup_code,"admin_id":obj.pk}
    owner=User.objects.get(username="DEMO-release-review")
    session=SessionStore();session["_auth_user_id"]=str(owner.pk)
    session["_auth_user_backend"]="django.contrib.auth.backends.ModelBackend"
    session["_auth_user_hash"]=owner.get_session_auth_hash();session.save()
    save("review-browser.json",{"journeys":paths,"session":session.session_key})
    private=data/"private";private.mkdir(exist_ok=True,mode=0o700)
    (private/"release-retained.bin").write_bytes(b"SYNTHETIC PRIVATE RELEASE BYTES\x00\x01")
    (private/"nested").mkdir(mode=0o700);(private/"nested/retained.txt").write_text("SYNTHETIC nested retained bytes")
    for p in private.rglob("*"):
        p.chmod(0o700 if p.is_dir() else 0o600)
    proof.update(containers=Container.objects.count(),events=ContainerEvent.objects.count(),
        private_hashes={p.relative_to(private).as_posix():sha(p) for p in private.rglob("*") if p.is_file()})
    save("release-proof.json",proof)
    print("PASS: installed production settings, complete synthetic lifecycle, default-off/opt-in publication, repeat/failure/manual/archive and recovery fixtures.")

elif args.mode in ("http","outage"):
    import re
    import urllib.request
    import urllib.error
    headers={"Host":"shipping.jahez.online","X-Forwarded-Proto":"https"}
    def request(path):
        try:return urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8000"+path,headers=headers),timeout=6)
        except urllib.error.HTTPError as error:return error
    if args.mode=="outage":
        for path in ("/health/ready/","/en/track/","/ar/track/"):
            assert request(path).status==503
        print("PASS: actual review Redis outage denies readiness and bilingual public lookup.")
    else:
        import runpy
        gunicorn=runpy.run_path("deploy/gunicorn.conf.py")
        assert (gunicorn["workers"],gunicorn["threads"],gunicorn["timeout"])==(1,2,30)
        assert request("/health/ready/").status==200
        config=json.loads((data/"review-browser.json").read_text())
        for lang in ("en","ar"):
            for path in (f"/{lang}/",f"/{lang}/who-we-are/",f"/{lang}/admin/login/"):
                response=request(path);assert response.status==200 and response.headers["X-Request-ID"]
                html=response.read().decode()
                for asset in re.findall(r'(?:href|src)="(/static/[^"?]+)',html):
                    assert request(asset).status==200
                if "/admin/" not in path:assert re.search(r"/static/css/site\.[0-9a-f]+\.css",html)
            code=config["journeys"]["fresh"]["code"]
            response=request(f"/{lang}/track/{code}/");html=response.read().decode()
            assert response.status==200 and "no-store" in response.headers["Cache-Control"]
            assert response.headers["Referrer-Policy"]=="no-referrer"
            assert "PRIVATE-RELEASE" not in html
            if lang=="ar":assert 'dir="rtl"' in html
            assert request(f"/{lang}/track/INVALID/").status==400
        # Separate processes use the actual shared Redis backend, not an in-memory substitute.
        import django;django.setup()
        from django.core.cache import cache
        cache.set("release-shared-counter",1,300)
        code="import django;django.setup();from django.core.cache import cache;assert cache.incr('release-shared-counter')==2"
        subprocess.run([sys.executable,"-c",code],check=True)
        assert cache.get("release-shared-counter")==2
        cache.clear()
        for i in range(30):assert request("/"+("en" if i%2 else "ar")+"/track/").status==200
        assert request("/en/track/").status==429
        cache.clear()
        try:Path("/app/release-write-probe").write_text("SYNTHETIC")
        except OSError as error:assert error.errno==30
        else:raise AssertionError("Writable root")
        for name in (".git",".env.dev",".env.prod","private","AGENTS.md","PROJECT_PROMPT.md","docs"):
            assert not (Path("/app")/name).exists()
        print("PASS: Gunicorn readiness/EN/AR/admin/public, hashed assets, read-only root, image privacy, cross-process Redis and actual shared 30/5-minute lookup limit.")

else:
    from apps.core import recovery
    archives=sorted((data/"backups").glob("[0-9]*"));assert archives
    archive=archives[-1];manifest=recovery.verify(archive)
    expected=rows(data/"shipping.sqlite3")
    target=data/"release-restored";recovery.restore(archive,target)
    assert rows(target/"shipping.sqlite3")==expected
    assert manifest["records"]["containers_container"]==4 and manifest["records"]["containers_containerevent"]==8
    recovery.verify_restored_database(target,manifest);recovery.verify_restored_private_files(target,manifest)
    def cli(destination):
        return subprocess.run([sys.executable,"scripts/verify_restore.py",str(archive),str(destination)],capture_output=True,text=True)
    verified=cli(target);assert verified.returncode==0 and "PASS:" in verified.stdout
    for kind in ("private","database"):
        damaged=data/("release-damaged-"+kind);recovery.restore(archive,damaged)
        if kind=="private":
            p=damaged/"private/release-retained.bin";value=p.read_bytes();p.write_bytes(bytes([value[0]^1])+value[1:])
        else:
            with sqlite3.connect(damaged/"shipping.sqlite3") as db:
                db.execute("UPDATE containers_container SET vessel='DEMO DAMAGED ROW'")
        failed=cli(damaged);assert failed.returncode!=0 and "PASS:" not in failed.stdout
    (target/"maintenance.lock").write_text(json.dumps({"project":"jahez-shipping"}))
    original=(target/"shipping.sqlite3").read_bytes();private_hashes={p.relative_to(target).as_posix():recovery.sha(p) for p in recovery.tree(target/"private")}
    copy2=shutil.copy2
    def damaged_copy(source,destination,*args,**kwargs):
        result=copy2(source,destination,*args,**kwargs)
        if Path(destination).name=="shipping.sqlite3":
            with sqlite3.connect(destination) as db:db.execute("UPDATE containers_container SET vessel='DEMO DAMAGED COPY'")
        return result
    with patch("apps.core.recovery.shutil.copy2",side_effect=damaged_copy):
        try:recovery.restore(archive,target,True,str(target),True)
        except recovery.RecoveryError as error:assert str(error)=="restored_database_checksum_mismatch"
        else:raise AssertionError("Damaged staging copy accepted")
    assert (target/"shipping.sqlite3").read_bytes()==original
    assert {p.relative_to(target).as_posix():recovery.sha(p) for p in recovery.tree(target/"private")}==private_hashes
    proof=json.loads((data/"release-proof.json").read_text())
    proof.update(backup_version=manifest["app_version"],restored_all_table_rows=True,restored_database_sha256=True,
                 restored_private_sha256=True,corrupt_database_and_private_cli_refused=True,failed_restore_preserved_original=True)
    save("release-proof.json",proof)
    print("PASS: matching-image backup and isolated restore preserve every table row, approved snapshots, events, auth/sessions and private hashes; valid SQLite row/private corruption fail CLI; bad staging preserves original target.")
