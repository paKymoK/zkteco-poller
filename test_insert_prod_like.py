"""
test_insert_prod_like.py
Standalone check that inserts one synthetic record into CHECKINOUT through the
real insert_records() path, to confirm bad/unusual device data (like the
in_out_mode=201 record pulled from production) is now handled as NULL instead
of crashing the whole batch.

Does NOT touch any ZKTeco device — DB only. Run from the same folder as
attendance_poller.py / zk_sdk.py / config/.env (same layout build.bat uses).
"""

import sys
from datetime import datetime

from attendance_poller import get_db_connection, verify_checkinout_table, insert_records

# The problematic record from production, reshaped per request:
#   - original: employee_id=0, CHECKTIME=2026-09-25 15:06:51, in_out_mode=201
#   - this run: employee_id=3, CHECKTIME=now
now = datetime.now()
TEST_RECORD = {
    "machine_id":  999,          # only used in log lines — CHECKINOUT has no machine column
    "employee_id": "3",
    "year":        now.year,
    "month":       now.month,
    "day":         now.day,
    "hour":        now.hour,
    "minute":      now.minute,
    "second":      now.second,
    "verify_mode": 1,
    "in_out_mode": 201,          # the out-of-range value that broke the old insert
    "work_code":   0,
}


def main() -> int:
    print(f"Test record: {TEST_RECORD}")

    try:
        conn = get_db_connection()
    except Exception as e:
        print(f"[FAIL] Could not connect to DB: {e}")
        return 1

    try:
        verify_checkinout_table(conn)
    except Exception as e:
        print(f"[FAIL] CHECKINOUT table check failed: {e}")
        return 1

    try:
        inserted = insert_records(conn, [TEST_RECORD])
    except Exception as e:
        print(f"[FAIL] insert_records raised — the batch-killing bug is back: {e}")
        return 1

    print(f"insert_records() returned inserted={inserted}")
    if inserted != 1:
        print("[FAIL] Expected 1 row inserted.")
        return 1

    # Read the row back exactly as stored, to see what landed in the
    # nice-to-have columns (should be NULL for CHECKTYPE given in_out_mode=201).
    cursor = conn.cursor()
    cursor.execute(
        "SELECT USERID, CHECKTIME, CHECKTYPE, VERIFYCODE, WorkCode, Badgenumber "
        "FROM CHECKINOUT WHERE USERID = ? AND CHECKTIME = ?",
        3, datetime(now.year, now.month, now.day, now.hour, now.minute, now.second)
    )
    row = cursor.fetchone()
    conn.close()

    if row is None:
        print("[FAIL] Row not found after insert.")
        return 1

    print(
        f"[OK] Stored row -> USERID={row.USERID} CHECKTIME={row.CHECKTIME} "
        f"CHECKTYPE={row.CHECKTYPE!r} VERIFYCODE={row.VERIFYCODE!r} "
        f"WorkCode={row.WorkCode!r} Badgenumber={row.Badgenumber!r}"
    )
    if row.CHECKTYPE is not None:
        print(f"[WARN] Expected CHECKTYPE to be NULL for in_out_mode=201, got {row.CHECKTYPE!r}")

    checktime_str = row.CHECKTIME.strftime("%Y-%m-%d %H:%M:%S")
    print("\nPASS — insert succeeded without crashing the batch.")
    print("Cleanup (run manually if you don't want this test row kept):")
    print(
        f"  DELETE FROM CHECKINOUT WHERE USERID = 3 AND CHECKTIME = '{checktime_str}' "
        f"AND InsertedBy = 'ZKPoller'"
    )
    return 0


if __name__ == "__main__":
    exit_code = main()
    # Keeps the window open when run by double-clicking the built exe
    # instead of from an already-open cmd window.
    input("\nPress Enter to exit...")
    sys.exit(exit_code)
