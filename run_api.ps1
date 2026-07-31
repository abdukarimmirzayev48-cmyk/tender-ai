# =============================================================================
# Backend'ni ishonchli ishga tushirish (Windows)
#   .\run_api.ps1                        # 8000-portda
#   .\run_api.ps1 -Reload                # kod o'zgarsa avtomatik qayta yuklash
#   .\run_api.ps1 -Reload -Foreground    # ishlab chiqish uchun eng qulay
#   .\run_api.ps1 -Port 8001
#
# NEGA SKRIPT KERAK: uvicorn ba'zan portni "Bound" holatida qoldirib osilib
# qoladi - "Listening" emas. Bunda `netstat ... LISTENING` HECH NARSA
# ko'rsatmaydi, lekin yangi jarayon "address already in use" xatosi bilan
# ishga tushmaydi. Skript aynan shu holatni topib tozalaydi.
#
# OSILISH QAYERDAN KELADI: `--reload` da uvicorn ikki jarayon ochadi. OTA
# jarayon portni band qiladi, BOLA esa ilovani import qiladi. Import xato
# bersa (masalan modul yo'li noto'g'ri: `app.main:app` <-> `api.main:app`)
# bola o'ladi, OTA esa tirik qolib portni ushlab turaveradi. Terminalда
# traceback ko'rinadi, lekin port bo'shamaydi.
#
# ESLATMA: fayl ATAYIN faqat ASCII belgilardan iborat. PowerShell 5.1 .ps1
# fayllarni BOM'siz UTF-8 emas, ANSI deb o'qiydi va uzun tire kabi belgilar
# qatorni buzib yuboradi.
# =============================================================================
param(
    [int]$Port = 8000,
    [switch]$Foreground,
    [switch]$Reload
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
    Write-Host "XATO: virtual muhit topilmadi: $python" -ForegroundColor Red
    Write-Host "  python -m venv .venv"
    Write-Host "  .\.venv\Scripts\pip install -r requirements-api.txt"
    exit 1
}

# --- 1) Portni ushlab turgan jarayonlarni tozalash -------------------------
# MUHIM: "-State Listen" bilan cheklamaymiz. Osilib qolgan jarayon "Bound"
# holatida turadi va shunda filtrga tushmaydi (aynan shu xato bo'lgan edi).
$held = @()
try { $held = @(Get-NetTCPConnection -LocalPort $Port -ErrorAction Stop) } catch { }
$pids = $held | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -gt 0 }

foreach ($processId in $pids) {
    $row = $held | Where-Object { $_.OwningProcess -eq $processId } | Select-Object -First 1
    Write-Host "Port $Port band (PID $processId, holat: $($row.State)). To'xtatilmoqda..." -ForegroundColor Yellow
    & taskkill /PID $processId /T /F 2>&1 | Out-Null
}
if ($pids) { Start-Sleep -Seconds 2 }

# --- 2) Ishga tushirish ----------------------------------------------------
# Modul yo'li: paket "api", "app" EMAS. `uvicorn app.main:app` -> ModuleNotFoundError.
$argv = @('-m', 'uvicorn', 'api.main:app', '--host', '127.0.0.1', '--port', "$Port")
if ($Reload) { $argv += '--reload' }

if ($Foreground) {
    Write-Host "Backend ishga tushmoqda. To'xtatish: Ctrl+C" -ForegroundColor Cyan
    & $python @argv
    exit $LASTEXITCODE
}

Start-Process -FilePath $python -ArgumentList $argv -WorkingDirectory $root -WindowStyle Hidden

# --- 3) Haqiqatan javob berayotganini tekshirish ---------------------------
# "Jarayon ishga tushdi" degani yetarli emas: yuqoridagi osilish holatida
# jarayon bor, port band, lekin javob yo'q. Shuning uchun /health so'raymiz.
$ok = $false
for ($i = 1; $i -le 20; $i++) {
    Start-Sleep -Milliseconds 700
    try {
        $r = Invoke-WebRequest "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 4
        if ($r.StatusCode -eq 200) { $ok = $true; break }
    } catch { }
}

if ($ok) {
    Write-Host "Backend tayyor:  http://127.0.0.1:$Port" -ForegroundColor Green
    Write-Host "Swagger:         http://127.0.0.1:$Port/docs"
} else {
    Write-Host "Backend javob bermadi." -ForegroundColor Red
    Write-Host "Sababini ko'rish uchun:  .\run_api.ps1 -Foreground" -ForegroundColor Yellow
    exit 1
}
