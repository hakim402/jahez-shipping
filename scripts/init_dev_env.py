#!/usr/bin/env python3
from pathlib import Path
import secrets
root = Path(__file__).resolve().parents[1]
target = root / ".env.dev"
if target.exists():
    raise SystemExit(".env.dev already exists; kept unchanged.")
text = (root / ".env.dev.example").read_text().replace("GENERATE_WITH_INIT_DEV_ENV", "dev-" + secrets.token_urlsafe(64))
fd = target.open("x")
with fd:
    fd.write(text)
target.chmod(0o600)
print("Created private .env.dev. No secrets displayed.")
