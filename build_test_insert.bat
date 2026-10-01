@echo off
echo ================================
echo  ZKTeco Poller - Build Test Insert EXE
echo ================================
echo.
echo  Builds a standalone TestInsertProdLike.exe from test_insert_prod_like.py
echo  so you can copy it straight to a server that has no Python installed —
echo  same way ZKTecoPoller.exe itself is built and deployed.
echo.
echo  Run this on your BUILD machine (the one with PYTHON32 set up below),
echo  not on the UAT/production server.
echo.

:: ── Read PYTHON32 path from build.config (same file build.bat uses) ──────────
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

if not exist "test_insert_prod_like.py" (
    echo [ERROR] test_insert_prod_like.py not found — run this from the repo folder.
    pause
    exit /b 1
)

:: ── Install dependencies (same as build.bat — attendance_poller.py needs them) ─
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

:: ── Clean previous test build only (does not touch ZKTecoPoller build) ───────
echo [2/3] Cleaning previous test build...
if exist dist\TestInsertProdLike.exe del dist\TestInsertProdLike.exe
if exist build\test_insert_prod_like rmdir /s /q build\test_insert_prod_like
if exist TestInsertProdLike.spec del TestInsertProdLike.spec
echo.

:: ── Build test exe ─────────────────────────────────────────────────────────────
echo [3/3] Building TestInsertProdLike.exe...
%PYTHON32% -m PyInstaller ^
    --onefile ^
    --name TestInsertProdLike ^
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
    test_insert_prod_like.py
if %errorlevel% neq 0 (
    echo [ERROR] TestInsertProdLike build failed.
    pause
    exit /b 1
)

echo.
echo ================================
echo  Build complete!
echo ================================
echo.
echo  Output: dist\TestInsertProdLike.exe
echo.
echo  Deploy to server (same folder as ZKTecoPoller.exe, needs the real config\.env):
echo    - dist\TestInsertProdLike.exe
echo    - config\.env
echo.
echo  Then on the server, just double-click TestInsertProdLike.exe — no Python needed.
echo.
pause
