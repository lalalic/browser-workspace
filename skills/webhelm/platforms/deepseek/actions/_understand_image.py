import json
from pathlib import Path
import _lifecycle_common as lifecycle

config_path = __OPTIONAL_CONFIG_PATH__
cfg = json.loads(Path(config_path).read_text(encoding="utf-8")) if config_path else {}
if not cfg.get("resume"):
    if "image" not in cfg:
        raise ValueError("image must be an existing absolute local file path")
    prompt = cfg.get("prompt", "Describe this image accurately, including visible text and important visual details. Do not guess details you cannot see.")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")
    cfg = {**cfg, "message": prompt}

result = lifecycle.run({**cfg, "wait": True}, "new-thread", globals())
result["url"] = result["thread_url"]
if cfg.get("screenshot_path"):
    result["screenshot"] = capture_screenshot(str(Path(cfg["screenshot_path"]).expanduser()))
print(json.dumps(result), flush=True)