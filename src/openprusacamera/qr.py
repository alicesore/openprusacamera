"""Find a Prusa Connect QR code in front of the camera and extract its payload."""

import json
import logging
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from .capture import CaptureError, capture

log = logging.getLogger("openprusacamera.qr")

TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]{8,128}$")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


@dataclass
class Payload:
    token: str
    ssid: str = ""
    password: str = ""


def _clean(value, max_len):
    """Reject anything that could break the config file or Wi-Fi settings."""
    if not isinstance(value, str) or len(value) > max_len or CONTROL_RE.search(value):
        return None
    return value


def _from_json(text):
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    token = data.get("token")
    if not isinstance(token, str) or not TOKEN_RE.match(token):
        return None
    ssid = _clean(data.get("ssid", ""), 32)
    password = _clean(data.get("pwd", ""), 63)
    if ssid is None or password is None:
        return None
    return Payload(token, ssid, password)


def _from_url(text):
    url = urlparse(text)
    host = url.hostname or ""
    if url.scheme != "https" or not (host == "prusa3d.com" or host.endswith(".prusa3d.com")):
        return None
    values = parse_qs(url.fragment).get("t")
    if not values or not TOKEN_RE.match(values[0]):
        return None
    return Payload(values[0])


def parse_payload(text):
    """Return a Payload for a Prusa QR code, or None for anything else."""
    text = text.strip()
    return _from_json(text) if text.startswith("{") else _from_url(text)


def decode(jpeg):
    """Return the text of every QR code found in a JPEG, using zbarimg."""
    with tempfile.NamedTemporaryFile(suffix=".jpg") as f:
        f.write(jpeg)
        f.flush()
        try:
            result = subprocess.run(
                ["zbarimg", "--quiet", "--raw", "-Sdisable", "-Sqrcode.enable", f.name],
                capture_output=True, text=True, timeout=60,
            )
        except FileNotFoundError:
            raise CaptureError("zbarimg is not installed; install zbar-tools")
        except subprocess.TimeoutExpired:
            return []
    # zbarimg exits 1 when it finds no code, which is the normal case here.
    return result.stdout.splitlines()


def scan_once(cfg):
    try:
        lines = decode(capture(cfg))
    except CaptureError as e:
        log.error("QR scan failed: %s", e)
        time.sleep(5)
        return None
    for line in lines:
        payload = parse_payload(line)
        if payload:
            return payload
        log.info("Ignoring a QR code that is not a Prusa Connect code")
    return None
