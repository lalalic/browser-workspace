"""Bounded polling helpers for ChatGPT submit readiness."""
from __future__ import annotations

import json
import re
import time


class SubmissionVerificationError(RuntimeError):
    def __init__(self, message, diagnostic):
        serialized = json.dumps(diagnostic, ensure_ascii=False, sort_keys=True)
        super().__init__(f"{message}: {serialized}")
        self.diagnostic = diagnostic

def wait_until_stable(read_state, ready, *, timeout, interval=0.25, stable_samples=2, phase):
    deadline = time.monotonic() + timeout
    stable = 0
    last_state = {}
    stable_state = None
    while time.monotonic() < deadline:
        try:
            last_state = read_state()
        except Exception:
            stable = 0
            time.sleep(interval)
            continue
        if ready(last_state):
            if stable_state == last_state:
                stable += 1
            else:
                stable_state = last_state
                stable = 1
            if stable >= stable_samples:
                return last_state
        else:
            stable = 0
        time.sleep(interval)
    raise RuntimeError(f"ChatGPT {phase} was not observed ready")

def prompt_text_matches(observed, expected):
    def normalize(value):
        text=re.sub(r"\s+", " ", value or "").strip()
        text=re.sub(r">\s+", ">", text)
        text=re.sub(r"\s+<", "<", text)
        return text
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
    for turn in turns[before_count:]:
        if prompt_text_matches(turn.get("text"), prompt):
            return {"verified_by": "user-turn", "turn": turn}
    return None


def submission_failure_diagnostic(turns, before_count, prompt, composer_text, ui_before=None, ui_after=None):
    return {
        "accepted": False,
        "reason": "no_accepted_user_turn",
        "user_turn_matched": False,
        "before_user_turn_count": len(turns[:before_count]),
        "user_turn_count": len(turns),
        "composer_populated": bool((composer_text or "").strip()),
        "composer_text_length": len((composer_text or "").strip()),
        "ui_changed": None if ui_before is None or ui_after is None else bool(ui_before != ui_after),
        "ui_before": ui_before,
        "ui_after": ui_after,
    }
