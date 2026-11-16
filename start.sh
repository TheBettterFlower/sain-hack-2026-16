#!/bin/bash
# Запускаем uvicorn (ASGI-сервер для FastAPI)
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"

