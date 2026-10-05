# openprusacamera

Turns a Raspberry Pi Zero W or Zero 2 W into a [Prusa Connect](https://connect.prusa3d.com) camera.
Work in progress: not yet tested on real hardware.

## Setup

Either flash the prebuilt image (see [Releases](../../releases)) or run the installer on Raspberry Pi OS Lite:

```bash
git clone https://github.com/alicesore/openprusacamera && cd openprusacamera
sudo ./install.sh --camera csi    # or --camera usb
sudo reboot
```

The installer enables console auto-login, installs the services and turns SSH **off** at next boot
(use `--ssh` to keep it).

## Connecting to Prusa Connect

Pick one:
- Put the camera token in `token =` in the config file.
- Leave it empty and, on boot, show the camera a Prusa Connect QR code. Both the Wi-Fi + token JSON
  code and the `camera-service-webcam.prusa3d.com/#t=...` link code are understood.

## Config file

`openprusacamera.txt` sits on the SD card's boot partition, so you can edit it from any computer.
It holds the token, camera type (`csi`/`usb`), interval, resolution, rotation, Wi-Fi, hostname and a
debug `ssh` switch. Settings apply on the next boot.

On first boot the Wi-Fi MAC address is written into the file, so you can register it with networks
that only allow known devices.

**Keep the `fingerprint` line.** Prusa Connect ties a camera token to the first fingerprint it sees and
silently ignores uploads from any other (it still answers HTTP 200). If you reflash the card, copy the
config file across, or use a new token.

## Building the image

```bash
./pi-gen/build.sh    # needs Docker; output in pi-gen/work/pi-gen/deploy/
```

Tagging a release (`v*`) builds the image in GitHub Actions and attaches it. The image logs in as `pi`
(password `raspberry`) with console auto-login and SSH disabled.

## Tests

```bash
python3 -m unittest discover -s tests
```
