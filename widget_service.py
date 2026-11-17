from datetime import datetime, timedelta, timezone

from repository import repo


def _event_datetime(value: str):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _numeric(value):
    try:
        number = float(value)
        if number < 0:
            return None
        return int(number) if number.is_integer() else number
    except (TypeError, ValueError):
        return None


def generate_morning_screen(user_id: str) -> list:
    """Build a small morning screen from observed data, without fake metrics."""
    active_widgets = set(repo.get_active_widgets(user_id))
    events = repo.get_user_events(user_id, days=90)
    if not active_widgets:
        return []

    now = datetime.now(timezone.utc)
    cutoff_14d = now - timedelta(days=14)
    recent_events = []
    for event in events:
        event_date = _event_datetime(event.date)
        if event_date and cutoff_14d <= event_date <= now:
            recent_events.append(event)

    selected_widgets = []

    # Prefer the latest sleep record, rather than allowing an older record to
    # overwrite it merely because it appears later in an arbitrary JSON list.
    sleep_events = [event for event in recent_events if event.type.lower() == "sleep"]
    latest_sleep = max(sleep_events, key=lambda item: item.date) if sleep_events else None
    sleep_duration = None
    if latest_sleep:
        sleep_duration = _numeric(latest_sleep.details.get("duration"))

    has_failed_habit = any(event.type.lower() in {"habit_fail", "habit_failed"} for event in recent_events)
    if has_failed_habit and "restart_card" in active_widgets:
        selected_widgets.append({
            "id": "restart_card",
            "payload": {
                "title": "Новый старт",
                "message": "Не обязательно начинать идеально. Можно вернуться к привычке небольшим шагом.",
            },
        })

    if sleep_duration is not None and sleep_duration < 6 and "sleep_card" in active_widgets:
        selected_widgets.append({
            "id": "sleep_card",
            "payload": {
                "title": "Сон",
                "duration": f"{sleep_duration:g} ч",
                "status": "bad",
            },
        })

    # The step ring is shown only when a real step count exists in the data.
    step_events = [event for event in recent_events if event.type.lower() in {"steps", "step_count"}]
    latest_steps_event = max(step_events, key=lambda item: item.date) if step_events else None
    if latest_steps_event and "steps_ring" in active_widgets:
        current_steps = _numeric(
            latest_steps_event.details.get(
                "steps", latest_steps_event.details.get("count", latest_steps_event.details.get("value"))
            )
        )
        target_steps = _numeric(latest_steps_event.details.get("target"))
        if current_steps is not None:
            step_payload = {"title": "Шаги", "current": current_steps}
            if target_steps is not None:
                step_payload["target"] = target_steps
            selected_widgets.append({"id": "steps_ring", "payload": step_payload})

    # Avoid inventing calendar entries or activity figures. A neutral planning
    # card is a suggestion, not a statement about events on the user's calendar.
    if not selected_widgets and "day_plan" in active_widgets:
        selected_widgets.append({
            "id": "day_plan",
            "payload": {
                "title": "План на сегодня",
                "message": "Выбери одну небольшую задачу, которая будет полезна сегодня.",
                "tasks": [],
            },
        })

    # If there is relevant activity but no card matched, provide a neutral
    # reminder only when the user has that widget enabled.
    if not selected_widgets and "calendar_brief" in active_widgets:
        selected_widgets.append({
            "id": "calendar_brief",
            "payload": {"title": "Сегодня", "message": "Проверь свои планы на день."},
        })

    return selected_widgets[:4]
