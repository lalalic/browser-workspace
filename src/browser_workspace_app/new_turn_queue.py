"""Durable FIFO lanes for ChatGPT new-turn requests."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path


class NewTurnQueue:
    """SQLite-backed per-thread FIFO with conservative crash recovery."""

    def __init__(self, path: str | Path, *, clock=time.time):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.clock = clock
        self._initialize()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        return db

    def _initialize(self):
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS new_turn_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL UNIQUE,
                thread_id TEXT NOT NULL,
                request_json TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('queued','checking','submitting','submitted','unknown','failed','discarded')),
                available_at REAL NOT NULL,
                claim_token TEXT,
                outcome TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS new_turn_ready ON new_turn_requests(state, available_at, id)")
            db.execute("CREATE INDEX IF NOT EXISTS new_turn_lane ON new_turn_requests(thread_id, id, state)")

    def enqueue(self, request: dict, *, wake=None) -> dict:
        thread_id = str(request.get("thread_id") or "").strip()
        message = request.get("message")
        if not thread_id:
            raise ValueError("thread_id is required")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("message is required")
        now = self.clock()
        request_id = uuid.uuid4().hex
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cur = db.execute(
                "INSERT INTO new_turn_requests(request_id,thread_id,request_json,state,available_at,created_at,updated_at) VALUES(?,?,?,'queued',?,?,?)",
                (request_id, thread_id, json.dumps(request, ensure_ascii=False), now, now, now),
            )
            position = db.execute(
                "SELECT count(*) FROM new_turn_requests WHERE thread_id=? AND id<=? AND state IN ('queued','checking','submitting','unknown','failed')",
                (thread_id, cur.lastrowid),
            ).fetchone()[0]
            db.commit()
        if wake is not None:
            wake.set()
        return {"status": "queued", "position": position}

    def claim(self, *, now: float | None = None) -> dict | None:
        now = self.clock() if now is None else now
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""SELECT q.* FROM new_turn_requests q
                WHERE q.state='queued' AND q.available_at<=?
                  AND NOT EXISTS (
                    SELECT 1 FROM new_turn_requests active
                    WHERE active.thread_id=q.thread_id
                      AND active.id<q.id
                      AND active.state IN ('checking','submitting','unknown','failed')
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM new_turn_requests earlier
                    WHERE earlier.thread_id=q.thread_id AND earlier.id<q.id
                      AND earlier.state IN ('queued','checking','submitting','unknown','failed')
                  )
                ORDER BY q.id LIMIT 1""", (now,)).fetchone()
            if row is None:
                db.commit()
                return None
            token = uuid.uuid4().hex
            changed = db.execute(
                "UPDATE new_turn_requests SET state='checking',claim_token=?,updated_at=? WHERE id=? AND state='queued'",
                (token, now, row["id"]),
            ).rowcount
            db.commit()
            if not changed:
                return None
            return {"id": row["id"], "request_id": row["request_id"], "thread_id": row["thread_id"],
                    "request": json.loads(row["request_json"]), "claim_token": token}

    def mark_submitting(self, request_id: str, token: str):
        return self._transition(request_id, token, "checking", "submitting")

    def mark_submitted(self, request_id: str, token: str, outcome: dict | None = None, *, wake=None):
        changed = self._transition(request_id, token, "submitting", "submitted", outcome)
        if changed and wake is not None:
            wake.set()
        return changed

    def defer_busy(self, request_id: str, token: str, *, now: float | None = None, delay: int = 60):
        return self._transition(request_id, token, "checking", "queued", {"reason": "busy"},
                                available_at=(self.clock() if now is None else now) + delay)

    def defer_busy_after_submit_check(self, request_id: str, token: str, *, now: float | None = None, delay: int = 60):
        return self._transition(request_id, token, "submitting", "queued", {"reason": "busy_before_click"},
                                available_at=(self.clock() if now is None else now) + delay)

    def fail_before_submit(self, request_id: str, token: str, reason: str):
        return self._transition(request_id, token, "checking", "failed", {"reason": reason})

    def mark_unknown(self, request_id: str, token: str, reason: str):
        return self._transition(request_id, token, "submitting", "unknown", {"reason": reason})

    def recover_after_restart(self):
        """Pre-send claims are safe to retry; post-boundary claims need review."""
        now = self.clock()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            safe = db.execute("UPDATE new_turn_requests SET state='queued',claim_token=NULL,available_at=?,updated_at=? WHERE state='checking'", (now, now)).rowcount
            uncertain = db.execute("UPDATE new_turn_requests SET state='unknown',claim_token=NULL,outcome=? ,updated_at=? WHERE state='submitting'",
                                   (json.dumps({"reason": "daemon restarted during submission; verify ChatGPT thread before resolving"}), now)).rowcount
            db.commit()
        return {"requeued_before_submit": safe, "unknown_submission_outcomes": uncertain}

    def resolve_unknown(self, request_id: str, resolution: str):
        if resolution not in {"submitted", "retry"}:
            raise ValueError("resolution must be submitted or retry")
        now = self.clock()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM new_turn_requests WHERE request_id=?", (request_id,)).fetchone()
            if row is None or row["state"] != "unknown":
                db.rollback()
                return False
            state = "submitted" if resolution == "submitted" else "queued"
            outcome = {"resolution": resolution, "resolved_at": now}
            db.execute("UPDATE new_turn_requests SET state=?,claim_token=NULL,available_at=?,outcome=?,updated_at=? WHERE request_id=?",
                       (state, now, json.dumps(outcome), now, request_id))
            db.commit()
        return True

    def resolve_failed(self, request_id: str, disposition: str):
        if disposition not in {"retry", "discard"}:
            raise ValueError("disposition must be retry or discard")
        now = self.clock()
        state = "queued" if disposition == "retry" else "discarded"
        outcome = json.dumps({"operator_disposition": disposition, "resolved_at": now})
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute(
                "UPDATE new_turn_requests SET state=?,claim_token=NULL,available_at=?,outcome=?,updated_at=? WHERE request_id=? AND state='failed'",
                (state, now, outcome, now, request_id),
            ).rowcount
            db.commit()
        return bool(count)

    def _transition(self, request_id, token, expected, state, outcome=None, available_at=None):
        now = self.clock()
        with self._connect() as db:
            values = (state, available_at if available_at is not None else now,
                      json.dumps(outcome, ensure_ascii=False) if outcome is not None else None,
                      now, state, request_id, token, expected)
            count = db.execute("""UPDATE new_turn_requests
                SET state=?,available_at=?,outcome=COALESCE(?,outcome),updated_at=?,
                    claim_token=CASE WHEN ?='submitting' THEN claim_token ELSE NULL END
                WHERE request_id=? AND claim_token=? AND state=?""", values).rowcount
        return bool(count)

    def next_wakeup(self, *, now: float | None = None):
        now = self.clock() if now is None else now
        with self._connect() as db:
            row = db.execute("""SELECT min(q.available_at) FROM new_turn_requests q
                WHERE q.state='queued' AND NOT EXISTS (
                    SELECT 1 FROM new_turn_requests earlier WHERE earlier.thread_id=q.thread_id
                      AND earlier.id<q.id AND earlier.state IN ('queued','checking','submitting','unknown','failed')
                )""").fetchone()
        return max(0.0, row[0] - now) if row and row[0] is not None else None

    def snapshot(self):
        with self._connect() as db:
            return [dict(row) for row in db.execute("SELECT id,request_id,thread_id,state,available_at,outcome FROM new_turn_requests ORDER BY id")]
