@echo off
echo ================================
echo  ZKTeco Poller - DB Insert Test
echo  (prod-like record: in_out_mode=201, USERID=3, CHECKTIME=now)
echo ================================
echo.
echo  This does NOT touch any ZKTeco device. It inserts one synthetic
echo  record straight into CHECKINOUT through the real insert_records()
echo  code path, to confirm bad device data is handled as NULL instead
echo  of crashing the whole insert batch.
echo.

:: ── Read PYTHON32 path from build.config (same file build.bat uses) ──────────
if not exist "build.config" (
    echo [ERROR] build.config not found.
    echo         Run this from the repo folder, next to build.bat.
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

if not exist "%PYTHON32%" (
    echo [ERROR] Python not found at: %PYTHON32%
    echo         Update PYTHON32 in build.config.
    pause
    exit /b 1
)

if not exist "config\.env" (
    echo [ERROR] config\.env not found — need real DB_SERVER/DB_USER/DB_PASSWORD/DB_DRIVER to connect.
    pause
    exit /b 1
)

echo [OK] Using Python: %PYTHON32%
echo.

%PYTHON32% test_insert_prod_like.py
set RESULT=%errorlevel%

echo.
if %RESULT% neq 0 (
    echo ================================
    echo  TEST FAILED  ^(exit code %RESULT%^)
    echo ================================
) else (
    echo ================================
    echo  TEST PASSED
    echo ================================
)
pause
exit /b %RESULT%
