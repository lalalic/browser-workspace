"""Restrict Browser Harness tab operations to one named Browser Workspace."""

import json as _json
import os as _os
import time as _time

from browser_harness import helpers as _bh

_EXTENSION_ID = _os.environ.get(
    "BH_WORKSPACE_MANAGER_EXTENSION_ID",
    "kgbghhigmbpefppgkocgjgnnnbhjchic",
)
_WORKSPACE_NAME = _os.environ.get(
    "BH_WORKSPACE_NAME",
    _os.environ.get("BH_MDB_GROUP_NAME", "Harness"),
)
_POOL_SIZE = int(_os.environ.get("BH_WORKSPACE_POOL_SIZE", "5"))
_TIMEOUT_SECONDS = 5.0

_original_switch_tab = _bh.switch_tab
_original_current_tab = _bh.current_tab
_original_goto_url = _bh.goto_url


def _worker_target():
    scope = f"chrome-extension://{_EXTENSION_ID}/"
    try:
        _bh.cdp("ServiceWorker.enable")
        _bh.cdp("ServiceWorker.startWorker", scopeURL=scope)
    except Exception as exc:
        raise RuntimeError(
            f"Browser Workspace extension {_EXTENSION_ID} is not installed"
        ) from exc

    deadline = _time.monotonic() + _TIMEOUT_SECONDS
    while _time.monotonic() < deadline:
        for target in _bh.cdp("Target.getTargets").get("targetInfos", []):
            if target.get("type") != "service_worker" or not target.get("url", "").startswith(scope):
                continue
            target_id = target["targetId"]
            try:
                if _bh.js(
                    "typeof globalThis.browserWorkspaceManagerRpc === 'function'",
                    target_id=target_id,
                ):
                    return target_id
            except Exception:
                pass
        _time.sleep(0.05)
    raise RuntimeError("Browser Workspace service worker did not become ready")


def _manager_call(method, args=None):
    request = _json.dumps({"method": method, "args": args or {}})
    response = _bh.js(
        f"globalThis.browserWorkspaceManagerRpc({request})",
        target_id=_worker_target(),
    )
    if not isinstance(response, dict) or not response.get("ok"):
        error = response.get("error", {}) if isinstance(response, dict) else {}
        raise RuntimeError(error.get("message") or "Browser Workspace request failed")
    return response.get("result") or {}


def workspace_create(name, pool_size=5):
    return _manager_call(
        "workspace.create",
        {"name": name, "poolSize": int(pool_size)},
    )


def workspace_list():
    return _manager_call("workspace.list")


def workspace_resize(name, pool_size):
    return _manager_call(
        "workspace.resize",
        {"name": name, "poolSize": int(pool_size)},
    )


def workspace_delete(name, force=False):
    return _manager_call(
        "workspace.delete",
        {"name": name, "force": bool(force)},
    )


def _ensure_workspace():
    return _manager_call(
        "workspace.ensure",
        {"name": _WORKSPACE_NAME, "poolSize": _POOL_SIZE},
    )


def workspace_status():
    return _ensure_workspace()


def _target_id(target):
    if isinstance(target, dict):
        return target.get("targetId") or target.get("target_id")
    return target


def _page_targets():
    return [
        target
        for target in _bh.cdp("Target.getTargets").get("targetInfos", [])
        if target.get("type") == "page"
    ]


def _map_workspace_tabs(chrome_tabs, target_infos):
    """Map Chrome tabs to CDP targets and drop every ambiguous match."""
    remaining = {
        target.get("targetId"): target
        for target in target_infos
        if target.get("targetId")
    }
    mapped = []
    for tab in chrome_tabs:
        url = tab.get("url") or ""
        candidates = [
            target
            for target in remaining.values()
            if (target.get("url") or "") == url
        ]
        if len(candidates) > 1:
            title = tab.get("title") or ""
            candidates = [
                target
                for target in candidates
                if (target.get("title") or "") == title
            ]
        if len(candidates) != 1:
            continue
        target = candidates[0]
        target_id = target["targetId"]
        remaining.pop(target_id, None)
        mapped.append(
            {
                "targetId": target_id,
                "target_id": target_id,
                "tabId": tab.get("tabId"),
                "groupId": tab.get("groupId"),
                "title": target.get("title", ""),
                "url": target.get("url", ""),
            }
        )
    return mapped


def _workspace_tabs():
    status = workspace_status()
    return _map_workspace_tabs(status.get("tabs", []), _page_targets())


def _workspace_tab_for_target(target):
    wanted = _target_id(target)
    matches = [tab for tab in _workspace_tabs() if tab["targetId"] == wanted]
    if len(matches) != 1:
        raise RuntimeError(
            f"Refusing Browser Harness access outside workspace {_WORKSPACE_NAME!r}"
        )
    return matches[0]


def list_tabs(include_chrome=True):
    tabs = _workspace_tabs()
    if include_chrome:
        return tabs
    internal = (
        "chrome://",
        "chrome-untrusted://",
        "devtools://",
        "chrome-extension://",
        "about:",
    )
    return [tab for tab in tabs if not tab["url"].startswith(internal)]


def current_tab():
    return _workspace_tab_for_target(_original_current_tab())


def activate_tab(target):
    raise RuntimeError("Workspace mode refuses visible tab activation")


def switch_tab(target, activate=False):
    if activate:
        raise RuntimeError("Workspace mode refuses visible tab activation")
    tab = _workspace_tab_for_target(target)
    return _original_switch_tab(tab["targetId"], activate=False)


def new_tab(url="about:blank"):
    if not (url.startswith("http://") or url.startswith("https://")):
        raise RuntimeError("Workspace new_tab requires an http(s) URL")
    opened = _manager_call(
        "workspace.acquire",
        {"name": _WORKSPACE_NAME, "url": url},
    )
    wanted_tab_id = opened.get("tabId")
    deadline = _time.monotonic() + _TIMEOUT_SECONDS
    while _time.monotonic() < deadline:
        for tab in _workspace_tabs():
            if tab.get("tabId") == wanted_tab_id:
                _original_switch_tab(tab["targetId"], activate=False)
                return tab["targetId"]
        _time.sleep(0.05)

    try:
        _manager_call(
            "workspace.release",
            {"name": _WORKSPACE_NAME, "tabId": wanted_tab_id},
        )
    except Exception:
        pass
    raise RuntimeError("Workspace tab could not be uniquely mapped to a CDP target")


def close_tab(target=None):
    tab = current_tab() if target is None else _workspace_tab_for_target(target)
    return _manager_call(
        "workspace.release",
        {"name": _WORKSPACE_NAME, "tabId": tab["tabId"]},
    )


def ensure_real_tab():
    try:
        current = current_tab()
        if current["url"] and not current["url"].startswith(
            (
                "chrome://",
                "chrome-untrusted://",
                "devtools://",
                "chrome-extension://",
                "about:",
            )
        ):
            return current
    except RuntimeError:
        pass

    tabs = list_tabs(include_chrome=False)
    if not tabs:
        return None
    switch_tab(tabs[0])
    return tabs[0]


def goto_url(url):
    current_tab()
    return _original_goto_url(url)
