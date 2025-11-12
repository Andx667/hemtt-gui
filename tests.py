import os
import unittest

from command_runner import build_command
from config_store import get_config_path, load_config, save_config


class TestHemttGUIHelpers(unittest.TestCase):
    def test_build_command(self):
        cmd = build_command("hemtt", ["build"])  # type: ignore[arg-type]
        self.assertEqual(cmd, ["hemtt", "build"])  # ensure proper concatenation

    def test_config_roundtrip(self):
        cfg = load_config()
        cfg["hemtt_path"] = "hemtt-custom"
        save_config(cfg)
        loaded = load_config()
        self.assertEqual(loaded["hemtt_path"], "hemtt-custom")

    def tearDown(self):
        # Cleanup test config side effect
        path = get_config_path()
        if os.path.isfile(path):
            try:
                os.remove(path)
            except Exception:
                pass

if __name__ == "__main__":
    unittest.main()
