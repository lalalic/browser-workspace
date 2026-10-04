import importlib.util
import json
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'managed_chrome.py'

def load_module(monkeypatch, tmp_path):
    monkeypatch.setenv('BROWSER_WORKSPACE_CONFIG_DIR', str(tmp_path/'config'))
    monkeypatch.setenv('BROWSER_WORKSPACE_RUNTIME_DIR', str(tmp_path/'runtime'))
    spec=importlib.util.spec_from_file_location('managed_chrome_under_test', MODULE)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

def test_explicit_cdp_url_is_preserved(monkeypatch,tmp_path):
    monkeypatch.setenv('BU_CDP_URL','http://127.0.0.1:9555')
    m=load_module(monkeypatch,tmp_path)
    assert m.ensure_managed_chrome()=={'mode':'override','endpoint':'http://127.0.0.1:9555'}

def test_choose_port_skips_occupied_candidate(monkeypatch,tmp_path):
    monkeypatch.delenv('BU_CDP_URL',raising=False); monkeypatch.delenv('BU_CDP_WS',raising=False)
    monkeypatch.setenv('BROWSER_WORKSPACE_CDP_PORT','9300'); monkeypatch.setenv('BROWSER_WORKSPACE_CDP_PORT_CANDIDATES','3')
    m=load_module(monkeypatch,tmp_path); monkeypatch.setattr(m,'_port_available',lambda p:p==9301)
    assert m._choose_port()==9301

def test_reuses_recorded_managed_browser(monkeypatch,tmp_path):
    monkeypatch.delenv('BU_CDP_URL',raising=False); monkeypatch.delenv('BU_CDP_WS',raising=False)
    m=load_module(monkeypatch,tmp_path); m.STATE_FILE.parent.mkdir(parents=True,exist_ok=True)
    m.STATE_FILE.write_text(json.dumps({'pid':123,'port':9444,'profile_dir':'/tmp/p'}))
    monkeypatch.setattr(m,'_pid_alive',lambda pid:pid==123); monkeypatch.setattr(m,'_endpoint_live',lambda port,timeout=.5:port==9444)
    r=m.ensure_managed_chrome(); assert r['reused'] is True and r['endpoint']=='http://127.0.0.1:9444'
