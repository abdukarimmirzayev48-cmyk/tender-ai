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

.PARAMETER Rag
    ETL o'rniga RAG quvurini ro'yxatdan o'tkazadi (--only-rag): hujjat
    matni, bo'laklash, talab ajratish va bo'lak vektorlash. Nomi
    TenderAI-RAG, soat :30 da, vaqt chegarasi 50 daqiqa.

    NEGA SHU YERDA: RAG vazifasi avval QO'LDA yaratilgan edi va shu
    sababli STANDART sozlamalarni olgan:

        DisallowStartIfOnBatteries = True
        StopIfGoingOnBatteries     = True
        WakeToRun                  = False

    Ya'ni noutbuk rozetkadan uzilsa vazifa darhol o'lardi va umuman
    boshlanmasdi. Natijada jurnalda uchta "RAG boshlandi" bor edi,
    BITTA ham "RAG tugadi" yo'q, va bo'lak vektorlash 38 242 da
    muzlab qolgandi. Endi sozlamalar ETL bilan BIR MANBADAN keladi.

.PARAMETER VectorBudget
    Bir RAG yurishida nechta bo'lak vektorlanadi (standart 1000).
    Vektorlash ~3 bo'lak/s, ya'ni 1000 ta ~6 daqiqa - 50 daqiqalik
    oynaga bemalol sig'adi.

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
    [switch] $Unregister,
    [switch] $RunWhenLoggedOff,
    # Faqat hujjat uchun: -RunWhenLoggedOff ALLAQACHON S4U qo'yadi.
    # Parametr QABUL QILINADI, chunki buyruq yozganda uni ko'rsatish
    # tabiiy va bo'lmasa PowerShell "parameter cannot be found" deb
    # yiqilardi. Boshqa qiymat berilsa ANIQ xato beriladi.
    [ValidateSet('S4U')]
    [string] $LogonType = 'S4U',
    [switch] $Rag,
    [int]    $VectorBudget = 1000
)

$ErrorActionPreference = 'Stop'

# --- Yo'llar -----------------------------------------------------------------
$Root = $PSScriptRoot
if (-not $Root) { $Root = (Get-Location).Path }

# RAG rejimi: nom va boshlanish daqiqasi ETL dan FARQ QILADI, aks holda
# ikkalasi bir vaqtda yurib bir-birini bloklardi (MultipleInstances emas -
# ular alohida vazifa, lekin CPU va manba limitini bo'lishadi).
if ($Rag -and $TaskName -eq 'TenderAI-ETL-Hourly') { $TaskName = 'TenderAI-RAG' }

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

$label = 'ETL'
if ($Rag) {
    $label   = 'RAG'
    $etlArgs = ' --only-rag --vector-budget ' + $VectorBudget
}

$parts = @(
    'set PYTHONIOENCODING=utf-8'
    ('echo ===== !DATE! !TIME! {0} boshlandi ^(interval {1}m^) ===== >> "{2}"' -f $label, $IntervalMinutes, $LogFile)
    ('"{0}" "{1}"{2} >> "{3}" 2>&1' -f $Python, $EtlScript, $etlArgs, $LogFile)
    ('echo ===== !DATE! !TIME! {0} tugadi, exit=!ERRORLEVEL! ===== >> "{1}"' -f $label, $LogFile)
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
# RAG soat :30 da - manba ETL :00 da tugagach ishga tushsin.
if ($Rag) { $startAt = $startAt.AddMinutes(30) }

$trigger = New-ScheduledTaskTrigger -Once -At $startAt
# PowerShell 5.1 da -Once + -RepetitionInterval bevosita ishlamasligi mumkin,
# shuning uchun Repetition ni alohida trigger'dan ko'chiramiz (ishonchli usul).
$repeatSource = New-ScheduledTaskTrigger -Once -At $startAt -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) -RepetitionDuration (New-TimeSpan -Days 3650)
$trigger.Repetition = $repeatSource.Repetition

