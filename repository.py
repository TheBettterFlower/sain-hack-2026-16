"""SQLite persistence for SAIN Case 1.

The organizer's payload shape currently visible in the project is
users[].profile.id and users[].events[]. The adapter accepts a few common
aliases, while preserving unknown profile/user/event fields in JSON columns.
By default, IDs remain global to preserve compatibility with the existing
SAIN frontend. Set SAIN_USER_ID_SCOPE=dataset if organizer IDs are only
unique inside each dataset_code (and pass that same identity scope to clients).
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


RETENTION_DAYS = 90


class DatasetValidationError(ValueError):
    """Raised when an organizer payload cannot be safely normalized."""


class Event(BaseModel):
    id: str
    type: str
    date: str
    details: Dict[str, Any]


DEFAULT_SAIN_WIDGETS = [
    "calendar_brief",
    "water_tracker",
    "sleep_card",
    "day_plan",
]

DEFAULT_SAIN_MODES = [
    {
        "id": "flight",
        "name": "Перед перелётом",
        "description": "Спокойная подготовка к поездке",
        "widget_ids": ["calendar_brief", "water_tracker", "sleep_card", "day_plan"],
    },
    {
        "id": "restart",
        "name": "После срыва привычки",
        "description": "Мягкое возвращение к привычному ритму",
        "widget_ids": ["recovery_tip", "habit_streak", "restart_card", "workout_suggest"],
    },
    {
        "id": "peak",
        "name": "Пик продуктивности",
        "description": "Планирование задач и периодов концентрации",
        "widget_ids": ["steps_ring", "goal_progress", "energy_forecast", "day_plan"],
    },
]

ALL_WIDGETS = [
    "sleep_card", "calendar_brief", "restart_card", "workout_suggest",
    "steps_ring", "water_tracker", "day_plan", "habit_streak",
    "recovery_tip", "energy_forecast", "evening_reflect", "goal_progress",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso_utc(value: Any) -> str:
    """Normalize ISO dates or Unix timestamps to lexicographically sortable UTC."""
    if isinstance(value, bool) or value is None:
        raise DatasetValidationError("У события отсутствует корректная дата")

    dt: Optional[datetime] = None
    if isinstance(value, (int, float)):
        timestamp = float(value)
        # Unix milliseconds are typically >= 1e12; seconds are ~1e9.
        if abs(timestamp) >= 100_000_000_000:
            timestamp /= 1000.0
        try:
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise DatasetValidationError("Некорректный Unix timestamp события") from exc
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            raise DatasetValidationError("У события пустая дата")
        try:
            # Also accept a numeric timestamp encoded as a string.
            if raw.replace(".", "", 1).isdigit():
                return to_iso_utc(float(raw))
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DatasetValidationError(
                f"Неизвестный формат даты события: {raw[:80]}"
            ) from exc
    else:
        raise DatasetValidationError("Дата события должна быть строкой или timestamp")

    if dt.tzinfo is None:
        # Naive organizer timestamps are interpreted as UTC, consistently.
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def retention_cutoff(days: int = RETENTION_DAYS) -> str:
    return (utc_now() - timedelta(days=days)).isoformat(timespec="seconds").replace("+00:00", "Z")


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _as_string_id(value: Any, label: str) -> str:
    if value is None or isinstance(value, (dict, list)):
        raise DatasetValidationError(f"У {label} отсутствует корректный идентификатор")
    result = str(value).strip()
    if not result:
        raise DatasetValidationError(f"У {label} пустой идентификатор")
    return result


def _get_user_profile(user_data: dict) -> dict:
    profile = user_data.get("profile")
    if profile is None:
        # Compatibility fallback for a flat user object.
        profile = user_data
    if not isinstance(profile, dict):
        raise DatasetValidationError("Поле пользователя profile должно быть объектом")
    return profile


def _get_external_user_id(profile: dict, user_data: dict) -> str:
    return _as_string_id(_get_external_user_id_value(profile, user_data), "пользователя")


def _get_external_user_id_value(profile: dict, user_data: dict) -> Any:
    candidate = profile.get("id")
    if candidate is None:
        candidate = profile.get("user_id", profile.get("userId"))
    if candidate is None:
        candidate = user_data.get("user_id", user_data.get("userId", user_data.get("id")))
    _as_string_id(candidate, "пользователя")
    return candidate


def _normalize_event(event: dict, user_id: str) -> dict:
    if not isinstance(event, dict):
        raise DatasetValidationError(f"Событие пользователя {user_id} должно быть объектом")

    event_type = event.get("type") or event.get("event_type")
    if not isinstance(event_type, str) or not event_type.strip():
        raise DatasetValidationError(f"У события пользователя {user_id} отсутствует type")

    raw_date = next(
        (event.get(key) for key in ("date", "timestamp", "created_at", "time") if event.get(key) is not None),
        None,
    )
    normalized_date = to_iso_utc(raw_date)

    details = event.get("details", event.get("payload", {}))
    if details is None:
        details = {}
    elif not isinstance(details, dict):
        # Preserve scalar/list payloads instead of silently discarding them.
        details = {"value": details}

    raw_id = event.get("id")
    if raw_id is None or raw_id == "":
        raw_id = event.get("event_id")
    if raw_id is None or raw_id == "":
        # Stable fallback for feeds that omit event IDs. Repeated identical
        # event objects for the same user will not be inserted twice.
        fingerprint_source = _json_dump({"user_id": user_id, "event": event})
        raw_id = "sha256:" + hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()

    return {
        "id": _as_string_id(raw_id, "события"),
        "type": event_type.strip(),
        "date": normalized_date,
        "details": details,
        "raw_json": event,
    }


class SQLiteRepository:
    def __init__(self, db_path: Optional[str] = None):
        configured_path = db_path or os.getenv("SAIN_DB_PATH")
        if configured_path:
            resolved_path = Path(configured_path).expanduser()
            if str(resolved_path) != ":memory:":
                resolved_path.parent.mkdir(parents=True, exist_ok=True)
            db_path_value = str(resolved_path)
        else:
            # A project-local file survives ordinary server restarts. On hosted
            # deployment, point SAIN_DB_PATH at the provider's persistent volume.
            data_dir = Path(__file__).resolve().parent / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            default_db = data_dir / "sain.db"
            legacy_db = Path("/tmp/hackathon.db")
            if not default_db.exists() and legacy_db.exists():
                # Keep data from the previous project version when possible.
                legacy_connection = sqlite3.connect(str(legacy_db))
                new_connection = sqlite3.connect(str(default_db))
                try:
                    legacy_connection.backup(new_connection)
                finally:
                    new_connection.close()
                    legacy_connection.close()
            db_path_value = str(default_db)

        self.conn = sqlite3.connect(db_path_value, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self):
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    goal TEXT,
                    disabled_widgets TEXT NOT NULL DEFAULT '[]',
                    profile_json TEXT NOT NULL DEFAULT '{}',
                    source_json TEXT NOT NULL DEFAULT '{}',
                    first_seen_at TEXT,
                    last_seen_at TEXT
                )"""
            )

            # Additive migration for databases created by earlier project versions.
            user_columns = {row["name"] for row in cursor.execute("PRAGMA table_info(users)")}
            user_migrations = {
                "goal": "TEXT",
                "profile_json": "TEXT NOT NULL DEFAULT '{}'",
                "source_json": "TEXT NOT NULL DEFAULT '{}'",
                "first_seen_at": "TEXT",
                "last_seen_at": "TEXT",
                "disabled_widgets": "TEXT NOT NULL DEFAULT '[]'",
            }
            for column, sql_type in user_migrations.items():
                if column not in user_columns:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {column} {sql_type}")

            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'events'"
            )
            events_exist = cursor.fetchone() is not None
            if not events_exist:
                self._create_events_table(cursor, "events")
            else:
                event_info = cursor.execute("PRAGMA table_info(events)").fetchall()
                event_columns = {row["name"] for row in event_info}
                primary_key = [
                    row["name"] for row in sorted(event_info, key=lambda item: item["pk"])
                    if row["pk"] > 0
                ]
                required_columns = {"id", "user_id", "type", "date", "details", "raw_json", "ingested_at"}
                if primary_key != ["user_id", "id"] or not required_columns.issubset(event_columns):
                    cursor.execute("ALTER TABLE events RENAME TO events_legacy")
                    self._create_events_table(cursor, "events")
                    legacy_columns = {row["name"] for row in cursor.execute("PRAGMA table_info(events_legacy)")}
                    if {"id", "user_id", "type", "date", "details"}.issubset(legacy_columns):
                        legacy_rows = cursor.execute("SELECT id, user_id, type, date, details FROM events_legacy").fetchall()
                        now = to_iso_utc(utc_now().isoformat())
                        for row in legacy_rows:
                            old_id = row["id"]
                            old_user_id = row["user_id"]
                            if old_id is None or old_user_id is None:
                                continue
                            try:
                                normalized_date = to_iso_utc(row["date"])
                            except DatasetValidationError:
                                # Keep legacy data readable; it will not be used
                                # for date-window analytics until corrected.
                                normalized_date = str(row["date"] or "")
                            try:
                                details = json.loads(row["details"] or "{}")
                            except json.JSONDecodeError:
                                details = {"legacy_raw": row["details"]}
                            if not isinstance(details, dict):
                                details = {"value": details}
                            self.conn.execute(
                                """INSERT OR IGNORE INTO events
                                   (user_id, id, type, date, details, raw_json, ingested_at)
                                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                                (
                                    str(old_user_id), str(old_id), str(row["type"] or "unknown"),
                                    normalized_date, _json_dump(details),
                                    _json_dump({"legacy": True, "details": details}), now,
                                ),
                            )
                    cursor.execute("DROP TABLE events_legacy")

            cursor.execute("DROP INDEX IF EXISTS idx_user_events")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_events ON events(user_id, date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_date ON events(date)")

            # SAIN's interactive dashboard remains separate from organizer data.
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS sain_dashboards (
                    user_id TEXT PRIMARY KEY,
                    widget_ids TEXT NOT NULL,
                    widget_configs TEXT NOT NULL DEFAULT '{}',
                    active_mode_id TEXT
                )"""
            )
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'sain_modes'"
            )
            modes_table_exists = cursor.fetchone() is not None
            primary_key_columns = []
            if modes_table_exists:
                table_info = cursor.execute("PRAGMA table_info(sain_modes)").fetchall()
                primary_key_columns = [
                    row["name"] for row in sorted(table_info, key=lambda item: item["pk"])
                    if row["pk"] > 0
                ]

            # Migrate old global mode IDs to per-user mode IDs.
            if modes_table_exists and primary_key_columns != ["user_id", "id"]:
                cursor.execute("ALTER TABLE sain_modes RENAME TO sain_modes_legacy")
                self._create_sain_modes_table(cursor)
                cursor.execute(
                    """INSERT OR IGNORE INTO sain_modes
                       (id, user_id, name, description, widget_ids, widget_configs, created_at)
                       SELECT id, user_id, name, description, widget_ids, widget_configs, created_at
                       FROM sain_modes_legacy"""
                )
                cursor.execute("DROP TABLE sain_modes_legacy")
            elif not modes_table_exists:
                self._create_sain_modes_table(cursor)

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sain_modes_user ON sain_modes(user_id)")
            cursor.execute("DELETE FROM events WHERE date < ?", (retention_cutoff(RETENTION_DAYS),))
            self.conn.commit()

    @staticmethod
    def _create_events_table(cursor: sqlite3.Cursor, table_name: str):
        cursor.execute(
            f"""CREATE TABLE {table_name} (
                user_id TEXT NOT NULL,
                id TEXT NOT NULL,
                type TEXT NOT NULL,
                date TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '{{}}',
                raw_json TEXT NOT NULL DEFAULT '{{}}',
                ingested_at TEXT NOT NULL,
                PRIMARY KEY (user_id, id),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )"""
        )

    @staticmethod
    def _create_sain_modes_table(cursor: sqlite3.Cursor):
        cursor.execute(
            """CREATE TABLE sain_modes (
                id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                widget_ids TEXT NOT NULL,
                widget_configs TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, id),
                UNIQUE(user_id, name)
            )"""
        )

    @staticmethod
    def storage_user_id(external_user_id: str, namespace: Optional[str] = None) -> str:
        if not namespace:
            return external_user_id
        namespace = str(namespace)
        # Length-prefixing avoids collisions when either part contains separators.
        return f"{len(namespace)}:{namespace}{external_user_id}"

    def load_from_json(self, raw_data: dict, namespace: Optional[str] = None) -> dict:
        """Normalize and upsert an organizer payload without deleting valid history.

        Missing users/events in a later batch are NOT interpreted as deletions.
        Events expire by their event date after 90 days. Unknown profile and
        event fields are retained in JSON columns.
        """
        if not isinstance(raw_data, dict):
            raise DatasetValidationError("Корень JSON должен быть объектом")

        raw_users = raw_data.get("users", [])
        if raw_users is None:
            raw_users = []
        if not isinstance(raw_users, list):
            raise DatasetValidationError("Поле users должно быть массивом")

        normalized_users = []
        normalized_by_storage_id = {}
        for user_data in raw_users:
            if not isinstance(user_data, dict):
                raise DatasetValidationError("Каждый элемент users должен быть объектом")
            profile = _get_user_profile(user_data)
            external_id_value = _get_external_user_id_value(profile, user_data)
            external_id = _as_string_id(external_id_value, "пользователя")
            storage_id = self.storage_user_id(external_id, namespace)
            raw_events = user_data.get("events", []) or []
            if not isinstance(raw_events, list):
                raise DatasetValidationError(f"Поле events пользователя {external_id} должно быть массивом")
            events = [_normalize_event(event, external_id) for event in raw_events]

            profile_copy = dict(profile)
            # In the flat compatibility format profile and user_data are the
            # same object; events belong in the events table, not profile_json.
            profile_copy.pop("events", None)
            profile_copy.setdefault("id", external_id)
            source_copy = {key: value for key, value in user_data.items() if key != "events"}
            if "profile" not in source_copy:
                source_copy["profile"] = profile_copy
            normalized_user = {
                "external_id": external_id,
                "response_id": external_id_value,
                "storage_id": storage_id,
                "profile": profile_copy,
                "source": source_copy,
                "events": events,
            }
            # A malformed/redundant feed may list one person more than once.
            # Merge those fragments before opening the transaction.
            existing_user = normalized_by_storage_id.get(storage_id)
            if existing_user is None:
                normalized_users.append(normalized_user)
                normalized_by_storage_id[storage_id] = normalized_user
            else:
                existing_user["profile"].update(profile_copy)
                existing_user["source"].update(source_copy)
                existing_user["events"].extend(events)

        now = to_iso_utc(utc_now().isoformat())
        imported_event_count = 0
        with self._lock:
            try:
                with self.conn:
                    cursor = self.conn.cursor()
                    for user in normalized_users:
                        storage_id = user["storage_id"]
                        profile = user["profile"]

                        existing_row = cursor.execute(
                            "SELECT profile_json, source_json, goal, disabled_widgets, first_seen_at FROM users WHERE id = ?",
                            (storage_id,),
                        ).fetchone()
                        if existing_row:
                            try:
                                old_profile = json.loads(existing_row["profile_json"] or "{}")
                            except json.JSONDecodeError:
                                old_profile = {}
                            try:
                                old_source = json.loads(existing_row["source_json"] or "{}")
                            except json.JSONDecodeError:
                                old_source = {}
                            if not isinstance(old_profile, dict):
                                old_profile = {}
                            if not isinstance(old_source, dict):
                                old_source = {}
                            merged_profile = {**old_profile, **profile}
                            merged_source = {**old_source, **user["source"]}
                            if "profile" in merged_source:
                                merged_source["profile"] = merged_profile
                            goal = profile.get("goal", existing_row["goal"] or "")
                            disabled = profile.get(
                                "disabled_widgets",
                                json.loads(existing_row["disabled_widgets"] or "[]"),
                            )
                            first_seen = existing_row["first_seen_at"] or now
                        else:
                            merged_profile = profile
                            merged_source = dict(user["source"])
                            if "profile" in merged_source:
                                merged_source["profile"] = merged_profile
                            goal = profile.get("goal", "")
                            disabled = profile.get("disabled_widgets", [])
                            first_seen = now

                        if not isinstance(disabled, list):
                            disabled = []
                        goal_text = goal if isinstance(goal, str) else _json_dump(goal)
                        cursor.execute(
                            """INSERT INTO users
                               (id, goal, disabled_widgets, profile_json, source_json, first_seen_at, last_seen_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?)
                               ON CONFLICT(id) DO UPDATE SET
                                 goal = excluded.goal,
                                 disabled_widgets = excluded.disabled_widgets,
                                 profile_json = excluded.profile_json,
                                 source_json = excluded.source_json,
                                 last_seen_at = excluded.last_seen_at""",
                            (
                                storage_id, goal_text, _json_dump(disabled),
                                _json_dump(merged_profile), _json_dump(merged_source),
                                first_seen, now,
                            ),
                        )

                        for event in user["events"]:
                            cursor.execute(
                                """INSERT INTO events
                                   (user_id, id, type, date, details, raw_json, ingested_at)
                                   VALUES (?, ?, ?, ?, ?, ?, ?)
                                   ON CONFLICT(user_id, id) DO UPDATE SET
                                     type = excluded.type,
                                     date = excluded.date,
                                     details = excluded.details,
                                     raw_json = excluded.raw_json,
                                     ingested_at = excluded.ingested_at""",
                                (
                                    storage_id, event["id"], event["type"], event["date"],
                                    _json_dump(event["details"]), _json_dump(event["raw_json"]), now,
                                ),
                            )
                            imported_event_count += 1

                    cutoff = retention_cutoff(RETENTION_DAYS)
                    cursor.execute("DELETE FROM events WHERE date < ?", (cutoff,))
            except sqlite3.Error:
                self.conn.rollback()
                raise

        return {
            "users": [
                {"external_id": user["response_id"], "storage_id": user["storage_id"]}
                for user in normalized_users
            ],
            "user_ids": [user["storage_id"] for user in normalized_users],
            "users_processed": len(normalized_users),
            "events_received": imported_event_count,
            "retention_days": RETENTION_DAYS,
        }

    def ensure_user(self, user_id: str):
        """Create a minimal memory record for a question whose user had no profile."""
        user_id = _as_string_id(user_id, "пользователя")
        now = to_iso_utc(utc_now().isoformat())
        with self._lock, self.conn:
            self.conn.execute(
                """INSERT OR IGNORE INTO users
                   (id, goal, disabled_widgets, profile_json, source_json, first_seen_at, last_seen_at)
                   VALUES (?, '', '[]', '{}', '{}', ?, ?)""",
                (user_id, now, now),
            )

    def has_user(self, user_id: str) -> bool:
        with self._lock:
            row = self.conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone()
        return row is not None

    def list_users(self) -> list:
        """Return lightweight user records for the connected frontend user picker."""
        with self._lock:
            rows = self.conn.execute(
                """SELECT u.id, u.goal, u.profile_json, u.last_seen_at,
                          (SELECT COUNT(*) FROM events e WHERE e.user_id = u.id
                           AND e.date >= ?) AS event_count_90d
                   FROM users u ORDER BY COALESCE(u.last_seen_at, '') DESC, u.id ASC""",
                (retention_cutoff(RETENTION_DAYS),),
            ).fetchall()

        users = []
        for row in rows:
            try:
                profile = json.loads(row["profile_json"] or "{}")
            except json.JSONDecodeError:
                profile = {}
            if not isinstance(profile, dict):
                profile = {}
            external_id = profile.get("id") or row["id"]
            display_name = next(
                (profile.get(key) for key in ("name", "full_name", "display_name", "username", "first_name")
                 if isinstance(profile.get(key), str) and profile.get(key).strip()),
                str(external_id),
            )
            users.append({
                "user_id": row["id"],
                "external_id": str(external_id),
                "label": str(display_name),
                "goal": row["goal"] or profile.get("goal") or "",
                "last_seen_at": row["last_seen_at"],
                "event_count_90d": int(row["event_count_90d"] or 0),
            })
        return users

    def get_user_profile(self, user_id: str) -> dict:
        with self._lock:
            row = self.conn.execute("SELECT profile_json FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return {}
        try:
            profile = json.loads(row["profile_json"] or "{}")
            return profile if isinstance(profile, dict) else {}
        except json.JSONDecodeError:
            return {}

    def get_user_source(self, user_id: str) -> dict:
        with self._lock:
            row = self.conn.execute("SELECT source_json FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return {}
        try:
            source = json.loads(row["source_json"] or "{}")
            return source if isinstance(source, dict) else {}
        except json.JSONDecodeError:
            return {}

    def get_user_event_type_counts(self, user_id: str, days: int = RETENTION_DAYS) -> dict:
        cutoff = retention_cutoff(days)
        now = to_iso_utc(utc_now().isoformat())
        with self._lock:
            rows = self.conn.execute(
                """SELECT type, COUNT(*) AS total_count
                   FROM events
                   WHERE user_id = ? AND date >= ? AND date <= ?
                   GROUP BY type ORDER BY total_count DESC""",
                (user_id, cutoff, now),
            ).fetchall()
        return {row["type"]: row["total_count"] for row in rows}

    def get_user_events(self, user_id: str, days: int = RETENTION_DAYS) -> List[Event]:
        cutoff = retention_cutoff(days)
        with self._lock:
            rows = self.conn.execute(
                """SELECT id, type, date, details FROM events
                   WHERE user_id = ? AND date >= ? ORDER BY date ASC""",
                (user_id, cutoff),
            ).fetchall()
        result = []
        for row in rows:
            try:
                details = json.loads(row["details"] or "{}")
            except json.JSONDecodeError:
                details = {}
            if not isinstance(details, dict):
                details = {"value": details}
            result.append(Event(
                id=row["id"], type=row["type"], date=row["date"], details=details
            ))
        return result

    def get_active_widgets(self, user_id: str) -> List[str]:
        with self._lock:
            row = self.conn.execute(
                "SELECT disabled_widgets FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        if not row:
            return []
        try:
            disabled = json.loads(row["disabled_widgets"] or "[]")
        except json.JSONDecodeError:
            disabled = []
        if not isinstance(disabled, list):
            disabled = []
        disabled_set = {value for value in disabled if isinstance(value, str)}
        return [widget_id for widget_id in ALL_WIDGETS if widget_id not in disabled_set]

    def get_user_habit_stats(self, user_id: str, days: int = RETENTION_DAYS) -> dict:
        cutoff = retention_cutoff(days)
        now = to_iso_utc(utc_now().isoformat())
        with self._lock:
            rows = self.conn.execute(
                """SELECT type,
                          json_extract(details, '$.name') AS detail_name,
                          COUNT(*) AS total_count
                   FROM events
                   WHERE user_id = ? AND date >= ? AND date <= ?
                     AND type NOT IN ('sleep', 'workout')
                   GROUP BY type, detail_name
                   ORDER BY total_count DESC""",
                (user_id, cutoff, now),
            ).fetchall()
        stats = {}
        for row in rows:
            key = row["type"]
            if row["detail_name"]:
                key += f" ({row['detail_name']})"
            stats[key] = row["total_count"]
        return stats

    def prune_old_events(self, days: int = RETENTION_DAYS) -> int:
        cutoff = retention_cutoff(days)
        with self._lock, self.conn:
            cursor = self.conn.execute("DELETE FROM events WHERE date < ?", (cutoff,))
            return cursor.rowcount

    # ------------------------- SAIN dashboard -------------------------
    def _ensure_sain_state(self, user_id: str):
        cursor = self.conn.cursor()
        cursor.execute("SELECT user_id FROM sain_dashboards WHERE user_id = ?", (user_id,))
        if cursor.fetchone() is None:
            cursor.execute(
                """INSERT INTO sain_dashboards
                   (user_id, widget_ids, widget_configs, active_mode_id)
                   VALUES (?, ?, '{}', 'flight')""",
                (user_id, _json_dump(DEFAULT_SAIN_WIDGETS)),
            )

        cursor.execute("SELECT COUNT(*) AS amount FROM sain_modes WHERE user_id = ?", (user_id,))
        if cursor.fetchone()["amount"] == 0:
            cursor.executemany(
                """INSERT INTO sain_modes
                   (id, user_id, name, description, widget_ids, widget_configs)
                   VALUES (?, ?, ?, ?, ?, '{}')""",
                [
                    (mode["id"], user_id, mode["name"], mode["description"], _json_dump(mode["widget_ids"]))
                    for mode in DEFAULT_SAIN_MODES
                ],
            )
        self.conn.commit()

    def get_sain_state(self, user_id: str) -> dict:
        with self._lock:
            self._ensure_sain_state(user_id)
            cursor = self.conn.cursor()
            dashboard = cursor.execute(
                "SELECT * FROM sain_dashboards WHERE user_id = ?", (user_id,)
            ).fetchone()
            rows = cursor.execute(
                """SELECT id, name, description, widget_ids, widget_configs
                   FROM sain_modes WHERE user_id = ? ORDER BY created_at, name""",
                (user_id,),
            ).fetchall()
            modes = [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "description": row["description"],
                    "widget_ids": json.loads(row["widget_ids"]),
                    "widget_configs": json.loads(row["widget_configs"] or "{}"),
                }
                for row in rows
            ]
            return {
                "user_id": user_id,
                "widget_ids": json.loads(dashboard["widget_ids"]),
                "widget_configs": json.loads(dashboard["widget_configs"] or "{}"),
                "active_mode_id": dashboard["active_mode_id"],
                "modes": modes,
            }

    def save_sain_dashboard(
        self,
        user_id: str,
        widget_ids: List[str],
        widget_configs: Optional[dict] = None,
        active_mode_id: Optional[str] = None,
    ):
        with self._lock, self.conn:
            self._ensure_sain_state(user_id)
            encoded_ids = _json_dump(widget_ids)
            encoded_configs = _json_dump(widget_configs or {})
            self.conn.execute(
                """UPDATE sain_dashboards
                   SET widget_ids = ?, widget_configs = ?,
                       active_mode_id = COALESCE(?, active_mode_id)
                   WHERE user_id = ?""",
                (encoded_ids, encoded_configs, active_mode_id, user_id),
            )
            if active_mode_id:
                self.conn.execute(
                    """UPDATE sain_modes SET widget_ids = ?, widget_configs = ?
                       WHERE id = ? AND user_id = ?""",
                    (encoded_ids, encoded_configs, active_mode_id, user_id),
                )

    def create_sain_mode(
        self,
        user_id: str,
        name: str,
        widget_ids: List[str],
        widget_configs: Optional[dict] = None,
        description: str = "",
    ) -> dict:
        with self._lock, self.conn:
            self._ensure_sain_state(user_id)
            existing_mode = self.conn.execute(
                "SELECT id FROM sain_modes WHERE user_id = ? AND name = ?", (user_id, name)
            ).fetchone()
            mode_id = existing_mode["id"] if existing_mode else f"custom-{uuid.uuid4().hex[:12]}"
            encoded_ids = _json_dump(widget_ids)
            encoded_configs = _json_dump(widget_configs or {})
            if existing_mode:
                self.conn.execute(
                    """UPDATE sain_modes SET description = ?, widget_ids = ?, widget_configs = ?
                       WHERE id = ? AND user_id = ?""",
                    (description, encoded_ids, encoded_configs, mode_id, user_id),
                )
            else:
                self.conn.execute(
                    """INSERT INTO sain_modes
                       (id, user_id, name, description, widget_ids, widget_configs)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (mode_id, user_id, name, description, encoded_ids, encoded_configs),
                )
            self.conn.execute(
                """UPDATE sain_dashboards
                   SET widget_ids = ?, widget_configs = ?, active_mode_id = ?
                   WHERE user_id = ?""",
                (encoded_ids, encoded_configs, mode_id, user_id),
            )
            return {
                "id": mode_id,
                "name": name,
                "description": description,
                "widget_ids": widget_ids,
                "widget_configs": widget_configs or {},
            }

    def activate_sain_mode(self, user_id: str, mode_id: str) -> bool:
        with self._lock, self.conn:
            self._ensure_sain_state(user_id)
            mode = self.conn.execute(
                "SELECT * FROM sain_modes WHERE id = ? AND user_id = ?", (mode_id, user_id)
            ).fetchone()
            if mode is None:
                return False
            self.conn.execute(
                """UPDATE sain_dashboards
                   SET widget_ids = ?, widget_configs = ?, active_mode_id = ?
                   WHERE user_id = ?""",
                (mode["widget_ids"], mode["widget_configs"], mode_id, user_id),
            )
            return True


# The global repository is used by FastAPI services.
repo = SQLiteRepository()
