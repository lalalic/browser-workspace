from pathlib import Path


HERE = Path(__file__).resolve().parents[1]


def test_actions_do_not_use_page_info_as_tab_url_authority():
    for name in ("_post.py", "_manage.py"):
        source = (HERE / "actions" / name).read_text()
        assert 'page_info()["url"]' not in source


def test_actions_use_current_tab_url_for_navigation_identity():
    post = (HERE / "actions" / "_post.py").read_text()
    manage = (HERE / "actions" / "_manage.py").read_text()
    assert '(current_tab().get("url") or "") != url' in post
    assert '(current_tab().get("url") or "") != url' in manage


def test_video_readiness_uses_editor_state_not_preview():
    source=(HERE/'actions'/'_post.py').read_text()
    assert '上传中' in source
    assert '重新上传' in source
    assert 'Upload processed and editor-ready!' in source

def test_collection_and_receipt_contracts_are_present():
    source=(HERE/'actions'/'_post.py').read_text()
    manifest=(HERE/'manifest.yaml').read_text()
    assert 'choose_collection' in source
    assert 'creator_manager_receipt' in source
    assert 'XHS_RECEIPT' in source
    assert 'duplicate_count' in source
    assert 'series_or_collection: true' in manifest
    assert 'collection:' in manifest
