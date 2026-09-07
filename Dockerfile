# syntax=docker/dockerfile:1
#
# Cross-builds ZKTecoPoller.exe on Linux using a 32-bit Wine prefix with
# the official 32-bit Windows Python installed in it, so you don't need
# a Windows machine to run build.bat. Requires BuildKit/buildx for the
# local-output final stage.
#
# IMPORTANT: this must produce a 32-bit (PE32) exe, matching build.bat's
# 32-bit Python requirement — the ZKTeco COM SDK (zkemkeeper.dll) is
# 32-bit-only ActiveX, and a 64-bit process cannot load a 32-bit-only COM
# server. An earlier version of this Dockerfile used the tobix/pywine
# base image, which (as of this writing) bakes in the 64-bit Windows
# Python installer unconditionally, silently producing a 64-bit exe that
# would fail against the real device. WINEARCH=win32 below is what
# actually pins this to 32-bit — verify with `file dist/ZKTecoPoller.exe`
# after building; it must read "PE32 executable ... Intel 80386", not
# "PE32+ ... x86-64".
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

FROM debian:bookworm-slim AS builder

ENV DEBIAN_FRONTEND=noninteractive

# WineHQ's own packages are needed for a working win32 (i386) Wine — the
# distro-provided "wine32" package on bookworm is not reliable for this.
#
# Debian no longer publishes i386 indexes for bookworm-updates/security (a
# project-wide policy change), so i386 is restricted to the base "bookworm
# main" suite here — amd64 still pulls from all three suites as normal.
#
# Sources use https:// (not http://) because some networks reject plain
# HTTP .deb downloads from deb.debian.org's CDN with a 403 "AuthorizedOnly"
# while the same paths work fine over HTTPS. The base image has no CA
# store yet, so HTTPS peer verification is disabled ONLY for this first
# bootstrap install (to fetch ca-certificates itself) and re-enabled
# immediately after — apt's own GPG/hash verification of the Release file
# and each package still applies throughout, independent of TLS.
RUN dpkg --add-architecture i386 \
    && rm -f /etc/apt/sources.list.d/debian.sources \
    && printf '%s\n' \
       'deb [arch=amd64,i386] https://deb.debian.org/debian bookworm main' \
       'deb [arch=amd64] https://deb.debian.org/debian bookworm-updates main' \
       'deb [arch=amd64] https://deb.debian.org/debian-security bookworm-security main' \
       > /etc/apt/sources.list \
    && printf '%s\n' 'Acquire::Retries "3";' > /etc/apt/apt.conf.d/99retries \
    && printf '%s\n' \
       'Acquire::https::Verify-Peer "false";' \
       'Acquire::https::Verify-Host "false";' \
       > /etc/apt/apt.conf.d/99bootstrap-no-verify \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates wget gnupg2 xvfb \
    && rm -f /etc/apt/apt.conf.d/99bootstrap-no-verify \
    && apt-get update \
    && mkdir -pm755 /etc/apt/keyrings \
    && wget -q -O /etc/apt/keyrings/winehq-archive.key https://dl.winehq.org/wine-builds/winehq.key \
    && wget -q -NP /etc/apt/sources.list.d/ https://dl.winehq.org/wine-builds/debian/dists/bookworm/winehq-bookworm.sources \
    && apt-get update \
    && apt-get install -y --install-recommends winehq-stable \
    && rm -rf /var/lib/apt/lists/*

ENV WINEARCH=win32 \
    WINEPREFIX=/wine \
    WINEDEBUG=-all

RUN xvfb-run wineboot --init && wineserver -w

ARG PYTHON_VERSION=3.9.13
# NOTE: no "-amd64" suffix — this is the 32-bit Windows installer.
RUN wget -q -O /tmp/python-installer.exe \
    https://www.python.org/ftp/python/${PYTHON_VERSION}/python-${PYTHON_VERSION}.exe \
    && xvfb-run wine /tmp/python-installer.exe /quiet InstallAllUsers=1 PrependPath=1 \
       Include_doc=0 Include_test=0 Include_launcher=0 TargetDir='C:\Python39' \
    && wineserver -w \
    && rm /tmp/python-installer.exe

WORKDIR /src

COPY requirements.txt .
RUN xvfb-run wine python -m pip install --upgrade pip \
    && xvfb-run wine python -m pip install --only-binary :all: greenlet==2.0.2 \
    && xvfb-run wine python -m pip install -r requirements.txt \
    && xvfb-run wine python -m pip install pyinstaller \
    && wineserver -w

COPY attendance_poller.py zk_sdk.py ./
COPY config/.env config/.env

RUN xvfb-run wine python -m PyInstaller \
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
    attendance_poller.py \
    && wineserver -w

FROM scratch AS export
COPY --from=builder /src/dist /dist
