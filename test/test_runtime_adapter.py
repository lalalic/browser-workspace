import ast
import unittest
from unittest.mock import patch

from chatgpt_queue_runtime import BrowserTurnDriver, DaemonTurnQueue
from fifo_queue import TurnQueue
from tempfile import TemporaryDirectory
from pathlib import Path


class BrowserAdapterTests(unittest.TestCase):
    def test_operator_reconcile_requires_explicit_evidence(self):
        with TemporaryDirectory() as directory:
            runtime = DaemonTurnQueue.__new__(DaemonTurnQueue)
            runtime.queue = TurnQueue(Path(directory) / "turns.db")
            class Notify:
                def __init__(self): self.count = 0
                def notify_enqueued(self): self.count += 1
            runtime.dispatcher = Notify()
            item = runtime.queue.enqueue("t", "hello", "key", now=10)
            runtime.queue.claim("w", now=10)
            runtime.queue.transition(item["id"], "w", "CHECKING", "SENDING", now=10)
            runtime.queue.transition(item["id"], "w", "SENDING", "UNCERTAIN", now=11, receipt="timeout")
            with self.assertRaises(ValueError):
                runtime.reconcile({"queue_id": item["id"], "accepted": False})
            self.assertEqual(runtime.reconcile({"queue_id": item["id"], "accepted": True,
                                                "evidence": "verified UI message"})["state"], "SENT")
            self.assertEqual(runtime.list_pending()["items"], [])

    def test_delayed_prompt_hydration_reuses_session(self):
        calls = []
        stopped = []
        def execute(sid, source):
            calls.append(sid)
            state = {"state": "NOT_READY", "composer_text": ""} if len(calls) == 1 else {
                "state": "READY", "composer_text": "hello"
            }
            return {"ok": True, "value": {
                "url": ("https://chatgpt.com/c/t?prompt=hello" if len(calls) == 1
                        else "https://chatgpt.com/c/t"), "state": state
            }}
        driver = BrowserTurnDriver(lambda url: {"session_id": "s"}, execute, stopped.append)
        item = {"id": "i", "project_id": None, "thread_id": "t", "message": "hello"}
        with patch("chatgpt_queue_runtime.time.sleep") as pause:
            self.assertEqual(driver.probe(item), "READY")
        self.assertEqual(calls, ["s", "s"])
        self.assertEqual(pause.call_count, 1)
        self.assertEqual(stopped, [])
        driver._close("i")
        self.assertEqual(stopped, ["s"])

    def test_slow_react_hydration_can_exceed_eight_seconds(self):
        calls = []
        def execute(sid, source):
            calls.append(sid)
            ready = len(calls) == 5
            return {"ok": True, "value": {
                "url": "https://chatgpt.com/c/t" if ready else "https://chatgpt.com/c/t?prompt=hello",
                "state": {"state": "READY" if ready else "NOT_READY",
                          "composer_text": "hello" if ready else ""},
            }}
        stopped = []
        driver = BrowserTurnDriver(lambda url: {"session_id": "s"}, execute, stopped.append)
        item = {"id": "i", "project_id": None, "thread_id": "t", "message": "hello"}
        # Each monotonic check advances five seconds; hydration takes 20 seconds.
        counter = iter(range(0, 60, 5))
        with patch("chatgpt_queue_runtime.time.monotonic", side_effect=lambda: next(counter)), \
             patch("chatgpt_queue_runtime.time.sleep"):
            self.assertEqual(driver.probe(item), "READY")
        self.assertEqual(len(calls), 5)
        self.assertEqual(stopped, [])
        driver._close("i")

    def test_stop_busy_exits_without_retry(self):
        calls = []
        def execute(sid, source):
            calls.append(sid)
            return {"ok": True, "value": {
                "url": "https://chatgpt.com/c/t",
                "state": {"state": "RUNNING", "stop_visible": True}
            }}
        stopped = []
        driver = BrowserTurnDriver(lambda url: {"session_id": "s"}, execute, stopped.append)
        item = {"id": "i", "project_id": None, "thread_id": "t", "message": "hello"}
        self.assertEqual(driver.probe(item), "RUNNING")
        self.assertEqual(calls, ["s"])
        self.assertEqual(stopped, ["s"])

    def test_driver_reuses_shared_send_and_does_not_wait_for_message(self):
        commands, stopped = [], []
        def execute(sid, source):
            ast.parse(source)
            commands.append(source)
            if len(commands) == 1:
                return {"ok": True, "value": {
                    "url": "https://chatgpt.com/c/t",
                    "state": {"state": "READY", "composer_text": "hello"}}}
            if len(commands) == 2:
                return {"ok": True, "value": {"clicked": True}}
            return {"ok": True, "value": True}

        driver = BrowserTurnDriver(lambda url: {"session_id": "s"}, execute, stopped.append)
        item = {"id": "i", "project_id": None, "thread_id": "t", "message": "hello"}
        self.assertEqual(driver.probe(item), "READY")
        self.assertEqual(driver.send_and_verify(item)["verified_by"], "send-button-disabled")
        self.assertEqual(len(commands), 4)
        self.assertNotIn("wait_for_load()", commands[0])
        self.assertIn("gate = js", commands[1])
        self.assertIn("not js(", commands[2])
        self.assertNotIn("user-message-bubble", "".join(commands))
        self.assertEqual(stopped, ["s"])

    def test_unverified_post_click_send_is_uncertain(self):
        calls = []
        def execute(_sid, source):
            calls.append(source)
            if len(calls) == 1:
                return {"ok": True, "value": {
                    "url": "https://chatgpt.com/c/t",
                    "state": {"state": "READY", "composer_text": "hello"}}}
            if len(calls) == 2:
                return {"ok": True, "value": {"clicked": True}}
            return {"ok": True, "value": False}

        driver = BrowserTurnDriver(lambda url: {"session_id": "s"}, execute, lambda sid: None)
        item = {"id": "i", "project_id": None, "thread_id": "t", "message": "hello"}
        self.assertEqual(driver.probe(item), "READY")
        counter = iter(range(100))
        with patch("chatgpt_queue_runtime.time.monotonic", side_effect=lambda: next(counter)), patch("chatgpt_queue_runtime.time.sleep"):
            result = driver.send_and_verify(item)
        self.assertTrue(result["clicked"])
        self.assertEqual(result["diagnostic"], "post_submit_send_state_unverified")

    def test_no_click_is_not_server_acceptance(self):
        calls = []
        def execute(_sid, source):
            calls.append(source)
            if len(calls) == 1:
                return {"ok": True, "value": {"url": "https://chatgpt.com/c/t",
                    "state": {"state": "READY",
                              "composer_text": "hello"}}}
            return {"ok": True, "value": {"clicked": False, "before": {}}}
        driver = BrowserTurnDriver(lambda url: {"session_id": "s"}, execute, lambda sid: None)
        item = {"id": "i", "project_id": None, "thread_id": "t", "message": "hello"}
        self.assertEqual(driver.probe(item), "READY")
        receipt = driver.send_and_verify(item)
        self.assertEqual(receipt["diagnostic"], "pre_send_gate_not_ready")
        self.assertNotIn("verified_by", receipt)


if __name__ == "__main__":
    unittest.main()
