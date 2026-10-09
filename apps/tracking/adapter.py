"""17TRACK v2.4 only; no redirects, arbitrary hosts or confidential errors."""
import http.client
import json
import re
import socket
import ssl
from dataclasses import dataclass
from django.conf import settings
from django.core.cache import cache

HOST = "api.17track.net"
VERSION = "v2.4"
MAX_RESPONSE = 1024 * 1024


class ProviderError(Exception):
    def __init__(self, code, retryable=False, retry_after=60):
        self.code, self.retryable = code, retryable
        self.retry_after = max(1, min(int(retry_after), 3600))
        super().__init__(code)


def configuration():
    if not settings.TRACK17_ENABLED:
        return "disabled"
    key = settings.TRACK17_API_KEY
    if not key or key.startswith(("REPLACE_", "YOUR_")) or any(c.isspace() for c in key):
        return "missing_key"
    return "ready"


def identifier(number, carrier):
    if not isinstance(number, str) or not re.fullmatch(r"[A-Za-z0-9-]{4,100}", number):
        raise ProviderError("invalid_identifier")
    if isinstance(carrier, bool) or not str(carrier).isdigit() or not 0 < int(carrier) < 100000000:
        raise ProviderError("explicit_carrier_required")
    return {"number": number, "carrier": int(carrier)}


def outbound_slot():
    try:
        if not cache.add("track17:outbound-slot", 1, timeout=1):
            raise ProviderError("local_rate_limit", True, 2)
    except ProviderError:
        raise
    except Exception:
        raise ProviderError("rate_store_unavailable", True, 60) from None


def request(endpoint, entries):
    if configuration() != "ready":
        raise ProviderError(configuration())
    if endpoint not in {"register", "gettrackinfo"} or not 1 <= len(entries) <= 40:
        raise ProviderError("invalid_request")
    entries = [identifier(e["number"], e["carrier"]) for e in entries]
    outbound_slot()
    conn = http.client.HTTPSConnection(HOST, timeout=3, context=ssl.create_default_context())
    try:
        conn.request("POST", f"/track/{VERSION}/{endpoint}", body=json.dumps(entries).encode(), headers={"17token": settings.TRACK17_API_KEY, "Content-Type": "application/json", "Accept": "application/json"})
        if conn.sock:
            conn.sock.settimeout(8)
        response = conn.getresponse()
        if response.status == 429:
            value = response.getheader("Retry-After", "60")
            raise ProviderError("provider_rate_limit", True, int(value) if value.isdigit() else 60)
        if response.status >= 500:
            raise ProviderError("provider_unavailable", True)
        if response.status != 200:
            raise ProviderError("provider_authentication" if response.status in (401, 403) else "provider_http_rejected")
        raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ProviderError("response_too_large")
        body = json.loads(raw)
        if not isinstance(body, dict) or type(body.get("code")) is not int or body.get("code") != 0:
            code = body.get("code") if isinstance(body, dict) else None
            raise ProviderError("provider_quota" if code in (-18019907, -18019908) else "provider_business_error", code in (-18019907, -18019908), 3600)
        data = body.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("accepted"), list) or not isinstance(data.get("rejected"), list) or len(data["accepted"]) + len(data["rejected"]) > 40:
            raise ProviderError("invalid_response")
        return data
    except ProviderError:
        raise
    except (TimeoutError, socket.timeout):
        raise ProviderError("provider_timeout", True) from None
    except (OSError, http.client.HTTPException):
        raise ProviderError("provider_connection", True) from None
    except (ValueError, RecursionError, KeyError, TypeError):
        raise ProviderError("invalid_response") from None
    finally:
        conn.close()


@dataclass(frozen=True)
class Outcome:
    accepted: bool
    code: str = ""
    payload: dict | None = None


def outcome(data, number, carrier, registering=False):
    matching = [e for e in data["accepted"] if isinstance(e, dict) and e.get("number") == number and type(e.get("carrier")) is int and e.get("carrier") == int(carrier)]
    rejected = [e for e in data["rejected"] if isinstance(e, dict) and e.get("number") == number and e.get("carrier") in (int(carrier), 0, None)]
    if len(matching) + len(rejected) != 1:
        raise ProviderError("ambiguous_response")
    if matching:
        return Outcome(True, payload=matching[0])
    error = rejected[0].get("error")
    if not isinstance(error, dict) or type(error.get("code")) is not int:
        raise ProviderError("invalid_response")
    code = error["code"]
    if registering and code == -18019901:
        return Outcome(True, code="already_registered")
    if code in (-18019907, -18019908):
        raise ProviderError("provider_quota", True, 3600)
    names = {-18019902: "not_registered", -18019903: "unsupported_identifier", -18019909: "no_carrier_updates", -18019910: "unsupported_carrier", -18019911: "carrier_registration_unavailable"}
    return Outcome(False, code=names.get(code, "number_rejected"))
