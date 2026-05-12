import threading
import uvicorn

# Start FastAPI in background thread on port 10000
def run_web():
    uvicorn.run('app.dashboard.mission_control:app', host='0.0.0.0', port=10000)

web_thread = threading.Thread(target=run_web, daemon=True)
web_thread.start()
print('Web dashboard started on port 10000')

# Then import and run telegram bot
from app.main import main
import asyncio

if __name__ == '__main__':
    main()

