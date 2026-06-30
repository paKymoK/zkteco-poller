"""
diagnostic.py
Lightweight diagnostic-only monitor for problematic ZKTeco machines.
Read-only — no attendance data pulled, no DB writes.

Config in config/.env:
    WATCH_MACHINES=IP:PORT:MACHINE_ID (comma-separated)
    DIAGNOSTIC_INTERVAL_SECONDS=30
    CONNECT_TIMEOUT_SECONDS=5
    KEEP_ALIVE=false
"""

import os
import sys
import time
import signal
import threading
import msvcrt
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv
from loguru import logger

from zk_sdk import ZKDevice, ZKSDKError

# ── Config ────────────────────────────────────────────────────────────────────
load_dotenv("config/.env")

INTERVAL        = int(os.getenv("DIAGNOSTIC_INTERVAL_SECONDS", 30))
CONNECT_TIMEOUT    = int(os.getenv("CONNECT_TIMEOUT_SECONDS", 5))
CONNECT_WARN       = int(os.getenv("CONNECT_WARN_THRESHOLD_SECONDS", 2))
KEEP_ALIVE      = os.getenv("KEEP_ALIVE", "false").strip().lower() == "true"

MACHINES = []
for entry in os.getenv("WATCH_MACHINES", os.getenv("MACHINES", "")).split(","):
    parts = entry.strip().split(":")
    if len(parts) == 3:
        MACHINES.append({
            "ip": parts[0], "port": int(parts[1]), "machine_id": int(parts[2])
        })

# Prevent overlapping cycles
_lock = threading.Lock()

# Global scheduler reference for clean shutdown
_scheduler = None
_skip_count = 0  # tracks consecutive skips — only logs first one

# Stop event — signals keep-alive loop to exit on shutdown
_stop_event = threading.Event()

# Track active SDK connections for graceful shutdown
_active_sdks: list[tuple[ZKDevice, int]] = []
_active_sdks_lock = threading.Lock()


# ── Graceful shutdown ─────────────────────────────────────────────────────────

def shutdown(signum=None, frame=None):
    """Stop scheduler, disconnect all machines and exit cleanly."""
    logger.info("Shutting down — stopping scheduler and disconnecting all machines...")

    # Stop scheduler first — prevents new cycles from starting
    global _scheduler
    if _scheduler and _scheduler.running:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass

    # Signal keep-alive loop to stop
    _stop_event.set()

    # Give keep-alive loop a moment to exit cleanly
    import time as _t
    _t.sleep(0.3)

    # Disconnect all active machines
    with _active_sdks_lock:
        for sdk, mid in _active_sdks:
            try:
                sdk.disconnect(mid)
            except Exception:
                pass

    logger.info("All machines disconnected. Goodbye!")
    sys.exit(0)

signal.signal(signal.SIGINT,  shutdown)
signal.signal(signal.SIGTERM, shutdown)


def keyboard_listener():
    """
    Background thread that listens for ESC key press.
    Triggers graceful shutdown when ESC is pressed.
    Works even over RDP where Ctrl+C may be blocked.
    """
    logger.info("Press ESC to gracefully shutdown")
    while True:
        if msvcrt.kbhit():
            key = msvcrt.getch()
            if key == b"":  # ESC key
                logger.info("ESC pressed — initiating graceful shutdown...")
                shutdown()
        import time as _t
        _t.sleep(0.1)  # check every 100ms


# ── Per machine ───────────────────────────────────────────────────────────────

def check_machine(machine: dict):
    ip, port, mid = machine["ip"], machine["port"], machine["machine_id"]
    start = time.time()

    try:
        sdk = ZKDevice()
    except ZKSDKError as e:
        logger.error(f"[Machine {mid}] SDK init failed: {e}")
        return

    with _active_sdks_lock:
        _active_sdks.append((sdk, mid))

    connected = sdk.connect(ip, port, mid, timeout=CONNECT_TIMEOUT, warn_threshold=CONNECT_WARN)
    if not connected:
        with _active_sdks_lock:
            _active_sdks.remove((sdk, mid))
        # ERROR level — unreachable machine is a real problem
        logger.error(f"[Machine {mid}] ✗ Unreachable — {ip}:{port}")
        return

    try:
        info = sdk.get_device_info(mid)

        platform = info.get("platform",           "?")
        serial   = info.get("serial",             "?")
        users    = info.get("user_count",         "?")
        logs     = info.get("att_log_count",      "?")
        drift    = info.get("clock_drift_seconds")
        elapsed  = round(time.time() - start, 1)

        if drift is not None:
            drift_str = f"Drift:{drift}s {'✓' if drift < 30 else '⚠ HIGH'}"
            if drift >= 60:
                logger.warning(
                    f"[Machine {mid}] ⚠ Clock drift {drift}s — "
                    f"sync via ATT2000 → Device Management → Sync Time"
                )
        else:
            drift_str = "Drift:?"

        logger.info(
            f"[Machine {mid}] ✓ {ip} | {platform} | S/N:{serial} | "
            f"Users:{users} | Logs:{logs} | {drift_str} | {elapsed}s"
        )

        if not info:
            logger.warning(f"[Machine {mid}] ✗ No diagnostic info returned")

        # ── Keep alive mode ───────────────────────────────────────────────────
        if KEEP_ALIVE:
            logger.info(f"[Machine {mid}] 🔒 KEEP_ALIVE=true — holding connection...")
            logger.info(f"[Machine {mid}] Watch if users can still punch normally.")
            logger.info(f"[Machine {mid}] Press ESC or Ctrl+C to stop and disconnect.")
            # Hold connection — check stop event every second
            while not _stop_event.is_set():
                _stop_event.wait(timeout=1)
                if not _stop_event.is_set():
                    logger.info(f"[Machine {mid}] 🔒 Still holding connection — {datetime.now().strftime('%H:%M:%S')}")
            logger.info(f"[Machine {mid}] 🔒 Stop signal received — releasing connection")

    finally:
        # Always disconnect and remove from tracking
        sdk.disconnect(mid)
        with _active_sdks_lock:
            if (sdk, mid) in _active_sdks:
                _active_sdks.remove((sdk, mid))


