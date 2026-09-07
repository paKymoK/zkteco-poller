# ZKTeco Attendance Poller

[🇬🇧 English](README.md)

Job chạy hàng ngày, lấy dữ liệu chấm công trực tiếp từ các máy ZKTeco thông
qua `zkemkeeper.dll` và chèn các bản ghi còn thiếu vào bảng `CHECKINOUT` của
ATT2000 trong SQL Server. An toàn khi chạy nhiều lần — tự loại bỏ bản ghi trùng
trước khi chèn.

## Ứng dụng này làm gì

Ứng dụng chạy hai job độc lập theo lịch, trong cùng một tiến trình:

- **Đồng bộ chấm công (backfill)** (`run_poll`, chạy hàng ngày lúc `POLL_TIME`)
  — kết nối tới từng máy trong `WATCH_MACHINES`, đọc log chấm công (trong một
  khoảng thời gian lookback, hoặc toàn bộ log của máy — xem `POLL_LOOKBACK_DAYS`),
  kiểm tra độ lệch giờ của từng máy so với giờ server (`CLOCK_DRIFT_THRESHOLD_SECONDS`),
  sau đó chèn các bản ghi chấm công chưa có trong `CHECKINOUT` (loại trùng theo
  nhân viên/thời gian). Cũng chạy ngay một lần khi khởi động.
- **Kiểm tra kết nối (health check)** (`run_health_check`, chạy mỗi
  `PING_INTERVAL_MINUTES`, nếu `PING_ENABLED=true`) — chỉ kết nối rồi ngắt kết
  nối, không đọc log, không ghi DB. Ghi log lỗi cho bất kỳ máy nào không kết
  nối được, để phát hiện sự cố kết nối sớm hơn thay vì phải chờ tới lần poll
  hàng ngày tiếp theo mới biết.

Cả hai job đều poll các máy đồng thời (giới hạn bởi `MAX_WORKERS`) và mỗi job
chỉ cho phép chạy một instance tại một thời điểm, nên một máy chạy chậm hoặc bị
treo sẽ không khiến lần chạy theo lịch tiếp theo bị chồng lên lần đang chạy.
Ngoài ra, nếu chu kỳ health check rơi đúng vào lúc một máy đang được poll, máy
đó sẽ được bỏ qua ở lượt ping đó (không mở thêm một kết nối thứ hai tới cùng
một máy) — vì hầu hết firmware ZKTeco chỉ chấp nhận một phiên kết nối tại một
thời điểm.

---

## Các file

```
zkteco-poller/
├── attendance_poller.py  ← script chính
├── zk_sdk.py             ← wrapper cho ZKTeco SDK
├── requirements.txt      ← các thư viện Python cần thiết
├── build.bat             ← build ra ZKTecoPoller.exe
├── build.config          ← đường dẫn tới Python 32-bit
└── config/
    └── .env              ← file cấu hình
```

---

## Yêu cầu trước khi chạy (Prerequisites)

- Hệ điều hành Windows (64-bit)
- Python 3.9 bản 32-bit — bắt buộc để khớp với `zkemkeeper.dll` (32-bit)
- Đã đăng ký `zkemkeeper.dll` — ATT2000 tự đăng ký khi cài đặt; nếu chưa có thì
  làm theo hướng dẫn thủ công bên dưới
- Đã cài ODBC Driver 17 for SQL Server trên máy chạy job

### Đăng ký zkemkeeper.dll

ATT2000 tự động đăng ký DLL này khi cài đặt. Chỉ cần làm các bước dưới đây nếu
DLL bị thiếu hoặc registry bị xóa.

**Bước 1 — Tìm file DLL**

Kiểm tra các đường dẫn sau (phổ biến nhất trước):

```
C:\Windows\SysWOW64\zkemkeeper.dll    ← phổ biến nhất (DLL 32-bit trên Windows 64-bit)
C:\Program Files\ZKTeco\ATT2000\
C:\Program Files (x86)\ZKTeco\ATT2000\
C:\ZKTime\
```

**Bước 2 — Đăng ký (chạy CMD với quyền Administrator)**

1. Nhấn **Win**, gõ `cmd`, chuột phải → **Run as Administrator**
2. Chạy:

```cmd
C:\Windows\SysWOW64\regsvr32.exe C:\Windows\SysWOW64\zkemkeeper.dll
```

