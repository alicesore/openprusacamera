"""Load the user-editable config file from the boot partition."""

import os
import uuid
from dataclasses import dataclass, fields



def default_path():
    """Bookworm and later mount the boot partition at /boot/firmware."""
    if os.environ.get("OPENPRUSACAMERA_CONFIG"):
        return os.environ["OPENPRUSACAMERA_CONFIG"]
    boot = "/boot/firmware" if os.path.isdir("/boot/firmware") else "/boot"
    return os.path.join(boot, "openprusacamera.txt")


@dataclass
class Config:
    token: str = ""
    camera: str = "csi"
    usb_device: str = "/dev/video0"
    interval: int = 10
    width: int = 1280
    height: int = 720
    jpeg_quality: int = 85
    rotation: int = 0
    wifi_ssid: str = ""
    wifi_password: str = ""
    wifi_country: str = "US"
    hostname: str = "openprusacamera"
    mac_address: str = ""
    fingerprint: str = ""
    ssh: bool = False

    def validate(self):
        if self.camera not in ("csi", "usb"):
            raise ValueError(f"camera must be 'csi' or 'usb', got {self.camera!r}")
        if self.rotation not in (0, 90, 180, 270):
            raise ValueError("rotation must be 0, 90, 180 or 270")
        if self.fingerprint and not 16 <= len(self.fingerprint) <= 64:
            raise ValueError("fingerprint must be 16-64 characters; clear it to generate a new one")
        if self.interval < 1:
            raise ValueError("interval must be at least 1 second")
        if not 1 <= self.jpeg_quality <= 100:
            raise ValueError("jpeg_quality must be between 1 and 100")


def parse(text):
    """Parse 'key = value' lines into a dict. Tolerates CRLF, a BOM and comments."""
    values = {}
    for line in text.lstrip("﻿").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip().lower()] = value.strip()
    return values


def load(path=None):
    path = path or default_path()
    with open(path, encoding="utf-8") as f:
        values = parse(f.read())

    cfg = Config()
    for field in fields(Config):
        if field.name in values:
            raw = values[field.name]
            if field.type is int:
                raw = int(raw)
            elif field.type is bool:
                raw = raw.lower() in ("1", "true", "yes", "on")
            setattr(cfg, field.name, raw)
    cfg.validate()
    return cfg


def update(path, changes):
    """Rewrite values for existing keys in place, keeping comments and layout."""
    with open(path, encoding="utf-8") as f:
        lines = f.read().lstrip("﻿").splitlines()

    remaining = dict(changes)
    for i, line in enumerate(lines):
        key = line.partition("=")[0].strip().lower()
        if "=" in line and not line.lstrip().startswith("#") and key in remaining:
            lines[i] = f"{key} = {remaining.pop(key)}"
    lines.extend(f"{k} = {v}" for k, v in remaining.items())

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def ensure_fingerprint(cfg, path=None):
    """Generate a fingerprint once and save it to the config so it survives reboots.

    Prusa Connect ties a camera token to the first fingerprint it sees and silently
    ignores uploads from any other, so this value must never change.
    """
    if not cfg.fingerprint:
        cfg.fingerprint = uuid.uuid4().hex
        update(path or default_path(), {"fingerprint": cfg.fingerprint})
    return cfg.fingerprint
