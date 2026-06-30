"""
ping_check.py
Simple connectivity checker for ZKTeco machines using ping + port check.
No SDK, no DLL registration needed — works on any Windows PC.

Config in config/.env:
    WATCH_MACHINES=IP:PORT:MACHINE_ID (comma-separated)
    PING_INTERVAL_SECONDS=10
"""

import os
import sys
import time
import threading
import subprocess
import socket
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv
from loguru import logger

# ── Config ────────────────────────────────────────────────────────────────────
load_dotenv("config/.env")

INTERVAL = int(os.getenv("PING_INTERVAL_SECONDS", 10))

MACHINES = []
for entry in os.getenv("WATCH_MACHINES", os.getenv("MACHINES", "")).split(","):
    parts = entry.strip().split(":")
    if len(parts) == 3:
        MACHINES.append({
            "ip": parts[0], "port": int(parts[1]), "machine_id": int(parts[2])
        })

# Prevent overlapping cycles
_lock = threading.Lock()


# ── Checks ────────────────────────────────────────────────────────────────────

def ping(ip: str) -> tuple[bool, float]:
    """Ping machine — returns (success, response_time_ms)."""
    try:
        start = time.time()
        result = subprocess.run(
            ["ping", "-n", "1", "-w", "1000", ip],
            capture_output=True, text=True
        )
        elapsed = (time.time() - start) * 1000
        success = result.returncode == 0
        return success, round(elapsed, 1)
    except Exception:
        return False, 0.0


def check_port(ip: str, port: int) -> tuple[bool, float]:
    """Check if port 4370 is open — returns (success, response_time_ms)."""
    try:
        start = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((ip, port))
        elapsed = (time.time() - start) * 1000
        sock.close()
        return result == 0, round(elapsed, 1)
    except Exception:
        return False, 0.0


# ── Per machine ───────────────────────────────────────────────────────────────

def check_machine(machine: dict):
    ip, port, mid = machine["ip"], machine["port"], machine["machine_id"]

    ping_ok, ping_ms   = ping(ip)
    port_ok, port_ms   = check_port(ip, port)

    ping_str = f"Ping:✓ {ping_ms}ms" if ping_ok else "Ping:✗"
    port_str = f"Port:{port}:✓ {port_ms}ms" if port_ok else f"Port:{port}:✗"

    if ping_ok and port_ok:
        logger.info(f"[Machine {mid}] ✓ {ip} | {ping_str} | {port_str}")
    elif ping_ok and not port_ok:
        logger.warning(f"[Machine {mid}] ⚠ {ip} | {ping_str} | {port_str} — port blocked or ATT2000 holding connection")
    else:
        logger.error(f"[Machine {mid}] ✗ {ip} | {ping_str} | {port_str} — machine unreachable")


# ── Cycle ─────────────────────────────────────────────────────────────────────

def run():
    if not _lock.acquire(blocking=False):
        logger.warning(
            f"⏭ Cycle skipped at {datetime.now().strftime('%H:%M:%S')} — "
            f"previous cycle still running. Increase PING_INTERVAL_SECONDS."
        )
        return
    try:
        logger.info(f"{'─'*50}")
        logger.info(f"Ping check | {datetime.now().strftime('%H:%M:%S')} | {len(MACHINES)} machines")
        logger.info(f"{'─'*50}")
        with ThreadPoolExecutor(max_workers=max(len(MACHINES), 1)) as ex:
            futures = {ex.submit(check_machine, m): m for m in MACHINES}
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception as e:
                    logger.error(f"[Machine {futures[f]['machine_id']}] Unhandled: {e}")
    finally:
        _lock.release()


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs("logs", exist_ok=True)

    # Remove default logger and re-add explicitly for PyInstaller compatibility
    logger.remove()

    # Console output
    logger.add(
        sys.stdout,
        level="INFO",
        colorize=True,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    )

    # Main log — all levels, rotated daily at midnight, kept 2 months
    logger.add(
        "logs/ping_check_{time:YYYY-MM-DD}.log",
        rotation="00:00",        # rotate at midnight every day
        retention="2 months",
        encoding="utf-8",
        level="DEBUG",
    )

    # Error log — errors only, rotate at 10MB, kept 2 months
    logger.add(
        "logs/error.log",
        rotation="10 MB",
        retention="2 months",
        encoding="utf-8",
        level="ERROR",
    )

    logger.info("=" * 50)
    logger.info("ZKTeco Ping Checker")
    logger.info(f"Interval : {INTERVAL}s")
    logger.info(f"Machines : {len(MACHINES)}")
    for m in MACHINES:
        logger.info(f"  Machine {m['machine_id']} → {m['ip']}:{m['port']}")
    logger.info("=" * 50)

    run()

    scheduler = BlockingScheduler()
    scheduler.add_job(run, "interval", seconds=INTERVAL, max_instances=1, misfire_grace_time=None, coalesce=True)
    scheduler.start()
