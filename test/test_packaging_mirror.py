import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIRROR = ROOT / "src" / "browser_workspace_app"


class PackagingMirrorTests(unittest.TestCase):
    def test_runtime_modules_match_distribution(self):
        for name in (
            "fifo_queue.py",
            "turn_dispatcher.py",
            "chatgpt_probe.py",
            "chatgpt_queue_runtime.py",
            "managed_chrome.py",
            "session_client.py",
            "session_daemon.py",
            "platform_runner.py",
        ):
            with self.subTest(module=name):
                self.assertEqual((ROOT / name).read_bytes(), (MIRROR / name).read_bytes())

    def test_cli_matches_distribution(self):
        source = (ROOT / "bin" / "browser-workspace").read_text()
        packaged = (MIRROR / "cli.py").read_text()
        self.assertEqual(source.replace("ROOT=Path(__file__).resolve().parents[1]",
                                        "ROOT=Path(__file__).resolve().parent"), packaged)


if __name__ == "__main__":
    unittest.main()
