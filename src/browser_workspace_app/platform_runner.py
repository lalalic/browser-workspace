#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from session_client import request

ROOT = Path(__file__).resolve().parent
PLATFORMS = ROOT / "platforms"


def platform_manifest(platform: str) -> dict:
    platform = platform.strip()
    manifest = PLATFORMS / platform / "manifest.yaml"
    if not manifest.is_file():
        raise FileNotFoundError(f"unknown platform: {platform}")
    data = yaml.safe_load(manifest.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"invalid platform manifest: {platform}")
    return data


def platform_profile(platform: str) -> dict:
    data = platform_manifest(platform)
    keys = (
        "platform", "display_name", "aliases", "implementation_status",
        "media", "fields", "capabilities", "content_mapping", "notes",
    )
    return {key: data[key] for key in keys if key in data}


def _validate_string(name: str, value, spec: dict) -> None:
    if value is None:
        return
    text = str(value)
    minimum = spec.get("min_chars")
    maximum = spec.get("max_chars") or spec.get("max_chars_including_tags")
    if minimum is not None and text and len(text) < int(minimum):
        raise ValueError(f"{name} too short: {len(text)} chars (min {minimum})")
    if maximum is not None and len(text) > int(maximum):
        raise ValueError(f"{name} too long: {len(text)} chars (max {maximum})")


def validate_platform_config(platform: str, action: str, config: dict) -> None:
    if action != "post":
        return
    profile = platform_profile(platform)
    fields = profile.get("fields") or {}
    for name, spec in fields.items():
        if not isinstance(spec, dict) or spec.get("type") == "operation":
            continue
        value = config.get(name)
        if spec.get("required") and (value is None or value == "" or value == []):
            raise ValueError(f"{platform}: missing required field {name}")
        if value is None:
            continue
        kind = spec.get("type")
        if kind == "string":
            _validate_string(name, value, spec)
        elif kind == "string_list":
            values = value if isinstance(value, list) else [x.strip() for x in str(value).split(",") if x.strip()]
            maximum = spec.get("max_count")
            if maximum is not None and len(values) > int(maximum):
                raise ValueError(f"{name} has {len(values)} items (max {maximum})")
            each = spec.get("max_chars_each")
            if each is not None:
                for item in values:
                    if len(str(item)) > int(each):
                        raise ValueError(f"{name} item too long: {item!r} (max {each})")
            total = spec.get("max_total_chars")
            if total is not None and sum(len(str(x)) for x in values) > int(total):
                raise ValueError(f"{name} total length exceeds {total}")
        elif kind == "enum":
            values = spec.get("values") or []
            if value not in values:
                raise ValueError(f"{name} must be one of: {', '.join(map(str, values))}")

    images_spec = (profile.get("media") or {}).get("images") or {}
    images = config.get("images") or []
    maximum = images_spec.get("max_count")
    if maximum is not None and len(images) > int(maximum):
        raise ValueError(f"images has {len(images)} items (max {maximum})")


def declared_actions(platform: str) -> dict[str, Path]:
    platform = platform.strip()
    manifest = PLATFORMS / platform / "manifest.yaml"
    if not manifest.is_file():
        raise FileNotFoundError(f"unknown platform: {platform}")

    text = manifest.read_text()
    match = re.search(
        r"^actions:\s*\n(?P<body>(?:^[ \t]+.*\n?)*)",
        text,
        flags=re.MULTILINE,
    )
    if not match:
        raise ValueError(f"{platform}/manifest.yaml has no actions block")

    actions: dict[str, Path] = {}
    for line in match.group("body").splitlines():
        entry = re.match(r'^\s{2}([\w-]+):\s*(.+?)\s*$', line)
        if not entry:
            continue
        name, relative = entry.groups()
        if len(relative) >= 2 and relative[0] == relative[-1] and relative[0] in {"\"", "'"}:
            relative = relative[1:-1]
        # Actions are simple relative file paths; comments and nested mappings are not runnable actions.
        if not relative or relative.startswith(("#", "{", "[")) or " #" in relative:
            continue
        path = PLATFORMS / platform / relative
        if not path.is_file():
            raise FileNotFoundError(f"declared platform action missing: {platform}/{name} -> {relative}")
        actions[name] = path
    if not actions:
        raise ValueError(f"{platform}/manifest.yaml declares no runnable actions")
    return actions


def action_path(platform: str, action: str) -> Path:
    platform = platform.strip()
    action = action.strip().replace("_", "-")
    actions = declared_actions(platform)
    if action not in actions:
        raise FileNotFoundError(
            f"unknown platform action {platform}/{action}; "
            f"available: {', '.join(sorted(actions)) or 'none'}"
        )
    return actions[action]


def prepare_action(path: Path, config_path: Path | None = None) -> str:
    source = path.read_text()
    source = "import sys\nsys.path.insert(0, " + repr(str(path.parent.resolve())) + ")\n" + source
    if "__CFG_PATH__" in source:
        if config_path is None:
            raise ValueError(f"{path.parent.parent.name}/{path.stem}: --config is required")
        escaped = str(config_path.resolve()).replace("\\", "\\\\").replace('"', '\\"')
        source = source.replace("__CFG_PATH__", escaped)
    return source


def run_platform_action(
    platform: str,
    action: str,
    *,
    config_path: str | None = None,
    url: str | None = None,
    session_id: str | None = None,
    auto_session: bool = False,
) -> dict:
    path = action_path(platform, action)
    config_file = Path(config_path) if config_path else None
    if config_file is not None:
        config = json.loads(config_file.read_text())
        if not isinstance(config, dict):
            raise ValueError("platform config must be a JSON object")
        validate_platform_config(platform, action, config)
    code = prepare_action(path, config_file)

    if not session_id and not auto_session:
        raise ValueError(
            "platform run requires session_id; orchestrators should use: "
            "session start -> platform run --session-id SESSION_ID -> self-heal in the same session -> session stop. "
            "Use auto_session=True only for a one-shot run without orchestrator self-heal."
        )
    if session_id and auto_session:
        raise ValueError("session_id and auto_session are mutually exclusive")

    owned_session = bool(auto_session)
    started = request({"op": "start", "workspace": None, "url": url}) if owned_session else {"session_id": session_id, "workspace_supported": None}
    sid = started["session_id"]
    result = None
    cleanup = None
    try:
        raw_result = request({"op": "exec", "session_id": sid, "code": code})
        result = {k: v for k, v in raw_result.items() if k not in {"session_id", "workspace", "target_id"}}
        output = {
            "platform": platform,
            "action": action,
            "workspace_supported": started.get("workspace_supported"),
            "session_mode": "auto_session_no_self_heal" if owned_session else "caller_owned_self_heal_capable",
            "self_heal_capable": not owned_session,
            "result": result,
        }
        if started.get("warning"):
            output["warning"] = started["warning"]
            output["extension_url"] = started.get("extension_url")
        return output
    finally:
        if owned_session:
            try:
                raw_cleanup = request({"op": "stop", "session_id": sid})
                cleanup = {k: v for k, v in raw_cleanup.items() if k not in {"session_id", "workspace", "target_id"}}
            except Exception as exc:
                cleanup = {"release_error": f"{type(exc).__name__}: {exc}"}
        else:
            cleanup = {"caller_owned_session": True}
        if result is not None:
            result["cleanup"] = cleanup
