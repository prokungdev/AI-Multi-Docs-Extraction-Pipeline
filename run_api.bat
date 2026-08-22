@echo off
:: Batch script to run the FastAPI REST API Server on Windows
title AI Multi-Docs Extraction Pipeline - REST API Server

echo ==========================================================
echo Starting AI Multi-Docs Extraction Pipeline REST API...
echo ==========================================================

:: Check if virtual environment exists
if not exist .venv (
    echo [ERROR] Virtual environment (.venv) not found.
    echo Please create the virtual environment first by running:
    echo   python -m venv .venv
    echo And install dependencies by running:
    echo   .venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

:: Activate virtual environment and start FastAPI via Uvicorn
echo [INFO] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [INFO] Starting FastAPI server on http://127.0.0.1:8000 ...
echo [INFO] Swagger API Docs available at http://127.0.0.1:8000/docs
uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8000

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] FastAPI server failed to start or exited with an error.
    pause
)
