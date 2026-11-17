import os
import httpx
from widget_service import generate_morning_screen
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Literal, Optional
from repository import repo
from llm_service import ask_llm_in_batches
from sain_service import chat_with_sain, WIDGETS

class RunRequest(BaseModel):
    case: int
    dataset_code: str

app = FastAPI(title="SAIN Hackathon Backend")

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS", "http://localhost:5173,http://localhost:3000,http://localhost:4173"
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

HACK_API_URL = os.getenv("HACK_API_URL", "https://hack-api.be-healthy.tech")

# --- МОНИТОРИНГ И ХЕЛСЧЕКИ ---
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
    history = [turn.model_dump() if hasattr(turn, "model_dump") else turn.dict() for turn in payload.history]
    return await chat_with_sain(payload.user_id, payload.message.strip(), history=history)

# --- ОСНОВНОЙ ЭНДПОИНТ ДЛЯ ОРГАНИЗАТОРОВ ---
@app.post("/run")
async def run_case(payload: RunRequest, authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing token")
    if payload.case != 1:
        raise HTTPException(status_code=400, detail="This server handles only Case 1")

    # --- 1. ЗАГРУЗКА ДАННЫХ ---
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(
            f"{HACK_API_URL}/case/1/getData",
            params={"dataset_code": payload.dataset_code},
            headers={"Authorization": authorization}
        )
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to get data")
            
        dataset = response.json()
        
    # Сохраняем в In-Memory базу (SQLite в /tmp)
    repo.load_from_json(dataset)

    # Вытаскиваем вопросы и пользователей
    raw_questions = dataset.get("questions", [])
    raw_users = dataset.get("users", [])
    
    # Очищаем исходный тяжелый JSON, чтобы не пробить лимит в 512 МБ ОЗУ[span_1](start_span)[span_1](end_span)
    del dataset 

    # --- 2. БИЗНЕС-ЛОГИКА ---
    final_questions_answers = []
    final_mornings = []

    # Метрика M (Ответы на вопросы через LLM с батчингом)
    questions_by_user = {}
    for q in raw_questions:
        uid = q.get("user_id")
        if uid not in questions_by_user:
            questions_by_user[uid] = []
        questions_by_user[uid].append(q)

    for user_id, user_qs in questions_by_user.items():
        answers = await ask_llm_in_batches(user_id, user_qs)
        final_questions_answers.extend(answers)

    # Метрика W (Экраны утра - генерация виджетов)
    for user_data in raw_users:
        user_id = user_data["profile"]["id"]
        
        # Делегируем выбор виджетов сервису
        user_widgets = generate_morning_screen(user_id)
        
        final_mornings.append({
            "user_id": user_id,
            "widgets": user_widgets
        })

    # --- 3. ФОРМИРОВАНИЕ ОТВЕТА (Строго по контракту кейса 1) ---
    return {
        "questions": final_questions_answers,
        "mornings": final_mornings
    }
