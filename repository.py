import sqlite3
import json
from typing import List, Dict
from pydantic import BaseModel

# --- 1. СТРУКТУРЫ ДАННЫХ (Для совместимости с остальным кодом) ---
class Event(BaseModel):
    id: str
    type: str
    date: str
    details: Dict 

# --- 2. СЛОЙ ХРАНЕНИЯ (Паттерн Data Access Object через SQLite) ---
class SQLiteRepository:
    def __init__(self, db_path="/tmp/hackathon.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        """DDL (Data Definition Language): Создаем строгую реляционную схему таблиц"""
        cursor = self.conn.cursor()
        
        # Таблица пользователей (храним отключенные виджеты как JSON-строку)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                goal TEXT,
                disabled_widgets TEXT
            )
        ''')
        
        # Связь Один-ко-Многим (Один пользователь -> Много событий)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                type TEXT,
                date TEXT,
                details TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        
        # Оптимизация: Индекс (B-Tree). Ускоряет поиск событий юзера с O(N) до O(log N)
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_events ON events(user_id)')
        self.conn.commit()

    def load_from_json(self, raw_data: dict):
        """Парсит сырой JSON и заливает его в базу (ETL-процесс)"""
        cursor = self.conn.cursor()
        
        # Очищаем таблицы перед новой заливкой от стенда
        cursor.execute('DELETE FROM events')
        cursor.execute('DELETE FROM users')

        users_batch = []
        events_batch = []

        # Формируем плоские кортежи для базы данных
        for user_data in raw_data.get("users", []):
            profile = user_data["profile"]
            u_id = profile["id"]
            
            users_batch.append((
                u_id, 
                profile.get("goal", ""), 
                json.dumps(profile.get("disabled_widgets", []))
            ))
            
            for event in user_data.get("events", []):
                events_batch.append((
                    event["id"],
                    u_id,
                    event["type"],
                    event["date"],
                    json.dumps(event.get("details", {}))
                ))

        # Prepared Statements: Безопасная и быстрая массовая вставка.
        # Защищает от SQL-инъекций, в отличие от f-строк.
        cursor.executemany(
            'INSERT INTO users (id, goal, disabled_widgets) VALUES (?, ?, ?)', 
            users_batch
        )
        cursor.executemany(
            'INSERT INTO events (id, user_id, type, date, details) VALUES (?, ?, ?, ?, ?)', 
            events_batch
        )
        
        self.conn.commit() # Фиксируем транзакцию на диске

    def get_user_events(self, user_id: str) -> List[Event]:
        """SQL-запрос выборки событий конкретного пользователя"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM events WHERE user_id = ? ORDER BY date ASC', (user_id,))
        
        # Упаковываем обратно в Pydantic-модели, чтобы не сломать llm_service.py
        events = []
        for row in cursor.fetchall():
            events.append(Event(
                id=row["id"],
                type=row["type"],
                date=row["date"],
                details=json.loads(row["details"])
            ))
        return events

    def get_active_widgets(self, user_id: str) -> List[str]:
        """SQL-запрос для проверки разрешенных виджетов"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT disabled_widgets FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        
        if not row:
            return []
            
        disabled = json.loads(row["disabled_widgets"])
        all_widgets = ["sleep_card", "day_plan", "workout_suggest", "restart_card", "steps_ring"]
        
        return [w for w in all_widgets if w not in disabled]

    def get_user_habit_stats(self, user_id: str) -> dict:
        """
        Агрегация событий средствами SQL. 
        Разгружает CPU сервера, перекладывая подсчет на движок БД.
        """
        cursor = self.conn.cursor()
        
        # SQL-магия: используем json_extract для парсинга JSON прямо внутри базы данных
        cursor.execute('''
            SELECT 
                type,
                json_extract(details, '$.name') as detail_name,
                COUNT(*) as total_count
            FROM events
            WHERE user_id = ? AND type NOT IN ('sleep', 'workout')
            GROUP BY type, detail_name
            ORDER BY total_count DESC
        ''', (user_id,))
        
        stats = {}
        for row in cursor.fetchall():
            key = row["type"]
            # Если в JSON было поле name (например, название привычки), добавляем его в ключ
            if row["detail_name"]:
                key += f" ({row['detail_name']})"
            stats[key] = row["total_count"]
            
        return stats

# Создаем глобальный объект подключения
repo = SQLiteRepository()
