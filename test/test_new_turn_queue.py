import multiprocessing
import threading
from pathlib import Path

from browser_workspace_app.new_turn_queue import NewTurnQueue


def _claim_in_process(path, barrier, output):
    queue = NewTurnQueue(path)
    barrier.wait()
    output.put(queue.claim())


def _enqueue_in_process(path, index, barrier):
    queue = NewTurnQueue(path)
    barrier.wait()
    queue.enqueue({"thread_id": "shared", "message": f"child-{index}"})


def _finish_submitted(queue, claim):
    assert queue.mark_submitting(claim["request_id"], claim["claim_token"])
    assert queue.mark_submitted(claim["request_id"], claim["claim_token"], {"verified_by": "test"})


def test_atomic_claim_is_single_per_thread_across_processes(tmp_path):
    path = str(tmp_path / "queue.sqlite3")
    q = NewTurnQueue(path)
    q.enqueue({"thread_id": "one", "message": "first"})
    q.enqueue({"thread_id": "one", "message": "second"})
    ctx = multiprocessing.get_context("fork")
    barrier = ctx.Barrier(2)
    output = ctx.Queue()
    workers = [ctx.Process(target=_claim_in_process, args=(path, barrier, output)) for _ in range(2)]
    for p in workers:
        p.start()
    results = [output.get(timeout=15) for _ in workers]
    for p in workers:
        p.join(15)
        assert p.exitcode == 0
    claims = [value for value in results if value]
    assert len(claims) == 1
    assert claims[0]["request"]["message"] == "first"


def test_different_threads_claim_independently_and_same_thread_is_fifo(tmp_path):
    q = NewTurnQueue(tmp_path / "queue.sqlite3")
    q.enqueue({"thread_id": "one", "message": "one-a"})
    q.enqueue({"thread_id": "one", "message": "one-b"})
    q.enqueue({"thread_id": "two", "message": "two-a"})
    first = q.claim()
    second = q.claim()
    assert {first["thread_id"], second["thread_id"]} == {"one", "two"}
    assert q.claim() is None
    one = first if first["thread_id"] == "one" else second
    _finish_submitted(q, one)
    next_one = q.claim()
    assert next_one["request"]["message"] == "one-b"


def test_restart_requeues_pre_send_claim_but_blocks_unknown_submission(tmp_path):
    path = tmp_path / "queue.sqlite3"
    q = NewTurnQueue(path)
    q.enqueue({"thread_id": "one", "message": "safe"})
    safe = q.claim()
    q.enqueue({"thread_id": "two", "message": "uncertain"})
    uncertain = q.claim()
    assert q.mark_submitting(uncertain["request_id"], uncertain["claim_token"])
    assert q.recover_after_restart() == {"requeued_before_submit": 1, "unknown_submission_outcomes": 1}
    q = NewTurnQueue(path)
    recovered = q.claim()
    assert recovered["request"]["message"] == "safe"
    assert q.claim() is None
    assert q.resolve_unknown(uncertain["request_id"], "submitted")
    _finish_submitted(q, recovered)
    assert q.claim() is None


def test_busy_lane_rechecks_after_sixty_seconds_and_enqueue_returns_accepted(tmp_path):
    now = [1000.0]
    q = NewTurnQueue(tmp_path / "queue.sqlite3", clock=lambda: now[0])
    accepted = q.enqueue({"thread_id": "one", "message": "first"})
    q.enqueue({"thread_id": "one", "message": "second"})
    assert accepted == {"status": "queued", "position": 1}
    first = q.claim()
    assert q.defer_busy(first["request_id"], first["claim_token"])
    assert q.claim() is None
    assert q.next_wakeup() == 60
    now[0] += 60
    assert q.claim()["request"]["message"] == "first"


def test_busy_recheck_at_click_boundary_releases_submission_claim(tmp_path):
    now = [500.0]
    q = NewTurnQueue(tmp_path / "queue.sqlite3", clock=lambda: now[0])
    q.enqueue({"thread_id": "one", "message": "first"})
    claim = q.claim()
    assert q.mark_submitting(claim["request_id"], claim["claim_token"])
    assert q.defer_busy_after_submit_check(claim["request_id"], claim["claim_token"])
    assert q.snapshot()[0]["state"] == "queued"
    assert q.next_wakeup() == 60


def test_enqueue_and_successful_dispatch_trigger_immediate_wakeup(tmp_path):
    q = NewTurnQueue(tmp_path / "queue.sqlite3")
    wake = threading.Event()
    assert q.enqueue({"thread_id": "one", "message": "send"}, wake=wake)["status"] == "queued"
    assert wake.is_set()
    wake.clear()
    claim = q.claim()
    assert q.mark_submitting(claim["request_id"], claim["claim_token"])
    assert q.mark_submitted(claim["request_id"], claim["claim_token"], {"ok": True}, wake=wake)
    assert wake.is_set()


def test_concurrent_child_reports_keep_commit_order_in_fifo(tmp_path):
    path = str(tmp_path / "queue.sqlite3")
    ctx = multiprocessing.get_context("fork")
    barrier = ctx.Barrier(8)
    workers = [ctx.Process(target=_enqueue_in_process, args=(path, i, barrier)) for i in range(8)]
    for p in workers:
        p.start()
    for p in workers:
        p.join(15)
        assert p.exitcode == 0
    q = NewTurnQueue(path)
    ordered = []
    ordered_ids = []
    while claim := q.claim():
        ordered.append(claim["request"]["message"])
        ordered_ids.append(claim["id"])
        _finish_submitted(q, claim)
    rows = q.snapshot()
    assert len(ordered) == 8
    assert len(set(ordered)) == 8
    assert ordered_ids == [r["id"] for r in rows]
    assert all(r["state"] == "submitted" for r in rows)


def test_unknown_outcome_is_never_claimed_until_explicit_resolution(tmp_path):
    q = NewTurnQueue(tmp_path / "queue.sqlite3")
    q.enqueue({"thread_id": "one", "message": "possibly sent"})
    q.enqueue({"thread_id": "one", "message": "next"})
    claim = q.claim()
    assert q.mark_submitting(claim["request_id"], claim["claim_token"])
    assert q.mark_unknown(claim["request_id"], claim["claim_token"], "lost response")
    assert q.claim() is None
    assert q.resolve_unknown(claim["request_id"], "retry")
    retry = q.claim()
    assert retry["request"]["message"] == "possibly sent"

