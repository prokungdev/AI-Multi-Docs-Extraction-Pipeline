@echo off
title Run 04 - Validate and Post-Process Data
echo =========================================================
echo Step 4: Validating and Post-Processing Extracted Data
echo =========================================================

.venv\Scripts\python.exe main.py --step validate
pause
