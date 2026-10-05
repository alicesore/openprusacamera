"""Grab a single JPEG frame from a CSI or USB camera."""

import shutil
import subprocess


class CaptureError(Exception):
    pass


def _run(cmd, timeout=60):
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        raise CaptureError(f"{cmd[0]} is not installed")
    except subprocess.TimeoutExpired:
        raise CaptureError(f"{cmd[0]} timed out")
    if result.returncode != 0 or not result.stdout:
        tail = result.stderr.decode(errors="replace").strip().splitlines()[-3:]
        raise CaptureError(f"{cmd[0]} failed: {' | '.join(tail)}")
    return result.stdout


def _ffmpeg_quality(jpeg_quality):
    """Map 1-100 (higher is better) onto ffmpeg's 31-2 (lower is better)."""
    return str(round(31 - (jpeg_quality - 1) * 29 / 99))


def _capture_csi(cfg):
    tool = shutil.which("rpicam-still") or shutil.which("libcamera-still")
    if not tool:
        raise CaptureError("rpicam-still not found; install rpicam-apps")
    cmd = [
        tool, "--nopreview", "--timeout", "1000",
        "--width", str(cfg.width), "--height", str(cfg.height),
        "--quality", str(cfg.jpeg_quality), "--output", "-",
    ]
    if cfg.rotation == 180:
        cmd += ["--hflip", "--vflip"]
    return _run(cmd)


def _capture_usb(cfg):
    cmd = [
        "ffmpeg", "-loglevel", "error", "-f", "video4linux2",
        "-video_size", f"{cfg.width}x{cfg.height}",
        "-ss", "1", "-i", cfg.usb_device, "-frames:v", "1",
    ]
    filters = {90: "transpose=1", 180: "transpose=1,transpose=1", 270: "transpose=2"}
    if cfg.rotation in filters:
        cmd += ["-vf", filters[cfg.rotation]]
    cmd += ["-q:v", _ffmpeg_quality(cfg.jpeg_quality), "-f", "image2pipe", "-c:v", "mjpeg", "-"]
    return _run(cmd)


def _rotate_with_ffmpeg(jpeg, rotation, jpeg_quality):
    transpose = {90: "transpose=1", 270: "transpose=2"}[rotation]
    try:
        result = subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-f", "image2pipe", "-i", "-", "-vf", transpose,
             "-q:v", _ffmpeg_quality(jpeg_quality), "-f", "image2pipe", "-c:v", "mjpeg", "-"],
            input=jpeg, capture_output=True, timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        raise CaptureError("ffmpeg is required for 90/270 degree rotation")
    if result.returncode != 0 or not result.stdout:
        raise CaptureError("ffmpeg could not rotate the image")
    return result.stdout


def capture(cfg):
    if cfg.camera == "usb":
        jpeg = _capture_usb(cfg)
    else:
        jpeg = _capture_csi(cfg)
        if cfg.rotation in (90, 270):
            jpeg = _rotate_with_ffmpeg(jpeg, cfg.rotation, cfg.jpeg_quality)
    if not jpeg.startswith(b"\xff\xd8"):
        raise CaptureError("camera did not return a JPEG image")
    return jpeg
