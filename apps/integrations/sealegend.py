"""Local source-access proof only: pinned carrier, no ORM, AI or browser execution."""
import hashlib
import http.client
import ipaddress
import json
import re
import socket
import ssl
import subprocess
import sys
from datetime import datetime

# Deliberately code configuration, not administrator-supplied URLs/environment overrides.
ADAPTER = "sealegend-web-proof-v1"
HOST = "www.slg-shipping.com"
PATH = "/slg-sealegend-rest/containerDynamicForWeb/list.do"
WEBSITE = "https://www.slg-shipping.com/#/home/tracking"
MAX_BYTES = 262144
TOTAL_SECONDS = 20
SOCKET_SECONDS = 6
MAX_CONTAINERS = 100
MAX_EVENTS = 200
ERROR_CODES = frozenset({"invalid_reference", "unavailable", "timeout", "blocked_address",
                         "redirect_refused", "too_large", "source_changed", "not_found",
                         "identity_mismatch"})


class SourceError(ValueError):
    def __init__(self, code):
        self.code = code if code in ERROR_CODES else "unavailable"
        super().__init__(self.code)


def reference_value(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z0-9][A-Z0-9-]{5,39}", value):
        raise SourceError("invalid_reference")
    return value


def _text(value, limit=256):
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
        raise SourceError("source_changed")
    return value


