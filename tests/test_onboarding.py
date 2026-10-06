import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from openprusacamera import config, qr, setup  # noqa: E402

TEMPLATE = os.path.join(os.path.dirname(__file__), "..", "config", "openprusacamera.txt")


class ParsePayload(unittest.TestCase):
    def test_json_with_wifi(self):
        p = qr.parse_payload('{"ssid":"Net","pwd":"hunter2hunter2","token":"AAAAAAAAAAAAAAAAAAAA"}')
        self.assertEqual((p.token, p.ssid, p.password), ("AAAAAAAAAAAAAAAAAAAA", "Net", "hunter2hunter2"))

    def test_url_token_keeps_v1_prefix(self):
        p = qr.parse_payload("https://camera-service-webcam.prusa3d.com/#t=v1.BBBBBBBBBBBBBBBBBBBBBBBBBBB")
        self.assertEqual(p.token, "v1.BBBBBBBBBBBBBBBBBBBBBBBBBBB")
        self.assertEqual(p.ssid, "")

    def test_rejects_other_codes(self):
        for text in ("hello", "https://evil.example/#t=v1.BBBBBBBBBBBBBBBBBBBBBBBBBBB",
                     "https://prusa3d.com.evil.example/#t=abcdefghij", "http://connect.prusa3d.com/#t=abcdefghij",
                     "https://connect.prusa3d.com/", '{"ssid":"x"}', "[1]"):
            self.assertIsNone(qr.parse_payload(text), text)

    def test_rejects_values_that_could_corrupt_config(self):
        self.assertIsNone(qr.parse_payload('{"ssid":"a\\nb","pwd":"x","token":"AAAAAAAAAAAAAAAAAAAA"}'))
        self.assertIsNone(qr.parse_payload('{"token":"abc\\ntoken=evil1234"}'))


def make_bmp(rows, bits=24, top_down=False):
    """Build a BMP from rows of (b, g, r) tuples; row 0 is the top of the image."""
    width, height = len(rows[0]), len(rows)
    step = bits // 8
    stride = ((width * bits + 31) // 32) * 4
    body = b""
    for row in (rows if top_down else reversed(rows)):
        raw = b"".join(bytes(px) + b"\xff" * (step - 3) for px in row)
        body += raw + b"\x00" * (stride - len(raw))
    header = (b"BM" + (54 + len(body)).to_bytes(4, "little") + b"\0\0\0\0" + (54).to_bytes(4, "little")
              + (40).to_bytes(4, "little") + width.to_bytes(4, "little")
              + (-height if top_down else height).to_bytes(4, "little", signed=True)
              + (1).to_bytes(2, "little") + bits.to_bytes(2, "little") + b"\0" * 24)
    return header + body


class BmpToGray(unittest.TestCase):
    ROWS = [[(0, 10, 0), (0, 20, 0), (0, 30, 0)], [(0, 40, 0), (0, 50, 0), (0, 60, 0)]]  # 3 wide: padding needed

    def test_bottom_up_24bit(self):
        self.assertEqual(qr.bmp_to_gray(make_bmp(self.ROWS)), (3, 2, bytes([10, 20, 30, 40, 50, 60])))

    def test_top_down_and_32bit(self):
        for kwargs in ({"top_down": True}, {"bits": 32}):
            self.assertEqual(qr.bmp_to_gray(make_bmp(self.ROWS, **kwargs))[2], bytes([10, 20, 30, 40, 50, 60]))

    def test_rejects_bad_input(self):
        for bad in (b"not a bmp", make_bmp(self.ROWS)[:-3]):
            with self.assertRaises(ValueError):
                qr.bmp_to_gray(bad)


class Config(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "c.txt")
        shutil.copy(TEMPLATE, self.path)

    def test_defaults_and_bool(self):
        cfg = config.load(self.path)
        self.assertFalse(cfg.ssh)
        config.update(self.path, {"ssh": "true"})
        self.assertTrue(config.load(self.path).ssh)

    def test_template_has_every_field(self):
        keys = config.parse(open(TEMPLATE).read())
        for field in config.fields(config.Config):
            self.assertIn(field.name, keys)


class Onboard(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "c.txt")
        shutil.copy(TEMPLATE, self.path)

    def test_scans_until_code_then_saves_token_and_wifi(self):
        results = iter([None, qr.Payload("AAAAAAAAAAAAAAAAAAAA", "Net", "pw12345678")])
        with mock.patch.object(setup, "apply_wifi") as wifi:
            cfg = setup.onboard(self.path, scan=lambda c: next(results))
        self.assertEqual((cfg.token, cfg.wifi_ssid, cfg.wifi_password),
                         ("AAAAAAAAAAAAAAAAAAAA", "Net", "pw12345678"))
        wifi.assert_called_once()

    def test_url_code_leaves_existing_wifi_alone(self):
        config.update(self.path, {"wifi_ssid": "Keep", "wifi_password": "keepkeep"})
        with mock.patch.object(setup, "apply_wifi") as wifi:
            cfg = setup.onboard(self.path, scan=lambda c: qr.Payload("v1.abcdefghijkl"))
        self.assertEqual((cfg.token, cfg.wifi_ssid), ("v1.abcdefghijkl", "Keep"))
        wifi.assert_not_called()

    def test_existing_token_skips_scanning(self):
        config.update(self.path, {"token": "AAAAAAAAAAAAAAAAAAAA"})
        setup.onboard(self.path, scan=lambda c: self.fail("should not scan"))


class Apply(unittest.TestCase):
    def test_ssh_off_by_default_on_when_set(self):
        with mock.patch.object(setup, "run") as run:
            setup.apply_ssh(config.Config())
            setup.apply_ssh(config.Config(ssh=True))
        self.assertEqual(run.call_args_list[0][0][0][:2], ["systemctl", "disable"])
        self.assertEqual(run.call_args_list[1][0][0][:2], ["systemctl", "enable"])

    def test_wifi_open_network_has_no_psk_and_skips_when_empty(self):
        with mock.patch.object(setup, "run", return_value=True) as run:
            setup.apply_wifi(config.Config())
            self.assertEqual(run.call_count, 0)
            setup.apply_wifi(config.Config(wifi_ssid="Open"))
        add = [c[0][0] for c in run.call_args_list if c[0][0][:3] == ["nmcli", "connection", "add"]][0]
        self.assertNotIn("wifi-sec.psk", add)
        self.assertIn("permanent", add)


if __name__ == "__main__":
    unittest.main()
