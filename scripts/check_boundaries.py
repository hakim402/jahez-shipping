#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, subprocess
root = Path(__file__).resolve().parents[1]
baseline_file = root / "docs/protected-baseline.json"
if not baseline_file.exists():
    raise SystemExit("Local protected-source baseline absent. Establish a fresh read-only baseline for this checkout before implementation; do not claim a protected-source verification.")
baseline = json.loads(baseline_file.read_text())
protected = Path(baseline["protected_path"])
parent = protected.parent
errors = []
assert root.resolve() == Path(baseline["project_path"]).resolve()
assert protected.resolve() not in root.resolve().parents
for name, digest in baseline["sha256"].items():
    p = parent / name
    if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
        errors.append(name)
status = subprocess.check_output(["git", "-C", str(protected), "status", "--porcelain=v1"]).decode()
head = subprocess.check_output(["git", "-C", str(protected), "rev-parse", "HEAD"]).decode().strip()
if status != baseline["git_status"] or head != baseline["git_head"]:
    errors.append("protected Git state")
if errors:
    print("Protected-source changes detected:", *errors, sep="\n")
    raise SystemExit(1)
print(f"PASS: {len(baseline['sha256'])} protected source/asset checksums and Git state unchanged.")
