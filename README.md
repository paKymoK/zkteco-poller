# ZKTeco Attendance Poller

Daily job that pulls attendance logs directly from ZKTeco machines via
`zkemkeeper.dll` and inserts any missing records into ATT2000's `CHECKINOUT`
table in SQL Server. Safe to run multiple times — deduplicates before inserting.
Also runs a lightweight periodic ping between polls to catch unreachable
machines early.

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
- ODBC Driver 17 for SQL Server installed on the machine

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

# How many days back to pull logs (safety buffer). Set to 0 to pull ALL records
# from the device with no date filter
POLL_LOOKBACK_DAYS=7

# Time to run the daily poll (24h HH:MM)
POLL_TIME=01:00

# Clock drift (device vs server time) at/above this many seconds is logged as an error
CLOCK_DRIFT_THRESHOLD_SECONDS=60

# Periodic connect/disconnect ping between polls, to catch unreachable machines early
PING_ENABLED=true
PING_INTERVAL_MINUTES=5

# SQL Server
DB_SERVER=ip_address
DB_PORT=1433
DB_NAME=Att2000
DB_USER=your_username
DB_PASSWORD=your_password
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

Runs an initial poll immediately on start, then repeats daily at `POLL_TIME`.
If `PING_ENABLED=true` (default), it also pings every configured machine every
`PING_INTERVAL_MINUTES` to catch unreachable machines between polls. Press
`Ctrl+C` to stop.

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
| `DB connection failed` | Check `DB_SERVER`/`DB_PORT`/`DB_NAME`/`DB_USER`/`DB_PASSWORD` in `config\.env` and SQL Server connectivity |
| Machine unreachable | Verify IP/port in `WATCH_MACHINES` and network access |
| `Clock drift ... HIGH` error in logs | Not a bug — the device's clock differs from the server by more than `CLOCK_DRIFT_THRESHOLD_SECONDS`. Resync the device's clock, or raise the threshold if the drift is expected |
| Records not appearing in ATT2000 | Check `CHECKINOUT` directly; verify `USERID` matches ATT2000 employee IDs |
