"""Restrict Browser Harness tab operations to one named Browser Workspace.

Any function that rewrites a ``browser_harness.helpers`` function must keep the
upstream function's input signature exactly.  Browser Workspace may change
behavior, but it must remain a drop-in helper layer.
"""

import contextvars as _contextvars
import json as _json
import os as _os
import time as _time

from browser_harness import helpers as _bh

_EXTENSION_ID = _os.environ.get(
    "BH_WORKSPACE_MANAGER_EXTENSION_ID",
    "kgbghhigmbpefppgkocgjgnnnbhjchic",
)
_DEFAULT_WORKSPACE_NAME = _os.environ.get(
    "BH_WORKSPACE_NAME",
    _os.environ.get("BH_MDB_GROUP_NAME", "Harness"),
)
_WORKSPACE_NAME = _DEFAULT_WORKSPACE_NAME
_WORKSPACE_CONTEXT = _contextvars.ContextVar("browser_workspace_name", default=None)

def workspace_name():
    return _WORKSPACE_CONTEXT.get() or _WORKSPACE_NAME

def workspace_set_name(name):
    if not isinstance(name, str) or not name.strip():
        raise ValueError("workspace name must be a non-empty string")
    return _WORKSPACE_CONTEXT.set(name.strip())

def workspace_reset_name(token):
    _WORKSPACE_CONTEXT.reset(token)
_POOL_SIZE = int(_os.environ.get("BH_WORKSPACE_POOL_SIZE", "5"))
_TIMEOUT_SECONDS = 5.0

_original_switch_tab = _bh.switch_tab
_original_current_tab = _bh.current_tab
_original_goto_url = _bh.goto_url

_tab_to_target = {}
_target_to_tab = {}


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
        {"name": workspace_name(), "poolSize": _POOL_SIZE},
    )


def workspace_status():
    return _ensure_workspace()


def workspace_capacity():
    """Return routing-friendly capacity facts derived from workspace_status()."""
    try:
        status = workspace_status()
    except Exception as exc:
        return {
            "name": workspace_name(),
            "poolSize": None,
            "maxCapacity": None,
            "physicalTabs": None,
            "idle": None,
            "leased": None,
            "available": None,
            "error": str(exc),
        }

    idle_ids = status.get("idleTabIds")
    leased_ids = status.get("leasedTabIds")
    if not status.get("initialized") or not isinstance(idle_ids, list) or not isinstance(leased_ids, list):
        return {
            "name": status.get("name", workspace_name()),
            "poolSize": status.get("poolSize"),
            "maxCapacity": status.get("maxCapacity", status.get("poolSize")),
            "physicalTabs": None,
            "idle": None,
            "leased": None,
            "available": None,
        }

    idle = len(idle_ids)
    leased = len(leased_ids)
    max_capacity = status.get("maxCapacity", status.get("poolSize"))
    physical_tabs = status.get("physicalTabs")
    if physical_tabs is None:
        physical_tabs = idle + leased
    available = max(0, max_capacity - leased) if isinstance(max_capacity, int) else None
    return {
        "name": status.get("name", workspace_name()),
        "poolSize": status.get("poolSize"),
        "maxCapacity": max_capacity,
        "physicalTabs": physical_tabs,
        "idle": idle,
        "leased": leased,
        "available": available,
    }


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


def _remember_mapping(tab_id, target_id):
    old_target = _tab_to_target.get(tab_id)
    if old_target and old_target != target_id:
        _target_to_tab.pop(old_target, None)
    old_tab = _target_to_tab.get(target_id)
    if old_tab is not None and old_tab != tab_id:
        _tab_to_target.pop(old_tab, None)
    _tab_to_target[tab_id] = target_id
    _target_to_tab[target_id] = tab_id


def _forget_mapping(tab_id=None, target_id=None):
    if tab_id is not None:
        known_target = _tab_to_target.pop(tab_id, None)
        if known_target:
            _target_to_tab.pop(known_target, None)
    if target_id is not None:
        known_tab = _target_to_tab.pop(target_id, None)
        if known_tab is not None:
            _tab_to_target.pop(known_tab, None)