def _timestamp(raw, kind):
    raw = _text(raw, 32)
    if raw is None:
        return None
    for pattern, fmt, precision in (
        (r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d", "date"),
        (r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", "%Y-%m-%d %H:%M", "minute"),
        (r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", "%Y-%m-%d %H:%M:%S", "second"),
    ):
        if re.fullmatch(pattern, raw):
            try:
                datetime.strptime(raw, fmt)
            except ValueError:
                break
            return {"raw": raw, "precision": precision, "designation": kind,
                    "source_timezone": None, "normalized_instant": None}
    raise SourceError("source_changed")


def _object(value):
    if not isinstance(value, dict):
        raise SourceError("source_changed")
    return value


def _array(value, limit):
    if not isinstance(value, list) or len(value) > limit:
        raise SourceError("source_changed")
    return value


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SourceError("source_changed")
        result[key] = value
    return result


def parse_candidate(body, reference):
    """All identities remain candidates; never silently choose containerList[0]."""
    reference_value(reference)
    if not isinstance(body, bytes) or len(body) > MAX_BYTES:
        raise SourceError("too_large")
    try:
        payload = _object(json.loads(body, object_pairs_hook=_unique_pairs))
    except (ValueError, UnicodeError, RecursionError):
        raise SourceError("source_changed") from None
    if "success" not in payload or "code" not in payload:
        raise SourceError("source_changed")
    if payload.get("success") is not True or payload.get("code") != 200:
        raise SourceError("unavailable")
    result = _object(payload.get("result"))
    if result.get("bkgNo") != reference:
        raise SourceError("identity_mismatch")
    entries = _array(result.get("containerList"), MAX_CONTAINERS)
    if not entries:
        raise SourceError("not_found")
    containers, identities = [], set()
    for item in entries:
        item = _object(item)
        number = _text(item.get("ctnno"), 11)
        if not number or not re.fullmatch(r"[A-Z]{4}\d{7}", number) or number in identities:
            raise SourceError("source_changed")
        identities.add(number)
        milestones, seen = [], set()
        for node in _array(item.get("nodeList", []), MAX_EVENTS):
            node = _object(node)
            combined = _text(node.get("voyageNo"))
            vessel, voyage = (combined.rsplit("/", 1) if combined and "/" in combined else (None, None))
            event = {"raw_status": _text(node.get("movementCode")),
                     "raw_text": _text(node.get("movementName")),
                     "location_code": _text(node.get("eventPort")),
                     "location_label": _text(node.get("portName")),
                     "vessel_code": _text(node.get("vesselName")),
                     "vessel_voyage_raw": combined, "vessel": vessel, "voyage": voyage,
                     "actual": _timestamp(node.get("actualDate"), "actual"),
                     "estimated": _timestamp(node.get("estimateDate"), "estimated")}
            # Source repeats the same facts with different presentation portFlag values.
            key = json.dumps(event, sort_keys=True, ensure_ascii=False)
            if key not in seen:
                seen.add(key)
                milestones.append(event)
        containers.append({"container_number": number, "milestones": milestones})
    equipment = _text(result.get("ctnSizeCount"))
    match = re.fullmatch(r"(\d{1,3})\*(\d{2}[A-Z]{2})", equipment or "")
    return {"adapter": ADAPTER, "website": WEBSITE, "search_reference": reference,
            "container_selection_required": len(containers) != 1,
            "containers": containers, "equipment_raw": equipment,
            "equipment_quantity": int(match[1]) if match else None,
            "equipment_type": match[2] if match else None,
            "route": {k: _text(result.get(k)) for k in ("por", "pol", "pod", "del")},
            # No shipment-level status is present in the observed response. B/L type is not progress.
            "raw_status": None, "source_sha256": hashlib.sha256(body).hexdigest()}


def public_addresses():
    """Reject the entire answer if any address is unsafe; connect to the checked literal."""
    answers = socket.getaddrinfo(HOST, 443, type=socket.SOCK_STREAM)
    if not answers or len(answers) > 32:
        raise SourceError("blocked_address")
    for answer in answers:
        address = ipaddress.ip_address(answer[4][0])
        if (not address.is_global or address.is_multicast
                or (address.version == 6 and (
                    address not in ipaddress.ip_network("2000::/3")
                    or address.sixtofour is not None or address.teredo is not None))):
            raise SourceError("blocked_address")
    return answers


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, answer):
        super().__init__(HOST, timeout=SOCKET_SECONDS, context=ssl.create_default_context())
        self.answer = answer

    def connect(self):
        family, socktype, proto, _, sockaddr = self.answer
        raw = socket.socket(family, socktype, proto)
        try:
            raw.settimeout(SOCKET_SECONDS)
            raw.connect(sockaddr)  # no second DNS lookup and no proxy support
            self.sock = self._context.wrap_socket(raw, server_hostname=HOST)
        except BaseException:
            raw.close()
            raise


def _network_body(reference):
    """Exactly one HTTPS request, zero retries/redirects/subresources/cookies."""
    reference_value(reference)
    conn = _PinnedHTTPS(public_addresses()[0])
    try:
        conn.request("POST", PATH, body=json.dumps({"bkgNo": reference}).encode(), headers={
            "Content-Type": "application/json", "Accept": "application/json",
            "Accept-Encoding": "identity", "User-Agent": "JAHEZ-Source-Proof/1"})
        response = conn.getresponse()
        if 300 <= response.status < 400:
            raise SourceError("redirect_refused")
        if response.status != 200:
            raise SourceError("unavailable")
        if response.getheader("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            raise SourceError("source_changed")
        if response.getheader("Content-Encoding", "identity").lower() != "identity":
            raise SourceError("source_changed")
        length = response.getheader("Content-Length")
        if length is not None and (not length.isdecimal() or int(length) > MAX_BYTES):
            raise SourceError("too_large")
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise SourceError("too_large")
        return body
    finally:
        conn.close()


def retrieve_body(reference):
    """Child deadline also bounds DNS, TLS, response headers and trickling bodies."""
    reference_value(reference)
    try:
        proc = subprocess.run([sys.executable, "-m", "apps.integrations.sealegend"],
                              input=reference.encode(), capture_output=True, timeout=TOTAL_SECONDS,
                              check=False)
    except subprocess.TimeoutExpired:
        raise SourceError("timeout") from None
    if proc.returncode:
        code = proc.stdout.decode("ascii", errors="ignore")
        raise SourceError(code if code in ERROR_CODES else "unavailable")
    if len(proc.stdout) > MAX_BYTES:
        raise SourceError("too_large")
    return proc.stdout


def retrieve_candidate(reference):
    return parse_candidate(retrieve_body(reference), reference)


def _worker():
    try:
        body = _network_body(sys.stdin.buffer.read(41).decode("ascii"))
    except SourceError as exc:
        sys.stdout.write(exc.code)
        return 1
    except (TimeoutError, socket.timeout):
        sys.stdout.write("timeout")
        return 1
    except Exception:
        sys.stdout.write("unavailable")
        return 1
    sys.stdout.buffer.write(body)
    return 0


if __name__ == "__main__":
    sys.exit(_worker())
