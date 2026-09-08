# syntax=docker/dockerfile:1
#
# Cross-builds ZKTecoPoller.exe on Linux using Wine, so you don't need a
# Windows machine to run build.bat. Requires BuildKit/buildx for the
# local-output final stage.
#
# IMPORTANT: this must produce a 32-bit (PE32) exe, matching build.bat's
# 32-bit Python requirement — the ZKTeco COM SDK (zkemkeeper.dll) is
# 32-bit-only ActiveX, and a 64-bit process cannot load a 32-bit-only COM
# server.
#
# History of what didn't work, so nobody re-tries it blindly:
#   - tobix/pywine's baked-in Python is 64-bit unconditionally (its own
#     Dockerfile always fetches the "-amd64" Windows installer), silently
#     producing a 64-bit exe.
#   - Hand-rolling Debian bookworm + WineHQ's own apt repo (to force a
#     32-bit build) hit a real upstream packaging gap: current WineHQ
#     wine-stable hard-depends on wine-stable-i386, but Debian dropped
#     i386 package indexes from bookworm-updates/bookworm-security, and
#     whatever i386 system library wine-stable-i386 needs at that exact
#     version isn't resolvable from bookworm's base "main" suite alone.
#     This reproduced identically with i386 explicitly enabled and with
#     it disabled — it's an apt/packaging problem, not a network one.
#
# What actually works: tobix/pywine's Wine installation already has a
# working 32-bit library setup (it's what let PyInstaller run at all
# last time, just against the wrong-bitness Python). So: keep that base
# image, but install a SECOND, 32-bit Python side-by-side with its
# pre-baked 64-bit one, into its own directory, and invoke it by full
# path everywhere below instead of relying on `wine python` (which would
# still resolve to the pre-baked 64-bit interpreter).
#
# Verify the result with `file dist/ZKTecoPoller.exe`; it must read
# "PE32 executable ... Intel 80386", not "PE32+ ... x86-64".
#
# Build (extracts the whole dist/ folder straight into the current
# directory on the host, no `docker run` or `docker cp` needed):
#
#   docker buildx build --output type=local,dest=. .
#
# Note: pywin32 (win32com/pythoncom) is Windows COM — Wine can emulate
# enough of it for PyInstaller to import and freeze the app, but this
# only proves the exe BUILDS. Actually talking to the ZKTeco device COM
# SDK still requires running the exe on real 32-bit-capable Windows with
# that SDK installed/registered.

FROM tobix/pywine:3.9 AS builder

WORKDIR /src

ARG PYTHON_VERSION=3.9.13
# NOTE: no "-amd64" suffix — this is the 32-bit Windows installer. TLS
# verification is skipped (curl -k / wget --no-check-certificate):
# this network's corporate proxy does TLS inspection (re-signs HTTPS with
# its own certificate, not in any public trust store), so genuine
# verification never passes here regardless of the target host being
# legitimate. Tries curl first, falls back to wget — this base image is
# an old (2022) build and it's not certain which one it has.
RUN PY_URL="https://www.python.org/ftp/python/${PYTHON_VERSION}/python-${PYTHON_VERSION}.exe"; \
    (curl -fsSLk -o /tmp/python-installer.exe "$PY_URL" \
     || wget -q --no-check-certificate -O /tmp/python-installer.exe "$PY_URL") \
    && xvfb-run wine /tmp/python-installer.exe /quiet InstallAllUsers=1 PrependPath=0 \
       Include_doc=0 Include_test=0 Include_launcher=0 TargetDir='C:\Python39-32' \
    && wineserver -w \
    && rm /tmp/python-installer.exe

# --trusted-host bypasses pip's own (certifi-based, OS-independent) TLS
# verification for these hosts — same corporate-proxy TLS inspection
# reason as -k above.
ARG PIP_TRUSTED_HOSTS="--trusted-host pypi.org --trusted-host files.pythonhosted.org --trusted-host pypi.python.org"

COPY requirements.txt .
RUN xvfb-run wine 'C:\Python39-32\python.exe' -m pip install --upgrade $PIP_TRUSTED_HOSTS pip \
    && xvfb-run wine 'C:\Python39-32\python.exe' -m pip install $PIP_TRUSTED_HOSTS --only-binary :all: greenlet==2.0.2 \
    && xvfb-run wine 'C:\Python39-32\python.exe' -m pip install $PIP_TRUSTED_HOSTS -r requirements.txt \
    && xvfb-run wine 'C:\Python39-32\python.exe' -m pip install $PIP_TRUSTED_HOSTS pyinstaller \
    && wineserver -w

COPY attendance_poller.py zk_sdk.py ./
COPY config/.env config/.env

RUN xvfb-run wine 'C:\Python39-32\python.exe' -m PyInstaller \
    --clean \
    --onefile \
    --noupx \
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
    attendance_poller.py \
    && wineserver -w

FROM scratch AS export
COPY --from=builder /src/dist /dist
