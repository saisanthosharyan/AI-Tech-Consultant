@echo off
TITLE AI Tech Consultant — Startup Launcher
echo ============================================================
echo   AI TECH CONSULTANT — MULTI-AGENT CAPSTONE PLATFORM
echo ============================================================
echo.

REM Verify Python installation
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not found in PATH. Please install Python 3.10+.
    pause
    exit /b 1
)

echo [1/3] Verifying data directories...
if not exist "data" mkdir data
if not exist "data\vector_index" mkdir data\vector_index

echo [2/3] Starting Task 1 Knowledge Brain REST API on port 8000...
start "Knowledge Brain API (Port 8000)" cmd /k "python -m uvicorn kb_app.main:app --host 0.0.0.0 --port 8000"

echo [Waiting 3 seconds for Knowledge Brain API to bind...]
timeout /t 3 /nobreak >nul

echo [3/3] Starting Unified Streamlit Dashboard on port 8501...
python -m streamlit run frontend\app.py

pause
