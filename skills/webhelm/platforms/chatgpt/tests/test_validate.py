"""Validate is a non-sending probe using the shared submission protocol."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_validate_uses_shared_send_switch():
    source = (ROOT / 'actions/_validate.py').read_text()
    assert 'common.target_url(' in source
    assert 'common.prefilled_submit(probe, send=False)' in source
    assert 'common.visible_delivery_error()' in source
    assert 'authentication_required' in source
    assert 'goto_url(' in source
    assert 'send=True' not in source
