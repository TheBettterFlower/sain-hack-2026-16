import os
import httpx
from widget_service import generate_morning_screen
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from repository import repo
from llm_service import ask_llm_in_batches # Подключаем наш сервис

class RunRequest(BaseModel):
    case: int
    dataset_code: str

app = FastAPI()
HACK_API_URL = os.getenv("HACK_API_URL", "https://hack-api.be-healthy.tech")

@app.get("/")
async def healthcheck():
    return {"status": "ok"}

@app.post("/run")
async def run_case(
    payload: RunRequest, 
    authorization: str = Header(None)
):
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
        
    # Сохраняем в In-Memory базу
    repo.load_from_json(dataset)

    # Вытаскиваем вопросы (предполагаем, что они лежат в корне JSON как 'questions')
    raw_questions = dataset.get("questions", [])
    raw_users = dataset.get("users", [])
    
    # Очищаем исходный тяжелый JSON, чтобы не пробить лимит в 512 МБ
    del dataset 

    # --- 2. БИЗНЕС-ЛОГИКА ---
    final_questions_answers = []
    final_mornings = []

    # Метрика M (Ответы на вопросы)
    # Группируем вопросы по пользователям, чтобы слать в LLM правильный контекст
    questions_by_user = {}
    for q in raw_questions:
        uid = q.get("user_id")
        if uid not in questions_by_user:
            questions_by_user[uid] = []
        questions_by_user[uid].append(q)

    for user_id, user_qs in questions_by_user.items():
        # Дирижер вызывает сервис. В Go это был бы вызов метода интерфейса.
        answers = await ask_llm_in_batches(user_id, user_qs)
        final_questions_answers.extend(answers)

    # Метрика W (Экраны утра - генерация виджетов)
        # Метрика W (Экраны утра - генерация виджетов)
    for user_data in raw_users:
        user_id = user_data["profile"]["id"]
        
        # Делегируем выбор виджетов сервису
        user_widgets = generate_morning_screen(user_id)
        
        final_mornings.append({
            "user_id": user_id,
            "widgets": user_widgets
        })


    # --- 3. ФОРМИРОВАНИЕ ОТВЕТА ---
    return {
        "questions": final_questions_answers,
        "mornings": final_mornings
    }
