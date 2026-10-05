"""Main service loop: capture a frame, upload it, repeat."""

import logging
import sys
import time

from . import config as config_mod
from .capture import CaptureError, capture
from .uploader import UploadError, upload

log = logging.getLogger("openprusacamera")

MAX_BACKOFF = 300
BAD_TOKEN_WAIT = 60


def run(path=None):
    failures = 0

    while True:
        started = time.monotonic()
        try:
            # Re-read each cycle so an edited token or setting applies without a reboot.
            cfg = config_mod.load(path)
        except (OSError, ValueError) as e:
            log.error("Cannot read config: %s", e)
            time.sleep(BAD_TOKEN_WAIT)
            continue

        if not cfg.token:
            log.error("No token set in config; waiting for one")
            time.sleep(BAD_TOKEN_WAIT)
            continue

        try:
            fingerprint = config_mod.ensure_fingerprint(cfg, path)
            upload(capture(cfg), cfg.token, fingerprint)
            if failures:
                log.info("Recovered after %d failed attempts", failures)
            failures = 0
        except (CaptureError, OSError) as e:
            failures += 1
            log.error("Capture failed: %s", e)
        except UploadError as e:
            failures += 1
            log.error("%s", e)
            if e.fatal:
                log.error("Token or fingerprint looks invalid; check the token in the config")
                time.sleep(BAD_TOKEN_WAIT)
                continue

        delay = cfg.interval
        if failures:
            delay = min(cfg.interval * 2 ** min(failures, 6), MAX_BACKOFF)
        time.sleep(max(0, delay - (time.monotonic() - started)))


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        run(sys.argv[1] if len(sys.argv) > 1 else None)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
