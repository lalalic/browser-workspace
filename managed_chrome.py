from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_ROOT = Path(os.environ.get("BROWSER_WORKSPACE_CONFIG_DIR", Path.home() / ".config/browser-workspace"))
PROFILE_DIR = Path(os.environ.get("BROWSER_WORKSPACE_CHROME_DATA_DIR", CONFIG_ROOT / "chrome"))
RUNTIME_DIR = Path(os.environ.get("BROWSER_WORKSPACE_RUNTIME_DIR", CONFIG_ROOT / "runtime"))
STATE_FILE = RUNTIME_DIR / "managed-chrome.json"
DEFAULT_PORT = int(os.environ.get("BROWSER_WORKSPACE_CDP_PORT", "9222"))
PORT_CANDIDATES = int(os.environ.get("BROWSER_WORKSPACE_CDP_PORT_CANDIDATES", "20"))


def _endpoint(port: int) -> str:
    return f"http://127.0.0.1:{port}"


def _endpoint_live(port: int, timeout: float = 0.5) -> bool:
    try:
        with urllib.request.urlopen(f"{_endpoint(port)}/json/version", timeout=timeout) as response:
            payload = json.loads(response.read())
        return bool(payload.get("webSocketDebuggerUrl"))
    except Exception:
        return False


def _port_available(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError, TypeError):
        return {}


def _write_state(payload: dict) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    os.replace(tmp, STATE_FILE)


def _chrome_path() -> str:
    configured = os.environ.get("BROWSER_WORKSPACE_CHROME_PATH") or os.environ.get("BH_CHROME_PATH")
    if configured:
        return configured
    system = platform.system()
    if system == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    elif system == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        program_files = [Path(os.environ.get("PROGRAMFILES", "")), Path(os.environ.get("PROGRAMFILES(X86)", ""))]
        candidates = [
            str(local / "Google/Chrome/Application/chrome.exe"),
            *(str(p / "Google/Chrome/Application/chrome.exe") for p in program_files if str(p)),
        ]
    else:
        candidates = ["google-chrome-stable", "google-chrome", "chromium", "chromium-browser"]
    for candidate in candidates:
        if os.path.isabs(candidate):
            if Path(candidate).exists():
                return candidate
        elif resolved := shutil.which(candidate):
            return resolved
    raise RuntimeError("Browser Workspace could not find Chrome; set BROWSER_WORKSPACE_CHROME_PATH")


def _choose_port() -> int:
    state = _load_state()
    state_port = state.get("port")
    state_pid = state.get("pid")
    if isinstance(state_port, int) and _pid_alive(state_pid) and _endpoint_live(state_port):
        return state_port
    for port in range(DEFAULT_PORT, DEFAULT_PORT + max(1, PORT_CANDIDATES)):
        if _port_available(port):
            return port
    raise RuntimeError(
        f"Browser Workspace could not find a free CDP port in "
        f"{DEFAULT_PORT}..{DEFAULT_PORT + max(1, PORT_CANDIDATES) - 1}"
    )


def ensure_managed_chrome() -> dict:
    """Ensure Browser Workspace's persistent non-headless Chrome is ready.

    Explicit BU_CDP_URL / BU_CDP_WS remain advanced overrides. Otherwise Browser
    Workspace owns one durable user-data-dir, chooses a local CDP port, starts
    Chrome visibly. Chrome Stable blocks silent unpacked-extension loading, so
    the bundled extension remains an optional enhancement when already installed.
    """
    if os.environ.get("BU_CDP_WS"):
        return {"mode": "override", "endpoint": "BU_CDP_WS"}
    if url := os.environ.get("BU_CDP_URL"):
        return {"mode": "override", "endpoint": url}

    state = _load_state()
    state_port = state.get("port")
    state_pid = state.get("pid")
    if isinstance(state_port, int) and _pid_alive(state_pid) and _endpoint_live(state_port):
        endpoint = _endpoint(state_port)
        os.environ["BU_CDP_URL"] = endpoint
        return {**state, "mode": "managed", "endpoint": endpoint, "reused": True}

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    extension = ROOT / "extension"
    port = _choose_port()
    chrome = _chrome_path()
    log_path = RUNTIME_DIR / "managed-chrome.log"
    log = open(log_path, "ab", buffering=0)
    command = [
        chrome,
        f"--user-data-dir={PROFILE_DIR}",
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank",
    ]
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        start_new_session=True,
        close_fds=True,
    )
    log.close()

    deadline = time.time() + float(os.environ.get("BROWSER_WORKSPACE_CHROME_START_TIMEOUT", "20"))
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"Browser Workspace managed Chrome exited with code {process.returncode}; see {log_path}"
            )
        if _endpoint_live(port):
            endpoint = _endpoint(port)
            payload = {
                "pid": process.pid,
                "port": port,
                "profile_dir": str(PROFILE_DIR),
                "extension_dir": str(extension),
                "extension_auto_load": False,
                "chrome_path": chrome,
            }
            _write_state(payload)
            os.environ["BU_CDP_URL"] = endpoint
            return {**payload, "mode": "managed", "endpoint": endpoint, "reused": False}
        time.sleep(0.1)
    raise RuntimeError(f"Browser Workspace managed Chrome did not expose CDP on port {port}; see {log_path}")