def _map_workspace_tabs(chrome_tabs, target_infos):
    """Map Chrome tabs to CDP targets, preferring mappings learned at acquire."""
    remaining = {
        target.get("targetId"): target
        for target in target_infos
        if target.get("targetId")
    }
    mapped = []

    for tab in chrome_tabs:
        tab_id = tab.get("tabId")
        target_id = _tab_to_target.get(tab_id)
        target = remaining.get(target_id)
        if target is None:
            if target_id:
                _forget_mapping(tab_id=tab_id)
            continue
        remaining.pop(target_id, None)
        mapped.append(
            {
                "targetId": target_id,
                "target_id": target_id,
                "tabId": tab_id,
                "groupId": tab.get("groupId"),
                "title": target.get("title", ""),
                "url": target.get("url", ""),
            }
        )

    mapped_tab_ids = {tab["tabId"] for tab in mapped}
    for tab in chrome_tabs:
        if tab.get("tabId") in mapped_tab_ids:
            continue
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
        _remember_mapping(tab.get("tabId"), target_id)
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
            f"Refusing Browser Harness access outside workspace {workspace_name()!r}"
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
    if not (
        url == "about:blank"
        or url.startswith("http://")
        or url.startswith("https://")
        or url.startswith("chrome-extension://")
    ):
        raise RuntimeError(
            "Workspace new_tab requires an http(s) or chrome-extension URL"
        )
    opened = _manager_call(
        "workspace.acquireIdentity",
        {"name": workspace_name()},
    )
    wanted_tab_id = opened.get("tabId")
    identity_title = opened.get("identityTitle") or f"__BW_TAB_{wanted_tab_id}__"
    deadline = _time.monotonic() + _TIMEOUT_SECONDS
    while _time.monotonic() < deadline:
        candidates = [
            target
            for target in _page_targets()
            if (target.get("title") or "").removeprefix("🐴 ") == identity_title
        ]
        if len(candidates) == 1:
            target_id = candidates[0]["targetId"]
            _remember_mapping(wanted_tab_id, target_id)
            _original_switch_tab(target_id, activate=False)
            _original_goto_url(url)
            return target_id
        _time.sleep(0.05)

    try:
        _manager_call(
            "workspace.release",
            {"name": workspace_name(), "tabId": wanted_tab_id},
        )
    except Exception:
        pass
    raise RuntimeError("Workspace tab could not be uniquely mapped to a CDP target")


def close_tab(target=None):
    tab = current_tab() if target is None else _workspace_tab_for_target(target)
    result = _manager_call(
        "workspace.release",
        {"name": workspace_name(), "tabId": tab["tabId"]},
    )
    _forget_mapping(tab_id=tab["tabId"])
    return result


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

# Snapshot role selection is adapted from vercel-labs/agent-browser's
# accessibility snapshot design (Apache-2.0), while Browser Workspace keeps a
# deliberately simpler ref contract: refs are written to the live DOM as
# data-ref attributes instead of stored in a separate ref registry.
_SNAPSHOT_INTERACTIVE_ROLES = {
    "button", "link", "textbox", "checkbox", "radio", "combobox", "listbox",
    "menuitem", "menuitemcheckbox", "menuitemradio", "option", "searchbox",
    "slider", "spinbutton", "switch", "tab", "treeitem",
}
_SNAPSHOT_CONTENT_ROLES = {
    "heading", "cell", "gridcell", "columnheader", "rowheader", "listitem",
    "article", "region", "main", "navigation",
}


def _snapshot_ax_value(node, key, default=None):
    value = node.get(key)
    if isinstance(value, dict):
        return value.get("value", default)
    return default


def _snapshot_prop(node, name):
    for prop in node.get("properties", []) or []:
        if prop.get("name") == name:
            value = prop.get("value")
            if isinstance(value, dict):
                return value.get("value")
    return None


def _snapshot_clean_name(value):
    if value is None:
        return ""
    return " ".join(str(value).replace("\u00a0", " ").split())


def _snapshot_session(target_id=None):
    if not target_id:
        return None
    return _bh.cdp("Target.attachToTarget", targetId=target_id, flatten=True)["sessionId"]


def _snapshot_eval(expression, session_id=None):
    result = _bh.cdp(
        "Runtime.evaluate",
        session_id=session_id,
        expression=expression,
        returnByValue=True,
        awaitPromise=False,
    )
    details = result.get("exceptionDetails")
    if details:
        raise RuntimeError(details.get("text") or "snapshot JavaScript failed")
    return (result.get("result") or {}).get("value")


