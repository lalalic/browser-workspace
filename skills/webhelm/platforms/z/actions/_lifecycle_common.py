import json
import time
from urllib.parse import quote, unquote, urlsplit


BASE_URL = "https://chat.z.ai/"
COMPOSER = 'textarea[placeholder="Send a Message"]'
SEND_BUTTON = "#send-message-button"


def thread_id_from_url(url):
    parsed = urlsplit(url)
    if parsed.hostname != "chat.z.ai" or not parsed.path.startswith("/c/"):
        return None
    candidate = parsed.path[len("/c/"):].split("/", 1)[0]
    return unquote(candidate) or None


def target_url(thread_id=None):
    if thread_id is None:
        return BASE_URL
    return BASE_URL + "c/" + quote(thread_id, safe="")


def page_state(browser):
    return browser["js"]("""(() => {
      const composer=document.querySelector('textarea[placeholder="Send a Message"]');
      return {
        composer: !!composer,
        text: composer?.value || "",
        attachmentCount: [...document.querySelectorAll('input[type="file"]')]
          .reduce((count, input) => count + (input.files?.length || 0), 0)
      };
    })()""")


def message_count(browser, message):
    expression = """(() => {
      const expected = %s;
      return [...document.querySelectorAll('.user-message')].filter(element =>
        element.innerText.trim() === expected).length;
    })()""" % json.dumps(message)
    return browser["js"](expression)


def reject_unsent_content(state):
    if state["text"].strip() or state["attachmentCount"]:
        raise RuntimeError("Unsent draft or attachment; leave it untouched")


def run(cfg, mode, browser):
    message = cfg.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("message is required and must be a non-empty string")
    message = message.strip()
    if cfg.get("project_id") or cfg.get("temporary") or cfg.get("mode", "chat") != "chat":
        raise ValueError("Z.ai lifecycle actions support ordinary chat only")

    try:
        timeout = float(cfg.get("timeout_seconds", 120))
    except (TypeError, ValueError) as exc:
        raise ValueError("timeout_seconds must be between 1 and 600") from exc
    if not 1 <= timeout <= 600:
        raise ValueError("timeout_seconds must be between 1 and 600")

    expected_id = None
    if mode == "new-turn":
        candidate = cfg.get("thread_id")
        if not isinstance(candidate, str) or not candidate.strip():
            raise ValueError("thread_id is required")
        expected_id = thread_id_from_url(target_url(candidate.strip()))
        if expected_id != candidate.strip():
            raise ValueError("thread_id must be a single URL path segment")
    elif mode != "new-thread":
        raise ValueError("mode must be new-thread or new-turn")

    current_url = browser["page_info"]().get("url", "")
    if urlsplit(current_url).hostname == "chat.z.ai":
        reject_unsent_content(page_state(browser))

    thread_url = target_url(expected_id)
    browser["goto_url"](thread_url)
    browser["wait_for_load"]()
    browser["wait_for_element"](COMPOSER, timeout=15, visible=True)
    reject_unsent_content(page_state(browser))

    current_url = browser["page_info"]().get("url", "")
    current_id = thread_id_from_url(current_url)
    if mode == "new-turn" and current_id != expected_id:
        raise RuntimeError("Z.ai thread redirect mismatch; nothing was submitted")
    if mode == "new-thread" and current_id is not None:
        raise RuntimeError("Z.ai did not open a new chat; nothing was submitted")

    before_count = message_count(browser, message)
    browser["fill_input"](COMPOSER, message)
    browser["wait_for_element"](f"{SEND_BUTTON}:not(:disabled)", timeout=15, visible=True)
    browser["click"](SEND_BUTTON)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current_url = browser["page_info"]().get("url", "")
        current_id = thread_id_from_url(current_url)
        state = page_state(browser)
        accepted = message_count(browser, message) > before_count
        if current_id and accepted and not state["text"]:
            if expected_id is None or current_id == expected_id:
                return {
                    "status": "submitted",
                    "mode": mode,
                    "project_id": None,
                    "thread_id": current_id,
                    "thread_url": target_url(current_id),
                    "source_thread_id": cfg.get("source_thread_id") if mode == "new-thread" else None,
                    "verified_by": "matching user message, cleared composer, and durable thread URL",
                    "user_message_id": None,
                }
        time.sleep(0.2)

    raise RuntimeError(
        "Submission may have succeeded but its receipt was not verified; inspect this session before retrying"
    )