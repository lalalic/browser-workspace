# Canonical one-shot ChatGPT Temporary Chat submission mechanics.
# Lifecycle/barrier ownership belongs to the caller (Agents Relay).
"""Bounded polling helpers for ChatGPT submit readiness."""
from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from urllib.parse import urlencode


def wait_until_stable(
    read_state: Callable[[], Mapping[str, object]],
    ready: Callable[[Mapping[str, object]], bool],
    *,
    timeout: float,
    interval: float = 0.25,
    stable_samples: int = 2,
    phase: str,
) -> Mapping[str, object]:
    """Return only after the observable state is ready for stable_samples polls."""
    deadline = time.monotonic() + timeout
    stable = 0
    last_state: Mapping[str, object] = {}
    while time.monotonic() < deadline:
        last_state = read_state()
        if ready(last_state):
            stable += 1
            if stable >= stable_samples:
                return last_state
        else:
            stable = 0
        time.sleep(interval)
    raise RuntimeError(f"Temporary Chat {phase} was not observed ready")


def actionable_temporary_chat_candidates(candidates):
    return [
        candidate for candidate in candidates
        if candidate.get("visible")
        and not candidate.get("disabled")
        and candidate.get("pointerEvents") != "none"
    ]


def temporary_chat_entry_url(prompt=""):
    """Open Temporary Chat and let ChatGPT prefill the prompt from the URL."""
    query = {"temporary-chat": "true"}
    if prompt:
        query["prompt"] = prompt
    return "https://chatgpt.com/?" + urlencode(query)



def temporary_chat_enabled_state(url, candidates):
    """Recognize Temporary Chat from stable URL state with semantic UI fallback."""
    if "temporary-chat=true" in (url or ""):
        return True
    return any(
        "turn off" in f"{candidate.get('label') or ''} {candidate.get('text') or ''}".lower()
        for candidate in candidates
        if candidate.get("visible")
        and not candidate.get("disabled")
        and candidate.get("pointerEvents") != "none"
    )


