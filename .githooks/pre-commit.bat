@echo off
chcp 65001 >nul
echo Checking Git remote status (git fetch)...
git fetch origin main >nul 2>&1

set BEHIND_COUNT=0
for /f "tokens=*" %%i in ('git rev-list --count HEAD..origin/main 2^>nul') do set BEHIND_COUNT=%%i

if "%BEHIND_COUNT%"=="0" goto :END
if "%BEHIND_COUNT%"=="" goto :END

echo.
echo ========================================================================
echo  WARNING: Remote repository (origin/main) has new commits!
echo  You are behind by %BEHIND_COUNT% commit(s).
echo  Please run: git pull origin main
echo ========================================================================
echo.
exit /b 1

:END
exit /b 0
