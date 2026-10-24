"""Transport-neutral durable ChatGPT turn dispatcher."""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from fifo_queue import TurnQueue


class TurnDispatcher:
    def __init__(self, queue: TurnQueue, driver, *, interval=60, concurrency=4, clock=time.time):
        self.queue = queue
        self.driver = driver
        self.interval = interval
        self.clock = clock
        self.wakeup = threading.Event()
        self.stop_event = threading.Event()
        self.slots = threading.BoundedSemaphore(concurrency)
        self.pool = ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="chatgpt-turn")
        self.loop_thread = None

    def start(self):
        if self.loop_thread is not None:
            return
        self.loop_thread = threading.Thread(target=self._run, daemon=True, name="chatgpt-turn-scheduler")
        self.loop_thread.start()
        self.wakeup.set()

    def notify_enqueued(self):
        self.wakeup.set()

    def _run(self):
        while not self.stop_event.is_set():
            # Always drain the currently eligible heads before waiting.
            while not self.stop_event.is_set():
                if not self.slots.acquire(blocking=False):
                    break
                item = self.queue.claim("dispatcher-" + str(time.monotonic_ns()), now=self.clock())
                if not item:
                    self.slots.release()
                    break
                future = self.pool.submit(self._process, item)
                future.add_done_callback(lambda _future: self.slots.release())
            self.wakeup.wait(self.interval)
            self.wakeup.clear()

    def _process(self, item):
        owner = item["lease_owner"]
        now = self.clock()
        try:
            # Driver performs ONE bounded page observation, releasing browser
            # locks when it returns. It must not wait for assistant completion.
            state = self.driver.probe(item)
            if state == "RUNNING":
                self.queue.transition(item["id"], owner, "CHECKING", "WAITING", now=now, delay=self.interval,
                                      receipt="stop_visible")
                return
            if state == "BLOCKED":
                self.queue.transition(item["id"], owner, "CHECKING", "BLOCKED", now=now, receipt="page blocked")
                return
            if state != "READY":
                self.queue.transition(item["id"], owner, "CHECKING", "WAITING", now=now, delay=self.interval,
                                      receipt="probe_" + str(state).lower())
                return
            self.queue.transition(item["id"], owner, "CHECKING", "SENDING", now=self.clock())
            # After entering SENDING, *any* transport exception or unverified
            # receipt is ambiguous. NEVER auto-submit again.
            receipt = self.driver.send_and_verify(item)
            if not receipt or receipt.get("verified_by") != "send-button-disabled":
                self.queue.transition(item["id"], owner, "SENDING", "UNCERTAIN", now=self.clock(),
                                      receipt=(receipt.get("diagnostic", "missing_user_turn_receipt")
                                               if receipt else "missing_user_turn_receipt"))
            else:
                self.queue.transition(item["id"], owner, "SENDING", "SENT", now=self.clock(), delay=self.interval, receipt="send-button-disabled")
        except Exception as exc:
            # Durable receipts must not contain a prompt or browser expression.
            diagnostic = ("session_identity_timeout" if "workspace.acquireIdentity" in str(exc)
                          else type(exc).__name__)
            current = next((r for r in self.queue.rows() if r["id"] == item["id"]), None)
            if current and current["state"] == "SENDING":
                self.queue.transition(item["id"], owner, "SENDING", "UNCERTAIN", now=self.clock(), receipt=diagnostic)
            elif current and current["state"] == "CHECKING":
                self.queue.transition(item["id"], owner, "CHECKING", "WAITING", now=self.clock(), delay=self.interval,
                                      receipt="probe_error_" + diagnostic)
        finally:
            # The Dispatcher owns only this attempt, never an external Session.
            finish = getattr(self.driver, "finish", None)
            if finish is not None:
                finish(item)
            self.wakeup.set()

    def close(self):
        self.stop_event.set()
        self.wakeup.set()
        if self.loop_thread is not None:
            self.loop_thread.join(timeout=5)
        self.pool.shutdown(wait=True)
