"""Load a small, synthetic dataset into a separate local SAIN database.

This script does not contact the organizer API or an LLM. It is intended only
for local UI/API testing. Run it with the same SAIN_DB_PATH as the backend.
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path


def iso_days_ago(days: int, *, hours: int = 9) -> str:
    value = datetime.now(timezone.utc) - timedelta(days=days)
    value = value.replace(hour=hours, minute=0, second=0, microsecond=0)
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def build_demo_dataset() -> dict:
    """Return deterministic user/event IDs with dates relative to the run."""
    return {
        "users": [
            {
                "profile": {
                    "id": "demo-alex",
                    "name": "Алексей (демо)",
                    "goal": "Поддерживать стабильный режим сна и регулярную активность",
                    "disabled_widgets": [],
                    "timezone": "Europe/Berlin",
                    "demo_record": True,
                },
                "events": [
                    {"id": "alex-sleep-78d", "type": "sleep", "date": iso_days_ago(78), "details": {"duration": 6.2, "quality": "обычный"}},
                    {"id": "alex-steps-12d", "type": "steps", "date": iso_days_ago(12), "details": {"steps": 6100, "target": 8000}},
                    {"id": "alex-sleep-6d", "type": "sleep", "date": iso_days_ago(6), "details": {"duration": 7.1, "quality": "хороший"}},
                    {"id": "alex-workout-4d", "type": "workout", "date": iso_days_ago(4), "details": {"type": "прогулка", "duration_minutes": 25}},
                    {"id": "alex-water-3d", "type": "water_intake", "date": iso_days_ago(3), "details": {"ml": 500}},
                    {"id": "alex-habit-2d", "type": "habit_done", "date": iso_days_ago(2), "details": {"name": "Вечерняя прогулка"}},
                    {"id": "alex-steps-1d", "type": "steps", "date": iso_days_ago(1), "details": {"steps": 7200, "target": 8000}},
                    {"id": "alex-sleep-0d", "type": "sleep", "date": iso_days_ago(0), "details": {"duration": 7.8, "quality": "хороший"}},
                ],
                "source_tag": "local-demo-fixture",
            },
            {
                "profile": {
                    "id": "demo-maria",
                    "name": "Мария (демо)",
                    "goal": "Отслеживать сон и постепенно выстраивать ежедневные привычки",
                    "disabled_widgets": ["energy_forecast"],
                    "timezone": "Europe/Berlin",
                    "demo_record": True,
                },
                "events": [
                    {"id": "maria-sleep-20d", "type": "sleep", "date": iso_days_ago(20), "details": {"duration": 6.5}},
                    {"id": "maria-habit-10d", "type": "habit_fail", "date": iso_days_ago(10), "details": {"name": "Режим отхода ко сну"}},
                    {"id": "maria-workout-2d", "type": "workout", "date": iso_days_ago(2), "details": {"type": "растяжка", "duration_minutes": 15}},
                    {"id": "maria-steps-1d", "type": "steps", "date": iso_days_ago(1), "details": {"count": 5300, "target": 7000}},
                    {"id": "maria-sleep-0d", "type": "sleep", "date": iso_days_ago(0), "details": {"duration": 6.9}},
                ],
                "source_tag": "local-demo-fixture",
            },
        ],
        "questions": [],
        "demo": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Загрузить синтетических пользователей SAIN для локального тестирования")
    parser.add_argument(
        "--db",
        default=os.getenv("SAIN_DB_PATH", "./data/sain_demo.db"),
        help="путь к отдельной SQLite базе (по умолчанию ./data/sain_demo.db)",
    )
    args = parser.parse_args()

    db_path = str(Path(args.db).expanduser())
    os.environ["SAIN_DB_PATH"] = db_path

    # Import only after SAIN_DB_PATH has been set: repository creates its
    # process-wide connection at import time.
    from repository import repo

    scope_mode = os.getenv("SAIN_USER_ID_SCOPE", "global").strip().lower()
    namespace = "local-demo" if scope_mode == "dataset" else None
    result = repo.load_from_json(build_demo_dataset(), namespace=namespace)

    print("Демо-данные SAIN загружены.")
    print(f"SQLite: {Path(db_path).resolve()}")
    print(f"Пространство ID: {'local-demo' if namespace else 'global'}")
    print(f"Пользователей обработано: {result['users_processed']}")
    print(f"Событий получено: {result['events_received']}")
    print("Пользователи для выбора во frontend:")
    for user in repo.list_users():
        print(f"  - {user['label']} | ID: {user['user_id']} | событий за 90 дней: {user['event_count_90d']}")
    print("Повторный запуск безопасен: ID событий стабильны, дубликаты не создаются.")
    print("Набор полностью синтетический и не обращается к API организаторов или LLM.")


if __name__ == "__main__":
    main()