def prompt_text_matches(observed, expected):
    """Verify long composer/user-turn text despite ProseMirror whitespace reshaping."""
    import re
    normalize = lambda value: re.sub(r"\s+", " ", value or "").strip()
    observed_n = normalize(observed)
    expected_n = normalize(expected)
    if expected_n in observed_n:
        return True
    if not expected_n:
        return not observed_n
    span = min(256, max(48, len(expected_n) // 8))
    return (
        len(observed_n) >= int(len(expected_n) * 0.9)
        and expected_n[:span] in observed_n
        and expected_n[-span:] in observed_n
    )


def submission_receipt(turns, before_count, prompt, composer_text):
    """Return a transport receipt after click without requiring one DOM message shape."""
    for turn in turns[before_count:]:
        if prompt_text_matches(turn.get("text"), prompt):
            return {"verified_by": "user-turn", "turn": turn}
    if not (composer_text or "").strip():
        return {
            "verified_by": "composer-cleared",
            "turn": {"id": None, "text": prompt},
        }
    return None


import atexit
import json
import os
import re
import time



CFG = json.load(open("__CFG_PATH__", encoding="utf-8"))
_OWNED_TABS = []
_KEEP_OWNED_TAB_OPEN = True
_SUBMISSION_SUCCEEDED = False



def _new_owned_tab(url):
    # Respect Browser Harness workspace adapters. Record both target + workspace
    # tab id so cleanup remains scoped to exactly this worker's own lease even
    # if ChatGPT navigation invalidates the original target mapping.
    target_id = new_tab(url)
    tabs = [tab for tab in list_tabs(include_chrome=False) if tab.get("targetId") == target_id]
    if len(tabs) != 1:
        raise RuntimeError(f"Owned Browser Workspace target {target_id!r} was not mapped to one tab")
    _OWNED_TABS.append({
        "targetId": target_id,
        "tabId": tabs[0].get("tabId"),
    })
    return target_id


def _close_owned_tabs():
    # close-policy=never preserves an owned tab only after a verified submit.
    # Any failure before that point must release this worker's own lease.
    if _KEEP_OWNED_TAB_OPEN and _SUBMISSION_SUCCEEDED:
        return
    while _OWNED_TABS:
        owned = _OWNED_TABS.pop()
        try:
            close_tab(owned["targetId"])
            continue
        except Exception:
            pass
        try:
            current = current_tab()
            if owned.get("tabId") is not None and current.get("tabId") == owned["tabId"]:
                close_tab()
        except Exception:
            pass


atexit.register(_close_owned_tabs)


def _composer():
    selector = js("""(() => {
      const selectors = [
        '#prompt-textarea',
        '[contenteditable="true"][data-composer-markdown]',
        '[contenteditable="true"][data-lexical-editor="true"]',
        'textarea'
      ];
      for (const selector of selectors) {
        const e=document.querySelector(selector);
        if (!e || e.id === 'pending-home-input' || e.disabled) continue;
        const r=e.getBoundingClientRect();
        if (r.width>0 && r.height>0) return selector;
      }
      const visible = [...document.querySelectorAll('[contenteditable="true"]')]
        .filter(e => {
          if (e.id === 'pending-home-input' || e.disabled) return false;
          const r=e.getBoundingClientRect();
          return r.width>0 && r.height>0;
        });
      return visible.length === 1 ? '[contenteditable="true"]' : null;
    })()""")
    if not selector:
        raise RuntimeError("ChatGPT composer was not observed")
    return selector

def _composer_text(selector):
    return js(f"""(() => {{
      const e=document.querySelector({json.dumps(selector)});
      if (!e) return '';
      return e.getAttribute('contenteditable') === 'true'
        ? (e.innerText || '')
        : (e.value || '');
    }})()""") or ""


def _wait_for_composer(timeout=30):
    def read_selector():
        try:
            return _composer()
        except RuntimeError:
            return None

    return wait_until_stable(
        lambda: {"selector": read_selector()},
        lambda state: bool(state["selector"]),
        timeout=timeout,
        phase="composer readiness",
    )["selector"]


def _same_text(observed, expected):
    normalize = lambda value: re.sub(r"\\s+", " ", value or "").strip()
    return normalize(expected) in normalize(observed)


def _normalized_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def _temporary_chat_candidates():
    return js(r"""(() => [...document.querySelectorAll('button')].map((b, index) => {
      const label=(b.getAttribute('aria-label') || '').trim();
      const text=(b.innerText || '').trim();
      const semantic=/temporary/i.test(label + ' ' + text) && /chat/i.test(label + ' ' + text);
      if (!semantic) return null;
      const r=b.getBoundingClientRect();
      const style=getComputedStyle(b);
      return {
        index,
        label,
        text,
        visible:r.width > 0 && r.height > 0 && style.visibility !== 'hidden' && style.display !== 'none',
        disabled:!!b.disabled || b.getAttribute('aria-disabled') === 'true',
        pointerEvents:style.pointerEvents,
      };
    }).filter(Boolean))()""") or []


def _temporary_chat_enabled():
    return temporary_chat_enabled_state(
        page_info().get("url", ""),
        _temporary_chat_candidates(),
    )


def _click_temporary_chat_toggle(timeout=20):
    deadline = time.time() + timeout
    last_candidates = []
    while time.time() < deadline:
        if _temporary_chat_enabled():
            return "already-enabled"
        last_candidates = _temporary_chat_candidates()
        actionable = actionable_temporary_chat_candidates(last_candidates)
        if len(actionable) == 1:
            clicked = js(f"""(() => {{
              const b=[...document.querySelectorAll('button')][{int(actionable[0]["index"])}];
              if (!b) return false;
              const r=b.getBoundingClientRect();
              const style=getComputedStyle(b);
              if (!(r.width > 0 && r.height > 0) || b.disabled ||
                  b.getAttribute('aria-disabled') === 'true' || style.pointerEvents === 'none') return false;
              b.click();
              return true;
            }})()""")
            if clicked:
                return "clicked"
        elif len(actionable) > 1:
            labels = [candidate.get("label") or candidate.get("text") or "<unnamed>" for candidate in actionable]
            raise RuntimeError(f"Temporary Chat toggle is ambiguous: {len(actionable)} actionable controls {labels}")
        time.sleep(.25)
    raise RuntimeError(
        "Temporary Chat toggle was not actionable after "
        f"{timeout}s; semantic candidates={last_candidates}"
    )


def _attachment_names():
    return js(r"""(() => [...document.querySelectorAll('button[aria-label^="Remove file"]')]
      .map(b => (b.getAttribute('aria-label') || '').replace(/^Remove file\s+\d+:\s*/, ''))
      .filter(Boolean))()""") or []


def _attachment_state():
    return js(r"""(() => {
      const names = [...document.querySelectorAll('button[aria-label^="Remove "]')]
        .map(b => (b.getAttribute('aria-label') || '')
          .replace(/^Remove file\s+\d+:\s*/, '')
          .replace(/^Remove\s+/, ''))
        .filter(Boolean);
      return {names, pending: false};
    })()""") or {"names": [], "pending": False}


def _send_state():
    return js(r"""(() => {
      const b=document.querySelector('button[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="Send"]');
      return {present: !!b, enabled: !!b && !b.disabled && b.getAttribute('aria-disabled') !== 'true'};
    })()""") or {"present": False, "enabled": False}


def _wait_for_attachments(expected, timeout=45):
    expected = set(expected)
    wait_until_stable(
        _attachment_state,
        lambda state: expected.issubset(state["names"]) and not state["pending"],
        timeout=timeout,
        phase="attachment upload readiness",
    )


def _upload_files(paths):
    if not paths:
        return []

    def file_input_selector():
        return js("""(() => {
          const selectors = [
            '#upload-files',
            '#upload-media',
            'input[name="upload-media"]',
            'input[type="file"]:not([accept])',
            'input[type="file"]'
          ];
          for (const s of selectors) if (document.querySelector(s)) return s;
          return null;
        })()""")

    selector = file_input_selector()
    if not selector:
        opened = js("""(() => {
          const b=[...document.querySelectorAll('button')].find(b =>
            (b.getAttribute('aria-label') || '').trim() === 'Add files and more');
          if (!b) return false;
          b.click();
          return true;
        })()""")
        if opened:
            deadline = time.time() + 5
            while time.time() < deadline and not selector:
                selector = file_input_selector()
                if not selector:
                    time.sleep(.1)
    if not selector:
        raise RuntimeError("ChatGPT file input was not observed")
    for path in paths:
        if not os.path.isfile(path):
            raise RuntimeError(f"attachment does not exist: {path}")
        upload_file(selector, path)
    expected = [os.path.basename(path) for path in paths]
    if expected:
        # Presence is a selection signal; upload readiness is checked separately.
        wait_until_stable(
            _attachment_state,
            lambda state: set(expected).issubset(state["names"]),
            timeout=30,
            phase="attachment presence",
        )
        _wait_for_attachments(expected)
    return expected


def _user_turns():
    return js("""(() => [...document.querySelectorAll('[data-message-author-role="user"]')]
      .map(e => ({text:e.innerText.trim(), id:e.getAttribute('data-message-id') || ''}))
      .filter(e => e.text))()""") or []


def _click_send():
    ok = js("""(() => {
      const b=document.querySelector('button[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="Send"]');
      if (!b || b.disabled || b.getAttribute('aria-disabled') === 'true') return false;
      b.click(); return true;
    })()""")
    if not ok:
        raise RuntimeError("Temporary Chat send readiness changed before click")


def _wait_for_send_ready(selector, prompt, attachments):
    expected = set(attachments)

    def read_state():
        try:
            live_selector = _composer()
        except RuntimeError:
            live_selector = selector
        return {
            "selector": live_selector,
            "text": _composer_text(live_selector),
            "attachments": _attachment_state(),
            "send": _send_state(),
        }

    return wait_until_stable(
        read_state,
        lambda state: (
            prompt_text_matches(state["text"], prompt)
            and expected.issubset(state["attachments"]["names"])
            and state["send"]["enabled"]
        ),
        timeout=45 if expected else 15,
        phase="send readiness",
    )


def _wait_user_turn(before_count, prompt, selector, timeout=20):
    deadline = time.time() + timeout
    cleared_polls = 0
    last_error = None
    while time.time() < deadline:
        try:
            receipt = submission_receipt(
                _user_turns(),
                before_count,
                prompt,
                _composer_text(selector),
            )
            last_error = None
        except RuntimeError as exc:
            # The Browser Harness/CDP daemon can transiently time out while
            # ChatGPT is committing a navigation/message update. Receipt
            # observation is read-only, so retry within the existing bound.
            last_error = exc
            time.sleep(.25)
            continue
        if receipt:
            if receipt["verified_by"] == "user-turn":
                return receipt
            cleared_polls += 1
            if cleared_polls >= 2:
                return receipt
        else:
            cleared_polls = 0
        time.sleep(.25)
    suffix = f"; last observation error: {last_error}" if last_error else ""
    raise RuntimeError(
        "ChatGPT submission verification did not observe an accepted submission" + suffix
    )


def _diagnostic_thread_id():
    match = re.search(r"/c/([^/?#]+)", page_info().get("url", ""))
    return match.group(1) if match else None




def _fill_prompt_if_needed(prompt, mode_label, timeout=30):
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        selector = _wait_for_composer(timeout=min(5, max(1, deadline - time.time())))
        if prompt_text_matches(_composer_text(selector), prompt):
            return selector

        is_contenteditable = bool(js(f"""(() => {{
          const e=document.querySelector({json.dumps(selector)});
          return !!e && e.getAttribute('contenteditable') === 'true';
        }})()"""))
        try:
            if is_contenteditable:
                cleared = js(f"""(() => {{
                  const e=document.querySelector({json.dumps(selector)});
                  if (!e) return false;
                  e.focus();
                  const sel=window.getSelection();
                  const range=document.createRange();
                  range.selectNodeContents(e);
                  sel.removeAllRanges();
                  sel.addRange(range);
                  document.execCommand('delete', false, null);
                  return true;
                }})()""")
                if not cleared:
                    raise RuntimeError(
                        f"{mode_label} contenteditable composer could not be cleared"
                    )
                for offset in range(0, len(prompt), 256):
                    chunk = prompt[offset:offset + 256]
                    inserted = js(f"""(() => {{
                      const e=document.querySelector({json.dumps(selector)});
                      if (!e) return false;
                      e.focus();
                      const ok=document.execCommand(
                        'insertText', false, {json.dumps(chunk)}
                      );
                      e.dispatchEvent(new InputEvent('input', {{
                        bubbles:true,
                        inputType:'insertText',
                        data:{json.dumps(chunk)}
                      }}));
                      return ok;
                    }})()""")
                    if not inserted:
                        raise RuntimeError(
                            f"{mode_label} composer rejected prompt chunk at offset {offset}"
                        )
            else:
                fill_input(selector, prompt, clear_first=True)
            return selector
        except RuntimeError as exc:
            # ChatGPT can replace textarea with ProseMirror during hydration.
            # Re-resolve the live composer instead of keeping a stale selector.
            last_error = exc
            time.sleep(.25)

    suffix = f"; last fill error: {last_error}" if last_error else ""
    raise RuntimeError(f"{mode_label} composer could not be filled{suffix}")


def _live_composer_state():
    try:
        selector = _composer()
    except RuntimeError:
        return {"selector": None, "text": ""}
    return {"selector": selector, "text": _composer_text(selector)}


def _submit_current_page(prompt, *, temporary, mode_label):
    _fill_prompt_if_needed(prompt, mode_label)
    composer_state = wait_until_stable(
        _live_composer_state,
        lambda state: (
            bool(state["selector"])
            and prompt_text_matches(state["text"], prompt)
        ),
        timeout=30,
        phase=f"{mode_label} composer readiness",
    )
    selector = composer_state["selector"]

    attachments = _upload_files(CFG.get("file", []))
    before_count = len(_user_turns())

    send_state = _wait_for_send_ready(selector, prompt, attachments)
    if isinstance(send_state, dict) and send_state.get("selector"):
        selector = send_state["selector"]

    _click_send()
    receipt = _wait_user_turn(before_count, prompt, selector)
    global _SUBMISSION_SUCCEEDED
    _SUBMISSION_SUCCEEDED = True
    owned = _OWNED_TABS[-1] if _OWNED_TABS else {}
    return {
        "operation": "submit",
        "status": "submitted",
        "temporary": temporary,
        "attachments": attachments,
        "diagnostic_thread_id": _diagnostic_thread_id(),
        "user_message_id": receipt["turn"].get("id") or None,
        "owned_tab_id": owned.get("tabId"),
        "owned_target_id": owned.get("targetId"),
        "verified_by": receipt["verified_by"],
        "verified": True,
    }

def _wait_for_release():
    release_file = CFG.get("release_file")
    if not release_file:
        raise RuntimeError("worker release file was not configured")
    if CFG.get("close_policy", "after-start") == "never":
        raise SystemExit(0)
    while not os.path.exists(release_file):
        time.sleep(.1)


prompt = CFG["prompt"]
_new_owned_tab(temporary_chat_entry_url(prompt))
wait_for_load()

_click_temporary_chat_toggle()
deadline = time.time() + 20
while time.time() < deadline:
    if _temporary_chat_enabled():
        break
    time.sleep(.25)
else:
    raise RuntimeError("Temporary Chat activation was not observed")

result = _submit_current_page(prompt, temporary=True, mode_label="Temporary Chat")
print(json.dumps(result, ensure_ascii=False), flush=True)
