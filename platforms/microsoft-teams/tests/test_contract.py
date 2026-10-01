from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = (ROOT / "runner" / "_meeting.py").read_text()
SKILL = (ROOT / "SKILL.md").read_text()
MANIFEST = (ROOT / "manifest.yaml").read_text()


def test_canonical_instant_meeting_path():
    assert "Calendar -> Meet now -> Start meeting (when shown) -> pre-join -> Join now" in SKILL
    assert "Start an instant Teams meeting." in RUNNER
    assert "#prejoin-join-button" in RUNNER
    assert "Start meeting" in RUNNER
    assert "#call-duration-custom" in RUNNER


def test_runner_uses_browser_harness_workspace_path():
    assert "new_tab(TEAMS_URL)" in RUNNER
    assert "websocket" not in RUNNER.lower()


def test_manifest_declares_side_effects():
    assert "instant-meeting" in MANIFEST
    assert "real Teams meeting" in MANIFEST
