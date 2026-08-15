@echo off
:: Batch script to run the Streamlit Web UI on Windows
title AI Multi-Docs Extraction Pipeline - Streamlit UI

echo ==========================================================
echo Starting AI Multi-Docs Extraction Pipeline...
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

:: Activate virtual environment and start Streamlit
echo [INFO] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [INFO] Starting Streamlit app...
streamlit run src/ui/app.py

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Streamlit failed to start or exited with an error.
    pause
)
