#!/usr/bin/env bash
# Install openprusacamera on Raspberry Pi OS (Lite, Bookworm or newer).
# Also used by the pi-gen image build, so it must work inside a chroot.
set -euo pipefail

CAMERA=""
SSH=false
LOGIN_USER=""

usage() {
    cat <<USAGE
Usage: sudo ./install.sh [--camera csi|usb] [--ssh] [--user NAME]

  --camera csi|usb  Camera type written to the config (default csi on a fresh install)
  --ssh             Leave SSH enabled (default: SSH is turned off at next boot)
  --user NAME       User to auto-login on the console (default: the user who ran sudo)
USAGE
}

while [ $# -gt 0 ]; do
    case "$1" in
        --camera) CAMERA="${2:-}"; shift 2 ;;
        --ssh) SSH=true; shift ;;
        --user) LOGIN_USER="${2:-}"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
    esac
done

if [ -n "$CAMERA" ] && [ "$CAMERA" != csi ] && [ "$CAMERA" != usb ]; then
    echo "--camera must be csi or usb" >&2; exit 1
fi
if [ "$(id -u)" -ne 0 ]; then
    echo "Run as root: sudo ./install.sh" >&2; exit 1
fi

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOOT=/boot/firmware
[ -d "$BOOT" ] || BOOT=/boot
CONFIG="$BOOT/openprusacamera.txt"
APP=/opt/openprusacamera

if ! command -v nmcli >/dev/null 2>&1 && ! dpkg -s network-manager >/dev/null 2>&1; then
    echo "NetworkManager is required (Raspberry Pi OS Bookworm or newer)." >&2; exit 1
fi

echo "==> Installing packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 ffmpeg zbar-tools
apt-get install -y rpicam-apps-lite || apt-get install -y libcamera-apps-lite

echo "==> Installing application to $APP"
rm -rf "$APP"
install -d "$APP"
cp -r "$REPO/src/openprusacamera" "$APP/openprusacamera"
find "$APP" -name __pycache__ -prune -exec rm -rf {} +

echo "==> Writing config to $CONFIG"
[ -e "$CONFIG" ] || cp "$REPO/config/openprusacamera.txt" "$CONFIG"
changes="{'ssh': '$SSH'}"
[ -z "$CAMERA" ] || changes="{'ssh': '$SSH', 'camera': '$CAMERA'}"
PYTHONPATH="$APP" python3 -c "from openprusacamera import config; config.update('$CONFIG', $changes)"

echo "==> Enabling console auto-login"
LOGIN_USER="${LOGIN_USER:-${SUDO_USER:-$(getent passwd 1000 | cut -d: -f1)}}"
if [ -n "$LOGIN_USER" ] && id "$LOGIN_USER" >/dev/null 2>&1; then
    install -d /etc/systemd/system/getty@tty1.service.d
    cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf <<AUTOLOGIN
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $LOGIN_USER --noclear %I \$TERM
AUTOLOGIN
else
    echo "    No login user found; skipping auto-login (use --user NAME)"
fi

echo "==> Installing services"
install -m 644 "$REPO"/systemd/openprusacamera.service "$REPO"/systemd/openprusacamera-setup.service /etc/systemd/system/
systemctl daemon-reload || true
systemctl enable openprusacamera-setup.service openprusacamera.service

echo
echo "Installed. Edit $CONFIG (token, Wi-Fi, camera) or show a Prusa Connect QR code to the camera."
if [ "$SSH" = false ]; then
    echo "SSH will be DISABLED at next boot. Re-run with --ssh, or set 'ssh = true' in the config, to keep it."
    [ -z "${SSH_CONNECTION:-}" ] || echo "WARNING: you are connected over SSH and will be locked out after reboot."
fi
echo "Reboot to start: sudo reboot"
