import os
import asyncio
import json
from openai import AsyncOpenAI # Асинхронный клиент для неблокирующей работы
from repository import repo

# Инициализируем клиент ключами из переменных окружения[span_10](start_span)[span_10](end_span)
client = AsyncOpenAI(
    base_url=os.getenv("LLM_BASE_URL", "https://bifrost.be-healthy.tech/v1"),
    api_key=os.getenv("LLM_API_KEY", "dev-key") # Локально бери из файла llm.key
)
MODEL_NAME = os.getenv("LLM_MODEL", "gpt-6-luna")

def build_user_context(events: list) -> str:
    """
    Сжимает сырые события в компактное текстовое досье (Data Transformation).
    """
    if not events:
        return "Нет данных."

    # Хэш-таблицы для агрегации (аналог map в Go)
    sleep_logs = []
    workouts = []
    habit_counts = {}

    for event in events:
        # Pydantic-объекты из нашего In-Memory репозитория
        e_type = event.type.lower()
        date = event.date
        details = event.details

        if e_type == "sleep":
            hours = details.get("duration", 0)
            sleep_logs.append(f"{date}: {hours}ч")
        elif e_type == "workout":
            w_type = details.get("type", "активность")
            workouts.append(f"{date}: {w_type}")
        else:
            # Агрегируем остальные повторяющиеся события (например, питание или воду)
            # Считаем частоту за 90 дней
            key = f"{e_type}"
            if "name" in details:
                key += f" ({details['name']})"
            habit_counts[key] = habit_counts.get(key, 0) + 1

    # Собираем итоговую строку. 
    # Ограничиваем историю сна и тренировок последними 14 днями, чтобы экономить токены.
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
    
    # 1. Достаем события пользователя из нашей In-Memory базы
    events = repo.get_user_events(user_id)
    
    # Сюда нужно написать функцию, которая сожмет 90 дней сырых данных
    # в компактное текстовое "досье", чтобы сэкономить токены.
    context_text = build_user_context(events) 
    
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
                
                # Если всё прошло успешно, принудительно выходим из цикла retry
                break 
                
            except Exception as e:
                print(f"Ошибка API (попытка {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    # Ждем 2, 4 секунды перед следующей попыткой (экспоненциальный рост)
                    wait_time = 2 ** (attempt + 1)
                    print(f"Ждем {wait_time} сек. перед повтором...")
                    await asyncio.sleep(wait_time)
                else:
                    print("Провал после 3 попыток. Заполняем пропущенные ответы 'X'.")
                    # Чтобы не сломать метрику ответа, в случае полного отказа API 
                    # возвращаем безопасный вариант "X" (нет данных)
                    for q in batch:
                        results.append({"question_id": q["id"], "answer": "X"})

    return results
