import importlib.util
import json
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "managed_chrome.py"


def load_module(monkeypatch, tmp_path):
    monkeypatch.delenv("BU_CDP_URL", raising=False)
    monkeypatch.delenv("BU_CDP_WS", raising=False)
    spec = importlib.util.spec_from_file_location("managed_chrome_under_test", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Unit tests never launch or touch the real machine singleton.
    module.SINGLETON_ROOT = tmp_path / "singleton"
    module.PROFILE_DIR = module.SINGLETON_ROOT / "chrome"
    module.STATE_FILE = module.SINGLETON_ROOT / "managed-chrome.json"
    module.LOCK_FILE = module.SINGLETON_ROOT / "managed-chrome.lock"
    module.LOG_FILE = module.SINGLETON_ROOT / "managed-chrome.log"
    return module


def test_existing_singleton_wins_over_endpoint_override(monkeypatch, tmp_path):
    module = load_module(monkeypatch, tmp_path)
    module.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    module.STATE_FILE.write_text(json.dumps({"pid": 123, "port": 9444, "profile_dir": str(module.PROFILE_DIR)}))
    monkeypatch.setenv("BU_CDP_URL", "http://127.0.0.1:9555")
    monkeypatch.setattr(module, "_pid_alive", lambda pid: pid == 123)
    monkeypatch.setattr(module, "_endpoint_live", lambda port, timeout=0.5: port == 9444)
    result = module.ensure_managed_chrome()
    assert result["endpoint"] == "http://127.0.0.1:9444"
    assert result["reused"] is True


def test_config_and_runtime_overrides_do_not_change_chrome_identity(monkeypatch, tmp_path):
    monkeypatch.setenv("BROWSER_WORKSPACE_CONFIG_DIR", str(tmp_path / "other-config"))
    monkeypatch.setenv("BROWSER_WORKSPACE_RUNTIME_DIR", str(tmp_path / "other-runtime"))
    module = load_module(monkeypatch, tmp_path)
    assert module.PROFILE_DIR.parent == module.SINGLETON_ROOT
    assert module.STATE_FILE.parent == module.SINGLETON_ROOT


def test_choose_port_skips_occupied_candidate(monkeypatch, tmp_path):
    module = load_module(monkeypatch, tmp_path)
    module.DEFAULT_PORT = 9300
    module.PORT_CANDIDATES = 3
    monkeypatch.setattr(module, "_port_available", lambda port: port == 9301)
    assert module._choose_port() == 9301


def test_reuses_recorded_managed_browser(monkeypatch, tmp_path):
    module = load_module(monkeypatch, tmp_path)
    module.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    module.STATE_FILE.write_text(json.dumps({"pid": 123, "port": 9444, "profile_dir": str(module.PROFILE_DIR)}))
    monkeypatch.setattr(module, "_pid_alive", lambda pid: pid == 123)
    monkeypatch.setattr(module, "_endpoint_live", lambda port, timeout=0.5: port == 9444)
    result = module.ensure_managed_chrome()
    assert result["reused"] is True
    assert result["endpoint"] == "http://127.0.0.1:9444"


def test_recovers_existing_process_when_state_is_missing(monkeypatch, tmp_path):
    module = load_module(monkeypatch, tmp_path)
    recovered = {"pid": 321, "port": 9333, "profile_dir": str(module.PROFILE_DIR), "chrome_path": "/Chrome"}
    monkeypatch.setattr(module, "_discover_existing_managed_chrome", lambda: recovered)
    result = module.ensure_managed_chrome()
    assert result["reused"] is True
    assert result["pid"] == 321
    assert json.loads(module.STATE_FILE.read_text())["pid"] == 321
