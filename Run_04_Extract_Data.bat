@echo off
echo ==========================================
echo   Run_04_Extract_Data: Running AI OCR
echo ==========================================
REM Check if GEMINI_API_KEY is defined
if "%GEMINI_API_KEY%"=="" (
    echo [WARNING] GEMINI_API_KEY is not defined in environment!
    echo Please make sure it is defined in .env file or command prompt.
)
.\.venv\Scripts\python.exe extract_data.py
echo ==========================================
pause
