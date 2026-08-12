"""
attendance_poller.py
Lightweight periodic health monitor for ZKTeco attendance machines.

Connects to each configured machine, checks reachability and clock drift
against the server, then disconnects — no attendance log reads, no database.
Runs once immediately on start, then repeats every PING_INTERVAL_MINUTES.

Config in config/.env:
    WATCH_MACHINES=IP:PORT:MACHINE_ID (comma-separated)
    CONNECT_TIMEOUT_SECONDS=5
    MAX_WORKERS=10
    CLOCK_DRIFT_THRESHOLD_SECONDS=60
    PING_INTERVAL_MINUTES=5
"""

import os
import sys
import signal
from concurrent.futures import ThreadPoolExecutor, as_completed

from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv
from loguru import logger

from zk_sdk import ZKDevice, ZKSDKError

# ── Config ────────────────────────────────────────────────────────────────────
load_dotenv("config/.env")

CONNECT_TIMEOUT = int(os.getenv("CONNECT_TIMEOUT_SECONDS", 5))
MAX_WORKERS     = int(os.getenv("MAX_WORKERS", 10))
CLOCK_DRIFT_THRESHOLD_SECONDS = int(os.getenv("CLOCK_DRIFT_THRESHOLD_SECONDS", 60))
PING_INTERVAL_MINUTES = int(os.getenv("PING_INTERVAL_MINUTES", 5))

MACHINES = []
for entry in os.getenv("WATCH_MACHINES", os.getenv("MACHINES", "")).split(","):
    parts = entry.strip().split(":")
    if len(parts) == 3:
        MACHINES.append({
            "ip": parts[0], "port": int(parts[1]), "machine_id": int(parts[2])
        })

_scheduler = None


# ── Graceful shutdown ─────────────────────────────────────────────────────────

def shutdown(signum=None, frame=None):
    logger.info("Shutting down...")
    global _scheduler
    if _scheduler and _scheduler.running:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass
    logger.info("Goodbye!")
    sys.exit(0)

signal.signal(signal.SIGINT,  shutdown)
signal.signal(signal.SIGTERM, shutdown)


# ── Per machine ───────────────────────────────────────────────────────────────

def ping_machine(machine: dict) -> bool:
    """Connect, check reachability and clock drift, then disconnect."""
    ip, port, mid = machine["ip"], machine["port"], machine["machine_id"]

    try:
        sdk = ZKDevice()
    except ZKSDKError as e:
        logger.error(f"[Machine {mid}] Ping failed — SDK init error: {e}")
        return False

    connected = sdk.connect(ip, port, mid, timeout=CONNECT_TIMEOUT)
    if not connected:
        logger.error(f"[Machine {mid}] Ping failed — unreachable at {ip}:{port}")
        return False

    try:
        info = sdk.get_device_info(mid)
        drift = info.get("clock_drift_seconds")
        if drift is not None:
            if drift >= CLOCK_DRIFT_THRESHOLD_SECONDS:
                logger.error(f"[Machine {mid}] Clock drift: {drift}s ⚠ HIGH")
            else:
                logger.info(f"[Machine {mid}] Clock drift: {drift}s ✓")
        else:
            logger.error(f"[Machine {mid}] Clock drift: unavailable")
    finally:
        sdk.disconnect(mid)

    return True


# ── Health check cycle ───────────────────────────────────────────────────────

def run_health_check():
    logger.info("=" * 50)
    logger.info(f"Health check | {len(MACHINES)} machine(s)")
    logger.info("=" * 50)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(ping_machine, m): m for m in MACHINES}
        for f in as_completed(futures):
            mid = futures[f]["machine_id"]
            try:
                f.result()
            except Exception as e:
                logger.error(f"[Machine {mid}] Ping failed — unhandled error: {e}")


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs("logs", exist_ok=True)

    logger.remove()

    logger.add(
        sys.stdout,
        level="INFO",
        colorize=True,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    )

    logger.add(
        "logs/attendance_poller_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="2 months",
        encoding="utf-8",
        level="DEBUG",
    )

    logger.add(
        "logs/error_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="2 months",
        encoding="utf-8",
        level="ERROR",
    )

    import logging
    logging.getLogger("apscheduler").setLevel(logging.CRITICAL)

    logger.info("=" * 50)
    logger.info("ZKTeco Machine Health Monitor")
    logger.info(f"Max workers : {MAX_WORKERS}")
    logger.info(f"Drift limit : {CLOCK_DRIFT_THRESHOLD_SECONDS}s")
    logger.info(f"Ping every  : {PING_INTERVAL_MINUTES}min")
    logger.info(f"Machines    : {len(MACHINES)}")
    for m in MACHINES:
        logger.info(f"  Machine {m['machine_id']} → {m['ip']}:{m['port']}")
    logger.info("=" * 50)

    # Run immediately on start so you don't have to wait until the first interval
    logger.info("Running initial check now...")
    run_health_check()

    _scheduler = BlockingScheduler()
    _scheduler.add_job(
        run_health_check,
        "interval",
        minutes=PING_INTERVAL_MINUTES,
        coalesce=True,
        max_instances=1,
    )

    logger.info(f"Scheduler started — checking every {PING_INTERVAL_MINUTES}min. Press Ctrl+C to stop.")
    _scheduler.start()
