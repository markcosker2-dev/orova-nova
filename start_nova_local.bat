@echo off
SETLOCAL EnableDelayedExpansion

echo 🚀 STARTING OROVA LOCAL ENGINE...
echo -----------------------------------

:: 1. Check for Python
python --version >nul 2>&1
if !errorlevel! neq 0 (
    echo ❌ Python not found. Please install Python 3.10+ from python.org
    pause
    exit /b
)

:: 2. Setup Virtual Environment
if not exist "venv" (
    echo 📦 Creating Virtual Environment...
    python -m venv venv
)

:: 3. Install Requirements
echo 📥 Installing dependencies (this may take a minute)...
call venv\Scripts\activate
pip install -r requirements.txt --quiet

:: 4. Verify Credentials
if not exist ".env" (
    echo ⚠️ .env file missing! Please create it from .env.example
    pause
    exit /b
)

if not exist "service_account.json" (
    echo ⚠️ service_account.json missing! Google Sheets will not work.
)

:: 5. Run Nova
echo 🧠 NOVA BRAIN INITIALIZING...
echo -----------------------------------
python app/main.py

pause
