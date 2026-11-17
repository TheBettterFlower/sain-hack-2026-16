import json
import os
import sqlite3
import threading
import uuid
from typing import Dict, List, Optional

from pydantic import BaseModel


class Event(BaseModel):
    id: str
    type: str
    date: str
    details: Dict


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


class SQLiteRepository:
    def __init__(self, db_path: Optional[str] = None):
        db_path = db_path or os.getenv("SAIN_DB_PATH", "/tmp/hackathon.db")
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                goal TEXT,
                disabled_widgets TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                type TEXT,
                date TEXT,
                details TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_events ON events(user_id)")

        # SAIN stores the interactive dashboard separately from the hackathon dataset.
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sain_dashboards (
                user_id TEXT PRIMARY KEY,
                widget_ids TEXT NOT NULL,
                widget_configs TEXT NOT NULL DEFAULT '{}',
                active_mode_id TEXT
            )
            """
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

        # Migrate the first draft (globally unique mode ID) to per-user mode IDs.
        if modes_table_exists and primary_key_columns != ["user_id", "id"]:
            cursor.execute("ALTER TABLE sain_modes RENAME TO sain_modes_legacy")
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
            cursor.execute(
                """INSERT OR IGNORE INTO sain_modes
                   (id, user_id, name, description, widget_ids, widget_configs, created_at)
                   SELECT id, user_id, name, description, widget_ids, widget_configs, created_at
                   FROM sain_modes_legacy"""
            )
            cursor.execute("DROP TABLE sain_modes_legacy")
        elif not modes_table_exists:
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
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sain_modes_user ON sain_modes(user_id)"
        )
        self.conn.commit()

    def load_from_json(self, raw_data: dict):
        """Loads the organizer dataset without touching SAIN dashboard settings."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM events")
            cursor.execute("DELETE FROM users")

            users_batch = []
            events_batch = []
            for user_data in raw_data.get("users", []):
                profile = user_data["profile"]
                user_id = profile["id"]
                users_batch.append(
                    (
                        user_id,
                        profile.get("goal", ""),
                        json.dumps(profile.get("disabled_widgets", []), ensure_ascii=False),
                    )
                )
                for event in user_data.get("events", []):
                    events_batch.append(
                        (
                            event["id"],
                            user_id,
                            event["type"],
                            event["date"],
                            json.dumps(event.get("details", {}), ensure_ascii=False),
                        )
                    )

            cursor.executemany(
                "INSERT INTO users (id, goal, disabled_widgets) VALUES (?, ?, ?)",
                users_batch,
            )
            cursor.executemany(
                "INSERT INTO events (id, user_id, type, date, details) VALUES (?, ?, ?, ?, ?)",
                events_batch,
            )
            self.conn.commit()

    def get_user_events(self, user_id: str) -> List[Event]:
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM events WHERE user_id = ? ORDER BY date ASC", (user_id,)
            )
            return [
                Event(
                    id=row["id"],
                    type=row["type"],
                    date=row["date"],
                    details=json.loads(row["details"]),
                )
                for row in cursor.fetchall()
            ]

    def get_active_widgets(self, user_id: str) -> List[str]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT disabled_widgets FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            return []
        disabled = json.loads(row["disabled_widgets"] or "[]")
        all_widgets = [
            "sleep_card", "calendar_brief", "restart_card", "workout_suggest",
            "steps_ring", "water_tracker", "day_plan", "habit_streak",
            "recovery_tip", "energy_forecast", "evening_reflect", "goal_progress",
        ]
        return [widget_id for widget_id in all_widgets if widget_id not in disabled]

    def get_user_habit_stats(self, user_id: str) -> dict:
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT type,
                       json_extract(details, '$.name') AS detail_name,
                       COUNT(*) AS total_count
                FROM events
                WHERE user_id = ? AND type NOT IN ('sleep', 'workout')
                GROUP BY type, detail_name
                ORDER BY total_count DESC
                """,
                (user_id,),
            )
            stats = {}
            for row in cursor.fetchall():
                key = row["type"]
                if row["detail_name"]:
                    key += f" ({row['detail_name']})"
                stats[key] = row["total_count"]
            return stats

    # ------------------------- SAIN dashboard -------------------------
    def _ensure_sain_state(self, user_id: str):
        cursor = self.conn.cursor()
        cursor.execute("SELECT user_id FROM sain_dashboards WHERE user_id = ?", (user_id,))
        if cursor.fetchone() is None:
            cursor.execute(
                """INSERT INTO sain_dashboards
                   (user_id, widget_ids, widget_configs, active_mode_id)
                   VALUES (?, ?, '{}', 'flight')""",
                (user_id, json.dumps(DEFAULT_SAIN_WIDGETS, ensure_ascii=False)),
            )

        cursor.execute("SELECT COUNT(*) AS amount FROM sain_modes WHERE user_id = ?", (user_id,))
        if cursor.fetchone()["amount"] == 0:
            cursor.executemany(
                """INSERT INTO sain_modes
                   (id, user_id, name, description, widget_ids, widget_configs)
                   VALUES (?, ?, ?, ?, ?, '{}')""",
                [
                    (
                        mode["id"], user_id, mode["name"], mode["description"],
                        json.dumps(mode["widget_ids"], ensure_ascii=False),
                    )
                    for mode in DEFAULT_SAIN_MODES
                ],
            )
        self.conn.commit()

    def get_sain_state(self, user_id: str) -> dict:
        with self._lock:
            self._ensure_sain_state(user_id)
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM sain_dashboards WHERE user_id = ?", (user_id,))
            dashboard = cursor.fetchone()
            cursor.execute(
                """SELECT id, name, description, widget_ids, widget_configs
                   FROM sain_modes WHERE user_id = ? ORDER BY created_at, name""",
                (user_id,),
            )
            modes = [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "description": row["description"],
                    "widget_ids": json.loads(row["widget_ids"]),
                    "widget_configs": json.loads(row["widget_configs"] or "{}"),
                }
                for row in cursor.fetchall()
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
        with self._lock:
            self._ensure_sain_state(user_id)
            cursor = self.conn.cursor()
            encoded_ids = json.dumps(widget_ids, ensure_ascii=False)
            encoded_configs = json.dumps(widget_configs or {}, ensure_ascii=False)
            cursor.execute(
                """UPDATE sain_dashboards
                   SET widget_ids = ?, widget_configs = ?,
                       active_mode_id = COALESCE(?, active_mode_id)
                   WHERE user_id = ?""",
                (encoded_ids, encoded_configs, active_mode_id, user_id),
            )
            if active_mode_id:
                cursor.execute(
                    """UPDATE sain_modes SET widget_ids = ?, widget_configs = ?
                       WHERE id = ? AND user_id = ?""",
                    (encoded_ids, encoded_configs, active_mode_id, user_id),
                )
            self.conn.commit()

    def create_sain_mode(
        self,
        user_id: str,
        name: str,
        widget_ids: List[str],
        widget_configs: Optional[dict] = None,
        description: str = "",
    ) -> dict:
        with self._lock:
            self._ensure_sain_state(user_id)
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT id FROM sain_modes WHERE user_id = ? AND name = ?",
                (user_id, name),
            )
            existing_mode = cursor.fetchone()
            mode_id = existing_mode["id"] if existing_mode else f"custom-{uuid.uuid4().hex[:12]}"
            if existing_mode:
                cursor.execute(
                    """UPDATE sain_modes
                       SET description = ?, widget_ids = ?, widget_configs = ?
                       WHERE id = ? AND user_id = ?""",
                    (
                        description,
                        json.dumps(widget_ids, ensure_ascii=False),
                        json.dumps(widget_configs or {}, ensure_ascii=False),
                        mode_id,
                        user_id,
                    ),
                )
            else:
                cursor.execute(
                    """INSERT INTO sain_modes
                       (id, user_id, name, description, widget_ids, widget_configs)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        mode_id,
                        user_id,
                        name,
                        description,
                        json.dumps(widget_ids, ensure_ascii=False),
                        json.dumps(widget_configs or {}, ensure_ascii=False),
                    ),
                )
            cursor.execute(
                """UPDATE sain_dashboards
                   SET widget_ids = ?, widget_configs = ?, active_mode_id = ?
                   WHERE user_id = ?""",
                (
                    json.dumps(widget_ids, ensure_ascii=False),
                    json.dumps(widget_configs or {}, ensure_ascii=False),
                    mode_id,
                    user_id,
                ),
            )
            self.conn.commit()
            return {
                "id": mode_id,
                "name": name,
                "description": description,
                "widget_ids": widget_ids,
                "widget_configs": widget_configs or {},
            }

    def activate_sain_mode(self, user_id: str, mode_id: str) -> bool:
        with self._lock:
            self._ensure_sain_state(user_id)
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM sain_modes WHERE id = ? AND user_id = ?",
                (mode_id, user_id),
            )
            mode = cursor.fetchone()
            if mode is None:
                return False
            cursor.execute(
                """UPDATE sain_dashboards
                   SET widget_ids = ?, widget_configs = ?, active_mode_id = ?
                   WHERE user_id = ?""",
                (mode["widget_ids"], mode["widget_configs"], mode_id, user_id),
            )
            self.conn.commit()
            return True


repo = SQLiteRepository()
