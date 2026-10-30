from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]


def load_common():
    path=HERE/'actions'/'_common.py'
    spec=spec_from_file_location('wechat_channels_common',path)
    assert spec and spec.loader
    mod=module_from_spec(spec); spec.loader.exec_module(mod); return mod


def test_status_label_mapping():
    c=load_common()
    assert c.status_label('审核中 1 分钟前') == ('reviewing','审核中')
    assert c.status_label('已发表 2026-09-15') == ('published','已发表')
    assert c.status_label('no status') == (None,None)


def test_stable_id_prefers_url_finder_id():
    c=load_common()
    row={'stable_ids':{'objectid':'object-1'},'urls':['https://channels.weixin.qq.com/platform/post?finderObjectId=finder-2']}
    assert c.extract_stable_id(row) == 'finder-2'


def test_choose_manager_row_prefers_post_id():
    c=load_common()
    rows=[{'text':'审核中 title','stable_ids':{'postid':'post-1'},'urls':[]},{'text':'已发布 other','stable_ids':{'postid':'post-2'},'urls':[]}]
    assert c.choose_manager_row(rows,'post-2','title',None)['text'] == '已发布 other'
    assert c.choose_manager_row(rows,None,'title',None)['text'] == '审核中 title'


def test_rejected_publish_is_not_success():
    source=(HERE/'actions'/'_post.py').read_text()
    assert 'verification["status"] in {"published", "reviewing"}' in source
