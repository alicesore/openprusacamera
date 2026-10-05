#!/usr/bin/env bash
# Build the openprusacamera Raspberry Pi image with pi-gen (needs Docker).
# Output lands in pi-gen/work/pi-gen/deploy/.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
PIGEN="$HERE/work/pi-gen"

if [ ! -d "$PIGEN" ]; then
    mkdir -p "$HERE/work"
    git clone --depth 1 https://github.com/RPi-Distro/pi-gen "$PIGEN"
fi

# Our stage, plus a copy of the project for it to install.
rm -rf "$PIGEN/stage-openprusacamera"
cp -R "$HERE/stage-openprusacamera" "$PIGEN/stage-openprusacamera"
mkdir -p "$PIGEN/stage-openprusacamera/00-install/files/repo"
tar -C "$REPO" --exclude=__pycache__ -cf - install.sh src systemd config \
    | tar -C "$PIGEN/stage-openprusacamera/00-install/files/repo" -xf -

cp "$HERE/config" "$PIGEN/config"
# Only the final image is wanted, not an intermediate stage2 one.
touch "$PIGEN/stage2/SKIP_IMAGES"

cd "$PIGEN"
./build-docker.sh -c config
echo "Image written to $PIGEN/deploy/"
