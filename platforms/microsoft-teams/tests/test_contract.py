from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTION = (ROOT / "actions" / "_meeting.py").read_text()
SKILL = (ROOT / "SKILL.md").read_text()
MANIFEST = (ROOT / "manifest.yaml").read_text()


def test_canonical_instant_meeting_path():
    assert "Calendar -> Meet now -> Start meeting (when shown) -> pre-join -> Join now" in SKILL
    assert "Start an instant Teams meeting." in ACTION
    assert "#prejoin-join-button" in ACTION
    assert "Start meeting" in ACTION
    assert "#call-duration-custom" in ACTION


def test_action_uses_browser_helper_path():
    assert "new_tab(TEAMS_URL)" in ACTION
    assert "websocket" not in ACTION.lower()


def test_manifest_declares_side_effects():
    assert "instant-meeting" in MANIFEST
    assert "real Teams meeting" in MANIFEST
