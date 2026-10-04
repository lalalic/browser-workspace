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
