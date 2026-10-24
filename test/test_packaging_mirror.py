import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackagingMirrorTests(unittest.TestCase):
    def test_canonical_runtime_modules_are_available_for_packaging(self):
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
                self.assertTrue((ROOT / name).is_file())

    def test_package_build_uses_canonical_platform_sources(self):
        setup = (ROOT / "setup.py").read_text()
        self.assertIn("copytree(source, target", setup)
        self.assertIn("copy2(Path(__file__).resolve().parent / 'platform_runner.py'", setup)

    def test_cli_distribution_sync_contract(self):
        source = (ROOT / "bin" / "browser-workspace").read_text()
        sync = (ROOT / "tools" / "sync-pypi-package.py").read_text()
        self.assertIn("ROOT=Path(__file__).resolve().parents[1]", source)
        self.assertIn("cli.py", sync)


if __name__ == "__main__":
    unittest.main()
