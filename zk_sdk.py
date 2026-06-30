"""
zk_sdk.py
Wrapper around ZKTeco zkemkeeper.dll using win32com (COM/ActiveX).
Must run with 32-bit Python to match the 32-bit DLL.
The DLL must be registered via:
    C:\Windows\SysWOW64\regsvr32.exe C:\Windows\SysWOW64\zkemkeeper.dll
"""

from datetime import datetime
from typing import Optional
from loguru import logger
import pythoncom
import win32com.client
from win32com.client import VARIANT


class ZKSDKError(Exception):
    pass


class ZKDevice:
    """
    Wraps the ZKTeco zkemkeeper.dll COM object (ZKEM class).
    Uses DumbDispatch so byref VARIANT parameters work correctly.
    """

    def __init__(self):
        # Must be called per thread — each machine runs in its own thread
        pythoncom.CoInitialize()
        try:
            # DumbDispatch required for byref VARIANT params to work
            raw = win32com.client.Dispatch("zkemkeeper.ZKEM")
            self.sdk = win32com.client.dynamic.DumbDispatch(raw)
        except Exception as e:
            raise ZKSDKError(
                f"Failed to instantiate zkemkeeper.ZKEM: {e}\n"
                f"Run as Admin: C:\\Windows\\SysWOW64\\regsvr32.exe C:\\Windows\\SysWOW64\\zkemkeeper.dll"
            )

    # ── Connection ────────────────────────────────────────────────────────────

    def connect(self, ip: str, port: int, machine_id: int, timeout: int = 5, warn_threshold: int = 2) -> bool:
        """
        Connect to a ZKTeco device over TCP/IP.
        Uses a thread-based timeout since Connect_Net has no native timeout param.
        shutdown(wait=False) abandons the thread immediately on timeout so it never
        blocks the cycle. The Connect_Net thread continues silently in background
        until Windows TCP timeout cleans it up.
        """
        import concurrent.futures
        import time as _time
        start = _time.time()
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = ex.submit(self.sdk.Connect_Net, ip, port)
            try:
                result = future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                elapsed = round(_time.time() - start, 1)
                logger.error(
                    f"[Machine {machine_id}] Connection timed out after {elapsed}s — {ip}:{port} "
                    f"(network problem or machine down)"
                )
                return False
            finally:
                ex.shutdown(wait=False)

            elapsed = round(_time.time() - start, 1)
            if not result:
                err = self._get_last_error()
                logger.error(
                    f"[Machine {machine_id}] Connection failed to {ip}:{port} "
                    f"— error: {err} ({_error_description(err)})"
                )
                return False

            if elapsed >= warn_threshold:
                logger.warning(
                    f"[Machine {machine_id}] Slow connection {elapsed}s — "
                    f"machine may be busy or network latency high"
                )
            else:
                logger.info(f"[Machine {machine_id}] Connected to {ip}:{port} in {elapsed}s")
            return True
        except Exception as e:
            logger.error(f"[Machine {machine_id}] Connect exception: {e}")
            ex.shutdown(wait=False)
            return False

    def disconnect(self, machine_id: int):
        """Disconnect from device."""
        try:
            self.sdk.Disconnect()
            logger.info(f"[Machine {machine_id}] Disconnected")
        except Exception as e:
            logger.error(f"[Machine {machine_id}] Disconnect error: {e}")

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def _get_last_error(self) -> int:
        try:
            err = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            self.sdk.GetLastError(err)
            return int(err.value)
        except Exception:
            return -1

    def get_device_info(self, machine_id: int) -> dict:
        """Pull key diagnostic info from the device."""
        info = {}

        try:
            year   = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            month  = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            day    = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            hour   = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            minute = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            second = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            ok = self.sdk.GetDeviceTime(machine_id, year, month, day, hour, minute, second)
            if ok:
                device_time = datetime(
                    int(year.value), int(month.value), int(day.value),
                    int(hour.value), int(minute.value), int(second.value)
                )
                server_time = datetime.now()
                drift = abs((server_time - device_time).total_seconds())
                info["device_time"]         = device_time.isoformat()
                info["server_time"]         = server_time.isoformat()
                info["clock_drift_seconds"] = round(drift, 1)
        except Exception as e:
            logger.debug(f"[Machine {machine_id}] GetDeviceTime skipped: {e}")

        try:
            val = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            if self.sdk.GetDeviceStatus(machine_id, 2, val):
                info["user_count"] = int(val.value)
        except Exception as e:
            logger.debug(f"[Machine {machine_id}] user_count skipped: {e}")

        try:
            val = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            if self.sdk.GetDeviceStatus(machine_id, 6, val):
                info["att_log_count"] = int(val.value)
        except Exception as e:
            logger.debug(f"[Machine {machine_id}] att_log_count skipped: {e}")

        try:
            val = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BSTR, "")
            if self.sdk.GetSysOption(machine_id, "~ZKFPVersion", val):
                info["firmware"] = str(val.value).strip()
        except Exception as e:
            logger.debug(f"[Machine {machine_id}] firmware skipped: {e}")

        try:
            val = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BSTR, "")
            if self.sdk.GetSysOption(machine_id, "~SerialNumber", val):
                info["serial"] = str(val.value).strip()
        except Exception as e:
            logger.debug(f"[Machine {machine_id}] serial skipped: {e}")

        try:
            val = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BSTR, "")
            if self.sdk.GetSysOption(machine_id, "~Platform", val):
                info["platform"] = str(val.value).strip()
        except Exception as e:
            logger.debug(f"[Machine {machine_id}] platform skipped: {e}")

        return info

    # ── Attendance Logs ───────────────────────────────────────────────────────

    def read_attendance_logs(self, machine_id: int) -> list[dict]:
        """Pull all attendance records stored on the device."""
        return self._fetch_logs(machine_id, use_time_filter=False)

    def read_attendance_logs_by_range(self, machine_id: int, start: datetime, end: datetime) -> list:
        """
        Pull attendance records within a date range.
        Falls back to pulling all logs and filtering in Python if the device
        ignores the time params (some F18 firmwares do).
        """
        records = self._fetch_logs(machine_id, use_time_filter=True, start=start, end=end)

        # If device returned records outside the requested range, it ignored the filter.
        # Apply Python-side filter as safety net.
        filtered = [
            r for r in records
            if start <= datetime(r["year"], r["month"], r["day"],
                                 r["hour"], r["minute"], r["second"]) <= end
        ]
        if len(filtered) < len(records):
            logger.debug(
                f"[Machine {machine_id}] Device ignored time filter — "
                f"dropped {len(records) - len(filtered)} out-of-range records in Python"
            )
        return filtered

    def _fetch_logs(
        self,
        machine_id: int,
        use_time_filter: bool = False,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list:
        records = []
        try:
            if use_time_filter and start and end:
                try:
                    ok = self.sdk.ReadTimeGLogData(
                        machine_id,
                        start.strftime("%Y-%m-%d %H:%M:%S"),
                        end.strftime("%Y-%m-%d %H:%M:%S"),
                    )
                    if not ok:
                        raise RuntimeError("ReadTimeGLogData returned false")
                except Exception as e:
                    # F18 firmware may not support ReadTimeGLogData — fall back to
                    # pulling all logs and filtering in Python (read_attendance_logs_by_range)
                    logger.warning(
                        f"[Machine {machine_id}] ReadTimeGLogData not supported ({e}) — "
                        f"falling back to ReadGeneralLogData with Python filter"
                    )
                    self.sdk.ReadGeneralLogData(machine_id)
            else:
                self.sdk.ReadGeneralLogData(machine_id)

            while True:
                enroll = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BSTR, "")
                verify = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                inout  = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                year   = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                month  = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                day    = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                hour   = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                minute = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                second = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                wcode  = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)

                try:
                    has_more = self.sdk.SSR_GetGeneralLogData(
                        machine_id,
                        enroll, verify, inout,
                        year, month, day,
                        hour, minute, second,
                        wcode
                    )
                except Exception as e:
                    logger.error(f"[Machine {machine_id}] SSR_GetGeneralLogData error: {e}")
                    break

                if not has_more:
                    break

                records.append({
                    "machine_id":  machine_id,
                    "employee_id": str(enroll.value).strip(),
                    "year":        int(year.value),
                    "month":       int(month.value),
                    "day":         int(day.value),
                    "hour":        int(hour.value),
                    "minute":      int(minute.value),
                    "second":      int(second.value),
                    "verify_mode": int(verify.value),
                    "in_out_mode": int(inout.value),
                    "work_code":   int(wcode.value),
                })

            logger.info(f"[Machine {machine_id}] Pulled {len(records)} records from device")

        except Exception as e:
            err = self._get_last_error()
            logger.error(
                f"[Machine {machine_id}] Error reading logs: {e} "
                f"— SDK error: {err} ({_error_description(err)})"
            )

        return records


# ── Helpers ───────────────────────────────────────────────────────────────────

def _error_description(code: int) -> str:
    errors = {
        0:     "No error",
        -1:    "Unknown",
        10060: "Connection timed out",
        10061: "Connection refused",
        10051: "Network unreachable",
        10065: "No route to host",
        10054: "Connection reset by machine",
        1:     "Authentication failed — check communication password",
        2:     "Device busy",
        3:     "Data error",
        4:     "Device not connected",
        5:     "Not supported by this device",
    }
    return errors.get(code, f"Unrecognized code {code}")
