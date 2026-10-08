from __future__ import annotations

import contextlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# Chrome identity is machine-global for Browser Workspace. Runtime/config overrides
# may move sockets/caches, but must never create another browser instance.
SINGLETON_ROOT = Path.home() / ".config/browser-workspace"
PROFILE_DIR = SINGLETON_ROOT / "chrome"
STATE_FILE = SINGLETON_ROOT / "managed-chrome.json"
LOCK_FILE = SINGLETON_ROOT / "managed-chrome.lock"
LOG_FILE = SINGLETON_ROOT / "managed-chrome.log"
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
    SINGLETON_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    os.replace(tmp, STATE_FILE)


@contextlib.contextmanager
def _singleton_lock():
    SINGLETON_ROOT.mkdir(parents=True, exist_ok=True)
    handle = open(LOCK_FILE, "a+")
    try:
        if platform.system() == "Windows":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if platform.system() == "Windows":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


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


def _discover_existing_managed_chrome() -> dict | None:
    """Recover the singleton even if its state file was deleted or became stale."""
    if platform.system() == "Windows":
        return None
    try:
        output = subprocess.check_output(["ps", "-axo", "pid=,command="], text=True)
    except Exception:
        return None
    profile_arg = f"--user-data-dir={PROFILE_DIR}"
    for line in output.splitlines():
        if profile_arg not in line:
            continue
        match = re.match(r"\s*(\d+)\s+(.+)", line)
        if not match:
            continue
        pid = int(match.group(1))
        command = match.group(2)
        if "--type=" in command:
            continue
        port_match = re.search(r"--remote-debugging-port=(\d+)", command)
        if not port_match:
            continue
        port = int(port_match.group(1))
        if _pid_alive(pid) and _endpoint_live(port):
            return {
                "pid": pid,
                "port": port,
                "profile_dir": str(PROFILE_DIR),
                "chrome_path": command.split(" --user-data-dir=", 1)[0],
            }
    return None


def _live_singleton() -> dict | None:
    state = _load_state()
    port = state.get("port")
    pid = state.get("pid")
    if isinstance(port, int) and _pid_alive(pid) and _endpoint_live(port):
        return state
    recovered = _discover_existing_managed_chrome()
    if recovered:
        _write_state(recovered)
        return recovered
    return None


def _choose_port() -> int:
    for port in range(DEFAULT_PORT, DEFAULT_PORT + max(1, PORT_CANDIDATES)):
        if _port_available(port):
            return port
    raise RuntimeError(
        f"Browser Workspace could not find a free CDP port in "
        f"{DEFAULT_PORT}..{DEFAULT_PORT + max(1, PORT_CANDIDATES) - 1}"
    )


def _as_result(state: dict, reused: bool) -> dict:
    endpoint = _endpoint(int(state["port"]))
    os.environ["BU_CDP_URL"] = endpoint
    return {**state, "mode": "managed", "endpoint": endpoint, "reused": reused}


def ensure_managed_chrome() -> dict:
    """Return the one machine-wide Browser Workspace Chrome, starting it only if absent."""
    with _singleton_lock():
        # Strong invariant: an existing Browser Workspace Chrome always wins.
        if existing := _live_singleton():
            return _as_result(existing, True)

        # Advanced external endpoint is only considered when no managed singleton exists.
        if os.environ.get("BU_CDP_WS"):
            return {"mode": "override", "endpoint": "BU_CDP_WS"}
        if url := os.environ.get("BU_CDP_URL"):
            return {"mode": "override", "endpoint": url}

        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        port = _choose_port()
        chrome = _chrome_path()
        log = open(LOG_FILE, "ab", buffering=0)
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
                    f"Browser Workspace managed Chrome exited with code {process.returncode}; see {LOG_FILE}"
                )
            if _endpoint_live(port):
                payload = {
                    "pid": process.pid,
                    "port": port,
                    "profile_dir": str(PROFILE_DIR),
                    "chrome_path": chrome,
                }
                _write_state(payload)
                return _as_result(payload, False)
            time.sleep(0.1)
        raise RuntimeError(f"Browser Workspace managed Chrome did not expose CDP on port {port}; see {LOG_FILE}")