> Dùng `regsvr32.exe` trong `SysWOW64`, không dùng bản trong `System32` — vì DLL
> là 32-bit nên cần trình đăng ký 32-bit tương ứng.

Thông báo thành công: `DllRegisterServer in C:\Windows\SysWOW64\zkemkeeper.dll succeeded.`

**Bước 3 — Kiểm tra lại**

Mở PowerShell bản 32-bit (bắt buộc phải là bản 32-bit — công cụ 64-bit sẽ
không thấy được DLL này):

```cmd
C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe
```

Sau đó chạy:

```powershell
New-Object -ComObject zkemkeeper.ZKEM
```

Thành công: in ra một COM object. Thất bại (`Class not registered`): chạy lại
Bước 2 với quyền Administrator.

| Vấn đề | Cách khắc phục |
|---|---|
| `DLL not found` | Kiểm tra lại đường dẫn bằng `dir C:\Windows\SysWOW64\zkemkeeper.dll` |
| `Access denied` | Chuột phải vào CMD → Run as Administrator |
| `Class not registered` trong PowerShell | Dùng `SysWOW64\WindowsPowerShell`, không dùng bản 64-bit mặc định |
| Popup báo `failed` | Cài lại ATT2000 hoặc copy DLL từ một máy khác đang hoạt động |

---

## Cấu hình

Sửa file `config\.env`:

```env
# Danh sách máy cần theo dõi — định dạng: IP:PORT:MACHINE_ID (cách nhau bằng dấu phẩy)
WATCH_MACHINES=192.168.1.101:4370:1,192.168.1.102:4370:2

# Số giây chờ máy chấp nhận kết nối trước khi bỏ cuộc. Số lượng máy được kết
# nối đồng thời, áp dụng riêng cho cả job poll hàng ngày lẫn job health check
# (mỗi job có giới hạn worker riêng, không dùng chung). Máy vượt quá số này sẽ
# chờ tới khi có worker thread rảnh.
CONNECT_TIMEOUT_SECONDS=5
MAX_WORKERS=10

# Số giây lệch giờ giữa máy và server trước khi bị ghi log lỗi (đồng hồ máy bị
# lệch có thể khiến thời gian chấm công rơi ra ngoài khoảng lookback, làm mất
# bản ghi mà không báo).
CLOCK_DRIFT_THRESHOLD_SECONDS=60

# Kiểm tra kết nối định kỳ, độc lập với job poll hàng ngày — chỉ kết nối rồi
# ngắt kết nối (không đọc log, không ghi DB), ghi log lỗi cho từng máy không
# kết nối được. Máy đang được poll sẽ tự động bị bỏ qua ở lượt ping đó. Đặt
# PING_ENABLED=false để tắt hoàn toàn tính năng này.
PING_ENABLED=true
PING_INTERVAL_MINUTES=5

# Số ngày lấy log lùi về trước mỗi lần poll (khoảng đệm an toàn phòng khi lỡ
# một lần poll). Đặt = 0 để lấy TOÀN BỘ log của máy, không lọc theo ngày
# (dùng cho lần chạy đầu tiên / backfill dữ liệu máy, sau đó chuyển lại về
# khoảng thời gian bình thường).
POLL_LOOKBACK_DAYS=7

# Giờ chạy poll chấm công hàng ngày (định dạng 24h HH:MM). Ngoài ra cũng chạy
# ngay một lần khi khởi động.
POLL_TIME=01:00

# SQL Server
DB_SERVER=ip_address
DB_PORT=1433
DB_NAME=Att2000
DB_USER=your_username
DB_PASSWORD=your_password
```

---

## Build

Chạy `build.bat` trên máy build (yêu cầu Python 32-bit):

```cmd
build.bat
```

Kết quả: `dist\ZKTecoPoller.exe`

### Build bằng Docker (không cần máy Windows)

Yêu cầu [Docker](https://docs.docker.com/get-docker/) có Buildx (đã tích hợp
sẵn trong Docker Desktop / Docker Engine bản mới). Cách này build exe trên
Linux/macOS bằng Wine, dùng file `Dockerfile` có sẵn trong repo:

```bash
docker buildx build --output type=local,dest=. .
```

Kết quả: `dist/ZKTecoPoller.exe` (giống hệt cấu trúc khi build bằng
`build.bat`).

