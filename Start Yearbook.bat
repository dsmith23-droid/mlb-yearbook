@echo off
cd /d "%~dp0"
echo =============================================
echo   MLB Yearbook
echo =============================================
echo.

REM Find Python
set PYTHON=
where python >nul 2>&1 && set PYTHON=python
if "%PYTHON%"=="" where python3 >nul 2>&1 && set PYTHON=python3
if "%PYTHON%"=="" where py >nul 2>&1 && set PYTHON=py

if "%PYTHON%"=="" (
    echo ERROR: Python not found.
    echo Install Python from https://python.org and try again.
    pause
    exit /b 1
)

REM Kill anything on port 8000
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8000 "') do (
    taskkill /f /pid %%a >nul 2>&1
)

echo Starting server...
start /min "MLB Yearbook Server" %PYTHON% server.py

timeout /t 2 /nobreak >nul

echo Opening browser...
start "" "http://localhost:8000"

echo.
echo Server running at http://localhost:8000
echo Close this window OR the minimized "MLB Yearbook Server" window to stop.
echo.
pause
