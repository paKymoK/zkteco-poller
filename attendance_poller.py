"""
attendance_poller.py
Daily job that pulls attendance logs from ZKTeco machines and inserts
any missing records into ATT2000's CHECKINOUT table in SQL Server.

Runs once immediately on start, then on a daily schedule (default 01:00).
Safe to run multiple times — deduplicates against existing DB records.

Config in config/.env:
    WATCH_MACHINES=IP:PORT:MACHINE_ID (comma-separated)
    POLL_LOOKBACK_DAYS=7
    POLL_TIME=01:00
    DB_CONNECTION_STRING=...
    CONNECT_TIMEOUT_SECONDS=5
"""

import os
import sys
import signal
import threading
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import pyodbc
from typing import Dict, List, Optional, Set
from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv
from loguru import logger

from zk_sdk import ZKDevice, ZKSDKError

# ── Config ────────────────────────────────────────────────────────────────────
load_dotenv("config/.env")

CONNECT_TIMEOUT = int(os.getenv("CONNECT_TIMEOUT_SECONDS", 5))
LOOKBACK_DAYS   = int(os.getenv("POLL_LOOKBACK_DAYS", 7))
POLL_TIME       = os.getenv("POLL_TIME", "01:00")
MAX_WORKERS     = int(os.getenv("MAX_WORKERS", 10))

DB_CONN_STR = (
    "DRIVER={{ODBC Driver 17 for SQL Server}};"
    "SERVER={server},{port};"
    "DATABASE={db};"
    "UID={user};"
    "PWD={pwd}"
).format(
    server=os.getenv("DB_SERVER", ""),
    port=os.getenv("DB_PORT", "1433"),
    db=os.getenv("DB_NAME", ""),
    user=os.getenv("DB_USER", ""),
    pwd=os.getenv("DB_PASSWORD", ""),
)

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
    logger.info("Shutting down attendance poller...")
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


# ── Database ──────────────────────────────────────────────────────────────────

def get_db_connection() -> pyodbc.Connection:
    if not os.getenv("DB_SERVER") or not os.getenv("DB_USER"):
        raise RuntimeError(
            "DB_SERVER and DB_USER must be set in config/.env"
        )
    return pyodbc.connect(DB_CONN_STR, autocommit=False)


def fetch_existing_keys(
    conn: pyodbc.Connection,
    user_id: int,
    start: Optional[datetime],
    end: datetime,
) -> Set[datetime]:
    """
    Return set of CHECKTIME values already in CHECKINOUT for this employee.
    If start is None, fetches all records for the employee (no date filter).
    """
    cursor = conn.cursor()
    if start is None:
        cursor.execute(
            "SELECT CHECKTIME FROM CHECKINOUT WHERE USERID = ?",
            user_id
        )
    else:
        cursor.execute(
            "SELECT CHECKTIME FROM CHECKINOUT "
            "WHERE USERID = ? AND CHECKTIME >= ? AND CHECKTIME <= ?",
            user_id, start, end
        )
    return {row.CHECKTIME for row in cursor.fetchall()}


def insert_records(conn: pyodbc.Connection, records: List[dict]) -> int:
    """
    Insert records into CHECKINOUT, skipping any that already exist.
    Returns count of rows actually inserted.
    """
    if not records:
        return 0

    # Group records by employee so we only query existing keys once per employee
    by_employee: Dict[int, List[dict]] = {}
    for r in records:
        uid = int(r["employee_id"])
        by_employee.setdefault(uid, []).append(r)

    all_times = [
        datetime(r["year"], r["month"], r["day"], r["hour"], r["minute"], r["second"])
        for r in records
    ]
    window_start = min(all_times) if LOOKBACK_DAYS > 0 else None
    window_end   = max(all_times)

    inserted = 0
    now = datetime.now()
    cursor = conn.cursor()

    for uid, emp_records in by_employee.items():
        existing = fetch_existing_keys(conn, uid, window_start, window_end)

        for r in emp_records:
            punch_time = datetime(
                r["year"], r["month"], r["day"],
                r["hour"], r["minute"], r["second"]
            )
            if punch_time in existing:
                continue

            logger.debug(
                f"[Insert] USERID={uid} CHECKTIME={punch_time} "
                f"CHECKTYPE={r['in_out_mode']!r} VERIFYCODE={r['verify_mode']} "
                f"WorkCode={r['work_code']!r} Badgenumber={str(uid)!r}"
            )
            cursor.execute(
                "INSERT INTO CHECKINOUT "
                "(USERID, CHECKTIME, CHECKTYPE, VERIFYCODE, WorkCode, Badgenumber, InsertedBy, InsertedDate) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                uid,
                punch_time,
                str(r["in_out_mode"]),
                r["verify_mode"],
                str(r["work_code"]),
                str(uid),
                "ZKPoller",                   # InsertedBy noreply
                now,                          # InsertedDate datetime
            )
            existing.add(punch_time)  # guard against dupes within the same batch
            inserted += 1

    conn.commit()
    return inserted


