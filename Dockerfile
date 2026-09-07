# syntax=docker/dockerfile:1
#
# Cross-builds ZKTecoPoller.exe on Linux using Wine with the official
# 32-bit Windows Python installed in it (via WoW64, see below), so you
# don't need a Windows machine to run build.bat. Requires BuildKit/buildx
# for the local-output final stage.
#
# IMPORTANT: this must produce a 32-bit (PE32) exe, matching build.bat's
# 32-bit Python requirement — the ZKTeco COM SDK (zkemkeeper.dll) is
# 32-bit-only ActiveX, and a 64-bit process cannot load a 32-bit-only COM
# server. An earlier version of this Dockerfile used the tobix/pywine
# base image, which (as of this writing) bakes in the 64-bit Windows
# Python installer unconditionally, silently producing a 64-bit exe that
# would fail against the real device.
#
# This does NOT need `dpkg --add-architecture i386` / a separate i386
# Wine build: modern WineHQ "wine-stable" ships WoW64 support built into
# a single 64-bit-hosted Wine, which runs 32-bit Windows binaries (the
# 32-bit Python installer, and anything built with it) natively without a
# dedicated 32-bit prefix. Requesting the i386 architecture explicitly
# actually broke the build here — apt couldn't resolve
# `wine-stable (= 11.0.0.0~bookworm-1)` because current WineHQ bookworm
# packages don't publish a matching i386 sub-package for that version.
# What actually produces the 32-bit exe is running the 32-bit Python
# installer (see PYTHON_VERSION below, no "-amd64" suffix) — Wine/WoW64
# executes it as a 32-bit process regardless of the prefix itself, and
# PyInstaller's bootloader bitness follows the interpreter running it.
# Verify with `file dist/ZKTecoPoller.exe` after building; it must read
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

FROM debian:bookworm-slim AS builder

ENV DEBIAN_FRONTEND=noninteractive

# Sources use https:// (not http://) because this network's corporate
# proxy rejects plain HTTP .deb downloads outright (403 "AuthorizedOnly").
# The proxy also does TLS inspection (re-signs HTTPS with its own cert, not
# in any public trust store), so TLS peer verification is disabled
# entirely here for both apt and wget rather than fought host-by-host.
# This trades away transport-layer authenticity to the proxy — acceptable
# for a local build-only image pulling public FOSS packages, since apt
# and pip still independently verify package hashes/signatures. It does
# NOT protect against a proxy that actively tampers with package content.
RUN sed -i 's#http://#https://#g' /etc/apt/sources.list /etc/apt/sources.list.d/debian.sources 2>/dev/null; \
    printf '%s\n' \
       'Acquire::Retries "3";' \
       'Acquire::https::Verify-Peer "false";' \
       'Acquire::https::Verify-Host "false";' \
       > /etc/apt/apt.conf.d/99no-verify \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates wget gnupg2 xvfb \
    && mkdir -pm755 /etc/apt/keyrings \
    && wget -q --no-check-certificate -O /etc/apt/keyrings/winehq-archive.key https://dl.winehq.org/wine-builds/winehq.key \
    && wget -q --no-check-certificate -NP /etc/apt/sources.list.d/ https://dl.winehq.org/wine-builds/debian/dists/bookworm/winehq-bookworm.sources \
    && apt-get update \
    && apt-get install -y --install-recommends winehq-stable \
    && rm -rf /var/lib/apt/lists/*

ENV WINEPREFIX=/wine \
    WINEDEBUG=-all

RUN xvfb-run wineboot --init && wineserver -w

ARG PYTHON_VERSION=3.9.13
# NOTE: no "-amd64" suffix — this is the 32-bit Windows installer.
RUN wget -q --no-check-certificate -O /tmp/python-installer.exe \
    https://www.python.org/ftp/python/${PYTHON_VERSION}/python-${PYTHON_VERSION}.exe \
    && xvfb-run wine /tmp/python-installer.exe /quiet InstallAllUsers=1 PrependPath=1 \
       Include_doc=0 Include_test=0 Include_launcher=0 TargetDir='C:\Python39' \
    && wineserver -w \
    && rm /tmp/python-installer.exe

WORKDIR /src

# --trusted-host bypasses pip's own (certifi-based, OS-independent) TLS
# verification for these hosts — same corporate-proxy TLS inspection
# reason as the apt/wget flags above.
ARG PIP_TRUSTED_HOSTS="--trusted-host pypi.org --trusted-host files.pythonhosted.org --trusted-host pypi.python.org"

COPY requirements.txt .
RUN xvfb-run wine python -m pip install --upgrade $PIP_TRUSTED_HOSTS pip \
    && xvfb-run wine python -m pip install $PIP_TRUSTED_HOSTS --only-binary :all: greenlet==2.0.2 \
    && xvfb-run wine python -m pip install $PIP_TRUSTED_HOSTS -r requirements.txt \
    && xvfb-run wine python -m pip install $PIP_TRUSTED_HOSTS pyinstaller \
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
