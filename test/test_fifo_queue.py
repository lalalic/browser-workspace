import concurrent.futures
import tempfile
import unittest
from pathlib import Path

from fifo_queue import TurnQueue


class FIFOTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "turns.sqlite3"
        self.q = TurnQueue(self.path)

    def test_immediate_persistence_and_restart(self):
        original = self.q.enqueue("A", "one", "req-1", now=100)
        restarted = TurnQueue(self.path)
        self.assertEqual(restarted.rows()[0]["id"], original["id"])
        self.assertEqual(restarted.claim("worker", now=101)["id"], original["id"])

    def test_idempotency_and_payload_conflict(self):
        first = self.q.enqueue("A", "one", "req-1", now=100)
        self.assertEqual(first["id"], self.q.enqueue("A", "one", "req-1", now=101)["id"])
        self.assertEqual(len(self.q.rows()), 1)
        with self.assertRaises(ValueError):
            self.q.enqueue("A", "DIFFERENT", "req-1")

    def test_thread_fifo_and_parallel_independent_heads(self):
        a = self.q.enqueue("A", "one", "a1", now=100)
        b = self.q.enqueue("A", "two", "a2", now=100)
        other = self.q.enqueue("B", "other", "b1", now=100)
        self.assertEqual(self.q.claim("w1", now=100)["id"], a["id"])
        self.assertEqual(self.q.claim("w2", now=100)["id"], other["id"])
        self.assertIsNone(self.q.claim("w3", now=100))
        self.q.transition(a["id"], "w1", "CHECKING", "SENDING", now=100)
        self.q.transition(a["id"], "w1", "SENDING", "SENT", now=101, receipt="accepted user turn")
        self.assertIsNone(self.q.claim("w3", now=102))
        self.assertEqual(self.q.claim("w3", now=161)["id"], b["id"])

    def test_wait_for_stop_does_not_block_other_thread(self):
        a = self.q.enqueue("A", "one", "a", now=100)
        b = self.q.enqueue("B", "two", "b", now=100)
        self.q.claim("w1", now=100)
        self.q.transition(a["id"], "w1", "CHECKING", "WAITING", now=100, delay=60)
        self.assertEqual(self.q.claim("w2", now=100)["id"], b["id"])
        # A slow probe must not expire B's lease after 30 seconds.
        self.assertIsNone(self.q.claim("w3", now=159))
        self.assertEqual(self.q.rows()[0]["state"], "WAITING")

    def test_sending_crash_requires_explicit_reconciliation(self):
        first = self.q.enqueue("A", "one", "a", now=100)
        self.q.enqueue("A", "two", "a2", now=100)
        self.q.claim("w1", now=100, lease_seconds=10)
        self.q.transition(first["id"], "w1", "CHECKING", "SENDING", now=100)
        self.assertIsNone(TurnQueue(self.path).claim("w2", now=221))
        self.assertEqual(self.q.rows()[0]["state"], "UNCERTAIN")
        with self.assertRaises(ValueError):
            self.q.transition(first["id"], "w2", "UNCERTAIN", "WAITING", now=132)
        self.q.transition(first["id"], "w2", "UNCERTAIN", "SENT", now=132, delay=0, receipt="observed user turn")
        self.assertEqual(self.q.claim("w2", now=133)["message"], "two")

    def test_three_fifo_turns_and_cross_thread_parallel_heads(self):
        turns = [self.q.enqueue("A", f"turn-{i}", f"a-{i}", now=100) for i in range(3)]
        b = self.q.enqueue("B", "parallel-b", "b", now=100)
        c = self.q.enqueue("C", "parallel-c", "c", now=100)
        claims = [self.q.claim(f"w{i}", now=100) for i in range(5)]
        self.assertEqual({x["id"] for x in claims if x},
                         {turns[0]["id"], b["id"], c["id"]})
        for idx in range(3):
            worker = f"sequence-{idx}"
            if idx == 0:
                # Reuse the first worker's claim rather than a new claim.
                worker = next(x["lease_owner"] for x in claims if x and x["id"] == turns[0]["id"])
            else:
                claimed = self.q.claim(worker, now=100 + idx * 61)
                self.assertEqual(claimed["id"], turns[idx]["id"])
            when = 100 + idx * 61
            self.q.transition(turns[idx]["id"], worker, "CHECKING", "SENDING", now=when)
            self.q.transition(turns[idx]["id"], worker, "SENDING", "SENT", now=when + 1,
                              delay=60, receipt=f"user-id-{idx}")
        self.assertEqual([x["state"] for x in self.q.rows()[:3]], ["SENT"] * 3)

    def test_concurrent_claim_single_winner(self):
        self.q.enqueue("A", "one", "a", now=100)
        def claim(i):
            return TurnQueue(self.path).claim(f"w{i}", now=100)
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            outcomes = list(pool.map(claim, range(12)))
        self.assertEqual(sum(bool(x) for x in outcomes), 1)

    def test_expired_lease_cannot_enter_sending_without_reclaim(self):
        item = self.q.enqueue("A", "hello", "a", now=100)
        self.q.claim("worker", now=100, lease_seconds=10)
        with self.assertRaisesRegex(ValueError, "expired lease"):
            self.q.transition(item["id"], "worker", "CHECKING", "SENDING", now=111)
        self.assertEqual(self.q.claim("new-worker", now=111)["id"], item["id"])

    def test_sent_requires_cooldown_before_successor_check(self):
        a = self.q.enqueue("A", "one", "a", now=100)
        b = self.q.enqueue("A", "two", "b", now=100)
        self.q.claim("w", now=100)
        self.q.transition(a["id"], "w", "CHECKING", "SENDING", now=101)
        self.q.transition(a["id"], "w", "SENDING", "SENT", now=102, delay=60, receipt="user bubble")
        self.assertIsNone(self.q.claim("next", now=161))
        self.assertEqual(self.q.claim("next", now=162)["id"], b["id"])

    def test_stale_worker_fenced(self):
        first = self.q.enqueue("A", "one", "a", now=100)
        self.q.claim("old", now=100, lease_seconds=10)
        self.assertEqual(self.q.claim("new", now=111)["id"], first["id"])
        with self.assertRaises(ValueError):
            self.q.transition(first["id"], "old", "CHECKING", "SENDING", now=112)


if __name__ == "__main__":
    unittest.main()