# -WakeToRun: kompyuter uyquda bo'lsa vazifa uchun UYG'OTADI. Busiz noutbuk
# yopilgan har soat o'tkazib yuboriladi (kuzatilgan: 03:00 dan 16:50 gacha
# 13.8 soat davomida BITTA ham yurish bo'lmagan).
# -AllowStartIfOnBatteries / -DontStopIfGoingOnBatteries: RAG vazifasi
# QO'LDA yaratilganda bu ikkisi standart (TAQIQ) holatda qolgan edi va
# noutbuk rozetkadan uzilishi bilan yurish o'lardi. Ikkala vazifa ham
# SHU YAGONA manbadan sozlansin.
#
# Vaqt chegarasi: ETL 2 soat, RAG 50 daqiqa (soatlik takrorlanishdan
# oldin tugasin, aks holda keyingi yurish IgnoreNew bilan tushib
# qolardi).
$timeLimit = if ($Rag) { New-TimeSpan -Minutes 50 } else { New-TimeSpan -Hours 2 }
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -WakeToRun -ExecutionTimeLimit $timeLimit -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 10)

# LogonType tanlovi:
#   Interactive (standart) - vazifa FAQAT siz tizimga kirgan bo'lsangiz yuradi.
#     Hisobdan chiqilsa/kompyuter qulflansa - yurish yo'q.
#   S4U (-RunWhenLoggedOff) - kirgan/kirmaganingizdan qat'i nazar yuradi.
#     MUHIM: S4U bilan ro'yxatdan o'tkazish uchun bu skriptni ADMINISTRATOR
#     huquqi bilan yurgizish kerak, aks holda Register-ScheduledTask "Access
#     is denied" beradi.
if ($RunWhenLoggedOff) {
    # ADMIN TEKSHIRUVI O'CHIRISHDAN OLDIN.
    #
    # Quyida eski vazifa AVVAL o'chiriladi, keyin yangisi yaratiladi.
    # Admin huquqisiz S4U bilan Register-ScheduledTask "Access is denied"
    # beradi - va o'sha paytda eski vazifa ALLAQACHON O'CHIRILGAN bo'lardi.
    # Ya'ni tuzatishga urinish avtomatlashtirishni BUTUNLAY yo'q qilardi.
    $idn = [Security.Principal.WindowsIdentity]::GetCurrent()
    $prn = New-Object Security.Principal.WindowsPrincipal($idn)
    if (-not $prn.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Host ''
        Write-Host "[XATO] -RunWhenLoggedOff (S4U) ADMIN huquqini talab qiladi."
        Write-Host "       Joriy foydalanuvchi: $($idn.Name) (admin emas)."
        Write-Host ''
        Write-Host "       Mavjud vazifa TEGILMADI - o'chirilmadi."
        Write-Host "       Administrator PowerShell ochib qayta yurgizing:"
        Write-Host ''
        Write-Host "         .\register_task.ps1 -RunWhenLoggedOff"
        Write-Host "         .\register_task.ps1 -Rag -RunWhenLoggedOff"
        Write-Host ''
        throw "Admin huquqi yo'q - S4U ro'yxatdan o'tkazib bo'lmaydi."
    }

    # S4U: parol SAQLANMAYDI. Cheklovi - tarmoq resurslariga (SMB, domen)
    # kira olmaydi. Bu quvurga TEGISHLI EMAS: baza localhost:5432, fayllar
    # lokal, tashqi tarmoq esa faqat CHIQUVCHI HTTPS (manba platformalar) -
    # S4U ikkalasini ham qo'llab-quvvatlaydi.
    #
    # O'Z hisobingiz ko'rsatiladi, SYSTEM emas: sentence-transformers
    # modeli %USERPROFILE%\.cache\huggingface dan o'qiladi va SYSTEM
    # ostida u BOSHQA yo'l bo'lardi - model qaytadan yuklanardi.
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Limited
    Write-Host "[i] Rejim: S4U - tizimga kirmagan holda ham yuradi (parol saqlanmaydi)."
} else {
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
    Write-Host "[i] Rejim: Interactive - FAQAT siz tizimga kirgan bo'lsangiz yuradi."
    Write-Host "    Doimiy ishlashi uchun: admin PowerShell'da -RunWhenLoggedOff bilan qayta yurgizing."
}

# --- Mavjud bo'lsa qayta yaratamiz -------------------------------------------
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    if ($PSCmdlet.ShouldProcess($TaskName, "Eski vazifani o'chirish")) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "[i] Eski '$TaskName' o'chirildi (qayta yaratiladi)."
    }
}

if ($PSCmdlet.ShouldProcess($TaskName, "Soatlik vazifani ro'yxatdan o'tkazish")) {
    $desc = if ($Rag) {
        'Tender AI: RAG quvuri (hujjat matni, bo`laklash, talablar, vektorlash)'
    } else {
        'Tender AI: davlat xaridlari ETL (xt-xarid + uzex), soatlik yangilanish'
    }
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description $desc | Out-Null
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
