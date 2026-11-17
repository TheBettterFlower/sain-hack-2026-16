import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from repository import DatasetValidationError, SQLiteRepository


def iso_utc(delta_days=0):
    value = datetime.now(timezone.utc) + timedelta(days=delta_days)
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.repo = SQLiteRepository(":memory:")

    def test_new_and_existing_users_are_upserted_without_erasing_history(self):
        self.repo.load_from_json({"users": [
            {"profile": {"id": "u-1", "goal": "sleep", "extra": {"level": 2}}, "events": [
                {"id": "e-1", "type": "sleep", "date": iso_utc(-2), "details": {"duration": 7}}
            ]},
            {"profile": {"id": "u-2"}, "events": []},
        ]})
        self.repo.load_from_json({"users": [
            {"profile": {"id": "u-1", "goal": "regular sleep"}, "events": [
                {"id": "e-2", "type": "workout", "date": iso_utc(-1), "details": {"kind": "walk"}}
            ]},
            {"profile": {"id": "u-3", "nickname": "new"}, "events": []},
        ]})

        self.assertEqual({event.id for event in self.repo.get_user_events("u-1")}, {"e-1", "e-2"})
        self.assertEqual(self.repo.get_user_profile("u-1")["extra"], {"level": 2})
        self.assertEqual(self.repo.get_user_profile("u-3")["nickname"], "new")
        self.assertEqual(self.repo.get_user_events("u-2"), [])

    def test_duplicate_event_is_updated_not_duplicated(self):
        for distance in (2, 5):
            self.repo.load_from_json({"users": [{
                "profile": {"id": "u-1"},
                "events": [{"id": "same", "type": "workout", "date": iso_utc(-1), "details": {"distance": distance}}],
            }]})
        events = self.repo.get_user_events("u-1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].details["distance"], 5)

    def test_old_events_are_removed_by_event_date(self):
        self.repo.load_from_json({"users": [{
            "profile": {"id": "u-1"},
            "events": [
                {"id": "recent", "type": "habit", "date": iso_utc(-10), "details": {}},
                {"id": "old", "type": "habit", "date": iso_utc(-95), "details": {}},
            ],
        }]})
        self.assertEqual([event.id for event in self.repo.get_user_events("u-1")], ["recent"])

    def test_unknown_event_and_profile_fields_are_preserved(self):
        self.repo.load_from_json({"users": [{
            "profile": {"id": "u-1", "future_profile_field": {"a": 1}},
            "events": [{
                "id": "e-1", "type": "flight", "date": iso_utc(-1),
                "details": {"departure": "Berlin"}, "future_event_field": "kept",
            }],
        }]})
        self.assertEqual(self.repo.get_user_profile("u-1")["future_profile_field"], {"a": 1})
        row = self.repo.conn.execute("SELECT raw_json FROM events WHERE user_id = 'u-1'").fetchone()
        self.assertEqual(__import__("json").loads(row["raw_json"])["future_event_field"], "kept")

    def test_dataset_namespace_prevents_identity_collision(self):
        first = self.repo.storage_user_id("42", "dataset-a")
        second = self.repo.storage_user_id("42", "dataset-b")
        self.assertNotEqual(first, second)
        self.repo.load_from_json({"users": [{"profile": {"id": "42", "name": "A"}, "events": []}]}, namespace="dataset-a")
        self.repo.load_from_json({"users": [{"profile": {"id": "42", "name": "B"}, "events": []}]}, namespace="dataset-b")
        self.assertEqual(self.repo.get_user_profile(first)["name"], "A")
        self.assertEqual(self.repo.get_user_profile(second)["name"], "B")

    def test_malformed_event_rejects_whole_import(self):
        with self.assertRaises(DatasetValidationError):
            self.repo.load_from_json({"users": [{
                "profile": {"id": "bad"},
                "events": [{"id": "e", "type": "sleep"}],
            }]})
        self.assertEqual(self.repo.get_user_profile("bad"), {})

    def test_event_summaries_cover_90_day_window(self):
        self.repo.load_from_json({"users": [{
            "profile": {"id": "u-stats"},
            "events": [
                {"id": "h1", "type": "habit_fail", "date": iso_utc(-3), "details": {"name": "reading"}},
                {"id": "h2", "type": "habit_fail", "date": iso_utc(-4), "details": {"name": "reading"}},
                {"id": "h-old", "type": "habit_fail", "date": iso_utc(-100), "details": {"name": "reading"}},
                {"id": "s1", "type": "sleep", "date": iso_utc(-1), "details": {"duration": 7}},
            ],
        }]})
        self.assertEqual(self.repo.get_user_habit_stats("u-stats"), {"habit_fail (reading)": 2})
        self.assertEqual(self.repo.get_user_event_type_counts("u-stats"), {"habit_fail": 2, "sleep": 1})

    def test_flat_user_and_event_aliases_are_accepted(self):
        self.repo.load_from_json({"users": [{
            "user_id": "flat-user",
            "goal": "move more",
            "events": [{
                "event_id": "walk-1", "event_type": "workout",
                "timestamp": iso_utc(-1), "payload": {"type": "walk"},
            }],
        }]})
        events = self.repo.get_user_events("flat-user")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].id, "walk-1")
        self.assertEqual(events[0].details, {"type": "walk"})

    def test_sain_dashboard_storage_still_works(self):
        state = self.repo.get_sain_state("frontend-user")
        self.assertEqual(state["user_id"], "frontend-user")
        self.repo.save_sain_dashboard("frontend-user", ["sleep_card"], {"sleep_card": {"size": "half"}})
        self.assertEqual(self.repo.get_sain_state("frontend-user")["widget_ids"], ["sleep_card"])

    def test_old_sqlite_schema_is_migrated(self):
        handle, path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        try:
            connection = sqlite3.connect(path)
            connection.executescript("""
                CREATE TABLE users (id TEXT PRIMARY KEY, goal TEXT, disabled_widgets TEXT);
                INSERT INTO users VALUES ('legacy-user', 'old goal', '[]');
                CREATE TABLE events (
                    id TEXT PRIMARY KEY, user_id TEXT, type TEXT, date TEXT, details TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );
                INSERT INTO events VALUES
                    ('legacy-event', 'legacy-user', 'sleep', '2026-11-15T22:00:00Z', '{"duration":8}');
                CREATE TABLE sain_dashboards (
                    user_id TEXT PRIMARY KEY, widget_ids TEXT NOT NULL,
                    widget_configs TEXT NOT NULL DEFAULT '{}', active_mode_id TEXT
                );
                CREATE TABLE sain_modes (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '', widget_ids TEXT NOT NULL,
                    widget_configs TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO sain_modes
                    (id, user_id, name, description, widget_ids, widget_configs)
                    VALUES ('flight', 'legacy-user', 'Flight', '', '["sleep_card"]', '{}');
            """)
            connection.commit()
            connection.close()

            migrated = SQLiteRepository(path)
            self.assertEqual(migrated.get_user_events("legacy-user")[0].details, {"duration": 8})
            self.assertEqual(migrated.get_sain_state("legacy-user")["user_id"], "legacy-user")
            migrated.conn.close()
        finally:
            if os.path.exists(path):
                os.remove(path)


if __name__ == "__main__":
    unittest.main()
