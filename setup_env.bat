@echo off
:: Batch script to setup environment for AI Multi-Docs Extraction Pipeline
title AI Multi-Docs Extraction Pipeline - Environment Setup

echo ==========================================================
echo  AI Multi-Docs Extraction Pipeline - Environment Setup
echo ==========================================================
echo.

:: 1. Check & Create Python Virtual Environment (.venv)
if not exist .venv (
    echo [INFO] Creating Python virtual environment (.venv)...
    python -m venv .venv
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment. Please ensure Python is installed and in PATH.
        pause
        exit /b 1
    )
    echo [SUCCESS] Virtual environment created successfully.
) else (
    echo [INFO] Virtual environment (.venv) already exists.
)

:: 2. Upgrade pip and install requirements
echo.
echo [INFO] Installing / Updating dependencies from requirements.txt...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install dependencies. Please check network connection or requirements.txt.
    pause
    exit /b 1
)
echo [SUCCESS] Dependencies installed successfully.

:: 3. Setup .env file
echo.
if not exist .env (
    echo [INFO] Creating .env file from .env.example...
    copy .env.example .env
    echo [WARNING] Please update .env with your actual GEMINI_API_KEY if needed.
) else (
    echo [INFO] .env file already exists.
)

:: 4. Configure Git Hooks (.githooks)
echo.
if exist .githooks (
    echo [INFO] Configuring Git hooks path to .githooks...
    git config core.hooksPath .githooks
    echo [SUCCESS] Git hooks configured successfully.
)

:: 5. Initialize Pipeline System Directories & Database Schema
echo.
echo [INFO] Initializing system directories and SQLite database schema...
python main.py --step init

if %ERRORLEVEL% neq 0 (
    echo [ERROR] System initialization encountered errors.
    pause
    exit /b 1
)

echo.
echo ==========================================================
echo  [SUCCESS] Environment setup completed successfully!
echo ==========================================================
echo.
echo You can now run the Streamlit Web UI by executing:
echo   run_ui_streamlit.bat
echo Or run pipeline steps directly using:
echo   python main.py --step <step_name>
echo.
pause
