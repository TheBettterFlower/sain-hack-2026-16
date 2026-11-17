import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from llm_service import ask_llm_in_batches
from repository import DatasetValidationError, repo
from sain_service import WIDGETS, chat_with_sain
from widget_service import generate_morning_screen


class RunRequest(BaseModel):
    case: int
    dataset_code: str


app = FastAPI(title="SAIN Hackathon Backend")

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:5173,http://localhost:3000,http://localhost:4173",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

HACK_API_URL = os.getenv("HACK_API_URL", "https://hack-api.be-healthy.tech").rstrip("/")


@app.get("/")
async def root_health():
    return {"status": "ok", "service": "backend-team16"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


class SainChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1500)


class SainChatRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=2000)
    history: List[SainChatTurn] = Field(default_factory=list, max_length=16)


class SainDashboardUpdate(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    widget_ids: List[str] = Field(max_length=12)
    widget_configs: Optional[Dict[str, Dict[str, Any]]] = None
    active_mode_id: Optional[str] = Field(default=None, max_length=80)


def validate_dashboard_payload(payload: SainDashboardUpdate):
    if len(set(payload.widget_ids)) != len(payload.widget_ids):
        raise HTTPException(status_code=422, detail="Duplicate widget IDs are not allowed")
    invalid_ids = [widget_id for widget_id in payload.widget_ids if widget_id not in WIDGETS]
    if invalid_ids:
        raise HTTPException(status_code=422, detail=f"Unknown widget IDs: {invalid_ids}")

    safe_configs = {}
    for widget_id, config in (payload.widget_configs or {}).items():
        if widget_id not in WIDGETS or not isinstance(config, dict):
            continue
        clean = {}
        if config.get("size") in {"half", "full"}:
            clean["size"] = config["size"]
        title = config.get("title")
        if isinstance(title, str) and 0 < len(title.strip()) <= 40:
            clean["title"] = title.strip()
        if clean:
            safe_configs[widget_id] = clean
    return safe_configs


@app.get("/api/sain/users")
async def list_sain_users():
    """List users imported through the organizer /run endpoint."""
    return {"users": repo.list_users()}


@app.get("/api/sain/users/{user_id}/summary")
async def get_sain_user_summary(user_id: str):
    """Return factual, user-specific metrics for the frontend dashboard."""
    if not user_id or len(user_id) > 256:
        raise HTTPException(status_code=422, detail="Invalid user_id")
    if not repo.has_user(user_id):
        raise HTTPException(status_code=404, detail="User has not been imported yet")

    profile = repo.get_user_profile(user_id)
    events_14d = repo.get_user_events(user_id, days=14)
    event_counts_90d = repo.get_user_event_type_counts(user_id, days=90)
    now = datetime.now(timezone.utc)
    cutoff_14d = now - timedelta(days=14)

    recent_events = []
    for event in events_14d:
        try:
            event_date = datetime.fromisoformat(event.date.replace("Z", "+00:00"))
            if event_date.tzinfo is None:
                event_date = event_date.replace(tzinfo=timezone.utc)
            event_date = event_date.astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
        if cutoff_14d <= event_date <= now:
            recent_events.append((event, event_date))

    def numeric(value):
        try:
            number = float(value)
            return number if number >= 0 else None
        except (TypeError, ValueError):
            return None

    sleep_records = [(event, date) for event, date in recent_events if event.type.lower() == "sleep"]
    latest_sleep = max(sleep_records, key=lambda item: item[1]) if sleep_records else None
    sleep_metric = None
    if latest_sleep:
        duration = numeric(latest_sleep[0].details.get("duration"))
        if duration is not None:
            sleep_metric = {"duration": duration, "date": latest_sleep[0].date}

    step_records = [
        (event, date) for event, date in recent_events
        if event.type.lower() in {"steps", "step_count"}
    ]
    latest_steps = max(step_records, key=lambda item: item[1]) if step_records else None
    steps_metric = None
    if latest_steps:
        details = latest_steps[0].details
        current = numeric(details.get("steps", details.get("count", details.get("value"))))
        target = numeric(details.get("target"))
        if current is not None:
            steps_metric = {"current": current, "target": target, "date": latest_steps[0].date}

    workout_count = sum(1 for event, _ in recent_events if event.type.lower() == "workout")
    failed_habits = sum(
        1 for event, _ in recent_events
        if event.type.lower() in {"habit_fail", "habit_failed"}
    )
    total_events_90d = sum(event_counts_90d.values())
    goal = profile.get("goal", "") if isinstance(profile, dict) else ""
    label = next(
        (profile.get(key) for key in ("name", "full_name", "display_name", "username", "first_name")
         if isinstance(profile.get(key), str) and profile.get(key).strip()),
        str(profile.get("id", user_id)) if isinstance(profile, dict) else user_id,
    )

    return {
        "user_id": user_id,
        "profile": {"id": str(profile.get("id", user_id)), "label": str(label), "goal": goal},
        "metrics": {
            "total_events_14d": len(recent_events),
            "total_events_90d": total_events_90d,
            "event_counts_90d": event_counts_90d,
            "habit_stats_90d": repo.get_user_habit_stats(user_id, days=90),
            "latest_sleep": sleep_metric,
            "latest_steps": steps_metric,
            "workout_count_14d": workout_count,
            "failed_habits_14d": failed_habits,
            "latest_event_date": max((date for _, date in recent_events), default=None).isoformat() if recent_events else None,
        },
        "recommended_widgets": generate_morning_screen(user_id),
    }


@app.get("/api/sain/state/{user_id}")
async def get_sain_state(user_id: str):
    if not user_id or len(user_id) > 128:
        raise HTTPException(status_code=422, detail="Invalid user_id")
    return repo.get_sain_state(user_id)


@app.put("/api/sain/dashboard")
async def update_sain_dashboard(payload: SainDashboardUpdate):
    safe_configs = validate_dashboard_payload(payload)
    repo.save_sain_dashboard(
        payload.user_id,
        payload.widget_ids,
        safe_configs,
        payload.active_mode_id,
    )
    return repo.get_sain_state(payload.user_id)


@app.post("/api/sain/chat")
async def sain_chat(payload: SainChatRequest):
    history = [
        turn.model_dump() if hasattr(turn, "model_dump") else turn.dict()
        for turn in payload.history
    ]
    return await chat_with_sain(payload.user_id, payload.message.strip(), history=history)


def _question_user_id(question: dict) -> str:
    value = question.get("user_id")
    if value is None:
        value = question.get("userId")
    if value is None or isinstance(value, (dict, list)) or not str(value).strip():
        raise DatasetValidationError("У вопроса отсутствует корректный user_id")
    return str(value).strip()


def _question_id(question: dict) -> Any:
    value = question.get("id")
    if value is None:
        value = question.get("question_id")
    if value is None or isinstance(value, (dict, list)):
        raise DatasetValidationError("У вопроса отсутствует корректный id/question_id")
    return value


@app.post("/run")
async def run_case(payload: RunRequest, authorization: str = Header(None)):
    """Organizer entrypoint. The response contract stays questions + mornings."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing token")
    if payload.case != 1:
        raise HTTPException(status_code=400, detail="This server handles only Case 1")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{HACK_API_URL}/case/1/getData",
                params={"dataset_code": payload.dataset_code},
                headers={"Authorization": authorization},
            )
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Failed to get data from organizer API",
                )
            try:
                dataset = response.json()
            except ValueError as exc:
                raise HTTPException(status_code=502, detail="Organizer API returned invalid JSON") from exc
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not reach organizer API") from exc

    if not isinstance(dataset, dict):
        raise HTTPException(status_code=502, detail="Organizer JSON root must be an object")

    # Keep global IDs by default for compatibility with the current SAIN
    # frontend. If organizers confirm IDs are only local to each dataset,
    # switch to dataset scope and pass the same scope when looking up memory.
    user_scope_mode = os.getenv("SAIN_USER_ID_SCOPE", "global").strip().lower()
    if user_scope_mode not in {"global", "dataset"}:
        raise HTTPException(status_code=500, detail="SAIN_USER_ID_SCOPE must be 'global' or 'dataset'")
    namespace = payload.dataset_code if user_scope_mode == "dataset" else None

    try:
        raw_questions = dataset.get("questions", []) or []
        if not isinstance(raw_questions, list):
            raise DatasetValidationError("Поле questions должно быть массивом")

        normalized_questions = []
        for raw_question in raw_questions:
            if not isinstance(raw_question, dict):
                raise DatasetValidationError("Каждый вопрос должен быть объектом")
            external_id = _question_user_id(raw_question)
            question_id = _question_id(raw_question)
            question = dict(raw_question)
            question["id"] = question_id
            normalized_questions.append((external_id, question))

        # Validate the whole payload before writing anything to the database.
        import_result = repo.load_from_json(dataset, namespace=namespace)
        questions_by_user = defaultdict(list)
        for external_id, question in normalized_questions:
            storage_id = repo.storage_user_id(external_id, namespace)
            repo.ensure_user(storage_id)
            questions_by_user[storage_id].append(question)

    except DatasetValidationError as exc:
        raise HTTPException(status_code=502, detail=f"Unsupported organizer data: {exc}") from exc

    # The raw payload is no longer needed; normalized records are persisted.
    del dataset

    final_questions_answers = []
    for user_id, user_questions in questions_by_user.items():
        final_questions_answers.extend(await ask_llm_in_batches(user_id, user_questions))

    final_mornings = []
    for user in import_result["users"]:
        storage_id = user["storage_id"]
        final_mornings.append(
            {
                "user_id": user["external_id"],
                "widgets": generate_morning_screen(storage_id),
            }
        )

    # Keep the exact response shape expected by the organizer's Case 1 contract.
    return {
        "questions": final_questions_answers,
        "mornings": final_mornings,
    }
