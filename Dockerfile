# syntax=docker/dockerfile:1
#
# Cross-builds ZKTecoPoller.exe on Linux using Wine + a 32-bit Windows
# Python (tobix/pywine), so you don't need a Windows machine to run
# build.bat. Requires BuildKit/buildx for the local-output final stage.
#
# Build (extracts the exe straight to ./dist on the host, no `docker run`
# or `docker cp` needed):
#
#   docker buildx build --output type=local,dest=./dist .
#
# Note: pywin32 (win32com/pythoncom) is Windows COM — Wine can emulate
# enough of it for PyInstaller to import and freeze the app, but this
# only proves the exe BUILDS. Actually talking to the ZKTeco device COM
# SDK still requires running the exe on real Windows with that SDK
# installed/registered.

FROM tobix/pywine:3.9 AS builder

WORKDIR /src

COPY requirements.txt .
RUN wine pip install --only-binary :all: greenlet==2.0.2 \
    && wine pip install -r requirements.txt \
    && wine pip install pyinstaller

COPY attendance_poller.py zk_sdk.py ./
COPY config/.env config/.env

RUN wine pyinstaller \
    --clean \
    --onefile \
    --name ZKTecoPoller \
    --add-data "config/.env;config" \
    --hidden-import apscheduler \
    --hidden-import apscheduler.schedulers.blocking \
    --hidden-import apscheduler.executors.pool \
    --hidden-import apscheduler.jobstores.memory \
    --hidden-import apscheduler.triggers.cron \
    --hidden-import win32com \
    --hidden-import win32com.client \
    --hidden-import pywintypes \
    --hidden-import loguru \
    --hidden-import dotenv \
    --hidden-import pyodbc \
    attendance_poller.py

FROM scratch AS export
COPY --from=builder /src/dist/ZKTecoPoller.exe /ZKTecoPoller.exe
