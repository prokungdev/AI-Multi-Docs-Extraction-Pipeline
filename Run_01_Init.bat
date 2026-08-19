@echo off
title Run 01 - System Initialization
echo =========================================================
echo Step 1: Initializing System and Validating Configurations
echo =========================================================

.venv\Scripts\python.exe main.py --step init
pause
