@echo off
title Run 06 - Transform Outputs and Export Reports
echo =========================================================
echo Step 6: Generating Output Reports (CSV / Excel / Express PV)
echo =========================================================

.venv\Scripts\python.exe main.py --step export
pause
