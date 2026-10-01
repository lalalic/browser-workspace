"""Bounded polling helpers for ChatGPT submit readiness."""
from __future__ import annotations

import re
import time

def wait_until_stable(read_state, ready, *, timeout, interval=0.25, stable_samples=2, phase):
    deadline = time.monotonic() + timeout
    stable = 0
    last_state = {}
    while time.monotonic() < deadline:
        last_state = read_state()
        if ready(last_state):
            stable += 1
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
    if not (composer_text or "").strip():
        return {"verified_by": "composer-cleared", "turn": {"id": None, "text": prompt}}
    return None
