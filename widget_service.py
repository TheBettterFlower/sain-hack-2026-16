from repository import repo

def generate_morning_screen(user_id: str) -> list:
    """
    Анализирует день пользователя и подбирает от 1 до 4 релевантных виджетов.
    В будущем фронтенд отрисует их на React на основе этого JSON.
    """
    active_widgets = repo.get_active_widgets(user_id)
    events = repo.get_user_events(user_id)
    
    selected_widgets = []

    # 1. Анализируем последние события пользователя
    has_failed_habit = False
    sleep_duration = 0
    
    if events:
        # Смотрим последние 5 событий для оценки контекста утра
        recent_events = events[-5:]
        for event in recent_events:
            if event.type.lower() == "habit_fail":
                has_failed_habit = True
            elif event.type.lower() == "sleep":
                sleep_duration = event.details.get("duration", 0)

    # 2. Движок правил (формируем массив от 1 до 4 виджетов)

    # Правило А: Если был срыв привычки, обязательно предлагаем начать заново (restart_card)
    if has_failed_habit and "restart_card" in active_widgets:
        selected_widgets.append({
            "id": "restart_card",
            "payload": {
                "title": "Не сдавайся!",
                "message": "Вчера был срыв, но сегодня новый день. Продолжим?"
            }
        })

    # Правило Б: Если спал мало (меньше 6 часов), показываем советы по сну
    if sleep_duration > 0 and sleep_duration < 6 and "sleep_card" in active_widgets:
        selected_widgets.append({
            "id": "sleep_card",
            "payload": {
                "title": "Сон",
                "duration": f"{sleep_duration}ч",
                "status": "bad"
            }
        })
    elif "day_plan" in active_widgets:
        # Если со сном всё ок, даем план на день (если разрешен)
        selected_widgets.append({
            "id": "day_plan",
            "payload": {
                "title": "План на сегодня",
                "tasks": ["Тренировка", "Чтение"]
            }
        })
        
    # Правило В: Докидываем кольцо активности, если лимит виджетов позволяет
    if "steps_ring" in active_widgets and len(selected_widgets) < 4:
        selected_widgets.append({
            "id": "steps_ring",
            "payload": {
                "title": "Шаги",
                "current": 2500,
                "target": 10000
            }
        })

    # Гарантируем, что не превысили лимит (от 1 до 4 виджетов)
    return selected_widgets[:4]
