<#
.SYNOPSIS
    Tender AI ETL uchun SOATLIK Windows Task Scheduler vazifasini ro'yxatdan
    o'tkazadi (P0-1: "tanlangan platformalarni soatiga bir marta tekshirish").

.DESCRIPTION
    macOS uchun com.birja.etl.plist + run_etl.sh bor edi; bu skript o'sha
    vazifani Windows'da bajaradi:
      - har $IntervalMinutes daqiqada `run_etl.py` ni yurgizadi
      - butun chiqishni $Root\etl_cron.log fayliga QO'SHIB yozadi
      - bir vaqtda faqat BITTA nusxa ishlaydi (MultipleInstances = IgnoreNew,
        ya'ni oldingi yurish tugamagan bo'lsa yangisi o'tkazib yuboriladi -
        run_etl.sh dagi mkdir-lock ning Windows ekvivalenti)
      - vazifa allaqachon bo'lsa - o'chirib, qaytadan yaratadi (idempotent)

    MUHIM: bu fayl FAQAT ASCII belgilardan iborat. PowerShell 5.1 BOM'siz .ps1
    faylni UTF-8 emas, tizim ANSI kodlash sahifasi deb o'qiydi; uzun tire yoki
    egri qo'shtirnoq kabi belgilar qatorni buzadi. Tahrirlaganda ham faqat
    ASCII ishlating.

.PARAMETER TaskName
    Vazifa nomi (standart: TenderAI-ETL-Hourly).

.PARAMETER IntervalMinutes
    Takrorlanish oralig'i daqiqada (standart: 60 = soatlik).

.PARAMETER WithDocs
    run_etl.py ga --with-docs beriladi (hujjatlar ham yig'iladi, sekinroq).

.PARAMETER RunNow
    Ro'yxatdan o'tkazgach darhol bir marta yurgizadi (soat kutmasdan sinash).

.PARAMETER Unregister
    Vazifani o'chiradi va chiqadi.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File .\register_task.ps1
.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File .\register_task.ps1 -WhatIf
.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File .\register_task.ps1 -Unregister
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string] $TaskName        = 'TenderAI-ETL-Hourly',
    [int]    $IntervalMinutes = 60,
    [switch] $WithDocs,
    [switch] $RunNow,
    [switch] $Unregister
)

$ErrorActionPreference = 'Stop'

# --- Yo'llar -----------------------------------------------------------------
$Root = $PSScriptRoot
if (-not $Root) { $Root = (Get-Location).Path }

$Python    = Join-Path $Root '.venv\Scripts\python.exe'
$EtlScript = Join-Path $Root 'run_etl.py'
$LogFile   = Join-Path $Root 'etl_cron.log'
$CmdExe    = Join-Path $env:SystemRoot 'System32\cmd.exe'

# --- O'chirish rejimi --------------------------------------------------------
if ($Unregister) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $existing) {
        Write-Host "[i] '$TaskName' vazifasi topilmadi - o'chiradigan narsa yo'q."
        return
    }
    if ($PSCmdlet.ShouldProcess($TaskName, "Vazifani o'chirish")) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "[OK] '$TaskName' o'chirildi."
    }
    return
}

# --- Tekshiruvlar ------------------------------------------------------------
if (-not (Test-Path $EtlScript)) {
    throw "run_etl.py topilmadi: $EtlScript"
}
if (-not (Test-Path $Python)) {
    Write-Warning "venv python topilmadi: $Python"
    Write-Warning "Avval virtual muhitni yarating: python -m venv .venv"
    Write-Warning "Vazifa baribir ro'yxatdan o'tkaziladi, lekin yurmaydi."
}
if (-not (Test-Path (Join-Path $Root '.env'))) {
    Write-Warning ".env topilmadi - run_etl.py XT_DB_DSN ni o'qiy olmaydi."
}

# --- Bajariladigan buyruq ----------------------------------------------------
# cmd.exe orqali yurgizamiz, chunki Task Scheduler o'zi chiqishni faylga
# yo'naltira olmaydi. /v:on = kechiktirilgan kengaytirish (!ERRORLEVEL! va
# yakuniy !TIME! to'g'ri qiymat berishi uchun).
# PYTHONIOENCODING=utf-8 - kirill matn log faylga buzilmasdan tushishi uchun.
$etlArgs = ''
if ($WithDocs) { $etlArgs = ' --with-docs' }

$parts = @(
    'set PYTHONIOENCODING=utf-8'
    ('echo ===== !DATE! !TIME! ETL boshlandi ^(interval {0}m^) ===== >> "{1}"' -f $IntervalMinutes, $LogFile)
    ('"{0}" "{1}"{2} >> "{3}" 2>&1' -f $Python, $EtlScript, $etlArgs, $LogFile)
    ('echo ===== !DATE! !TIME! ETL tugadi, exit=!ERRORLEVEL! ===== >> "{0}"' -f $LogFile)
)
$TaskArgument = '/v:on /c "' + ($parts -join ' & ') + '"'

Write-Host "Katalog        : $Root"
Write-Host "Python         : $Python"
Write-Host "Log            : $LogFile"
Write-Host "Interval       : $IntervalMinutes daqiqa"
Write-Host "Vazifa nomi    : $TaskName"
Write-Host ''

# --- Vazifa qismlari ---------------------------------------------------------
$action = New-ScheduledTaskAction -Execute $CmdExe -Argument $TaskArgument -WorkingDirectory $Root

# Boshlanish - keyingi soat boshi (kechagi/o'tgan vaqt qo'yilsa Scheduler
# vazifani darhol yurgizib yuborishi mumkin).
$now     = Get-Date
$startAt = $now.Date.AddHours($now.Hour + 1)

$trigger = New-ScheduledTaskTrigger -Once -At $startAt
# PowerShell 5.1 da -Once + -RepetitionInterval bevosita ishlamasligi mumkin,
# shuning uchun Repetition ni alohida trigger'dan ko'chiramiz (ishonchli usul).
$repeatSource = New-ScheduledTaskTrigger -Once -At $startAt -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) -RepetitionDuration (New-TimeSpan -Days 3650)
$trigger.Repetition = $repeatSource.Repetition

$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2) -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 10)

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

# --- Mavjud bo'lsa qayta yaratamiz -------------------------------------------
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    if ($PSCmdlet.ShouldProcess($TaskName, "Eski vazifani o'chirish")) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "[i] Eski '$TaskName' o'chirildi (qayta yaratiladi)."
    }
}

if ($PSCmdlet.ShouldProcess($TaskName, "Soatlik vazifani ro'yxatdan o'tkazish")) {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Tender AI: davlat xaridlari ETL (xt-xarid + uzex), soatlik yangilanish' | Out-Null
    Write-Host "[OK] '$TaskName' ro'yxatdan o'tkazildi. Birinchi yurish: $startAt"
    Write-Host ''
    Write-Host "Tekshirish  : Get-ScheduledTask -TaskName $TaskName"
    Write-Host "Tarix       : Get-ScheduledTaskInfo -TaskName $TaskName"
    Write-Host "Qo'lda      : Start-ScheduledTask -TaskName $TaskName"
    Write-Host "O'chirish   : .\register_task.ps1 -Unregister"
    Write-Host "Log         : Get-Content '$LogFile' -Tail 40 -Wait"

    if ($RunNow) {
        Start-ScheduledTask -TaskName $TaskName
        Write-Host "[i] Darhol bir marta yurgizildi - logni kuzating."
    }
}
