"""WebHelm daemon adapter for durable ChatGPT new-turn delivery.

Imported by session_daemon after its browser/session functions exist.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

from chatgpt_probe import PROBE_JS, classify_probe, target_url
from fifo_queue import TurnQueue
from turn_dispatcher import TurnDispatcher

# Both direct new-turn/validate and FIFO use the same site Send selectors.
sys.path.insert(0, str(Path(__file__).resolve().parent / "platforms" / "chatgpt" / "actions"))
from _lifecycle_common import SEND_ENABLED_JS


def _result(response):
    if not response.get("ok"):
        raise RuntimeError(response.get("error") or response.get("stderr") or "browser action failed")
    return response.get("value")


class BrowserTurnDriver:
    def __init__(self, start_session, exec_session, stop_session):
        self.start_session = start_session
        self.exec_session = exec_session
        self.stop_session = stop_session
        self.active = {}
        self.lock = threading.Lock()

    def _close(self, item_id):
        with self.lock:
            sid = self.active.pop(item_id, None)
        if sid:
            try:
                self.stop_session(sid)
            except Exception:
                pass

    def finish(self, item):
        """Release this attempt's private Session on every exit path."""
        self._close(item["id"])

    def probe(self, item):
        url = target_url(item["project_id"], item["thread_id"], item["message"])
        session = self.start_session(url=url)
        sid = session["session_id"]
        with self.lock:
            self.active[item["id"]] = sid
        try:
            code = "page = page_info()\n" + \
                   "state = js(" + repr(PROBE_JS) + ")\n" + \
                   "if state and state.get('state') == 'READY' and not js(" + repr(SEND_ENABLED_JS) + "):\n" + \
                   "    state['state'] = 'NOT_READY'\n" + \
                   "{'url': page.get('url',''), 'state': state}"
            # Load completion can precede React hydration of ?prompt=.
            # Each short exec releases the shared browser lock.
            deadline = time.monotonic() + 45
            while True:
                observed = _result(self.exec_session(sid, code))
                state = classify_probe(observed["url"], url, observed["state"], item["message"])
                if state in ("READY", "RUNNING", "BLOCKED"):
                    if state != "READY":
                        self._close(item["id"])
                    return state
                if time.monotonic() >= deadline:
                    self._close(item["id"])
                    return state
                time.sleep(.4)
        except Exception:
            self._close(item["id"])
            raise

    def send_and_verify(self, item):
        with self.lock:
            sid = self.active.get(item["id"])
        if not sid:
            raise RuntimeError("missing prepared browser session")
        # Use the synchronous new-turn Send/verification implementation.
        expected_page = target_url(item["project_id"], item["thread_id"], item["message"]).split("?", 1)[0]
        source = ("prompt = " + repr(item["message"]) + "\n"
                  "import _lifecycle_common as lifecycle\n"
                  "lifecycle.js = js\n"
                  "gate = js(" + repr(PROBE_JS) + ")\n"
                  "gate_url = page_info().get('url','')\n"
                  "receipt = {'diagnostic':'pre_send_gate_not_ready'}\n"
                  "if gate and gate.get('state') == 'READY' and js(" + repr(SEND_ENABLED_JS) + ") and "
                  "gate.get('composer_text','').strip() == prompt.strip() and "
                  "gate_url == " + repr(expected_page) + ":\n"
                  "    receipt = lifecycle.prefilled_submit(prompt)\n"
                  "receipt")
        try:
            return _result(self.exec_session(sid, source))
        finally:
            self._close(item["id"])


class DaemonTurnQueue:
    def __init__(self, runtime_dir: Path, start_session, exec_session, stop_session):
        self.queue = TurnQueue(runtime_dir / "chatgpt-new-turn.sqlite3")
        self.driver = BrowserTurnDriver(start_session, exec_session, stop_session)
        self.dispatcher = TurnDispatcher(self.queue, self.driver, interval=60, concurrency=4)
        self.dispatcher.start()

    def enqueue(self, request):
        item = self.queue.enqueue(
            str(request.get("thread_id") or "").strip(),
            str(request.get("message") or ""),
            str(request.get("idempotency_key") or "").strip(),
            str(request.get("project_id") or "").strip() or None,
        )
        self.dispatcher.notify_enqueued()
        return {"ok": True, "status": "queued", "queue_id": item["id"],
                "thread_id": item["thread_id"], "state": item["state"]}

    def list_pending(self):
        # Do not include raw prompts in daemon diagnostics.
        rows = self.queue.rows()
        return {"ok": True, "items": [
            {key: row[key] for key in ("id", "thread_id", "state", "attempts", "created_at", "receipt")}
            for row in rows if row["state"] not in ("SENT", "CANCELLED")
        ]}

    def reconcile(self, request):
        item_id = str(request.get("queue_id") or "")
        evidence = str(request.get("evidence") or "").strip()
        accepted = request.get("accepted")
        if not item_id or not evidence or type(accepted) is not bool:
            raise ValueError("queue_id, evidence and boolean accepted required")
        target = "SENT" if accepted else "WAITING"
        self.queue.transition(item_id, "reconciler", "UNCERTAIN", target,
                              receipt=evidence, delay=0)
        self.dispatcher.notify_enqueued()
        return {"ok": True, "queue_id": item_id, "state": target}

    def close(self):
        self.dispatcher.close()
