"""Durable per-thread FIFO scheduler for WebHelm daemon.
"""
from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


ACTIVE = ("QUEUED", "CHECKING", "WAITING", "SENDING", "UNCERTAIN", "BLOCKED")


class TurnQueue:
    def __init__(self, path: str | Path):
        self.path = str(path)
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS turns (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE,
                    idem_key TEXT NOT NULL UNIQUE,
                    project_id TEXT,
                    thread_id TEXT NOT NULL,
                    message TEXT NOT NULL,
                    state TEXT NOT NULL,
                    lease_owner TEXT,
                    lease_until REAL,
                    next_check_at REAL NOT NULL,
                    created_at REAL NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    receipt TEXT
                );
                CREATE INDEX IF NOT EXISTS turns_thread_order ON turns(thread_id, seq);
                CREATE TABLE IF NOT EXISTS merged_requests (
                    idem_key TEXT PRIMARY KEY,
                    project_id TEXT,
                    thread_id TEXT NOT NULL,
                    message TEXT NOT NULL,
                    queue_id TEXT NOT NULL
                );
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(turns)")}
            if "mergeable" not in columns:
                db.execute("ALTER TABLE turns ADD COLUMN mergeable INTEGER NOT NULL DEFAULT 0")

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA busy_timeout=5000")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            with db:
                yield db
        finally:
            db.close()

    def enqueue(self, thread_id, message, idem_key, project_id=None, now=None, mergeable=False):
        if not thread_id or not message or not idem_key:
            raise ValueError("thread_id, message, idem_key required")
        if type(mergeable) is not bool:
            raise ValueError("mergeable must be a boolean")
        now = time.time() if now is None else now
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            merged = db.execute("SELECT * FROM merged_requests WHERE idem_key=?", (idem_key,)).fetchone()
            if merged:
                if (merged["thread_id"], merged["message"], merged["project_id"]) != (thread_id, message, project_id):
                    raise ValueError("idempotency key reused with different payload")
                return dict(db.execute("SELECT * FROM turns WHERE id=?", (merged["queue_id"],)).fetchone())
            row = db.execute("SELECT * FROM turns WHERE idem_key=?", (idem_key,)).fetchone()
            if row:
                if (row["thread_id"], row["message"], row["project_id"]) != (thread_id, message, project_id):
                    raise ValueError("idempotency key reused with different payload")
                return dict(row)
            if mergeable:
                tail = db.execute("SELECT * FROM turns WHERE thread_id=? ORDER BY seq DESC LIMIT 1", (thread_id,)).fetchone()
                if (tail and tail["mergeable"] and tail["project_id"] == project_id
                        and tail["state"] in ("QUEUED", "WAITING")):
                    db.execute("INSERT OR IGNORE INTO merged_requests VALUES(?,?,?,?,?)",
                               (tail["idem_key"], tail["project_id"], thread_id, tail["message"], tail["id"]))
                    db.execute("INSERT INTO merged_requests VALUES(?,?,?,?,?)",
                               (idem_key, project_id, thread_id, message, tail["id"]))
                    db.execute("UPDATE turns SET message=message || ? WHERE id=?", ("\n" + message, tail["id"]))
                    return dict(db.execute("SELECT * FROM turns WHERE id=?", (tail["id"],)).fetchone())
            item_id = str(uuid.uuid4())
            db.execute("INSERT INTO turns(id, idem_key, project_id, thread_id, message, state, next_check_at, created_at, mergeable) VALUES(?,?,?,?,?,?,?,?,?)",
                       (item_id, idem_key, project_id, thread_id, message, "QUEUED", now, now, int(mergeable)))
            return dict(db.execute("SELECT * FROM turns WHERE id=?", (item_id,)).fetchone())

    def claim(self, owner, now=None, lease_seconds=120):
        """Atomically claim an eligible head from each thread, one at a time."""
        now = time.time() if now is None else now
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            # CHECKING leases can be re-acquired. SENDING leases must NEVER
            # be re-sent: recovery moves them into UNCERTAIN first.
            db.execute("UPDATE turns SET state='UNCERTAIN', lease_owner=NULL, lease_until=NULL "
                       "WHERE state='SENDING' AND lease_until<=?", (now,))
            db.execute("UPDATE turns SET state='WAITING', lease_owner=NULL, lease_until=NULL, next_check_at=? "
                       "WHERE state='CHECKING' AND lease_until<=?", (now, now))
            row = db.execute("""
                SELECT t.* FROM turns t
                WHERE t.state IN ('QUEUED','WAITING') AND t.next_check_at<=?
                  AND NOT EXISTS (
                    SELECT 1 FROM turns older
                    WHERE older.thread_id=t.thread_id AND older.seq<t.seq
                      AND (older.state NOT IN ('SENT','CANCELLED') OR (older.state='SENT' AND older.next_check_at>?)))
                ORDER BY t.seq LIMIT 1
            """, (now, now)).fetchone()
            if not row:
                return None
            db.execute("UPDATE turns SET state='CHECKING', lease_owner=?, lease_until=?, attempts=attempts+1 WHERE id=?",
                       (owner, now+lease_seconds, row["id"]))
            return dict(db.execute("SELECT * FROM turns WHERE id=?", (row["id"],)).fetchone())

    def transition(self, item_id, owner, source, target, *, now=None, delay=60, receipt=None):
        """Fenced transition: a stale worker cannot overwrite a newer result."""
        now = time.time() if now is None else now
        if (source, target) not in {
            ("CHECKING", "WAITING"), ("CHECKING", "SENDING"),
            ("CHECKING", "BLOCKED"), ("SENDING", "SENT"),
            ("SENDING", "UNCERTAIN"), ("UNCERTAIN", "SENT"),
            ("UNCERTAIN", "WAITING"), ("BLOCKED", "WAITING"),
        }:
            raise ValueError("invalid transition")
        # Only explicit reconciliation can clear UNCERTAIN; caller must
        # provide read-only evidence in `receipt` to authorize that action.
        if source == "UNCERTAIN" and not receipt:
            raise ValueError("UNCERTAIN requires reconciliation evidence")
        if source == "BLOCKED" and not receipt:
            raise ValueError("BLOCKED requires unblock evidence")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM turns WHERE id=?", (item_id,)).fetchone()
            if not row or row["state"] != source:
                raise ValueError("stale state")
            if source in ("CHECKING", "SENDING") and row["lease_owner"] != owner:
                raise ValueError("stale owner")
            if source in ("CHECKING", "SENDING") and row["lease_until"] <= now:
                raise ValueError("expired lease")
            release = target in ("WAITING", "SENT", "UNCERTAIN", "BLOCKED")
            db.execute("UPDATE turns SET state=?, lease_owner=?, lease_until=?, next_check_at=?, receipt=? WHERE id=?",
                       (target, None if release else owner,
                        None if release else now+120,
                        now + delay if target in ("WAITING", "SENT") else now,
                        receipt, item_id))

    def rows(self):
        with self.db() as db:
            return [dict(row) for row in db.execute("SELECT * FROM turns ORDER BY seq")]
