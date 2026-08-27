# =============================================================================
# HAMMASINI BITTA BUYRUQ BILAN KO'TARISH (backend + frontend + ngrok tunnel)
#
#   .\run_all.ps1              # uchalasini yurgizadi va tekshiradi
#   .\run_all.ps1 -NoTunnel    # faqat mahalliy ish (tunnelsiz)
#   .\run_all.ps1 -Stop        # uchalasini to'xtatadi
#
# NEGA SKRIPT: ilgari uchta alohida terminal kerak edi va tartib MUHIM -
# tunnel Vite'dan oldin ko'tarilsa, dastlabki so'rovlar 404 bo'ladi. Skript
# tartibni saqlaydi va har bosqichni HAQIQATAN javob berayotganini tekshiradi
# ("jarayon bor" degani "ishlayapti" degani emas).
#
# ARXITEKTURA (nega bitta tunnel yetadi):
#   brauzer -> ngrok -> Vite :5173 -> (/api proksi) -> FastAPI :8000
# Backend TASHQARIGA ochilmaydi, shuning uchun CORS ham kerak emas.
#
# ESLATMA: fayl ATAYIN faqat ASCII belgilardan iborat - PowerShell 5.1 BOM'siz
# .ps1 ni ANSI deb o'qiydi va lotin bo'lmagan belgilar qatorni buzadi.
# =============================================================================
param(
    [switch] $NoTunnel,
    [switch] $Stop
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
if (-not $Root) { $Root = (Get-Location).Path }

$TunnelName = 'tenderai'
$NgrokCfg   = Join-Path $Root 'ngrok.yml'
$GlobalCfg  = Join-Path $env:LOCALAPPDATA 'ngrok\ngrok.yml'

# --- To'xtatish rejimi -------------------------------------------------------
if ($Stop) {
    # MUHIM: jarayonlarni NOM bo'yicha emas, PORT bo'yicha topamiz.
    # `Get-Process node` butun tizimdagi har qanday Node ishini (foydalanuvchi
    # ochib qo'ygan boshqa loyihalarni ham) o'ldirib yuborardi; `python` esa
    # ayni damda yurayotgan ETL'ni uzib qo'yardi.
    foreach ($spec in @(@{ Port = 8000; Nomi = 'backend' }, @{ Port = 5173; Nomi = 'frontend' })) {
        try {
            Get-NetTCPConnection -LocalPort $spec.Port -ErrorAction Stop |
                Select-Object -ExpandProperty OwningProcess -Unique |
                Where-Object { $_ -gt 0 } |
                ForEach-Object {
                    Write-Host "[i] $($spec.Nomi) (port $($spec.Port), PID $_) to'xtatilmoqda..."
                    & taskkill /PID $_ /T /F 2>&1 | Out-Null
                }
        } catch { }
    }
    # ngrok tashqi portni tinglamaydi, shuning uchun uni nom bilan topamiz -
    # bu yerda xavf yo'q, ngrok faqat shu loyiha uchun ishlatiladi.
    Get-Process -Name 'ngrok' -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host "[i] ngrok (PID $($_.Id)) to'xtatilmoqda..."
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "[OK] Hammasi to'xtatildi."
    return
}

# --- 1) Backend --------------------------------------------------------------
Write-Host "`n[1/3] Backend (FastAPI :8000)" -ForegroundColor Cyan
& (Join-Path $Root 'run_api.ps1')
# TEKSHIRUV EXIT KODIGA EMAS, JAVOBGA qaraydi: skript ichidagi oxirgi tashqi
# buyruq (netstat/taskkill) $LASTEXITCODE ni o'zgartirib yuborishi mumkin va
# backend ko'tarilgan bo'lsa ham bu yer yiqilardi.
$apiOk = $false
try {
    $r = Invoke-WebRequest 'http://127.0.0.1:8000/health' -UseBasicParsing -TimeoutSec 4
    $apiOk = ($r.StatusCode -eq 200)
} catch { }
if (-not $apiOk) { throw "Backend ko'tarilmadi - .\run_api.ps1 -Foreground bilan sababini ko'ring." }

# --- 2) Frontend -------------------------------------------------------------
Write-Host "`n[2/3] Frontend (Vite :5173)" -ForegroundColor Cyan
$fe = Join-Path $Root 'frontend'

# ALLAQACHON YURAYOTGAN BO'LSA - QAYTA ISHLATAMIZ.
# Busiz ikkinchi Vite ko'tarilardi; :5173 band bo'lgani uchun u o'zi :5174 ga
# o'tib ketardi va tunnel (u :5173 ga qaraydi) ESKI nusxaga ulanib qolardi -
# ya'ni kod o'zgarsa ham tunnelda eski versiya ko'rinaverardi.
$ok = $false
try {
    $r = Invoke-WebRequest 'http://127.0.0.1:5173/' -UseBasicParsing -TimeoutSec 3
    if ($r.StatusCode -eq 200) {
        $ok = $true
        Write-Host "[i] :5173 da Vite allaqachon yuribdi - qayta ishlatilmoqda."
    }
} catch { }

if (-not $ok) {
    if (-not (Test-Path (Join-Path $fe 'node_modules'))) {
        Write-Host "[i] node_modules yo'q - npm install yurgizilmoqda..."
        Push-Location $fe; & npm install; Pop-Location
    }
    Start-Process -FilePath 'cmd.exe' `
        -ArgumentList '/c', 'npm run dev' `
        -WorkingDirectory $fe -WindowStyle Hidden

    # "Port band" emas, HAQIQATAN sahifa qaytayotganini kutamiz.
    for ($i = 1; $i -le 30; $i++) {
        Start-Sleep -Milliseconds 700
        try {
            $r = Invoke-WebRequest 'http://127.0.0.1:5173/' -UseBasicParsing -TimeoutSec 4
            if ($r.StatusCode -eq 200) { $ok = $true; break }
        } catch { }
    }
}
if (-not $ok) { throw "Frontend javob bermadi (:5173)." }
Write-Host "Frontend tayyor: http://127.0.0.1:5173" -ForegroundColor Green

# --- 3) Tunnel ---------------------------------------------------------------
if ($NoTunnel) {
    Write-Host "`n[3/3] Tunnel o'tkazib yuborildi (-NoTunnel)." -ForegroundColor Yellow
    return
}

Write-Host "`n[3/3] ngrok tunnel" -ForegroundColor Cyan
if (-not (Test-Path $NgrokCfg))  { throw "ngrok.yml topilmadi: $NgrokCfg" }
if (-not (Test-Path $GlobalCfg)) { throw "ngrok authtoken konfiguratsiyasi topilmadi: $GlobalCfg`n  ngrok config add-authtoken <TOKEN>" }

function Get-TunnelUrl {
    try {
        $t = Invoke-RestMethod 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 4
        return ($t.tunnels | Where-Object { $_.name -eq $TunnelName } | Select-Object -First 1).public_url
    } catch { return $null }
}

# Bepul tarifda bir vaqtda BITTA agent seansi bo'ladi: ikkinchisini ko'tarsak
# "limited to 1 simultaneous session" xatosi chiqadi. Shuning uchun avval
# tirikmi deb tekshiramiz.
$url = Get-TunnelUrl
if ($url) {
    Write-Host "[i] Tunnel allaqachon ochiq - qayta ishlatilmoqda."
} else {
    # IKKALA konfiguratsiya ham beriladi: authtoken globalda, tunnel ta'rifi va
    # parol esa loyihadagi faylda. ngrok ularni birlashtiradi.
    Start-Process -FilePath 'ngrok' `
        -ArgumentList 'start', '--config', "`"$GlobalCfg`"", '--config', "`"$NgrokCfg`"", $TunnelName `
        -WorkingDirectory $Root -WindowStyle Hidden

    for ($i = 1; $i -le 30; $i++) {
        Start-Sleep -Milliseconds 700
        $url = Get-TunnelUrl
        if ($url) { break }
    }
}
if (-not $url) { throw "Tunnel ko'tarilmadi. ngrok logini tekshiring." }

Write-Host ""
Write-Host "=========================================================" -ForegroundColor Green
Write-Host " Tunnel tayyor: $url" -ForegroundColor Green
Write-Host " Parol bilan himoyalangan (ngrok.yml -> traffic_policy)." -ForegroundColor Green
Write-Host "=========================================================" -ForegroundColor Green
Write-Host ""
Write-Host "ngrok paneli : http://127.0.0.1:4040"
Write-Host "To'xtatish   : .\run_all.ps1 -Stop"
