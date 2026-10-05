"""Apply the boot-partition config to the system, then onboard via QR if needed.

Runs on every boot before the camera service. The config file is the source of
truth, so settings edited on the SD card take effect on the next boot.
"""

import logging
import re
import socket
import subprocess
import sys
import time

from . import config as config_mod
from . import qr

log = logging.getLogger("openprusacamera.setup")

WIFI_IFACE = "wlan0"
CONNECTION = "openprusacamera"
HOSTNAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def run(cmd):
    """Run a system command, logging and swallowing failures."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.warning("%s: %s", cmd[0], e)
        return False
    if result.returncode != 0:
        log.warning("%s failed: %s", " ".join(cmd[:3]), result.stderr.strip())
        return False
    return True


def read_mac(wait=30):
    path = f"/sys/class/net/{WIFI_IFACE}/address"
    for _ in range(wait):
        try:
            with open(path) as f:
                return f.read().strip()
        except OSError:
            time.sleep(1)
    return ""


def record_mac(cfg, path):
    mac = read_mac()
    if mac and mac != cfg.mac_address:
        config_mod.update(path, {"mac_address": mac})
        cfg.mac_address = mac
        log.info("Recorded Wi-Fi MAC address %s", mac)


def apply_hostname(cfg):
    if not HOSTNAME_RE.match(cfg.hostname):
        log.warning("Ignoring invalid hostname %r", cfg.hostname)
    elif cfg.hostname != socket.gethostname():
        run(["hostnamectl", "set-hostname", cfg.hostname])


def apply_ssh(cfg):
    if cfg.ssh:
        run(["systemctl", "enable", "--now", "ssh"])
    else:
        run(["systemctl", "disable", "--now", "ssh", "ssh.socket"])


def apply_wifi(cfg):
    if not cfg.wifi_ssid:
        return
    country = cfg.wifi_country.upper()
    if re.fullmatch(r"[A-Z]{2}", country):
        run(["raspi-config", "nonint", "do_wifi_country", country])
    run(["rfkill", "unblock", "wifi"])

    run(["nmcli", "connection", "delete", CONNECTION])
    cmd = [
        "nmcli", "connection", "add", "type", "wifi", "con-name", CONNECTION,
        "ifname", WIFI_IFACE, "ssid", cfg.wifi_ssid,
        # Use the real hardware MAC so network allow-lists match the recorded address.
        "802-11-wireless.cloned-mac-address", "permanent",
    ]
    if cfg.wifi_password:
        cmd += ["wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", cfg.wifi_password]
    if run(cmd):
        run(["nmcli", "connection", "up", CONNECTION])


def onboard(path, scan=qr.scan_once):
    """Block until a token is in the config, scanning for a QR code if needed."""
    while True:
        cfg = config_mod.load(path)
        if cfg.token:
            return cfg
        log.info("No token set. Show a Prusa Connect QR code to the camera.")
        payload = scan(cfg)
        if not payload:
            continue
        changes = {"token": payload.token}
        if payload.ssid:
            changes.update(wifi_ssid=payload.ssid, wifi_password=payload.password)
        config_mod.update(path, changes)
        log.info("Token received from QR code")
        if payload.ssid:
            apply_wifi(config_mod.load(path))


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    path = config_mod.default_path()
    try:
        cfg = config_mod.load(path)
    except (OSError, ValueError) as e:
        log.error("Cannot read %s: %s", path, e)
        sys.exit(1)

    record_mac(cfg, path)
    apply_hostname(cfg)
    apply_ssh(cfg)
    apply_wifi(cfg)
    onboard(path)


if __name__ == "__main__":
    main()
