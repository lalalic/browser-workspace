#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

from session_client import request

ROOT = Path(__file__).resolve().parent
PLATFORMS = ROOT / "platforms"


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
    for name, relative in re.findall(
        r'^\s{2}([\w-]+):\s*["\']([^"\']+)["\']\s*$',
        match.group("body"),
        flags=re.MULTILINE,
    ):
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
) -> dict:
    path = action_path(platform, action)
    code = prepare_action(path, Path(config_path) if config_path else None)

    started = request({"op": "start", "workspace": None, "url": url})
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
            "result": result,
        }
        if started.get("warning"):
            output["warning"] = started["warning"]
            output["extension_url"] = started.get("extension_url")
        return output
    finally:
        try:
            raw_cleanup = request({"op": "stop", "session_id": sid})
            cleanup = {k: v for k, v in raw_cleanup.items() if k not in {"session_id", "workspace", "target_id"}}
        except Exception as exc:
            cleanup = {"release_error": f"{type(exc).__name__}: {exc}"}
        if result is not None:
            result["cleanup"] = cleanup