# ── Per machine ───────────────────────────────────────────────────────────────

def poll_machine(machine: dict, start: Optional[datetime], end: datetime) -> List[dict]:
    ip, port, mid = machine["ip"], machine["port"], machine["machine_id"]

    try:
        sdk = ZKDevice()
    except ZKSDKError as e:
        logger.error(f"[Machine {mid}] SDK init failed: {e}")
        return []

    connected = sdk.connect(ip, port, mid, timeout=CONNECT_TIMEOUT)
    if not connected:
        logger.error(f"[Machine {mid}] ✗ Unreachable — {ip}:{port}")
        return []

    try:
        info = sdk.get_device_info(mid)
        drift = info.get("clock_drift_seconds")
        if drift is not None:
            if drift >= 60:
                logger.warning(f"[Machine {mid}] Clock drift: {drift}s ⚠ HIGH — timestamps may fall outside lookback window")
            else:
                logger.info(f"[Machine {mid}] Clock drift: {drift}s ✓")
        else:
            logger.warning(f"[Machine {mid}] Clock drift: unavailable")

        if start is None:
            records = sdk.read_all_attendance_logs(mid)
            logger.info(f"[Machine {mid}] ✓ {len(records)} total records (no date filter)")
        else:
            records = sdk.read_attendance_logs_by_range(mid, start, end)
            logger.info(f"[Machine {mid}] ✓ {len(records)} records in window")
        return records
    finally:
        sdk.disconnect(mid)


# ── Poll cycle ────────────────────────────────────────────────────────────────

def run_poll():
    end = datetime.now()

    # POLL_LOOKBACK_DAYS=0 means pull everything on the device (no date filter)
    if LOOKBACK_DAYS == 0:
        start = None
        window_label = "ALL"
    else:
        start = end - timedelta(days=LOOKBACK_DAYS)
        window_label = f"{start.strftime('%Y-%m-%d')} → {end.strftime('%Y-%m-%d')} ({LOOKBACK_DAYS}d)"

    logger.info("=" * 50)
    logger.info(f"Attendance poll | {end.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Window  : {window_label}")
    logger.info(f"Machines: {len(MACHINES)}")
    logger.info("=" * 50)

    all_records: List[dict] = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(poll_machine, m, start, end): m for m in MACHINES}  # start=None means pull all
        for f in as_completed(futures):
            mid = futures[f]["machine_id"]
            try:
                records = f.result()
                all_records.extend(records)
            except Exception as e:
                logger.error(f"[Machine {mid}] Unhandled error: {e}")

    logger.info(f"Total records pulled from all machines: {len(all_records)}")

    if not all_records:
        logger.info("Nothing to insert.")
        return

    try:
        conn = get_db_connection()
    except Exception as e:
        logger.error(f"DB connection failed: {e}")
        return

    try:
        inserted = insert_records(conn, all_records)
        skipped  = len(all_records) - inserted
        logger.info(f"Inserted: {inserted} | Skipped (already exist): {skipped}")
    except Exception as e:
        logger.error(f"DB insert failed: {e}")
        conn.rollback()
    finally:
        conn.close()


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

    poll_hour, poll_minute = map(int, POLL_TIME.split(":"))

    logger.info("=" * 50)
    logger.info("ZKTeco Attendance Poller")
    logger.info(f"Lookback    : {LOOKBACK_DAYS} days" if LOOKBACK_DAYS > 0 else "Lookback    : ALL (no date filter)")
    logger.info(f"Daily at    : {POLL_TIME}")
    logger.info(f"Max workers : {MAX_WORKERS}")
    logger.info(f"Machines    : {len(MACHINES)}")
    for m in MACHINES:
        logger.info(f"  Machine {m['machine_id']} → {m['ip']}:{m['port']}")
    logger.info("=" * 50)

    # Verify DB connection before starting
    logger.info("Checking database connection...")
    try:
        conn = get_db_connection()
        conn.close()
        logger.info("Database connection OK")
    except Exception as e:
        logger.error(f"Database connection failed at startup: {e}")
        logger.error("Fix DB_SERVER / DB_USER / DB_PASSWORD in config/.env and restart.")
        sys.exit(1)

    # Run immediately on start so you don't have to wait until scheduled time
    logger.info("Running initial poll now...")
    run_poll()

    _scheduler = BlockingScheduler()
    _scheduler.add_job(
        run_poll,
        "cron",
        hour=poll_hour,
        minute=poll_minute,
        misfire_grace_time=300,
        coalesce=True,
    )
    logger.info(f"Scheduler started — next poll at {POLL_TIME} daily. Press Ctrl+C to stop.")
    _scheduler.start()
