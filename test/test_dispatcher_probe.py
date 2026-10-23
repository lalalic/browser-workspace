import tempfile
import threading
import time
import unittest
from pathlib import Path

from chatgpt_probe import classify_probe, target_url
from fifo_queue import TurnQueue
from turn_dispatcher import TurnDispatcher


class FakeDriver:
    def __init__(self, states, receipts=None):
        self.states = states
        self.receipts = receipts or {}
        self.probed = []
        self.sent = []
        self.lock = threading.Lock()

    def probe(self, item):
        with self.lock:
            self.probed.append(item["id"])
            return self.states[item["id"]]

    def send_and_verify(self, item):
        with self.lock:
            self.sent.append(item["id"])
            response = self.receipts.get(item["id"])
        if isinstance(response, Exception):
            raise response
        return response


class DispatcherTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.q = TurnQueue(Path(tmp.name) / "q.sqlite3")

    def await_state(self, item_id, state, timeout=3):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            rows = self.q.rows()
            if any(r["id"] == item_id and r["state"] == state for r in rows):
                return
            time.sleep(.01)
        self.fail(f"{item_id} did not reach {state}")

    def test_stop_60s_delay_and_other_thread_progress(self):
        a = self.q.enqueue("A", "one", "a")
        b = self.q.enqueue("B", "two", "b")
        d = FakeDriver({a["id"]: "RUNNING", b["id"]: "READY"},
                       {b["id"]: {"clicked": True, "verified_by": "send-button-disabled"}})
        runner = TurnDispatcher(self.q, d, interval=60)
        runner.start()
        try:
            self.await_state(a["id"], "WAITING")
            self.await_state(b["id"], "SENT")
            self.assertNotIn(a["id"], d.sent)
            a_row = next(r for r in self.q.rows() if r["id"] == a["id"])
            self.assertGreaterEqual(a_row["next_check_at"] - a_row["created_at"], 59)
        finally:
            runner.close()

    def test_unverified_receipt_becomes_uncertain_and_blocks_successor(self):
        a = self.q.enqueue("A", "one", "a")
        b = self.q.enqueue("A", "two", "b")
        d = FakeDriver({a["id"]: "READY", b["id"]: "READY"}, {a["id"]: {"send_disabled": True}})
        runner = TurnDispatcher(self.q, d, interval=60)
        runner.start()
        try:
            self.await_state(a["id"], "UNCERTAIN")
            self.assertEqual(d.sent, [a["id"]])
            self.assertEqual(next(r for r in self.q.rows() if r["id"] == b["id"])["state"], "QUEUED")
        finally:
            runner.close()

    def test_unverified_send_cannot_mark_sent(self):
        for provenance in (None, "dom-message-id", "server-conversation-exact-user-message"):
            with self.subTest(provenance=provenance):
                with tempfile.TemporaryDirectory() as directory:
                    queue = TurnQueue(Path(directory) / "q.sqlite3")
                    a = queue.enqueue("A", "one", "key")
                    driver = FakeDriver({a["id"]: "READY"}, {
                        a["id"]: {"user_message_id": "ui-id", "verified_by": provenance}})
                    runner = TurnDispatcher(queue, driver, interval=.01)
                    runner.start()
                    try:
                        end = time.monotonic() + 3
                        while time.monotonic() < end and queue.rows()[0]["state"] != "UNCERTAIN":
                            time.sleep(.01)
                        self.assertEqual(queue.rows()[0]["state"], "UNCERTAIN")
                        self.assertEqual(driver.sent, [a["id"]])
                    finally:
                        runner.close()

    def test_optimistic_bubble_is_uncertain_and_never_replayed(self):
        a = self.q.enqueue("A", "same text", "bubble-a")
        b = self.q.enqueue("A", "next", "bubble-b")
        d = FakeDriver(
            {a["id"]: "READY", b["id"]: "READY"},
            {a["id"]: {"clicked": True,
                       "diagnostic": "stable_ui_bubble_no_message_id",
                       "user_message_id": None}},
        )
        runner = TurnDispatcher(self.q, d, interval=.01)
        runner.start()
        try:
            self.await_state(a["id"], "UNCERTAIN")
            time.sleep(.06)
            rows = {row["id"]: row for row in self.q.rows()}
            self.assertEqual(rows[b["id"]]["state"], "QUEUED")
            self.assertIn("stable_ui_bubble_no_message_id", str(rows[a["id"]]))
            self.assertEqual(d.sent, [a["id"]])
        finally:
            runner.close()

    def test_server_conversation_without_message_proof_is_uncertain(self):
        a = self.q.enqueue("A", "exact message", "server-200")
        d = FakeDriver(
            {a["id"]: "READY"},
            {a["id"]: {"clicked": True, "user_message_id": None,
                       "diagnostic": "server_conversation_200_no_matching_message"}},
        )
        runner = TurnDispatcher(self.q, d, interval=.01)
        runner.start()
        try:
            self.await_state(a["id"], "UNCERTAIN")
            time.sleep(.05)
            self.assertEqual(d.sent, [a["id"]])
            self.assertIn("server_conversation_200_no_matching_message",
                          str(next(r for r in self.q.rows() if r["id"] == a["id"])))
        finally:
            runner.close()

    def test_send_exception_does_not_retry(self):
        a = self.q.enqueue("A", "one", "a")
        d = FakeDriver({a["id"]: "READY"}, {a["id"]: TimeoutError("after click")})
        runner = TurnDispatcher(self.q, d, interval=.01)
        runner.start()
        try:
            self.await_state(a["id"], "UNCERTAIN")
            time.sleep(.05)
            self.assertEqual(d.sent, [a["id"]])
        finally:
            runner.close()

    def test_two_concurrent_new_turns_keep_fifo_order(self):
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=2) as pool:
            items = list(pool.map(lambda pair: self.q.enqueue("A", pair[0], pair[1]),
                                  [("one", "concurrent-1"), ("two", "concurrent-2")]))
        ordered = sorted(items, key=lambda item: item["seq"])
        receipt = lambda: {"clicked": True, "verified_by": "send-button-disabled"}
        driver = FakeDriver({item["id"]: "READY" for item in ordered},
                            {item["id"]: receipt() for item in ordered})
        runner = TurnDispatcher(self.q, driver, interval=.02)
        runner.start()
        try:
            for item in ordered:
                self.await_state(item["id"], "SENT")
            self.assertEqual(driver.sent, [item["id"] for item in ordered])
        finally:
            runner.close()

    def test_queued_item_runs_immediately_after_daemon_start_and_enqueue(self):
        item = self.q.enqueue("A", "before startup", "startup-item")
        receipt = {"clicked": True, "verified_by": "send-button-disabled"}
        driver = FakeDriver({item["id"]: "READY"}, {item["id"]: receipt})
        runner = TurnDispatcher(TurnQueue(self.q.path), driver, interval=60)
        runner.start()
        try:
            self.await_state(item["id"], "SENT", timeout=1)
            # The live dispatcher is sleeping on its 60s interval.
            item2 = self.q.enqueue("B", "after startup", "live-item")
            driver.states[item2["id"]] = "READY"
            driver.receipts[item2["id"]] = receipt
            runner.notify_enqueued()
            self.await_state(item2["id"], "SENT", timeout=1)
        finally:
            runner.close()

    def test_read_only_page_probe(self):
        url = target_url("g-p-project-name", "abc-123", "hi & 你好")
        self.assertIn("/g/g-p-project-name/c/abc-123?prompt=", url)
        self.assertEqual(classify_probe(url, url, {"state":"RUNNING"}, "hi & 你好"), "RUNNING")
        self.assertEqual(classify_probe(url, url, {"state":"READY", "composer_text":"hi & 你好"}, "hi & 你好"), "NOT_READY")
        self.assertEqual(classify_probe(url.split("?")[0], url, {"state":"READY", "composer_text":"hi & 你好"}, "hi & 你好"), "READY")
        self.assertEqual(classify_probe("https://chatgpt.com/", url, {"state":"READY", "composer_text":"hi & 你好"}, "hi & 你好"), "BLOCKED")
        self.assertEqual(classify_probe("https://chatgpt.com/c/wrong", url, {"state":"READY", "composer_text":"hi & 你好"}, "hi & 你好"), "BLOCKED")
        self.assertEqual(classify_probe(url, url, {"state":"READY", "composer_text":"other"}, "hi & 你好"), "NOT_READY")



if __name__ == "__main__":
    unittest.main()
