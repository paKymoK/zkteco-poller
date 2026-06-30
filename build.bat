@echo off
echo ================================
echo  ZKTeco Poller - Build Script
echo ================================
echo.

:: ── Read PYTHON32 path from build.config ─────────────────────────────────────
if not exist "build.config" (
    echo [ERROR] build.config not found.
    echo         Please create build.config with your 32-bit Python path.
    echo         Example: PYTHON32=C:\Python39-32\python.exe
    pause
    exit /b 1
)

for /f "tokens=1,2 delims==" %%a in (build.config) do (
    if "%%a"=="PYTHON32" set PYTHON32=%%b
)

if "%PYTHON32%"=="" (
    echo [ERROR] PYTHON32 not set in build.config
    pause
    exit /b 1
)
echo [OK] Python path: %PYTHON32%
echo.

:: ── Check 32-bit Python exists ────────────────────────────────────────────────
if not exist "%PYTHON32%" (
    echo [ERROR] 32-bit Python not found at: %PYTHON32%
    echo         Please update PYTHON32 in build.config
    pause
    exit /b 1
)

%PYTHON32% -c "import struct; import sys; bits=struct.calcsize('P')*8; print(f'Python {sys.version}'); exit(0 if bits==32 else 1)"
if %errorlevel% neq 0 (
    echo [ERROR] Python at %PYTHON32% is not 32-bit.
    pause
    exit /b 1
)
echo [OK] 32-bit Python confirmed
echo.

:: ── Install dependencies ──────────────────────────────────────────────────────
echo [1/3] Installing dependencies...
%PYTHON32% -m pip install --only-binary :all: greenlet==2.0.2
%PYTHON32% -m pip install -r requirements.txt
%PYTHON32% -m pip install pyinstaller
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo.

:: ── Clean previous build ──────────────────────────────────────────────────────
echo [2/3] Cleaning previous build...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
if exist ZKTecoPoller.spec del ZKTecoPoller.spec
echo.

:: ── Build attendance poller exe ───────────────────────────────────────────────
echo [3/3] Building ZKTecoPoller.exe...
%PYTHON32% -m PyInstaller ^
    --onefile ^
    --name ZKTecoPoller ^
    --add-data "config/.env;config" ^
    --hidden-import apscheduler ^
    --hidden-import apscheduler.schedulers.blocking ^
    --hidden-import apscheduler.executors.pool ^
    --hidden-import apscheduler.jobstores.memory ^
    --hidden-import apscheduler.triggers.cron ^
    --hidden-import win32com ^
    --hidden-import win32com.client ^
    --hidden-import pywintypes ^
    --hidden-import loguru ^
    --hidden-import dotenv ^
    --hidden-import pyodbc ^
    attendance_poller.py
if %errorlevel% neq 0 (
    echo [ERROR] ZKTecoPoller build failed.
    pause
    exit /b 1
)

echo.
echo ================================
echo  Build complete!
echo ================================
echo.
echo  Output: dist\ZKTecoPoller.exe
echo.
echo  Deploy to server:
echo    - dist\ZKTecoPoller.exe
echo    - config\.env
echo.
pause
