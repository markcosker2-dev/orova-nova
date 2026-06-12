@echo off
echo === OROVA Apollo Scraper Setup for Windows ===
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.11+ from python.org
    pause
    exit /b 1
)
echo [OK] Python found

:: Install playwright
echo [*] Installing Playwright...
pip install playwright
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install playwright
    pause
    exit /b 1
)
echo [OK] Playwright installed

:: Install browsers
echo [*] Installing Chromium browser...
python -m playwright install chromium
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install Chromium
    pause
    exit /b 1
)
echo [OK] Chromium installed

:: Check for cookies
set COOKIE_FILE=app\skills\apollo_scraper\apollo_cookies.json
if exist "%COOKIE_FILE%" (
    echo [OK] Apollo cookies found
) else (
    echo [WARN] No Apollo cookies found. To use Apollo scraper:
    echo   1. Open Chrome and log into app.apollo.io
    echo   2. Install 'EditThisCookie' extension
    echo   3. Export cookies as JSON
    echo   4. Save to: %CD%\%COOKIE_FILE%
)

echo.
echo === Setup Complete ===
echo.
echo To test the scraper:
echo   python -c "import asyncio; from app.skills.apollo_free_scraper import search_apollo_and_enrich; print(asyncio.run(search_apollo_and_enrich('test', max_results=5)))"
echo.
pause