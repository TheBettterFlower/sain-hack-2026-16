import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from openai import AsyncOpenAI

from prompts import SYSTEM_PROMPT_TEMPLATE
from repository import repo


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# SAIN_CHAT_MOCK=0 must activate the real LLM both in organizer /run and chat.
MOCK_MODE = _env_flag("SAIN_CHAT_MOCK", os.getenv("ENV", "dev").strip().lower() == "dev")

client = AsyncOpenAI(
    base_url=os.getenv("LLM_BASE_URL", "https://bifrost.be-healthy.tech/v1"),
    api_key=os.getenv("LLM_API_KEY", "dev-key"),
)
MODEL_NAME = os.getenv("LLM_MODEL", "gpt-6-luna")


def _parse_date(value: str):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _compact_json(value: Any, max_chars: int = 700) -> str:
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        encoded = str(value)
    return encoded if len(encoded) <= max_chars else encoded[: max_chars - 1] + "…"


def build_user_context(user_id: str, events: list) -> str:
    """Build a factual context from the persisted profile and last 90 days."""
    profile = repo.get_user_profile(user_id)
    now = datetime.now(timezone.utc)
    cutoff_14d = now - timedelta(days=14)

    parts = []
    profile_context = {
        key: value for key, value in profile.items()
        if key not in {"id", "user_id", "userId", "disabled_widgets"}
    }
    if profile_context:
        parts.append("Профиль пользователя (факты из источника): " + _compact_json(profile_context, 2500))

    source = repo.get_user_source(user_id)
    source_extras = {
        key: value for key, value in source.items()
        if key not in {"profile", "events", "id", "user_id", "userId"}
        and key not in profile
    }
    if source_extras:
        parts.append("Дополнительные данные пользователя: " + _compact_json(source_extras, 1500))

    recent_sleep = []
    recent_workouts = []
    recent_events = []
    context_sensitive_events = []
    for event in events:
        event_date = _parse_date(event.date)
        if event_date and cutoff_14d <= event_date <= now:
            if event.type.lower() == "sleep":
                duration = event.details.get("duration")
                if duration is not None:
                    recent_sleep.append(f"{event.date}: {duration} ч")
            elif event.type.lower() == "workout":
                activity = event.details.get("type", event.details.get("name", "активность"))
                recent_workouts.append(f"{event.date}: {_compact_json(activity, 120)}")

        # Include other event types too, so context can surface patterns that
        # are not hard-coded into the application (e.g. flights/travel).
        event_line = f"{event.date} | {event.type} | {_compact_json(event.details, 500)}"
        recent_events.append(event_line)

        # Keep potentially explanatory travel and food/diet events even when
        # they are older than the latest 40 records. The source schema is
        # extensible, so inspect both event type and its raw details.
        searchable = (event.type + " " + _compact_json(event.details, 700)).lower()
        related_keywords = (
            "flight", "travel", "trip", "journey", "перелёт", "перелет",
            "самолёт", "самолет", "поездк", "diet", "meal", "food",
            "nutrition", "еда", "диет", "питан", "приём пищи", "прием пищи",
        )
        if any(keyword in searchable for keyword in related_keywords):
            context_sensitive_events.append(event_line)

    if recent_sleep:
        parts.append("Сон за последние 14 календарных дней: " + "; ".join(recent_sleep[-20:]))
    if recent_workouts:
        parts.append("Тренировки за последние 14 календарных дней: " + "; ".join(recent_workouts[-20:]))

    event_type_counts = repo.get_user_event_type_counts(user_id, days=90)
    if event_type_counts:
        counts_text = ", ".join(f"{event_type}: {count}" for event_type, count in list(event_type_counts.items())[:20])
        parts.append(f"Количество событий каждого типа за 90 дней: {counts_text}")

    stats = repo.get_user_habit_stats(user_id, days=90)
    if stats:
        stat_text = ", ".join(f"{key}: {count} раз" for key, count in list(stats.items())[:20])
        parts.append(f"Сводка привычек за последние 90 дней: {stat_text}")

    if context_sensitive_events:
        # Avoid duplicates from the recent-event section while retaining older
        # travel/diet records that may explain recurring patterns.
        special = list(dict.fromkeys(context_sensitive_events))[-20:]
        parts.append("События, которые могут быть связаны с поездками или питанием (до 20 записей за 90 дней):\n" + "\n".join(special))

    if recent_events:
        parts.append("Последние события за доступный период (не более 40 записей):\n" + "\n".join(recent_events[-40:]))

    if not parts:
        return "За последние 90 дней нет сохранённых событий или заполненных данных профиля. Не делай предположений о привычках пользователя."
    return "\n".join(parts)


def _question_identifier(question: dict):
    return question.get("id", question.get("question_id"))


def _normalize_answers(batch: list, model_payload: Any) -> list:
    """Return exactly one valid A/B/C/D/X answer per requested question."""
    raw_answers = model_payload.get("answers", []) if isinstance(model_payload, dict) else []
    if not isinstance(raw_answers, list):
        raw_answers = []

    answer_by_id = {}
    for item in raw_answers:
        if not isinstance(item, dict):
            continue
        question_id = item.get("question_id", item.get("id"))
        answer = item.get("answer")
        if answer is not None:
            normalized = str(answer).strip().upper()
            if normalized in {"A", "B", "C", "D", "X"}:
                answer_by_id[str(question_id)] = normalized

    result = []
    for question in batch:
        question_id = _question_identifier(question)
        result.append({
            "question_id": question_id,
            "answer": answer_by_id.get(str(question_id), "X"),
        })
    return result


async def ask_llm_in_batches(user_id: str, user_questions: list) -> list:
    """Answer organizer questions in batches, preserving the required contract."""
    if not user_questions:
        return []

    if MOCK_MODE:
        print(f"SAIN MOCK MODE: возвращаем тестовые ответы для пользователя {user_id}")
        await asyncio.sleep(0)
        return [
            {"question_id": _question_identifier(question), "answer": "A"}
            for question in user_questions
        ]

    events = repo.get_user_events(user_id, days=90)
    context_text = build_user_context(user_id, events)

    batch_size = 20
    results = []
    for start in range(0, len(user_questions), batch_size):
        batch = user_questions[start : start + batch_size]
        prompt = SYSTEM_PROMPT_TEMPLATE.format(
            context=context_text,
            questions=json.dumps(batch, ensure_ascii=False, default=str),
        )

        batch_result = None
        for attempt in range(3):
            try:
                response = await client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=2500,
                    response_format={"type": "json_object"},
                    temperature=0.1,
                )
                raw_content = response.choices[0].message.content or "{}"
                parsed = json.loads(raw_content)
                batch_result = _normalize_answers(batch, parsed)
                break
            except Exception as exc:
                print(f"Organizer LLM error (attempt {attempt + 1}/3): {exc}")
                if attempt < 2:
                    await asyncio.sleep(2 ** (attempt + 1))

        if batch_result is None:
            batch_result = [
                {"question_id": _question_identifier(question), "answer": "X"}
                for question in batch
            ]
        results.extend(batch_result)

    return results
