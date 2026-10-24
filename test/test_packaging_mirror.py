import unittest
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


class PackagingMirrorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run([sys.executable, str(ROOT / "tools/sync-pypi-package.py")], check=True)

    def test_packaged_runtime_is_generated_from_canonical_sources(self):
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
                self.assertEqual((ROOT / name).read_bytes(), (ROOT / "src/browser_workspace_app" / name).read_bytes())

    def test_packaged_cli_and_chatgpt_docs_match_canonical_sources(self):
        cli = (ROOT / "bin/browser-workspace").read_text()
        packaged_cli = cli.replace("ROOT=Path(__file__).resolve().parents[1]", "ROOT=Path(__file__).resolve().parent")
        self.assertEqual(packaged_cli, (ROOT / "src/browser_workspace_app/cli.py").read_text())
        for path in ("README.md", "manifest.yaml", "actions/_new_turn.py"):
            with self.subTest(path=path):
                self.assertEqual(
                    (ROOT / "platforms/chatgpt" / path).read_bytes(),
                    (ROOT / "src/browser_workspace_app/platforms/chatgpt" / path).read_bytes(),
                )

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
