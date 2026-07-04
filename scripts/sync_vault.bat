@echo off
REM Double-click to sync Nova's latest production learning into the Obsidian vault.
REM Pulls leads, CEO briefs, and learned strategies from the live Render backend.
REM Needs DASHBOARD_API_KEY + RENDER_EXTERNAL_URL in .env (already set).

cd /d "%~dp0.."

set "VENV_PY=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe"
if exist "%VENV_PY%" (
    "%VENV_PY%" scripts\vault_pull.py
) else (
    python scripts\vault_pull.py
)

echo.
echo Done. Open the vault in Obsidian to see the latest.
pause
