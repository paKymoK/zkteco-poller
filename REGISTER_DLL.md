# Registering zkemkeeper.dll

ZKTeco's `zkemkeeper.dll` is a COM/ActiveX object that must be registered
with Windows before any SDK-based application can use it.

---

## Prerequisites

- Windows OS (32-bit or 64-bit)
- `zkemkeeper.dll` present on the machine
- Administrator privileges

---

## Step 1 — Locate zkemkeeper.dll

ATT2000 installs `zkemkeeper.dll` automatically. Check these locations:

```
C:\Windows\SysWOW64\zkemkeeper.dll        ← most common (32-bit DLL on 64-bit Windows)
C:\Program Files\ZKTeco\ATT2000\
C:\Program Files (x86)\ZKTeco\ATT2000\
C:\ZKTime\
```

If found in `SysWOW64` — that is correct and expected.
`SysWOW64` stores 32-bit DLLs on 64-bit Windows systems.

---

## Step 2 — Register the DLL

Open **Command Prompt as Administrator**:
1. Press **Win** key
2. Type `cmd`
3. Right-click **Command Prompt** → **Run as Administrator**

Then run:

```cmd
C:\Windows\SysWOW64\regsvr32.exe C:\Windows\SysWOW64\zkemkeeper.dll
```

> **Important:** Use the 32-bit `regsvr32.exe` located in `SysWOW64` — NOT the
> one in `System32`. Even though the folder name says `SysWOW64`, it contains
> the 32-bit version of system tools. This is a known Windows naming quirk.

**Success:** A popup appears saying:
```
DllRegisterServer in C:\Windows\SysWOW64\zkemkeeper.dll succeeded.
```

**Failure:** If you see an error — check that the path is correct and you are
running as Administrator.

---

## Step 3 — Verify Registration

Open **32-bit PowerShell**:

```cmd
C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe
```

> Must use 32-bit PowerShell — the DLL is 32-bit and invisible to 64-bit tools.

Then run:

```powershell
New-Object -ComObject zkemkeeper.ZKEM
```

**Success:** PowerShell prints a COM object — no error message.

**Failure:** `Class not registered` error — registration did not work.
Try running `regsvr32` again as Administrator.

---

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `DLL not found` | Wrong path | Verify path with `dir C:\Windows\SysWOW64\zkemkeeper.dll` |
| `Access denied` | Not running as Admin | Right-click CMD → Run as Administrator |
| `Class not registered` in PowerShell | Used 64-bit PowerShell | Use `SysWOW64\WindowsPowerShell` instead |
| `Class not registered` after regsvr32 success | COM registry mismatch | Reboot and try again |
| Popup says `failed` | DLL may be corrupted | Reinstall ATT2000 or copy DLL from another machine |

---

## Notes

- Registration only needs to be done **once per machine**
- ATT2000 installation usually registers the DLL automatically — manual
  registration is only needed if it was skipped or the registry was cleared
- If ATT2000 is already working on the machine, the DLL is already registered
- The `ZKTecoDiagnostic.exe` and `ZKTecoPoller.exe` both require this DLL
  to be registered before running
