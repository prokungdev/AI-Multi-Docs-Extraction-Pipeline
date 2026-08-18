@echo off
title Run 05 - Transform Data to SQLite Database
echo =========================================================
echo Step 5: Transforming Extracted Records to Database
echo =========================================================

.venv\Scripts\python.exe main.py --step transform
pause