# ── Cycle ─────────────────────────────────────────────────────────────────────

def run():
    global _skip_count
    if not _lock.acquire(blocking=False):
        _skip_count += 1
        if _skip_count == 1:
            logger.warning(
                f"⏭ Cycle skipped at {datetime.now().strftime('%H:%M:%S')} — "
                f"previous cycle still running..."
            )
        return
    if _skip_count > 1:
        logger.warning(f"⏭ {_skip_count} cycles were skipped while previous cycle was running")
    _skip_count = 0
    try:
        logger.info(f"{'─'*50}")
        logger.info(f"Diagnostic cycle | {datetime.now().strftime('%H:%M:%S')} | {len(MACHINES)} machines")
        logger.info(f"{'─'*50}")

        # Timeout = connect timeout + 2s buffer
        # Ensures lock is always released even if threads hang
        cycle_timeout = CONNECT_TIMEOUT + 2

        import concurrent.futures as cf
        with ThreadPoolExecutor(max_workers=max(len(MACHINES), 1)) as ex:
            futures = {ex.submit(check_machine, m): m for m in MACHINES}
            done, pending = cf.wait(futures, timeout=cycle_timeout)

            # Process completed futures
            for f in done:
                try:
                    f.result()
                except Exception as e:
                    logger.error(f"[Machine {futures[f]['machine_id']}] Unhandled: {e}")

            # Log any threads that didn't finish in time
            for f in pending:
                mid = futures[f]["machine_id"]
                logger.error(
                    f"[Machine {mid}] Thread did not finish within {cycle_timeout}s — "
                    f"forcing release. Check machine connection."
                )
                f.cancel()

            # Release lock immediately after wait() — before executor cleanup
            # This prevents false skip warnings during executor teardown
            _lock.release()

    except Exception as e:
        logger.error(f"Cycle error: {e}")
        if _lock.locked():
            _lock.release()


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs("logs", exist_ok=True)

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
        "logs/diagnostic_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="2 months",
        encoding="utf-8",
        level="DEBUG",
    )

    # Error log — errors only, rotated daily at midnight, kept 2 months
    logger.add(
        "logs/error_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="2 months",
        encoding="utf-8",
        level="ERROR",
    )

    # Suppress APScheduler internal skip messages — we handle this ourselves
    import logging
    logging.getLogger("apscheduler").setLevel(logging.CRITICAL)

    # Start keyboard listener in background thread
    kb_thread = threading.Thread(target=keyboard_listener, daemon=True)
    kb_thread.start()

    logger.info("=" * 50)
    logger.info("ZKTeco Diagnostic Monitor")
    logger.info(f"Interval        : {INTERVAL}s")
    logger.info(f"Connect timeout : {CONNECT_TIMEOUT}s")
    logger.info(f"Slow warn after : {CONNECT_WARN}s")
    logger.info(f"Keep alive      : {KEEP_ALIVE}")
    logger.info(f"Machines        : {len(MACHINES)}")
    for m in MACHINES:
        logger.info(f"  Machine {m['machine_id']} → {m['ip']}:{m['port']}")
    logger.info("=" * 50)

    if KEEP_ALIVE:
        logger.warning("⚠ KEEP_ALIVE mode — connections will be held indefinitely")
        logger.warning("⚠ ATT2000 may fail to sync while connection is held")
        logger.warning("⚠ Press Ctrl+C to stop and release all connections")

    run()

    if not KEEP_ALIVE:
        _scheduler = BlockingScheduler()
        _scheduler.add_job(
            run, "interval",
            seconds=INTERVAL,
            misfire_grace_time=None,
            coalesce=True,
        )
        _scheduler.start()
