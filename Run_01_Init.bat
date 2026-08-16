@echo off
echo ==========================================
echo   Run_01_Init: Resetting Pipeline System
echo ==========================================

REM 1. Delete SQLite Database
if exist pipeline_storage\pipeline.db (
    echo Deleting pipeline.db...
    del /f /q pipeline_storage\pipeline.db
)

REM 2. Clear split pages folder (including source subfolders)
if exist pipeline_storage\expense_receipt\02_split_pages (
    echo Clearing 02_split_pages...
    for /d %%p in (pipeline_storage\expense_receipt\02_split_pages\*) do rmdir /s /q "%%p"
    for /F "delims=" %%i in ('dir /b pipeline_storage\expense_receipt\02_split_pages\*.*') do (
        if not "%%i"==".gitkeep" del /q "pipeline_storage\expense_receipt\02_split_pages\%%i"
    )
)

REM 3. Clear processing queue folder (excluding .gitkeep)
if exist pipeline_storage\expense_receipt\03_processing_queue (
    echo Clearing 03_processing_queue...
    for /F "delims=" %%i in ('dir /b pipeline_storage\expense_receipt\03_processing_queue\*.*') do (
        if not "%%i"==".gitkeep" del /q "pipeline_storage\expense_receipt\03_processing_queue\%%i"
    )
)

REM 4. Clear archive folder
if exist pipeline_storage\expense_receipt\04_archive (
    echo Clearing 04_archive...
    for /d %%p in (pipeline_storage\expense_receipt\04_archive\*) do rmdir /s /q "%%p"
)

REM 5. Clear server logs (excluding .gitkeep)
if exist logs (
    echo Clearing logs...
    for /F "delims=" %%i in ('dir /b logs\*.*') do (
        if not "%%i"==".gitkeep" del /q "logs\%%i"
    )
)

echo.
echo Re-initializing storage folders and relational SQLite database...
.\.venv\Scripts\python.exe init_system.py

echo.
echo Reset completed successfully! Storage folders and SQLite DB are fresh.
pause
