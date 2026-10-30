import json


def select_media_type(media_type, browser_js, wait_for_element):
    if media_type not in {"image", "video"}:
        raise ValueError("media_type must be 'image' or 'video'")

    mode = media_type.capitalize()
    has_selector = browser_js(
        "(()=>Array.from(document.querySelectorAll('button[aria-label]'))"
        ".some(x=>['Image','Video'].includes((x.getAttribute('aria-label')||'').trim())))()"
    )
    if not has_selector:
        raise RuntimeError("CapCut media mode selector was not found")
    browser_js(
        "(()=>{const b=Array.from(document.querySelectorAll('button[aria-label]'))"
        ".find(x=>['Image','Video'].includes((x.getAttribute('aria-label')||'').trim()));"
        "if(b.getAttribute('aria-expanded')!=='true')b.click();return true})()"
    )
    if not wait_for_element('[role="menuitemradio"]', timeout=5, visible=True):
        raise RuntimeError("CapCut media mode menu did not open")

    selected = browser_js(
        "(()=>{const e=Array.from(document.querySelectorAll('[role=menuitemradio]'))"
        ".find(x=>x.textContent.trim()==="
        + json.dumps(mode)
        + ");if(!e)return false;e.click();return true})()"
    )
    if not selected:
        raise RuntimeError(f"CapCut {mode} mode option was not found")
    if not wait_for_element(f'button[aria-label*="{mode}"]', timeout=5, visible=True):
        raise RuntimeError(f"CapCut did not switch to {mode} mode")


def set_model_picker_open(is_open, browser_js, wait_for_element):
    button_found = browser_js(
        "(()=>{const b=Array.from(document.querySelectorAll('button[aria-expanded]'))"
        ".find(x=>/^(Seedance|Seedream|GPT Image|Nano Banana)/i.test("
        "(x.getAttribute('aria-label')||x.innerText).trim()));return !!b})()"
    )
    if not button_found:
        raise RuntimeError("CapCut model picker was not found")
    browser_js(
        "(()=>{const b=Array.from(document.querySelectorAll('button[aria-expanded]'))"
        ".find(x=>/^(Seedance|Seedream|GPT Image|Nano Banana)/i.test("
        "(x.getAttribute('aria-label')||x.innerText).trim()));"
        "if(b&&(b.getAttribute('aria-expanded')==='true')!=="
        + json.dumps(is_open)
        + ")b.click();return true})()"
    )
    if is_open and not wait_for_element('[role="listbox"][aria-label="Model"]', timeout=5, visible=True):
        raise RuntimeError("CapCut model list did not open")


def model_options(browser_js):
    options = browser_js(
        "(()=>{const l=document.querySelector('[role=listbox][aria-label="
        "\"Model\"]');if(!l)return [];return Array.from(l.querySelectorAll('[role=option]'))"
        ".map(e=>({name:(e.querySelector('[title]')||e).getAttribute('title')||"
        "e.innerText.trim().split('\\n')[0],key:e.getAttribute('data-model-key')}))})()"
    )
    return options or []


def available_models(media_type, browser_js, wait_for_element):
    select_media_type(media_type, browser_js, wait_for_element)
    set_model_picker_open(True, browser_js, wait_for_element)
    options = model_options(browser_js)
    set_model_picker_open(False, browser_js, wait_for_element)
    if not options:
        raise RuntimeError(f"No CapCut models were found for {media_type}")
    return options


def select_model(model, browser_js, wait_for_element):
    set_model_picker_open(True, browser_js, wait_for_element)
    options = model_options(browser_js)
    matches = [option for option in options if option["name"].casefold() == model.casefold()]
    if len(matches) != 1:
        set_model_picker_open(False, browser_js, wait_for_element)
        available = ", ".join(option["name"] for option in options) or "none"
        raise ValueError(f"Model {model!r} is not available. Available models: {available}")

    selected = browser_js(
        "(()=>{const l=document.querySelector('[role=listbox][aria-label="
        "\"Model\"]');if(!l)return false;const e=Array.from(l.querySelectorAll('[role=option]'))"
        ".find(x=>x.getAttribute('data-model-key')==="
        + json.dumps(matches[0]["key"])
        + ");if(!e)return false;e.click();return true})()"
    )
    if not selected:
        raise RuntimeError(f"Could not select CapCut model {model!r}")
    set_model_picker_open(False, browser_js, wait_for_element)
    return matches[0]["name"]