def _snapshot_set_ref(backend_node_id, ref_id, session_id=None):
    resolved = _bh.cdp(
        "DOM.resolveNode",
        session_id=session_id,
        backendNodeId=int(backend_node_id),
        objectGroup="browser-workspace-snapshot",
    )
    object_id = (resolved.get("object") or {}).get("objectId")
    if not object_id:
        return False
    result = _bh.cdp(
        "Runtime.callFunctionOn",
        session_id=session_id,
        objectId=object_id,
        functionDeclaration="function(ref){this.setAttribute('data-ref', ref); return true;}",
        arguments=[{"value": ref_id}],
        returnByValue=True,
    )
    return bool(((result.get("result") or {}).get("value")))


def _snapshot_line(role, name, ref_id, node=None, extra=None):
    attrs = [f"ref={ref_id}"]
    if node:
        level = _snapshot_prop(node, "level")
        checked = _snapshot_prop(node, "checked")
        expanded = _snapshot_prop(node, "expanded")
        selected = _snapshot_prop(node, "selected")
        disabled = _snapshot_prop(node, "disabled")
        required = _snapshot_prop(node, "required")
        value = _snapshot_prop(node, "value")
        if level is not None:
            attrs.append(f"level={level}")
        if checked is not None:
            attrs.append(f"checked={str(checked).lower()}")
        if expanded is not None:
            attrs.append(f"expanded={str(expanded).lower()}")
        if selected is not None:
            attrs.append(f"selected={str(selected).lower()}")
        if disabled:
            attrs.append("disabled=true")
        if required:
            attrs.append("required=true")
        if value not in (None, ""):
            attrs.append(f"value={_snapshot_clean_name(value)!r}")
    if extra:
        attrs.extend(extra)
    label = f' "{name}"' if name else ""
    return f"- {role}{label} [{', '.join(attrs)}]"


