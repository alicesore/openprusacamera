import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from openprusacamera import config, setup  # noqa: E402

TEMPLATE = os.path.join(os.path.dirname(__file__), "..", "config", "openprusacamera.txt")


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
