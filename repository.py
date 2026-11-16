from typing import List, Dict, Optional
from pydantic import BaseModel

# --- 1. СТРУКТУРЫ ДАННЫХ (Аналог struct в Go / классов в C++) ---

class Event(BaseModel):
    id: str
    type: str
    date: str
    # В Python Pydantic сам валидирует типы, как строгая типизация в плюсах
    details: Dict 

class UserProfile(BaseModel):
    id: str
    goal: str
    disabled_widgets: List[str]

class User(BaseModel):
    profile: UserProfile
    events: List[Event]

# --- 2. СЛОЙ ХРАНЕНИЯ (Паттерн In-Memory Repository) ---
# В Go ты бы описал это через интерфейс type UserRepository interface { ... }
# Это позволяет легко подменить память на PostgreSQL в будущем.

class DatasetRepository:
    def __init__(self):
        # Храним пользователей в хэш-таблице (dict) для быстрого доступа за O(1)
        # Это полный аналог std::unordered_map в C++ или map[string]User в Go
        self._users: Dict[str, User] = {}

    def load_from_json(self, raw_data: dict):
        """Парсит сырой JSON от организаторов и очищает память"""
        self._users.clear()
        
        # Предположим, сырой JSON имеет поле "users"
        for user_data in raw_data.get("users", []):
            user = User(**user_data)
            self._users[user.profile.id] = user

    def get_user_events(self, user_id: str) -> List[Event]:
        """Возвращает ленту событий конкретного пользователя"""
        user = self._users.get(user_id)
        if user:
            return user.events
        return []
        
    def get_active_widgets(self, user_id: str) -> List[str]:
        """Пример бизнес-логики: какие виджеты разрешено показывать"""
        user = self._users.get(user_id)
        if not user:
            return []
        
        # Тут мы отфильтруем виджеты, которые пользователь отключил[span_2](start_span)[span_2](end_span)
        all_widgets = ["sleep_card", "day_plan", "workout_suggest"] # и т.д.
        return [w for w in all_widgets if w not in user.profile.disabled_widgets]

# Создаем единственный экземпляр (Singleton) нашего хранилища
repo = DatasetRepository()