def snapshot(interactive_only=True, target_id=None):
    """Return a compact accessibility snapshot and annotate live elements with data-ref.

    The selection/format follows the useful parts of agent-browser's snapshot
    approach, but refs are deliberately DOM-native: each returned ref is written
    as ``data-ref=\"eN\"`` on the corresponding live element. Interact with the
    result using normal Browser Harness CSS-selector helpers, e.g.
    ``click('[data-ref=\"e3\"]')`` or ``fill_input('[data-ref=\"e4\"]', 'text')``.

    Re-run snapshot after navigation or major DOM changes; a new snapshot clears
    and rewrites the page's data-ref attributes.
    """
    session_id = _snapshot_session(target_id)
    _bh.cdp("DOM.enable", session_id=session_id)
    _bh.cdp("Accessibility.enable", session_id=session_id)
    _snapshot_eval(
        "document.querySelectorAll('[data-ref]').forEach(e=>e.removeAttribute('data-ref')); true",
        session_id=session_id,
    )

    ax = _bh.cdp("Accessibility.getFullAXTree", session_id=session_id)
    nodes = ax.get("nodes", []) or []
    lines = []
    next_ref = 1

    for node in nodes:
        role = _snapshot_clean_name(_snapshot_ax_value(node, "role", ""))
        name = _snapshot_clean_name(_snapshot_ax_value(node, "name", ""))
        backend_node_id = node.get("backendDOMNodeId")
        if not backend_node_id:
            continue
        should_include = role in _SNAPSHOT_INTERACTIVE_ROLES
        if not interactive_only and role in _SNAPSHOT_CONTENT_ROLES and name:
            should_include = True
        if not should_include:
            continue
        ref_id = f"e{next_ref}"
        try:
            if not _snapshot_set_ref(backend_node_id, ref_id, session_id=session_id):
                continue
        except Exception:
            continue
        lines.append(_snapshot_line(role or "element", name, ref_id, node=node))
        next_ref += 1

    # Modern apps often use div/span elements with pointer handlers instead of
    # semantic controls. agent-browser explicitly promotes those too. We do the
    # same directly in the DOM, skipping elements already tagged through AX.
    cursor_script = r"""
(() => {
  const out = [];
  const semanticTags = new Set(['a','button','input','select','textarea','details','summary']);
  const semanticRoles = new Set(['button','link','textbox','checkbox','radio','combobox','listbox','menuitem','menuitemcheckbox','menuitemradio','option','searchbox','slider','spinbutton','switch','tab','treeitem']);
  for (const el of document.body ? document.body.querySelectorAll('*') : []) {
    if (el.hasAttribute('data-ref')) continue;
    if (el.closest('[hidden],[aria-hidden="true"]')) continue;
    const tag = el.tagName.toLowerCase();
    if (semanticTags.has(tag)) continue;
    const role = (el.getAttribute('role') || '').toLowerCase();
    if (semanticRoles.has(role)) continue;
    const style = getComputedStyle(el);
    const pointer = style.cursor === 'pointer';
    const onclick = el.hasAttribute('onclick') || el.onclick !== null;
    const tabindex = el.getAttribute('tabindex');
    const focusable = tabindex !== null && tabindex !== '-1';
    const ce = el.getAttribute('contenteditable');
    const editable = ce === '' || ce === 'true';
    if (!pointer && !onclick && !focusable && !editable) continue;
    if (pointer && !onclick && !focusable && !editable && el.parentElement && getComputedStyle(el.parentElement).cursor === 'pointer') continue;
    const rect = el.getBoundingClientRect();
    if (!rect.width || !rect.height) continue;
    out.push({
      element: el,
      role: role || (editable ? 'textbox' : 'clickable'),
      name: (el.getAttribute('aria-label') || el.getAttribute('title') || el.textContent || '').trim().replace(/\s+/g,' ').slice(0,160)
    });
  }
  return out.map(x => ({role:x.role,name:x.name}));
})()
"""
    cursor_items = _snapshot_eval(cursor_script, session_id=session_id) or []
    # The returned values intentionally omit object handles. Assign refs in one
    # second DOM pass by the same deterministic filter/order.
    if cursor_items:
        assignment = _snapshot_eval(
            f"""
(() => {{
  let n = {next_ref};
  const out = [];
  const semanticTags = new Set(['a','button','input','select','textarea','details','summary']);
  const semanticRoles = new Set(['button','link','textbox','checkbox','radio','combobox','listbox','menuitem','menuitemcheckbox','menuitemradio','option','searchbox','slider','spinbutton','switch','tab','treeitem']);
  for (const el of document.body ? document.body.querySelectorAll('*') : []) {{
    if (el.hasAttribute('data-ref')) continue;
    if (el.closest('[hidden],[aria-hidden=\"true\"]')) continue;
    const tag = el.tagName.toLowerCase();
    if (semanticTags.has(tag)) continue;
    const role = (el.getAttribute('role') || '').toLowerCase();
    if (semanticRoles.has(role)) continue;
    const style = getComputedStyle(el);
    const pointer = style.cursor === 'pointer';
    const onclick = el.hasAttribute('onclick') || el.onclick !== null;
    const tabindex = el.getAttribute('tabindex');
    const focusable = tabindex !== null && tabindex !== '-1';
    const ce = el.getAttribute('contenteditable');
    const editable = ce === '' || ce === 'true';
    if (!pointer && !onclick && !focusable && !editable) continue;
    if (pointer && !onclick && !focusable && !editable && el.parentElement && getComputedStyle(el.parentElement).cursor === 'pointer') continue;
    const rect = el.getBoundingClientRect();
    if (!rect.width || !rect.height) continue;
    const ref = 'e' + n++;
    el.setAttribute('data-ref', ref);
    out.push({{ref, role: role || (editable ? 'textbox' : 'clickable'), name:(el.getAttribute('aria-label') || el.getAttribute('title') || el.textContent || '').trim().replace(/\\s+/g,' ').slice(0,160)}});
  }}
  return out;
}})()
""",
            session_id=session_id,
        ) or []
        for item in assignment:
            lines.append(_snapshot_line(item.get("role") or "clickable", _snapshot_clean_name(item.get("name")), item.get("ref")))

    info = _bh.page_info() if target_id is None else None
    header = []
    if info and not info.get("dialog"):
        header.append(f"Page: {info.get('title','')}")
        header.append(f"URL: {info.get('url','')}")
    return "\n".join(header + ([""] if header and lines else []) + lines)



def click(selector, target_id=None):
    """Click a CSS selector; snapshot refs are used as [data-ref="eN"]."""
    selector_json = _json.dumps(selector)
    ok = _bh.js(
        f"(()=>{{const e=document.querySelector({selector_json});if(!e)return false;"
        "e.scrollIntoView({block:'center',inline:'center'});e.click();return true;})()",
        target_id=target_id,
    )
    if not ok:
        raise RuntimeError(f"click: element not found: {selector!r}")
    return True
