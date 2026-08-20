@echo off
:: Batch wrapper script to launch cross-platform Python environment setup
title AI Multi-Docs Extraction Pipeline - Environment Setup
echo ==========================================================
echo  AI Multi-Docs Extraction Pipeline - Environment Setup
echo ==========================================================
echo.

:: Execute cross-platform Python setup script
python setup_env.py

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Setup encountered errors. Please check the log messages above.
    pause
    exit /b %ERRORLEVEL%
)

pause
