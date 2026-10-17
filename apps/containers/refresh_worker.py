"""One bounded provider subprocess. Secrets use stdin only; no ORM/session/owner DB."""
import json
import sys


def main():
    try:
        data = json.loads(sys.stdin.buffer.read(32769))
        from django.conf import settings
        settings.configure(USE_I18N=False, SECRET_KEY="provider-worker-no-session", INSTALLED_APPS=[], **data["groq"])
        from .pipeline import prepare, RefreshError
        from apps.integrations.sealegend import SourceError
        output = prepare(data["reference"], data["number"], data["labels"])
        result = {"ok": True, "result": output}
    except Exception as exc:
        code = getattr(exc, "code", "invalid_extraction")
        allowed = {"ambiguous_container", "identity_mismatch", "invalid_extraction", "ai_unavailable", "invalid_reference", "unavailable", "timeout", "blocked_address", "redirect_refused", "too_large", "source_changed", "not_found"}
        result = {"ok": False, "code": code if code in allowed else "invalid_extraction"}
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
