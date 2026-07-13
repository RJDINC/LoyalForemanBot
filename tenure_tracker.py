"""
SQLite-backed tenure tracker.

Schema:
    foremen(
        discord_id      TEXT PRIMARY KEY,
        patreon_id      TEXT NOT NULL,
        foreman_since   TEXT NOT NULL,   -- ISO datetime, UTC. Reset on a >grace lapse.
        last_active_at  TEXT NOT NULL,   -- last time we saw them active+paid
        last_seen_at    TEXT NOT NULL,   -- last time the reconciler saw them at all
        role_granted    INTEGER NOT NULL DEFAULT 0
    )

The tracker is the source of truth for "have they been Foreman for N continuous days?"
Patreon's API only tells us "are they Foreman right now?" — we maintain history ourselves.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Iterator


# Sentinel patreon_id for rows created by the /foreman-grant admin command.
# These rows are exempt from reconciliation cleanup and eligibility checks:
# the role sticks until /foreman-revoke, or until the person shows up on
# Patreon as a normally-tracked Foreman (upsert_active then overwrites this).
MANUAL_OVERRIDE_PATREON_ID = "manual-override"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse(raw: str) -> datetime:
    return datetime.fromisoformat(raw)


def compute_streak_start(
    paid_charge_dates: list[datetime],
    *,
    now: datetime,
    max_gap_days: float,
) -> datetime | None:
    """
    Given the dates of a patron's SUCCESSFUL charges, return the start date of
    their most recent UNBROKEN monthly streak — or None if they have no live
    streak at all.

    Walks backward from the newest charge, chaining charges while the gap
    between consecutive ones is <= max_gap_days (one billing cycle plus grace).
    Any bigger gap breaks the chain: earlier charges are ancient history and
    earn no credit. A patron who paid in June 2025, lapsed, and paid again in
    June 2026 gets credit only from the June 2026 charge.
    """
    if not paid_charge_dates:
        return None
    ds = sorted(paid_charge_dates, reverse=True)
    # Newest charge must itself be recent, otherwise there is no live streak.
    if (now - ds[0]).total_seconds() / 86400.0 > max_gap_days:
        return None
    streak_start = ds[0]
    prev = ds[0]
    for d in ds[1:]:
        gap = (prev - d).total_seconds() / 86400.0
        if gap > max_gap_days:
            break
        streak_start = d
        prev = d
    return streak_start


@dataclass
class TenureRow:
    discord_id: str
    patreon_id: str
    foreman_since: datetime
    last_active_at: datetime
    last_seen_at: datetime
    role_granted: bool

    def tenure_days(self, now: datetime | None = None) -> float:
        now = now or _utcnow()
        return (now - self.foreman_since).total_seconds() / 86400.0


class TenureTracker:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS foremen (
                    discord_id     TEXT PRIMARY KEY,
                    patreon_id     TEXT NOT NULL,
                    foreman_since  TEXT NOT NULL,
                    last_active_at TEXT NOT NULL,
                    last_seen_at   TEXT NOT NULL,
                    role_granted   INTEGER NOT NULL DEFAULT 0
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS excluded (
                    discord_id  TEXT PRIMARY KEY,
                    excluded_at TEXT NOT NULL,
                    reason      TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS bot_state (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

    # --- read ---------------------------------------------------------------

    def get(self, discord_id: str) -> TenureRow | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM foremen WHERE discord_id = ?", (discord_id,)
            ).fetchone()
        return _row(row) if row else None

    def all_rows(self) -> list[TenureRow]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM foremen").fetchall()
        return [_row(r) for r in rows]

    # --- write --------------------------------------------------------------

    def upsert_active(
        self,
        *,
        discord_id: str,
        patreon_id: str,
        now: datetime | None = None,
        historical_since: datetime | None = None,
    ) -> TenureRow:
        """
        Called when we see a member who IS currently an active paying Foreman.

        On the FIRST sighting (no existing row), `historical_since` is used as
        `foreman_since` if it's set and not in the future — so an existing
        long-time patron immediately gets credit for their actual tenure
        instead of starting their clock at the moment the bot first saw them.
        On subsequent sightings `historical_since` is ignored (we trust our
        own row, which knows about lapses we've observed).
        """
        now = now or _utcnow()
        existing = self.get(discord_id)
        if existing is None:
            # Pick the earlier of (historical_since, now) so we never get a future start date.
            since = now
            if historical_since is not None and historical_since < now:
                since = historical_since
            with self._conn() as c:
                c.execute(
                    """INSERT INTO foremen
                       (discord_id, patreon_id, foreman_since, last_active_at, last_seen_at, role_granted)
                       VALUES (?, ?, ?, ?, ?, 0)""",
                    (discord_id, patreon_id, _iso(since), _iso(now), _iso(now)),
                )
            return self.get(discord_id)  # type: ignore[return-value]

        with self._conn() as c:
            c.execute(
                "UPDATE foremen SET patreon_id = ?, last_active_at = ?, last_seen_at = ? WHERE discord_id = ?",
                (patreon_id, _iso(now), _iso(now), discord_id),
            )
        return self.get(discord_id)  # type: ignore[return-value]

    def mark_lapsed_or_reset(
        self,
        *,
        discord_id: str,
        grace_days: int,
        now: datetime | None = None,
    ) -> TenureRow | None:
        """
        Called when we see a tracked member who is NOT currently active+paid.
        If they've been lapsed longer than grace_days, reset foreman_since
        (so they'd start the 3-month clock over if they come back).
        """
        now = now or _utcnow()
        row = self.get(discord_id)
        if row is None:
            return None

        with self._conn() as c:
            c.execute(
                "UPDATE foremen SET last_seen_at = ? WHERE discord_id = ?",
                (_iso(now), discord_id),
            )

        lapse = (now - row.last_active_at).total_seconds() / 86400.0
        if lapse > grace_days:
            with self._conn() as c:
                c.execute(
                    "UPDATE foremen SET foreman_since = ? WHERE discord_id = ?",
                    (_iso(now), discord_id),
                )
        return self.get(discord_id)

    def set_role_granted(self, discord_id: str, granted: bool) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE foremen SET role_granted = ? WHERE discord_id = ?",
                (1 if granted else 0, discord_id),
            )

    def mark_fully_tenured(
        self,
        *,
        discord_id: str,
        patreon_id: str,
        tenure_days: int,
        now: datetime | None = None,
    ) -> None:
        """
        Insert-or-update a row so the member appears already past the tenure
        threshold. Used by the manual /foreman-grant admin command.
        """
        now = now or _utcnow()
        backdated = now - timedelta(days=tenure_days + 1)
        existing = self.get(discord_id)
        with self._conn() as c:
            if existing is None:
                c.execute(
                    """INSERT INTO foremen
                       (discord_id, patreon_id, foreman_since, last_active_at, last_seen_at, role_granted)
                       VALUES (?, ?, ?, ?, ?, 1)""",
                    (discord_id, patreon_id, _iso(backdated), _iso(now), _iso(now)),
                )
            else:
                c.execute(
                    """UPDATE foremen
                       SET patreon_id = ?, foreman_since = ?, last_active_at = ?,
                           last_seen_at = ?, role_granted = 1
                       WHERE discord_id = ?""",
                    (patreon_id, _iso(backdated), _iso(now), _iso(now), discord_id),
                )

    def remove(self, discord_id: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM foremen WHERE discord_id = ?", (discord_id,))

    def reset_nonmanual_rows(self) -> int:
        """
        Delete every tracked row EXCEPT manual grants. Used for one-time
        migrations when the backfill algorithm changes: the next reconciliation
        cycle re-evaluates everyone from scratch with the new rules.
        Exclusions and bot_state are untouched.
        """
        with self._conn() as c:
            cur = c.execute(
                "DELETE FROM foremen WHERE patreon_id != ?",
                (MANUAL_OVERRIDE_PATREON_ID,),
            )
            return cur.rowcount

    # --- exclusion list (manual revoke is sticky) ---------------------------

    def is_excluded(self, discord_id: str) -> bool:
        with self._conn() as c:
            row = c.execute(
                "SELECT 1 FROM excluded WHERE discord_id = ?", (discord_id,)
            ).fetchone()
        return row is not None

    def add_exclusion(self, discord_id: str, *, reason: str | None = None) -> None:
        now = _utcnow()
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO excluded (discord_id, excluded_at, reason) VALUES (?, ?, ?)",
                (discord_id, _iso(now), reason),
            )

    def remove_exclusion(self, discord_id: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM excluded WHERE discord_id = ?", (discord_id,))

    # --- persistent bot state (k/v store) -----------------------------------

    def get_state(self, key: str) -> str | None:
        with self._conn() as c:
            row = c.execute("SELECT value FROM bot_state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_state(self, key: str, value: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO bot_state (key, value) VALUES (?, ?)",
                (key, value),
            )

    def remove_unseen(self, before: datetime) -> list[TenureRow]:
        """
        Remove rows we haven't seen this reconciliation cycle — they're no longer
        on the Foreman tier at all. Returns the rows that were deleted so the
        caller can revoke roles.

        Rows created by /foreman-grant (manual-override) are exempt: they're
        never "seen" on Patreon, so cleaning them up here would silently undo
        the admin's manual grant within an hour.
        """
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM foremen WHERE last_seen_at < ? AND patreon_id != ?",
                (_iso(before), MANUAL_OVERRIDE_PATREON_ID),
            ).fetchall()
            c.execute(
                "DELETE FROM foremen WHERE last_seen_at < ? AND patreon_id != ?",
                (_iso(before), MANUAL_OVERRIDE_PATREON_ID),
            )
        return [_row(r) for r in rows]


def _row(r: sqlite3.Row) -> TenureRow:
    return TenureRow(
        discord_id=r["discord_id"],
        patreon_id=r["patreon_id"],
        foreman_since=_parse(r["foreman_since"]),
        last_active_at=_parse(r["last_active_at"]),
        last_seen_at=_parse(r["last_seen_at"]),
        role_granted=bool(r["role_granted"]),
    )
