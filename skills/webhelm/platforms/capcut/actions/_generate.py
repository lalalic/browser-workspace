import json

from _capcut_common import select_media_type, select_model


CFG = json.load(open("__CFG_PATH__"))
prompt = CFG.get("prompt", "").strip()
media_type = CFG.get("media_type")
model = CFG.get("model", "").strip()

if not prompt:
    raise ValueError("prompt is required")
if media_type not in {"image", "video"}:
    raise ValueError("media_type must be 'image' or 'video'")
if not model:
    raise ValueError("model is required; run the models action to list choices")
if CFG.get("confirm_generation") is not True:
    raise ValueError("Set confirm_generation to true to submit and potentially consume CapCut credits")

info = page_info()
if "capcut.com" not in info["url"].lower() or "/editor" not in info["url"].lower():
    raise RuntimeError("Open the CapCut editor before running generate")

select_media_type(media_type, js, wait_for_element)
selected_model = select_model(model, js, wait_for_element)
fill_input('[role="textbox"][contenteditable="true"]', prompt)

ready = js(
    "(()=>{const b=document.querySelector('button[aria-label="
    "\"Generate\"]');return !!b&&!b.disabled})()"
)
if not ready:
    raise RuntimeError("CapCut Generate is unavailable; inspect the editor state before retrying")

click('button[aria-label="Generate"]')
print(f"Submitted {media_type} generation with {selected_model}.")
print("Generation completion is not inferred; inspect the CapCut Generated tab.")
print(snapshot())