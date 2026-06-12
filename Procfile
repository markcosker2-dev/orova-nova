release: python -c "from app.core.database import DatabaseManager; DatabaseManager.init_db(); print('DB ready')"
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
