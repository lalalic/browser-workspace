"""Contract tests for conservative, non-mutating platform validation."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_validate_declared_and_reuses_common_readiness():
    manifest = (ROOT / 'manifest.yaml').read_text()
    source = (ROOT / 'actions/_validate.py').read_text()
    assert 'validate: "actions/_validate.py"' in manifest
    assert 'common.composer_selector()' in source
    assert 'common.visible_delivery_error()' in source
    assert 'wait_until_stable(' in source
    assert 'json.dumps(True)' in source
    for error in ('PAGE_NOT_READY', 'COMPOSER_NOT_READY', 'DELIVERY_ERROR'):
        assert error in source
    assert 'submit(' not in source
    assert 'fill_prompt(' not in source
    assert 'AUTH_REQUIRED' not in source
