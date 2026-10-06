"""Find a Prusa Connect QR code in front of the camera and extract its payload."""

import ctypes
import ctypes.util
import json
import logging
import re
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from .capture import CaptureError, capture_bmp

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


def bmp_to_gray(bmp):
    """Return (width, height, 8-bit gray bytes) from an uncompressed 24/32-bit BMP.

    The green channel stands in for brightness, which is plenty for a QR code and
    keeps this to fast byte slicing instead of per-pixel Python loops.
    """
    if bmp[:2] != b"BM" or len(bmp) < 54:
        raise ValueError("not a BMP image")
    offset = int.from_bytes(bmp[10:14], "little")
    width = int.from_bytes(bmp[18:22], "little", signed=True)
    height = int.from_bytes(bmp[22:26], "little", signed=True)
    bits = int.from_bytes(bmp[28:30], "little")
    compression = int.from_bytes(bmp[30:34], "little")
    if bits not in (24, 32) or compression not in (0, 3) or width <= 0 or height == 0:
        raise ValueError("unsupported BMP format")
    step = bits // 8
    stride = ((width * bits + 31) // 32) * 4
    rows = abs(height)
    if len(bmp) < offset + stride * rows:
        raise ValueError("truncated BMP image")
    order = range(rows - 1, -1, -1) if height > 0 else range(rows)  # positive height is bottom-up
    gray = b"".join(
        bmp[offset + r * stride + 1: offset + r * stride + width * step: step] for r in order
    )
    return width, rows, gray


_zbar = None


def _load_zbar():
    global _zbar
    if _zbar is None:
        name = ctypes.util.find_library("zbar") or "libzbar.so.0"
        try:
            lib = ctypes.CDLL(name)
        except OSError:
            raise CaptureError("libzbar is not installed; install libzbar0t64 (or libzbar0)")
        vp = ctypes.c_void_p
        lib.zbar_image_scanner_create.restype = vp
        lib.zbar_image_scanner_set_config.argtypes = [vp, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        lib.zbar_image_create.restype = vp
        lib.zbar_image_set_format.argtypes = [vp, ctypes.c_ulong]
        lib.zbar_image_set_size.argtypes = [vp, ctypes.c_uint, ctypes.c_uint]
        lib.zbar_image_set_data.argtypes = [vp, ctypes.c_char_p, ctypes.c_ulong, vp]
        lib.zbar_scan_image.argtypes = [vp, vp]
        lib.zbar_image_first_symbol.argtypes = [vp]
        lib.zbar_image_first_symbol.restype = vp
        lib.zbar_symbol_next.argtypes = [vp]
        lib.zbar_symbol_next.restype = vp
        lib.zbar_symbol_get_data.argtypes = [vp]
        lib.zbar_symbol_get_data.restype = ctypes.c_char_p
        lib.zbar_image_destroy.argtypes = [vp]
        lib.zbar_image_scanner_destroy.argtypes = [vp]
        _zbar = lib
    return _zbar


def decode_gray(width, height, gray):
    """Return the text of every QR code in an 8-bit gray image, using libzbar."""
    lib = _load_zbar()
    ZBAR_QRCODE, ZBAR_CFG_ENABLE = 64, 0
    scanner = lib.zbar_image_scanner_create()
    image = lib.zbar_image_create()
    try:
        lib.zbar_image_scanner_set_config(scanner, 0, ZBAR_CFG_ENABLE, 0)  # everything off...
        lib.zbar_image_scanner_set_config(scanner, ZBAR_QRCODE, ZBAR_CFG_ENABLE, 1)  # ...except QR
        lib.zbar_image_set_format(image, int.from_bytes(b"Y800", "little"))
        lib.zbar_image_set_size(image, width, height)
        lib.zbar_image_set_data(image, gray, len(gray), None)
        found = []
        if lib.zbar_scan_image(scanner, image) > 0:
            symbol = lib.zbar_image_first_symbol(image)
            while symbol:
                found.append(lib.zbar_symbol_get_data(symbol).decode("utf-8", "replace"))
                symbol = lib.zbar_symbol_next(symbol)
        return found
    finally:
        lib.zbar_image_destroy(image)
        lib.zbar_image_scanner_destroy(scanner)


def decode(bmp):
    try:
        return decode_gray(*bmp_to_gray(bmp))
    except ValueError as e:
        raise CaptureError(str(e))


def scan_once(cfg):
    try:
        lines = decode(capture_bmp(cfg))
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
