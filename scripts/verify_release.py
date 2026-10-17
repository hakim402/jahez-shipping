"""Synthetic production-image acceptance. Never loads owner env/data or activates schedules."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

from production_tools import ROOT,scope,call,contract

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--image",default="jahez-shipping-phase07:0.9.0")
parser.add_argument("--keep-review",action="store_true",help="Keep a successful isolated fixture for immediate browser review; clean it with --cleanup.")
parser.add_argument("--cleanup",metavar="PRIVATE_REVIEW_DIRECTORY")
args=parser.parse_args()


def cleanup(directory,compose,project,model):
    call(compose+["down","--remove-orphans"])
    for volume in model["volumes"].values():
        found=subprocess.run(["docker","volume","inspect",volume["name"]],capture_output=True)
        if found.returncode:continue
        info=json.loads(found.stdout)[0]
        assert info.get("Labels",{}).get("com.docker.compose.project")==project
        call(["docker","volume","rm",volume["name"]],True)
    for kind in ("container","volume","network"):
        command=["docker",kind,"ls","-q","--filter","label=com.docker.compose.project="+project]
        if kind=="container":command.insert(3,"-a")
        assert not call(command,True).strip(),"Review resources remain"
    (directory/"cleanup.json").write_text(json.dumps({"removed":True,"project":project}))


if args.cleanup:
    directory=Path(args.cleanup).resolve();project,compose=scope(directory)
    assert project=="jahez-shipping-release-review"
    os.environ["SHIPPING_ENV_FILE"]=str(directory/"review.env")
    os.environ.update(SHIPPING_WEB_MEMORY="768m",SHIPPING_REDIS_MEMORY="256m")
    os.environ.pop("SHIPPING_IMAGE",None)
    model=json.loads(call(compose+["config","--format","json"],True));contract(model,project,True)
    cleanup(directory,compose,project,model)
    for name in ("review.env","browser.json"):
        p=directory/name
        if p.exists():p.unlink()
    print("PASS: only verified disposable release-review resources/configuration removed; owner resources and retained images untouched.")
    raise SystemExit(0)

base=ROOT/"private/release-review";base.mkdir(parents=True,exist_ok=True,mode=0o700)
directory=Path(tempfile.mkdtemp(prefix="compose-",dir=base));directory.chmod(0o700)
env=directory/"review.env"
text=(ROOT/".env.prod.example").read_text().replace("REPLACE_WITH_INDEPENDENT_RANDOM_SECRET_AT_LEAST_50_CHARACTERS",secrets.token_urlsafe(64))
text=text.replace("SHIPPING_IMAGE=jahez-shipping:0.9.0","SHIPPING_IMAGE="+args.image)
text=text.replace("SHIPPING_WHATSAPP_NUMBER=\n","SHIPPING_WHATSAPP_NUMBER=971501234567\n")
text+="\nSHIPPING_ENV_FILE="+json.dumps(str(env))+"\n";env.write_text(text);env.chmod(0o600)
# Inherited owner shell interpolation must never redirect the isolated env/image/limits.
os.environ.update(SHIPPING_ENV_FILE=str(env),SHIPPING_IMAGE=args.image,SHIPPING_WEB_MEMORY="768m",SHIPPING_REDIS_MEMORY="256m")
(directory/"review.yml").write_text("services:\n  web:\n    ports: !reset []\nnetworks:\n  shipping:\n    internal: true\n")
project,compose=scope(directory)
for kind in ("container","volume","network"):
    command=["docker",kind,"ls","-q","--filter","label=com.docker.compose.project="+project]
    if kind=="container":command.insert(3,"-a")
    assert not call(command,True).strip(),"Existing release-review resources preserved; inspect/clean them explicitly first."
model=json.loads(call(compose+["config","--format","json"],True));contract(model,project,True)
assert all(net.get("internal") for net in model["networks"].values())
assert model["services"]["web"]["environment"]["GROQ_API_KEY"]==""
image=json.loads(call(["docker","image","inspect",args.image],True))[0]
version=next(ast.literal_eval(node.value) for node in ast.parse((ROOT/"config/settings/base.py").read_text()).body
    if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="APP_VERSION" for t in node.targets))
assert version==json.loads((ROOT/"package.json").read_text())["version"]=="0.9.0"
assert image["Config"]["User"]=="shipping"
assert not any(value.startswith(("DJANGO_SECRET_KEY=","GROQ_API_KEY=")) for value in image["Config"]["Env"])
names=[name.decode() for name in subprocess.check_output(["git","ls-files","--cached","--others","--exclude-standard","-z"],cwd=ROOT).split(b"\0") if name]
source_roots={"apps","config","templates","locale","scripts","deploy","tests","static"}
expected={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names
    if (Path(name).parts[0] in source_roots or name in ("manage.py","requirements.lock")) and (ROOT/name).is_file()
    and name not in ("static/css/site.css","static/js/alpine.min.js")}
check="import sys,json,hashlib;from pathlib import Path;expected=json.load(sys.stdin);assert all(hashlib.sha256((Path('/app')/name).read_bytes()).hexdigest()==digest for name,digest in expected.items()),'Installed source differs from intended checkout';print('PASS: installed source, templates, catalog, fixtures and locked requirements match the intended checkout.')"
checked=subprocess.run(["docker","run","--rm","-i","--network","none",args.image,"python","-c",check],input=json.dumps(expected),text=True,capture_output=True)
if checked.returncode:raise RuntimeError("Installed image differs from intended source; rebuild the reviewed image before acceptance.")
print(checked.stdout,end="")


def fixture(mode,one_off=False):
    prefix=["run","--rm","--no-deps","--pull","never","web"] if one_off else ["exec","-T","web"]
    result=subprocess.run(compose+prefix+["python","tests/verify_release_candidate.py",mode],cwd=ROOT,text=True,capture_output=True)
    log=directory/("fixture-"+mode+".txt");log.write_text(result.stdout+result.stderr);log.chmod(0o600)
    if result.returncode:raise RuntimeError("Installed-image "+mode+" acceptance failed; private fixture diagnostics retained.")
    if result.stdout:print(result.stdout,end="")


success=False
try:
    call([sys.executable,"scripts/preflight.py","--review-dir",str(directory)])
    call(["docker","run","--rm","--network","none",args.image,"python","-m","pip","check"])
    dependency_check="import importlib.util;assert not any(importlib.util.find_spec(m) for m in ('celery','kombu','billiard','pypdf','pypdfium2','PIL','playwright','selenium'));print('PASS: retired/background/document/browser dependencies absent; direct bounded HTTP needs no browser runtime.')"
    call(["docker","run","--rm","--network","none",args.image,"python","-c",dependency_check])
    call(compose+["up","-d","--pull","never","--wait","--wait-timeout","120","redis"])
    call(compose+["run","--rm","--no-deps","--pull","never","web","python","manage.py","migrate","--noinput"])
    call(compose+["run","--rm","--no-deps","--pull","never","web","python","manage.py","check","--deploy","--fail-level","ERROR"])
    call(compose+["up","-d","--pull","never","--wait","--wait-timeout","120","web"])
    fixture("journey")
    fixture("http")
    container=call(compose+["ps","-q","web"],True).strip()
    info=json.loads(call(["docker","inspect",container],True))[0]
    host=info["HostConfig"]
    assert host["ReadonlyRootfs"] and host["PidsLimit"]==128 and host["NanoCpus"]==1000000000
    assert host["Memory"]==int(model["services"]["web"]["mem_limit"])
    assert host["CapDrop"]==["ALL"] and "no-new-privileges:true" in host["SecurityOpt"]
    assert not host.get("PortBindings") and info["Config"]["Cmd"][0]=="gunicorn"
    assert all(mount["Type"]=="volume" and mount["Name"].startswith(project+"_") for mount in info["Mounts"])
    call(compose+["stop","redis"])
    fixture("outage")
    call(compose+["up","-d","--pull","never","--wait","--wait-timeout","120","redis"])
    fixture("http")
    for action in ("pause","backup"):
        call([sys.executable,"scripts/release.py",action,"--review-dir",str(directory)])
    fixture("restore",True)
    call([sys.executable,"scripts/release.py","resume","--review-dir",str(directory)])
    call(compose+["up","-d","--pull","never","--force-recreate","--wait","--wait-timeout","120","web"])
    fixture("http")
    proof=json.loads(call(compose+["exec","-T","web","cat","/data/release-proof.json"],True))
    browser=json.loads(call(compose+["exec","-T","web","cat","/data/review-browser.json"],True))
    (directory/"browser.json").write_text(json.dumps(browser));(directory/"browser.json").chmod(0o600)
    proof.update(passed=True,image=args.image,image_id=image["Id"],version=version,project=project,installed_source_hashes_verified=len(expected),
        runtime={"nonroot_uid":10001,"read_only":True,"pids":host["PidsLimit"],"memory_bytes":host["Memory"],"cpu":1,
                 "gunicorn_timeout_seconds":30,"grace_seconds":95,"network_internal":True,"owner_mounts":False,"host_ports":False},
        actual_redis_outage_fail_closed=True,recreated_web_preserved_data=True,providers="synthetic-only",production_changed=False)
    (directory/"result.json").write_text(json.dumps(proof,indent=2));(directory/"result.json").chmod(0o600)
    (base/"latest-review.txt").write_text(str(directory));(base/"latest-review.txt").chmod(0o600)
    success=True
    print("PASS: isolated installed-image lifecycle/runtime/Redis-outage/recreation/backup/restore acceptance. Private evidence retained; no owner environment, database, provider, schedule or server touched.")
finally:
    if not (success and args.keep_review):
        cleanup(directory,compose,project,model)
        for name in ("review.env","browser.json"):
            p=directory/name
            if p.exists():p.unlink()
