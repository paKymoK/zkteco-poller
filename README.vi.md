# ZKTeco Machine Health Monitor

[🇬🇧 English](README.md)

Ứng dụng theo dõi tình trạng kết nối của các máy chấm công ZKTeco theo chu kỳ.
Kết nối tới từng máy đã cấu hình, kiểm tra khả năng kết nối và độ lệch giờ so
với server, sau đó ngắt kết nối — không đọc log chấm công, không dùng database.
Chạy ngay một lần khi khởi động, sau đó lặp lại mỗi `PING_INTERVAL_MINUTES`.

## Ứng dụng này làm gì

`run_health_check` ping tới từng máy trong `WATCH_MACHINES` đồng thời (giới
hạn bởi `MAX_WORKERS`). Với mỗi máy, ứng dụng sẽ:

- Kết nối và ghi log lỗi nếu không kết nối được (`CONNECT_TIMEOUT_SECONDS`)
- Kiểm tra đồng hồ của máy so với server, ghi log lỗi nếu độ lệch từ
  `CLOCK_DRIFT_THRESHOLD_SECONDS` trở lên
- Ngắt kết nối

Chỉ một chu kỳ health check được chạy tại một thời điểm — nếu chu kỳ hiện tại
vẫn đang chạy khi tới lúc chu kỳ tiếp theo, chu kỳ tiếp theo đó sẽ bị bỏ qua
thay vì chạy chồng lên.

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

# Số giây chờ máy chấp nhận kết nối trước khi bỏ cuộc, và số lượng máy được
# kết nối đồng thời (máy vượt quá số này sẽ chờ tới khi có worker thread rảnh)
CONNECT_TIMEOUT_SECONDS=5
MAX_WORKERS=10

# Số giây lệch giờ giữa máy và server trước khi bị ghi log lỗi
CLOCK_DRIFT_THRESHOLD_SECONDS=60

# Chu kỳ ping tới từng máy, tính bằng phút
PING_INTERVAL_MINUTES=5
```

---

## Build

Chạy `build.bat` trên máy build (yêu cầu Python 32-bit):

```cmd
build.bat
```

Kết quả: `dist\ZKTecoPoller.exe`

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

Chạy ngay một lượt health check khi khởi động, sau đó lặp lại mỗi
`PING_INTERVAL_MINUTES`. Nhấn `Ctrl+C` để dừng.

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
| Máy không kết nối được (Machine unreachable) | Kiểm tra lại IP/port trong `WATCH_MACHINES` và kết nối mạng |
| Lỗi `Ping failed` lặp lại nhiều lần cho một máy | Xác nhận đây là sự cố kết nối/nguồn điện thực sự, không phải lỗi tạm thời — cần kiểm tra máy tại chỗ |
| Lỗi `Clock drift ... HIGH` trong log | Không phải bug — đồng hồ máy đang lệch so với giờ server nhiều hơn `CLOCK_DRIFT_THRESHOLD_SECONDS`. Chỉnh lại đồng hồ máy, hoặc tăng ngưỡng này lên nếu độ lệch đó là bình thường |
