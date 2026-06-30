# ZKTeco Attendance Poller

Daily job that pulls attendance logs directly from ZKTeco F18 machines via
`zkemkeeper.dll` and inserts any missing records into ATT2000's `CHECKINOUT`
table in SQL Server. Safe to run multiple times — deduplicates before inserting.

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
- `zkemkeeper.dll` registered (installed automatically by ATT2000)
- ODBC Driver 17 for SQL Server installed on the machine

Register the DLL if needed (run CMD as Administrator):
```cmd
C:\Windows\SysWOW64\regsvr32.exe C:\Windows\SysWOW64\zkemkeeper.dll
```

---

## Configuration

Edit `config\.env`:

```env
# Machines to monitor — format: IP:PORT:MACHINE_ID
WATCH_MACHINES=192.168.1.101:4370:1,192.168.1.102:4370:2

# How many days back to pull logs (safety buffer)
POLL_LOOKBACK_DAYS=7

# Time to run the daily poll (24h HH:MM)
POLL_TIME=01:00

# SQL Server connection string
DB_CONNECTION_STRING=DRIVER={ODBC Driver 17 for SQL Server};SERVER=192.168.1.10;DATABASE=att2000;UID=sa;PWD=yourpassword
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
Press `Ctrl+C` to stop.

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
| `DB connection failed` | Check `DB_CONNECTION_STRING` and SQL Server connectivity |
| Machine unreachable | Verify IP/port in `WATCH_MACHINES` and network access |
| Records not appearing in ATT2000 | Check `CHECKINOUT` directly; verify `USERID` matches ATT2000 employee IDs |
