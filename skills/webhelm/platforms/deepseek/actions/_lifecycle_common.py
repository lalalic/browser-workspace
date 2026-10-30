import json
import re
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

ANSWER_STATE = """(() => {
  const answers = [...document.querySelectorAll('.ds-assistant-message-main-content')];
  const generating = !!document.querySelector('[role=button].ds-button--primary:not(.ds-button--disabled)');
  const finished = document.querySelectorAll('[aria-label="Read aloud"]').length >= answers.length;
  return {count: answers.length, answer: answers.at(-1)?.innerText.trim() || '', settled: !generating && finished};
})()"""


def parse_json_answer(answer):
    fenced = re.search(r"```(?:json)?\s*(.*?)```", answer, re.S)
    try:
        return json.loads(fenced.group(1) if fenced else answer), None
    except ValueError as exc:
        return None, str(exc)


def wait_for_answer(browser, receipt, cfg, min_count, timeout):
    """Waits for the answer after `min_count` existing answers; never resubmits."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = browser["js"](ANSWER_STATE)
        if state["count"] > min_count and state["answer"] and state["settled"]:
            result = {**receipt, "status": "completed", "answer": state["answer"]}
            if cfg.get("response_format") == "json":
                result["data"], error = parse_json_answer(state["answer"])
                if error:
                    result["parse_error"] = error
            return result
        browser["wait"](1)
    return {**receipt, "status": "pending",
            "next_step": "Keep this session and rerun with resume=true and this thread_id; do not resend"}


def thread_id_from_url(url):
    parsed = urlsplit(url)
    prefix = "/a/chat/s/"
    if parsed.hostname != "chat.deepseek.com" or not parsed.path.startswith(prefix):
        return None
    candidate = parsed.path[len(prefix):].rstrip("/")
    try:
        return str(UUID(candidate)) if candidate == str(UUID(candidate)) else None
    except ValueError:
        return None


def run(cfg, mode, browser):
    timeout = float(cfg.get("timeout_seconds", 120))
    if not 1 <= timeout <= 600:
        raise ValueError("timeout_seconds must be between 1 and 600")
    if cfg.get("response_format", "text") not in {"text", "json"}:
        raise ValueError("response_format must be text or json")
    if cfg.get("resume"):
        return resume(cfg, mode, browser, timeout)
    message = cfg.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("message is required and must be a non-empty string")
    message = message.strip()
    if cfg.get("project_id") or cfg.get("temporary") or cfg.get("mode", "chat") != "chat":
        raise ValueError("DeepSeek lifecycle actions support ordinary chat only, not Projects or Temporary Chat")
    image = None
    if "image" in cfg:
        image = Path(cfg["image"]).expanduser()
        if not image.is_absolute() or not image.is_file():
            raise ValueError("image must be an existing absolute local file path")
        if image.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tif', '.tiff', '.avif'}:
            raise ValueError("Use a PNG, JPEG, WebP, GIF, BMP, TIFF, or AVIF image")
    expected_id = None
    if mode == "new-turn":
        candidate = cfg.get("thread_id", "")
        if not isinstance(candidate, str):
            raise ValueError("thread_id must be a canonical UUID")
        expected_id = thread_id_from_url("https://chat.deepseek.com/a/chat/s/" + candidate)
        if expected_id is None or expected_id != candidate:
            raise ValueError("thread_id must be a canonical UUID")
    js = browser["js"]
    composer = 'textarea[placeholder="Message DeepSeek"]'
    primary = '[role="button"].ds-button--primary'

    def idle():
        browser["wait_for_element"](composer, timeout=15, visible=True)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = js("""(() => {
              const composer = document.querySelector('textarea[placeholder="Message DeepSeek"]');
              const send = document.querySelector('[role="button"].ds-button--primary');
              const attachments = [...document.querySelectorAll('img[alt]')].some(image =>
                image.closest('[role=button]') && !image.closest('.ds-message'));
              return {draft: !!composer?.value || attachments,
                idle: !!composer && !composer.disabled && !!send && send.classList.contains('ds-button--disabled')};
            })()""")
            if state["draft"]:
                raise RuntimeError("Unsent draft or attachment; leave it untouched")
            if state["idle"]:
                return
            browser["wait"](0.2)
        raise RuntimeError("DeepSeek is still generating; nothing was submitted")

    if urlsplit(browser["page_info"]()["url"]).hostname == "chat.deepseek.com":
        idle()
    target = "https://chat.deepseek.com/" + ("a/chat/s/" + expected_id if expected_id else "")
    browser["goto_url"](target)
    browser["wait_for_load"]()
    idle()
    current_id = thread_id_from_url(browser["page_info"]()["url"])
    if current_id != expected_id:
        raise RuntimeError("DeepSeek thread redirect mismatch; nothing was submitted")
    expression = """(() => {
      const message = %s;
      return [...document.querySelectorAll('.ds-message')].filter(element =>
        element.innerText.trim() === message).length;
    })()""" % json.dumps(message)
    before = js(expression)
    answers_before = js(ANSWER_STATE)["count"]
    if image is not None:
        accepted = js("document.querySelector('input[type=file]')?.accept || ''").split(',')
        if image.suffix.lower() not in accepted:
            raise ValueError("DeepSeek's attachment input does not accept this image extension")
        browser["upload_file"]('input[type="file"]', str(image))
    browser["fill_input"](composer, message)
    browser["wait_for_element"](primary + ':not(.ds-button--disabled)', timeout=60 if image else 15, visible=True)
    if image is not None:
        attached = js("""(() => {
          const name = %s;
          return [...document.querySelectorAll('img[alt]')].some(image =>
            image.alt === name && image.complete && image.naturalWidth > 0);
        })()""" % json.dumps(image.name))
        if not attached:
            raise RuntimeError("Image preview is not ready; nothing was submitted")
    browser["click"](primary + ':not(.ds-button--disabled)')
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current_url = browser["page_info"]()["url"]
        current_id = thread_id_from_url(current_url)
        accepted = js(expression) > before
        cleared = js("document.querySelector('textarea[placeholder=\"Message DeepSeek\"]')?.value === ''")
        if current_id and accepted and cleared and (expected_id is None or current_id == expected_id):
            receipt = {
                "status": "submitted", "mode": mode, "project_id": None,
                "thread_id": current_id,
                "thread_url": "https://chat.deepseek.com/a/chat/s/" + current_id,
                "source_thread_id": cfg.get("source_thread_id"),
                "verified_by": "new matching message, cleared composer, and durable thread URL",
                "user_message_id": None,
            }
            if cfg.get("wait", True) is False:
                return receipt
            return wait_for_answer(browser, receipt, cfg, answers_before, timeout)
        browser["wait"](0.2)
    raise RuntimeError("Submission may have succeeded but its receipt was not verified; inspect this session before retrying")


def resume(cfg, mode, browser, timeout):
    thread_id = cfg.get("thread_id") or thread_id_from_url(browser["page_info"]()["url"])
    if not isinstance(thread_id, str) or thread_id_from_url("https://chat.deepseek.com/a/chat/s/" + thread_id) != thread_id:
        raise ValueError("resume needs a canonical thread_id or an open DeepSeek thread")
    url = "https://chat.deepseek.com/a/chat/s/" + thread_id
    if thread_id_from_url(browser["page_info"]()["url"]) != thread_id:
        browser["goto_url"](url)
        browser["wait_for_load"]()
    receipt = {"status": "submitted", "mode": mode, "project_id": None, "thread_id": thread_id,
               "thread_url": url, "source_thread_id": cfg.get("source_thread_id"),
               "verified_by": "resumed without resubmitting", "user_message_id": None}
    return wait_for_answer(browser, receipt, cfg, 0, timeout)