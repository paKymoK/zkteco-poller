# ZKTeco Machine Health Monitor

[🇻🇳 Tiếng Việt](README.vi.md)

Lightweight periodic health monitor for ZKTeco attendance machines. Connects
to each configured machine, checks reachability and clock drift against the
server, then disconnects — no attendance log reads, no database. Runs once
immediately on start, then repeats every `PING_INTERVAL_MINUTES`.

## What this app does

`run_health_check` pings every machine in `WATCH_MACHINES` concurrently
(capped by `MAX_WORKERS`). For each machine it:

- Connects and logs an error if the machine can't be reached
  (`CONNECT_TIMEOUT_SECONDS`)
- Checks the machine's clock against the server and logs an error if the
  drift is at or above `CLOCK_DRIFT_THRESHOLD_SECONDS`
- Disconnects

Only one health-check cycle runs at a time — if a cycle is still running when
the next one is due, the next one is skipped rather than overlapping it.

---

## Files

```
zkteco-poller/
├── attendance_poller.py  ← main script
├── zk_sdk.py             ← ZKTeco SDK wrapper
├── requirements.txt      ← Python dependencies
├── build.bat             ← build ZKTecoPoller.exe
├── build.config          ← path to 32-bit Python
└── config/
    └── .env              ← configuration
```

---

## Prerequisites

- Windows OS (64-bit)
- 32-bit Python 3.9 — required to match the 32-bit `zkemkeeper.dll`
- `zkemkeeper.dll` registered — ATT2000 does this automatically; manual steps below if needed

### Registering zkemkeeper.dll

ATT2000 registers the DLL automatically on install. Only follow these steps if
the DLL is missing or the registry was cleared.

**Step 1 — Locate the DLL**

Check these paths (most common first):
```
C:\Windows\SysWOW64\zkemkeeper.dll    ← most common (32-bit DLL on 64-bit Windows)
C:\Program Files\ZKTeco\ATT2000\
C:\Program Files (x86)\ZKTeco\ATT2000\
C:\ZKTime\
```

**Step 2 — Register (run CMD as Administrator)**

1. Press **Win**, type `cmd`, right-click → **Run as Administrator**
2. Run:
```cmd
C:\Windows\SysWOW64\regsvr32.exe C:\Windows\SysWOW64\zkemkeeper.dll
```
> Use the `regsvr32.exe` in `SysWOW64`, not `System32` — the DLL is 32-bit and needs the 32-bit registrar.

Success message: `DllRegisterServer in C:\Windows\SysWOW64\zkemkeeper.dll succeeded.`

**Step 3 — Verify**

Open 32-bit PowerShell (must be 32-bit — 64-bit tools cannot see the DLL):
```cmd
C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe
```
Then run:
```powershell
New-Object -ComObject zkemkeeper.ZKEM
```
Success: prints a COM object. Failure (`Class not registered`): re-run Step 2 as Administrator.

| Problem | Fix |
|---|---|
| `DLL not found` | Verify path with `dir C:\Windows\SysWOW64\zkemkeeper.dll` |
| `Access denied` | Right-click CMD → Run as Administrator |
| `Class not registered` in PowerShell | Use `SysWOW64\WindowsPowerShell` not the default 64-bit one |
| Popup says `failed` | Reinstall ATT2000 or copy DLL from another working machine |

---

## Configuration

Edit `config\.env`:

```env
# Machines to monitor — format: IP:PORT:MACHINE_ID
WATCH_MACHINES=192.168.1.101:4370:1,192.168.1.102:4370:2

# Connection timeout when reaching a machine, and max concurrent machine connections
CONNECT_TIMEOUT_SECONDS=5
MAX_WORKERS=10

# Clock drift (device vs server time) at/above this many seconds is logged as an error
CLOCK_DRIFT_THRESHOLD_SECONDS=60

# How often to ping each machine, in minutes
PING_INTERVAL_MINUTES=5
```

---

## Build

Run `build.bat` on your build machine (requires 32-bit Python):

```cmd
build.bat
```

Output: `dist\ZKTecoPoller.exe`

---

## Deploy

Copy these two items to the target machine:

```
ZKTecoPoller.exe
config\.env
```

The `logs\` folder is created automatically on first run.

---

## Run

Open Command Prompt and run:

```cmd
cd C:\ZKTecoPoller
ZKTecoPoller.exe
```

Runs an initial health check immediately on start, then repeats every
`PING_INTERVAL_MINUTES`. Press `Ctrl+C` to stop.

---

## Logs

| File | Content | Kept |
|---|---|---|
| `logs\attendance_poller_<date>.log` | All output | 2 months |
| `logs\error_<date>.log` | Errors only | 2 months |

---

## Run as Windows Service (Production)

Use NSSM to run as a background service that starts automatically:

**Step 1 — Download NSSM:**
Place `nssm.exe` at `C:\tools\nssm.exe`

**Step 2 — Install service (run CMD as Administrator):**
```cmd
C:\tools\nssm.exe install ZKTecoPoller
```

Fill in the GUI:

| Field | Value |
|---|---|
| Path | `C:\ZKTecoPoller\ZKTecoPoller.exe` |
| Startup directory | `C:\ZKTecoPoller` |

**Step 3 — Configure logging:**
```cmd
C:\tools\nssm.exe set ZKTecoPoller AppStdout C:\ZKTecoPoller\logs\service_out.log
C:\tools\nssm.exe set ZKTecoPoller AppStderr C:\ZKTecoPoller\logs\service_err.log
C:\tools\nssm.exe set ZKTecoPoller AppExit Default Restart
```

**Step 4 — Start:**
```cmd
C:\tools\nssm.exe start ZKTecoPoller
```

**Step 5 — Verify:**
```cmd
C:\tools\nssm.exe status ZKTecoPoller
```
Should print: `SERVICE_RUNNING`

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `SDK init failed` | Register `zkemkeeper.dll` — see Prerequisites above |
| Machine unreachable | Verify IP/port in `WATCH_MACHINES` and network access |
| Repeated `Ping failed` for one machine | Confirms a real connectivity/power issue, not a blip — check the machine on-site |
| `Clock drift ... HIGH` error in logs | Not a bug — the device's clock differs from the server by more than `CLOCK_DRIFT_THRESHOLD_SECONDS`. Resync the device's clock, or raise the threshold if the drift is expected |
