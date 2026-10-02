import pytest
import platform_runner


def test_platform_profile_owns_publish_contract():
    xhs = platform_runner.platform_profile('xhs')
    assert xhs['fields']['title']['max_chars'] == 20
    assert xhs['media']['images']['max_count'] == 18
    assert xhs['capabilities']['read_comments'] is True
    youtube = platform_runner.platform_profile('youtube')
    assert youtube['fields']['title']['max_chars'] == 100
    assert youtube['fields']['visibility']['default'] == 'PRIVATE'


def test_post_validation_uses_manifest_limits():
    platform_runner.validate_platform_config('xhs', 'post', {'title':'ok','body':'body','tags':['a'],'images':['/tmp/a.jpg']})
    with pytest.raises(ValueError, match='title too long'):
        platform_runner.validate_platform_config('xhs', 'post', {'title':'x'*21,'body':'body','tags':[],'images':['/tmp/a.jpg']})
    with pytest.raises(ValueError, match='images has 19 items'):
        platform_runner.validate_platform_config('xhs', 'post', {'title':'ok','body':'body','tags':[],'images':[str(i) for i in range(19)]})

def test_chatgpt_temporary_submit_is_platform_owned(tmp_path):
    actions = platform_runner.declared_actions('chatgpt')
    assert 'temporary-submit' in actions
    config = tmp_path / 'config.json'
    config.write_text('{"prompt":"hello","file":[],"close_policy":"never"}')
    source = platform_runner.prepare_action(actions['temporary-submit'], config)
    assert 'Temporary Chat' in source
    assert '__CFG_PATH__' not in source
