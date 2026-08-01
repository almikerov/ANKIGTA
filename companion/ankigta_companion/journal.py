"""The durable Review Transaction journal.

A rating that crashed mid-flight leaves a question no amount of retrying can
answer on its own: did Anki commit it? Prototype 0003 established the shape of
the answer — record the intent and the before-state *before* invoking the
scheduler, then on restart compare against evidence rather than guessing.

The journal is keyed by `(collection identity, reviewTransactionId)`, because a
`reviewTransactionId` means nothing outside the collection it was minted for
(ADR 0009). `cardId` and rating are immutable once recorded: reusing an id for
anything else is a conflict, not a retry.

`outcome_unknown` is a quarantine state, not an invitation to guess. It blocks
the affected card, a collection switch, and session restoration until evidence
resolves it.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from .collection_identity import AnkiCardIdentity


SCHEMA_VERSION = 1

RECEIVED = "received"
RATING_STARTED = "rating_started"
RATING_APPLIED = "rating_applied"
COMPLETED = "completed"
OUTCOME_UNKNOWN = "outcome_unknown"

TERMINAL_STATES = frozenset({COMPLETED, OUTCOME_UNKNOWN})
#: States that still owe the user an answer and block switching or rebuilding.
BLOCKING_STATES = frozenset({RECEIVED, RATING_STARTED, RATING_APPLIED, OUTCOME_UNKNOWN})

MAX_RESENDS = 1


class JournalError(RuntimeError):
    """A categorized journal failure."""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category
        self.message = message


@dataclass(frozen=True)
class JournalRecord:
    collection_uuid: str
    review_transaction_id: str
    card_id: int
    rating: str
    state: str
    scheduler_calls: int
    resends: int
    before: dict[str, object]
    result: dict[str, object] | None
    reason: str | None

    @property
    def identity(self) -> AnkiCardIdentity:
        return AnkiCardIdentity(self.collection_uuid, self.card_id)

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL_STATES


#: Returns True when evidence proves the rating was applied, False when it
#: proves it was not, and None when neither can be proved.
Verifier = Callable[[JournalRecord], bool | None]


@dataclass(frozen=True)
class Reconciliation:
    record: JournalRecord
    action: str  # "confirmed" | "resend" | "quarantined" | "none"


class ReviewJournal:
    """Companion-owned durable record of every Review Transaction."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._lock = Lock()
        self._connection = sqlite3.connect(self._path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS review_transactions (
                    collection_uuid TEXT NOT NULL,
                    review_transaction_id TEXT NOT NULL,
                    card_id INTEGER NOT NULL,
                    rating TEXT NOT NULL,
                    state TEXT NOT NULL,
                    scheduler_calls INTEGER NOT NULL DEFAULT 0,
                    resends INTEGER NOT NULL DEFAULT 0,
                    before_json TEXT NOT NULL,
                    result_json TEXT,
                    reason TEXT,
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
                    PRIMARY KEY (collection_uuid, review_transaction_id)
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS journal_meta (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    version INTEGER NOT NULL
                )
                """
            )
            self._connection.execute(
                "INSERT OR IGNORE INTO journal_meta (singleton, version) VALUES (1, ?)",
                (SCHEMA_VERSION,),
            )

    # ------------------------------------------------------------------ reads

    def get(
        self,
        collection_uuid: str,
        review_transaction_id: str,
    ) -> JournalRecord | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT * FROM review_transactions
                WHERE collection_uuid = ? AND review_transaction_id = ?
                """,
                (collection_uuid, review_transaction_id),
            ).fetchone()
        return self._record(row) if row is not None else None

    def find(self, review_transaction_id: str) -> tuple[JournalRecord, ...]:
        """Every record carrying this id, across collections.

        A `reviewTransactionId` is only unique within its collection, so this
        can legitimately return more than one; callers still compare identity.
        """
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM review_transactions WHERE review_transaction_id = ?",
                (review_transaction_id,),
            ).fetchall()
        return tuple(self._record(row) for row in rows)

    def blocking(self, collection_uuid: str | None = None) -> tuple[JournalRecord, ...]:
        """Records that must be reconciled before switching or rebuilding."""
        placeholders = ",".join("?" for _ in BLOCKING_STATES)
        parameters: list[object] = list(sorted(BLOCKING_STATES))
        query = (
            f"SELECT * FROM review_transactions WHERE state IN ({placeholders})"
        )
        if collection_uuid is not None:
            query += " AND collection_uuid = ?"
            parameters.append(collection_uuid)
        with self._lock:
            rows = self._connection.execute(query, parameters).fetchall()
        return tuple(self._record(row) for row in rows)

    # ----------------------------------------------------------------- writes

    def record_intent(
        self,
        identity: AnkiCardIdentity,
        review_transaction_id: str,
        rating: str,
        before: dict[str, object],
    ) -> JournalRecord:
        """Make the intent and before-state durable before Anki is invoked."""
        existing = self.get(identity.collection_uuid, review_transaction_id)
        if existing is not None:
            if existing.card_id != identity.card_id or existing.rating != rating:
                raise JournalError(
                    "transaction_conflict",
                    "reviewTransactionId was already used for a different rating",
                )
            return existing
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO review_transactions (
                    collection_uuid, review_transaction_id, card_id, rating,
                    state, scheduler_calls, resends, before_json
                ) VALUES (?, ?, ?, ?, ?, 0, 0, ?)
                """,
                (
                    identity.collection_uuid,
                    review_transaction_id,
                    identity.card_id,
                    rating,
                    RECEIVED,
                    json.dumps(before),
                ),
            )
        found = self.get(identity.collection_uuid, review_transaction_id)
        assert found is not None
        return found

    def mark_rating_started(self, record: JournalRecord) -> JournalRecord:
        """Count the scheduler invocation before making it, never after.

        A crash between the write and the call must look like a call that may
        have happened, which is exactly what reconciliation is for.
        """
        return self._transition(
            record,
            RATING_STARTED,
            scheduler_calls=record.scheduler_calls + 1,
        )

    def mark_applied(
        self,
        record: JournalRecord,
        result: dict[str, object],
    ) -> JournalRecord:
        return self._transition(record, RATING_APPLIED, result=result)

    def mark_completed(
        self,
        record: JournalRecord,
        result: dict[str, object] | None = None,
    ) -> JournalRecord:
        return self._transition(
            record,
            COMPLETED,
            result=result if result is not None else record.result,
        )

    def mark_outcome_unknown(
        self,
        record: JournalRecord,
        reason: str,
    ) -> JournalRecord:
        return self._transition(record, OUTCOME_UNKNOWN, reason=reason)

    def _transition(
        self,
        record: JournalRecord,
        state: str,
        *,
        scheduler_calls: int | None = None,
        resends: int | None = None,
        result: dict[str, object] | None = None,
        reason: str | None = None,
    ) -> JournalRecord:
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE review_transactions
                SET state = ?,
                    scheduler_calls = ?,
                    resends = ?,
                    result_json = ?,
                    reason = ?,
                    updated_at = strftime('%s', 'now')
                WHERE collection_uuid = ? AND review_transaction_id = ?
                """,
                (
                    state,
                    record.scheduler_calls if scheduler_calls is None else scheduler_calls,
                    record.resends if resends is None else resends,
                    json.dumps(result) if result is not None else None,
                    reason,
                    record.collection_uuid,
                    record.review_transaction_id,
                ),
            )
        found = self.get(record.collection_uuid, record.review_transaction_id)
        assert found is not None
        return found

    # --------------------------------------------------------- reconciliation

    def reconcile(self, verify: Verifier) -> tuple[Reconciliation, ...]:
        """Resolve every unfinished transaction against evidence.

        Called on startup. A record that was never handed to the scheduler is
        safe to resend under the same id; one that may have been applied is
        decided by evidence alone.
        """
        results: list[Reconciliation] = []
        for record in self.blocking():
            if record.state == RATING_APPLIED:
                results.append(
                    Reconciliation(self.mark_completed(record), "confirmed")
                )
                continue
            if record.state == RECEIVED:
                # The scheduler was never invoked, so nothing can have been
                # applied; the same transaction may be sent again.
                results.append(Reconciliation(record, "resend"))
                continue

            proved = verify(record)
            if proved is True:
                results.append(
                    Reconciliation(self.mark_completed(record), "confirmed")
                )
            elif proved is False:
                if record.resends >= MAX_RESENDS:
                    results.append(
                        Reconciliation(
                            self.mark_outcome_unknown(record, "resend_limit"),
                            "quarantined",
                        )
                    )
                else:
                    resent = self._transition(
                        record,
                        RECEIVED,
                        resends=record.resends + 1,
                    )
                    results.append(Reconciliation(resent, "resend"))
            else:
                results.append(
                    Reconciliation(
                        self.mark_outcome_unknown(record, "indeterminate"),
                        "quarantined",
                    )
                )
        return tuple(results)

    # ------------------------------------------------------------------- gc

    def collect_garbage(self, acknowledged: set[str]) -> int:
        """Delete completed records both sides are finished with.

        `outcome_unknown` is never collected: it is the only remaining record
        that a rating happened at all.
        """
        if not acknowledged:
            return 0
        placeholders = ",".join("?" for _ in acknowledged)
        with self._lock, self._connection:
            cursor = self._connection.execute(
                f"""
                DELETE FROM review_transactions
                WHERE state = ? AND review_transaction_id IN ({placeholders})
                """,
                [COMPLETED, *sorted(acknowledged)],
            )
        return int(cursor.rowcount)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @staticmethod
    def _record(row: sqlite3.Row) -> JournalRecord:
        return JournalRecord(
            collection_uuid=row["collection_uuid"],
            review_transaction_id=row["review_transaction_id"],
            card_id=int(row["card_id"]),
            rating=row["rating"],
            state=row["state"],
            scheduler_calls=int(row["scheduler_calls"]),
            resends=int(row["resends"]),
            before=json.loads(row["before_json"]),
            result=(
                json.loads(row["result_json"])
                if row["result_json"] is not None
                else None
            ),
            reason=row["reason"],
        )
