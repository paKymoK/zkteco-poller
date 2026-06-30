# test_connection.ps1
# Tests TCP connectivity to ZKTeco machines on port 4370
# No SDK, no DLL, no Python needed — pure PowerShell
# Run: powershell -ExecutionPolicy Bypass -File test_connection.ps1

# ── Config — edit your machine IPs here ──────────────────────────────────────
$machines = @(
    @{ id = 1; ip = "192.168.1.101"; port = 4370 },
    @{ id = 2; ip = "192.168.1.102"; port = 4370 },
    @{ id = 3; ip = "192.168.1.103"; port = 4370 }
)
# ─────────────────────────────────────────────────────────────────────────────

$timeout = 2000  # milliseconds

Write-Host "================================================" -ForegroundColor Cyan
Write-Host " ZKTeco Machine TCP Connectivity Test" -ForegroundColor Cyan
Write-Host " Port: 4370 | Timeout: $($timeout/1000)s" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

$ok      = 0
$failed  = 0

foreach ($m in $machines) {
    $start  = Get-Date
    $result = Test-NetConnection -ComputerName $m.ip -Port $m.port -WarningAction SilentlyContinue
    $ms     = [math]::Round(((Get-Date) - $start).TotalMilliseconds, 0)

    if ($result.TcpTestSucceeded) {
        Write-Host "[Machine $($m.id)] ✓  $($m.ip):$($m.port) — TCP open ($ms ms)" -ForegroundColor Green
        $ok++
    } else {
        Write-Host "[Machine $($m.id)] ✗  $($m.ip):$($m.port) — TCP failed" -ForegroundColor Red
        $failed++
    }
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host " Results: $ok reachable | $failed unreachable" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Note: This tests TCP port 4370 directly — same protocol as SDK." -ForegroundColor Gray
Write-Host "      If TCP open but SDK fails → DLL registration issue." -ForegroundColor Gray
Write-Host "      If TCP fails → network/firewall issue." -ForegroundColor Gray
Write-Host ""
Read-Host "Press Enter to exit"