> **Lưu ý:** Cách này chỉ chứng minh exe *build và đóng gói* thành công, chưa
> kiểm tra được hành vi lúc chạy thật — vì phần giao tiếp COM với máy chấm
> công ZKTeco (`win32com`/`pythoncom`) vẫn cần chạy exe trên Windows thật, có
> đăng ký `zkemkeeper.dll` (xem [Đăng ký
> zkemkeeper.dll](#đăng-ký-zkemkeeperdll)).

---

## Deploy

Copy hai thứ sau sang máy đích:

```
ZKTecoPoller.exe
config\.env
```

Thư mục `logs\` sẽ tự động được tạo trong lần chạy đầu tiên.

---

## Chạy

Mở Command Prompt và chạy:

```cmd
cd C:\ZKTecoPoller
ZKTecoPoller.exe
```

Chạy ngay một lần poll khi khởi động, sau đó lặp lại hàng ngày vào lúc
`POLL_TIME`. Job health check (nếu `PING_ENABLED=true`) sẽ bắt đầu chạy song
song, mỗi `PING_INTERVAL_MINUTES` một lần. Nhấn `Ctrl+C` để dừng.

---

## Log

| File | Nội dung | Giữ trong |
|---|---|---|
| `logs\attendance_poller_<date>.log` | Toàn bộ output | 2 tháng |
| `logs\error_<date>.log` | Chỉ lỗi | 2 tháng |

---

## Chạy như Windows Service (Production)

Dùng NSSM để chạy như một service nền, tự khởi động cùng hệ thống:

**Bước 1 — Tải NSSM:**
Đặt `nssm.exe` tại `C:\tools\nssm.exe`

**Bước 2 — Cài đặt service (chạy CMD với quyền Administrator):**
```cmd
C:\tools\nssm.exe install ZKTecoPoller
```

Điền vào giao diện:

| Trường | Giá trị |
|---|---|
| Path | `C:\ZKTecoPoller\ZKTecoPoller.exe` |
| Startup directory | `C:\ZKTecoPoller` |

**Bước 3 — Cấu hình logging:**
```cmd
C:\tools\nssm.exe set ZKTecoPoller AppStdout C:\ZKTecoPoller\logs\service_out.log
C:\tools\nssm.exe set ZKTecoPoller AppStderr C:\ZKTecoPoller\logs\service_err.log
C:\tools\nssm.exe set ZKTecoPoller AppExit Default Restart
```

**Bước 4 — Khởi động:**
```cmd
C:\tools\nssm.exe start ZKTecoPoller
```

**Bước 5 — Kiểm tra lại:**
```cmd
C:\tools\nssm.exe status ZKTecoPoller
```
Sẽ in ra: `SERVICE_RUNNING`

---

## Xử lý sự cố (Troubleshooting)

| Vấn đề | Cách khắc phục |
|---|---|
| `SDK init failed` | Đăng ký `zkemkeeper.dll` — xem phần Yêu cầu trước khi chạy ở trên |
| `DB connection failed` | Kiểm tra `DB_SERVER`/`DB_PORT`/`DB_NAME`/`DB_USER`/`DB_PASSWORD` trong `config\.env` và kết nối tới SQL Server |
| Máy không kết nối được (Machine unreachable) | Kiểm tra lại IP/port trong `WATCH_MACHINES` và kết nối mạng |
| Lỗi `Ping failed` lặp lại nhiều lần cho một máy | Health check xác nhận đây là sự cố kết nối/nguồn điện thực sự, không phải lỗi tạm thời — cần kiểm tra máy tại chỗ; không ảnh hưởng tới lần poll chấm công theo lịch tiếp theo, job đó vẫn sẽ tự thử lại độc lập |
| Lỗi `Clock drift ... HIGH` trong log | Không phải bug — đồng hồ máy đang lệch so với giờ server nhiều hơn `CLOCK_DRIFT_THRESHOLD_SECONDS`. Chỉnh lại đồng hồ máy, hoặc tăng ngưỡng này lên nếu độ lệch đó là bình thường |
| Bản ghi không xuất hiện trong ATT2000 | Kiểm tra trực tiếp bảng `CHECKINOUT`; đảm bảo `USERID` khớp với mã nhân viên trong ATT2000 |
