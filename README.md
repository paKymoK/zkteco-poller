# ZKTeco Diagnostic Monitor

Lightweight read-only monitor for ZKTeco F18 machines.
Connects to each machine periodically and logs health info.
No attendance data is pulled. No database writes.

---

## Files

```
zkteco_diagnostic/
├── build.bat           ← build the exe
├── diagnostic.py       ← main script
├── zk_sdk.py           ← ZKTeco SDK wrapper
├── requirements.txt    ← Python dependencies
├── REGISTER_DLL.md     ← how to register zkemkeeper.dll
└── config/
    └── .env            ← configuration
```

---

## Prerequisites

- Windows OS (64-bit)
- 32-bit Python 3.9 — download from https://www.python.org/downloads/windows/
- `zkemkeeper.dll` registered — see `REGISTER_DLL.md`

---

## Configuration

Edit `config\.env` before running:

```env
# How often to check each machine (in seconds)
DIAGNOSTIC_INTERVAL_SECONDS=30

# Machines to monitor — format: IP:PORT:MACHINE_ID
WATCH_MACHINES=192.168.1.101:4370:1,192.168.1.102:4370:2
```

---

## Build

Run `build.bat` on your build machine (requires 32-bit Python):

```cmd
build.bat
```

Output: `dist\ZKTecoDiagnostic.exe`

---

## Deploy to UAT / Production

Copy these two items to the target machine:

```
ZKTecoDiagnostic.exe
config\.env
```

The `logs\` folder is created automatically on first run.

---

## Run

Open Command Prompt and run:

```cmd
cd C:\ZKTecoDiagnostic
ZKTecoDiagnostic.exe
```

Keep the window open to see live output. Press `Ctrl+C` to stop.

---

## Logs

| File | Content | Kept |
|---|---|---|
| `logs\diagnostic_<date>.log` | All output — INFO, WARNING, ERROR | 3 days |
| `logs\error.log` | Errors only | 1 month, max 10MB |

**Check `error.log` first** when something goes wrong — it only contains errors,
no noise from normal operation.

---

## Sample Output

**Healthy machines:**
```
──────────────────────────────────────────────────
Diagnostic cycle | 14:30:05 | 2 machines
──────────────────────────────────────────────────
[Machine 1] ✓ 192.168.1.101 | ZMM210_TFT | S/N:8116211361237 | Users:150 | Logs:1523 | Drift:3s ✓ | 0.4s
[Machine 2] ✓ 192.168.1.102 | ZMM210_TFT | S/N:8116211361238 | Users:148 | Logs:892  | Drift:5s ✓ | 0.5s
```

**Unreachable machine:**
```
[Machine 2] ✗ Unreachable — 192.168.1.102:4370
```

**Clock drift warning:**
```
[Machine 1] ✓ 192.168.1.101 | ZMM210_TFT | S/N:8116211361237 | Users:150 | Logs:1523 | Drift:134s ⚠ | 0.4s
[Machine 1] ⚠ Clock drift 134s — sync via ATT2000 → Device Management → Sync Time
```

**Cycle skipped (interval too short):**
```
⏭ Cycle skipped at 14:30:06 — previous cycle still running. Increase DIAGNOSTIC_INTERVAL_SECONDS.
```

---

## Run as Windows Service (Production)

Use NSSM to run as a background service that starts automatically:

**Step 1 — Download NSSM:**
```
https://nssm.cc/download
```
Place `nssm.exe` at `C:\tools\nssm.exe`

**Step 2 — Install service (run CMD as Administrator):**
```cmd
C:\tools\nssm.exe install ZKTecoDiagnostic
```

Fill in the GUI:

| Field | Value |
|---|---|
| Path | `C:\ZKTecoDiagnostic\ZKTecoDiagnostic.exe` |
| Startup directory | `C:\ZKTecoDiagnostic` |

**Step 3 — Configure logging:**
```cmd
C:\tools\nssm.exe set ZKTecoDiagnostic AppStdout C:\ZKTecoDiagnostic\logs\service_out.log
C:\tools\nssm.exe set ZKTecoDiagnostic AppStderr C:\ZKTecoDiagnostic\logs\service_err.log
C:\tools\nssm.exe set ZKTecoDiagnostic AppExit Default Restart
```

**Step 4 — Start:**
```cmd
C:\tools\nssm.exe start ZKTecoDiagnostic
```

**Step 5 — Verify:**
```cmd
C:\tools\nssm.exe status ZKTecoDiagnostic
```
Should print: `SERVICE_RUNNING`

**Other commands:**
```cmd
C:\tools\nssm.exe stop ZKTecoDiagnostic
C:\tools\nssm.exe restart ZKTecoDiagnostic
C:\tools\nssm.exe remove ZKTecoDiagnostic confirm
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Exe closes immediately | Run from CMD to see error output |
| `SDK init failed` | Register `zkemkeeper.dll` — see `REGISTER_DLL.md` |
| All machines unreachable | Check network — ping the machine IPs |
| `⏭ Cycle skipped` frequently | Increase `DIAGNOSTIC_INTERVAL_SECONDS` |
| Clock drift warning | Sync device time via ATT2000 → Device Management → Sync Time |
| `config\.env` not found | Place `config` folder in same directory as exe |
