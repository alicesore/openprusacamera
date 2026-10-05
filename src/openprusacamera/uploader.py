"""Upload JPEG snapshots to the Prusa Connect camera API."""

import urllib.error
import urllib.request

SNAPSHOT_URL = "https://connect.prusa3d.com/c/snapshot"


class UploadError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status

    @property
    def fatal(self):
        """True when retrying with the same token will not help."""
        return self.status in (401, 403)


def upload(jpeg, token, fingerprint, url=SNAPSHOT_URL, timeout=30):
    request = urllib.request.Request(
        url,
        data=jpeg,
        method="PUT",
        headers={
            "Content-Type": "image/jpg",
            "Token": token,
            "Fingerprint": fingerprint,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as e:
        raise UploadError(f"Prusa Connect rejected the upload: HTTP {e.code}", e.code)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise UploadError(f"Could not reach Prusa Connect: {e}")
