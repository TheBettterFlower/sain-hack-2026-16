import os
import asyncio
import json
from openai import AsyncOpenAI
from repository import repo

# --- ПЕРЕКЛЮЧАТЕЛЬ ОКРУЖЕНИЯ ---
# Защищает лимит в 300к токенов. Локально отдаем фейк, на сервере - реальную LLM.
IS_DEV = os.getenv("ENV", "dev") == "dev"

client = AsyncOpenAI(
    base_url=os.getenv("LLM_BASE_URL", "https://bifrost.be-healthy.tech/v1"),
    api_key=os.getenv("LLM_API_KEY", "dev-key")
)
MODEL_NAME = os.getenv("LLM_MODEL", "gpt-6-luna")

def build_user_context(user_id: str, events: list) -> str:
    """
    Гибридное сжатие: сон/тренировки достаем из горячего кэша (events), 
    а агрегацию за 90 дней запрашиваем у базы через SQL.
    """
    if not events:
        return "Нет данных."

    sleep_logs = []
    workouts = []

    # Оставляем Python-цикл только для хронологии последних 14 дней
    for event in events:
        e_type = event.type.lower()
        date = event.date
        details = event.details

        if e_type == "sleep":
            hours = details.get("duration", 0)
            sleep_logs.append(f"{date}: {hours}ч")
        elif e_type == "workout":
            w_type = details.get("type", "активность")
            workouts.append(f"{date}: {w_type}")

    # Запрашиваем готовую статистику напрямую из базы данных SQLite
    habit_counts = repo.get_user_habit_stats(user_id)

    parts = []
    if sleep_logs:
        parts.append("Сон (последние 14 дней): " + "; ".join(sleep_logs[-14:]))
    if workouts:
        parts.append("Тренировки (последние 14 дней): " + "; ".join(workouts[-14:]))
    if habit_counts:
        stats = ", ".join([f"{k}: {v} раз" for k, v in habit_counts.items()])
        parts.append(f"Сводка за 90 дней: {stats}")

    return "\n".join(parts)


async def ask_llm_in_batches(user_id: str, user_questions: list) -> list:
    """Обрабатывает вопросы пачками, чтобы не пробить лимит 30 RPM"""
    
    # --- ЗАЩИТА ТОКЕНОВ ПРИ ЛОКАЛЬНОЙ ОТЛАДКЕ ---
    if IS_DEV:
        print(f"DEV MODE: Возвращаем мок-ответы для юзера {user_id} (экономим токены!)")
        await asyncio.sleep(0.5) 
        return [{"question_id": q["id"], "answer": "A"} for q in user_questions]

    # Достаем события пользователя из базы
    events = repo.get_user_events(user_id)
    
    # Сжимаем 90 дней истории в текст (передаем и user_id, и events)
    context_text = build_user_context(user_id, events) 
    
    batch_size = 20
    results = []
    
    for i in range(0, len(user_questions), batch_size):
        batch = user_questions[i:i + batch_size]
        
        prompt = f"""
        Ты — аналитик данных. Проанализируй контекст пользователя и ответь на вопросы.
        СТРОГОЕ ПРАВИЛО: Не давай медицинских советов, не используй диагнозы, названия лечения и дозировки.
        
        Контекст пользователя (события за 90 дней):
        {context_text}
        
        Вопросы:
        {json.dumps(batch, ensure_ascii=False)}
        
        Верни ответ в формате валидного JSON-массива, где каждый объект содержит:
        "question_id" и "answer" (строго A, B, C, D или X, если ответа в контексте нет).
        """
        
        # --- ПАТТЕРН RETRY С EXPONENTIAL BACKOFF ---
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=2500,
                    response_format={"type": "json_object"}
                )
                
                raw_content = response.choices[0].message.content
                batch_answers = json.loads(raw_content)
                results.extend(batch_answers.get("answers", []))
                
                break # Успех - выходим из цикла retry
                
            except Exception as e:
                print(f"Ошибка API (попытка {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    wait_time = 2 ** (attempt + 1)
                    print(f"Ждем {wait_time} сек. перед повтором...")
                    await asyncio.sleep(wait_time)
                else:
                    print("Провал после 3 попыток. Заполняем пропущенные ответы 'X'.")
                    for q in batch:
                        results.append({"question_id": q["id"], "answer": "X"})

    return results
