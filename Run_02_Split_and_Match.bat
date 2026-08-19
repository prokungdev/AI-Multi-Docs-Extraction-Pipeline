@echo off
title Run 02 - Split and Match Merchant Sources
echo =========================================================
echo Step 2: Splitting PDF and Matching Sources
echo =========================================================

.venv\Scripts\python.exe main.py --step split
pause
