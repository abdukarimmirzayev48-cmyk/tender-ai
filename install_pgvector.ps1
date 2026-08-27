# =============================================================================
# pgvector ni PostgreSQL 18 (Windows) ga o'rnatish
#
#   ADMINISTRATOR PowerShell da yurgizing:
#       .\install_pgvector.ps1
#       .\install_pgvector.ps1 -WhatIf     # faqat ko'rsatadi, ko'chirmaydi
#
# NEGA SKRIPT: uch papkaga fayl ko'chiriladi va O'RTASIDA xizmat
# to'xtatiladi. Qo'lda qilinganda eng ko'p uchraydigan xato — xizmat
# ishlab turganda `vector.dll` ni ko'chirishga urinish: Windows faylni
# band deb hisoblaydi va nusxa JIMGINA muvaffaqiyatsiz bo'ladi.
#
# MANBA: `_pgvector/` papkasi (vector.v0.8.6-pg18.zip dan ochilgan).
#   https://github.com/andreiramani/pgvector_pgsql_windows
#   SHA-256: bda17eb97d9e687e3da701adbf4b65a342943b3e0cdc81935ccf0b9833a1ed62
#
# DIQQAT: bu RASMIY pgvector binari EMAS — jamoa a'zosi qurgan.
# Manbani va SHA-256 ni O'ZINGIZ tekshiring; ishonchingiz komil bo'lmasa
# Docker yo'lini tanlang (reja_ai_chat.md §16.16).
#
# ESLATMA: fayl ATAYIN faqat ASCII belgilardan iborat - PowerShell 5.1
# BOM'siz .ps1 ni ANSI deb o'qiydi va lotin bo'lmagan belgi qatorni buzadi.
# =============================================================================
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$PgRoot = "C:\Program Files\PostgreSQL\18",
    [string]$Source = (Join-Path $PSScriptRoot "_pgvector"),
    [string]$ServiceName = "",
    [string]$Database = "xtxarid"
)

$ErrorActionPreference = "Stop"

# --- 1. Administrator ekanini tekshiramiz ---------------------------------
$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($id)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "XATO: administrator huquqi kerak." -ForegroundColor Red
    Write-Host "  PowerShell ni 'Run as administrator' bilan oching."
    exit 1
}

# --- 2. Manba va manzil joyida ekanini tekshiramiz ------------------------
foreach ($p in @("$Source\lib\vector.dll",
                 "$Source\share\extension\vector.control")) {
    if (-not (Test-Path $p)) {
        Write-Host "XATO: manba topilmadi: $p" -ForegroundColor Red
        Write-Host "  Arxivni _pgvector\ ga oching."
        exit 1
    }
}
if (-not (Test-Path "$PgRoot\bin\postgres.exe")) {
    Write-Host "XATO: PostgreSQL topilmadi: $PgRoot" -ForegroundColor Red
    Write-Host "  -PgRoot bilan aniq yo'lni ko'rsating."
    exit 1
}

# --- 3. Xizmatni topamiz --------------------------------------------------
if (-not $ServiceName) {
    $svc = Get-Service | Where-Object { $_.Name -like "postgresql*18*" } |
           Select-Object -First 1
    if (-not $svc) {
        $svc = Get-Service | Where-Object { $_.Name -like "postgresql*" } |
               Select-Object -First 1
    }
} else {
    $svc = Get-Service -Name $ServiceName
}
if (-not $svc) {
    Write-Host "XATO: PostgreSQL xizmati topilmadi." -ForegroundColor Red
    Write-Host "  services.msc da nomini toping va -ServiceName bilan bering."
    exit 1
}
Write-Host "Xizmat: $($svc.Name)  (holat: $($svc.Status))"

# --- 4. To'xtatamiz -------------------------------------------------------
$wasRunning = $svc.Status -eq "Running"
if ($wasRunning) {
    if ($PSCmdlet.ShouldProcess($svc.Name, "Stop-Service")) {
        Write-Host "  to'xtatilmoqda..."
        Stop-Service -Name $svc.Name -Force
        (Get-Service $svc.Name).WaitForStatus("Stopped", "00:00:30")
        Write-Host "  to'xtatildi."
    }
}

try {
    # --- 5. Fayllarni ko'chiramiz ----------------------------------------
    $pairs = @(
        @{ From = "$Source\lib";              To = "$PgRoot\lib" },
        @{ From = "$Source\share\extension";  To = "$PgRoot\share\extension" },
        @{ From = "$Source\include";          To = "$PgRoot\include" }
    )
    foreach ($p in $pairs) {
        if (-not (Test-Path $p.From)) { continue }
        if ($PSCmdlet.ShouldProcess($p.To, "Copy-Item")) {
            Copy-Item -Path "$($p.From)\*" -Destination $p.To -Recurse -Force
            Write-Host "  ko'chirildi: $($p.From) -> $($p.To)"
        }
    }
} finally {
    # --- 6. Xizmatni QAYTA ishga tushiramiz (xato bo'lsa ham) -------------
    if ($wasRunning) {
        if ($PSCmdlet.ShouldProcess($svc.Name, "Start-Service")) {
            Write-Host "  ishga tushirilmoqda..."
            Start-Service -Name $svc.Name
            (Get-Service $svc.Name).WaitForStatus("Running", "00:01:00")
            Write-Host "  ishga tushdi."
        }
    }
}

# --- 7. Tekshiramiz -------------------------------------------------------
if ($WhatIfPreference) { Write-Host "`n(-WhatIf: hech narsa o'zgarmadi)"; exit 0 }

Write-Host "`nTekshirilmoqda..."
$psql = "$PgRoot\bin\psql.exe"
$env:PGCLIENTENCODING = "UTF8"
& $psql -d $Database -tAc "SELECT name || ' ' || default_version FROM pg_available_extensions WHERE name = 'vector'"
if ($LASTEXITCODE -ne 0) {
    Write-Host "psql ulanmadi - PGPASSWORD/PGUSER ni bering yoki qo'lda tekshiring:" -ForegroundColor Yellow
    Write-Host "  psql -d $Database -c ""CREATE EXTENSION vector;"""
    exit 0
}

Write-Host "`nEndi kengaytmani yoqing:"
Write-Host "  psql -d $Database -c ""CREATE EXTENSION vector;"""
Write-Host "so'ng:"
Write-Host "  psql -d $Database -v ON_ERROR_STOP=1 -f schema_patch_ai_chat.sql"
