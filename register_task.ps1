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
    [int]    $VectorBudget = 1000,
    # Bitta platforma guruhining vaqt byudjeti (sekund). ETL shu vaqtda
    # TOZA to'xtaydi va checkpoint yozadi. ExecutionTimeLimit (40 daqiqa)
    # dan ANIQ KICHIK bo'lishi SHART - aks holda Windows jarayonni
    # o'ldiradi va holat saqlanmaydi.
    [int]    $MaxSeconds = 1500
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
# --max-seconds: SKRIPT o'zi to'xtaydi, Windows o'ldirmasin.
# Bu qiymat ExecutionTimeLimit dan ANIQ KICHIK (25 daqiqa / 40 daqiqa).
# Byudjet tugaganda checkpoint yoziladi va keyingi yurish shu yerdan
# davom etadi - ya'ni uzun yig'ish soatlar bo'yicha bo'lib bajariladi.
$etlArgs = ' --max-seconds ' + [int]($MaxSeconds)
if ($WithDocs) { $etlArgs += ' --with-docs' }

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
# VAQT CHEGARASI - O'LCHANGAN SABAB BILAN QAYTA HISOBLANDI (2026-08-30).
#
# Ilgari ETL uchun 2 SOAT edi, interval esa 1 soat. Ikki oqibati bor edi:
#   1. Osilgan yurish IgnoreNew bilan KEYINGI ikki yurishni ham to'sardi.
#   2. Chegara tugaganda Windows jarayonni O'LDIRADI (0xC000013A) va
#      hech qanday holat saqlanmasdi - yurish noldan boshlanardi.
#
# Endi tartib teskari: SKRIPT o'zi to'xtaydi, Windows emas.
#   run_etl.py --max-seconds 1500  (25 daqiqa, guruh bo'yicha taqsimlanadi)
#   ExecutionTimeLimit 40 daqiqa   (15 daqiqa zaxira)
# Chegara endi NORMAL yo'l emas, XAVFSIZLIK TO'RI: unga yetish
# skriptning o'z byudjeti ishlamaganini bildiradi.
$timeLimit = if ($Rag) { New-TimeSpan -Minutes 45 } else { New-TimeSpan -Minutes 40 }

# -DontStopOnIdleEnd: `IdleSettings.StopOnIdleEnd` STANDART holatda
#   True. O'lchangan (2026-08-30): mavjud vazifada u True turgan edi.
#   Bu "bo'sh turish tugasa vazifani to'xtat" degani va aynan
#   foydalanuvchi mashinaga qaytgan paytda yurishni o'ldirardi.
# -Priority 5: standart 7 (past). Modern Standby'da (bu mashinada
#   FAQAT S0 mavjud - `powercfg /a` bilan tekshirilgan) past
#   prioritetli jarayonlar birinchi bo'lib to'xtatiladi.
# -WakeToRun: SAQLANADI, lekin bu mashinada u va'dani BAJARA OLMAYDI.
#   S1/S2/S3 yo'q, faqat Modern Standby (S0 low-power idle). Uyg'otish
#   taymeri klassik S3 dagidek ishlamaydi. Shuning uchun asosiy tayanch
#   -StartWhenAvailable: o'tkazib yuborilgan yurish mashina uyg'onishi
#   bilan bajariladi.
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -DontStopOnIdleEnd `
    -WakeToRun `
    -Priority 5 `
    -ExecutionTimeLimit $timeLimit `
    -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 10)

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
    Write-Host ''
    Write-Host "[OGOHLANTIRISH] Rejim: Interactive - bu O'LCHANGAN NOSOZLIK SABABI."
    Write-Host ''
    Write-Host "    2026-08-30 tahlili (14 kun, etl_run + etl_cron.log):"
    Write-Host "      LastTaskResult      0xC000013A (majburan to'xtatildi)"
    Write-Host "      etl_cron.log        161 'boshlandi' / 11 'tugadi'"
    Write-Host "      jurnalda            literal ^C belgilari"
    Write-Host ''
    Write-Host "    Interactive vazifa seans tugashi bilan O'LADI: hisobdan"
    Write-Host "    chiqish, qulflash yoki foydalanuvchi almashish butun"
    Write-Host "    jarayon daraxtini konsol hodisasi bilan o'ldiradi."
    Write-Host ''
    Write-Host "    TUZATISH - administrator PowerShell'da:"
    Write-Host "      .\register_task.ps1 -RunWhenLoggedOff"
    Write-Host "      .\register_task.ps1 -Rag -RunWhenLoggedOff"
    Write-Host ''
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

    # --- DIAGNOSTIKA JURNALI -------------------------------------------------
    # `Microsoft-Windows-TaskScheduler/Operational` STANDART holatda
    # O'CHIQ va bu mashinada ham o'chiq edi (o'lchangan 2026-08-30:
    # IsEnabled=False). Natijada vazifa NEGA tugagani haqida yagona
    # ishonchli manba YO'Q edi: biz faqat oqibatni (yetim 'running'
    # qatorlari) ko'rardik, sababini emas.
    try {
        $opLog = Get-WinEvent -ListLog 'Microsoft-Windows-TaskScheduler/Operational' -ErrorAction Stop
        if (-not $opLog.IsEnabled) {
            $opLog.IsEnabled = $true
            $opLog.SaveChanges()
            Write-Host ''
            Write-Host "[OK] TaskScheduler/Operational jurnali YOQILDI."
            Write-Host "     Endi vazifa nega tugagani yozib boriladi (111=to'xtatildi,"
            Write-Host "     201=tugadi, 329=vaqt chegarasi, 332=shart bajarilmadi)."
        } else {
            Write-Host "[i] TaskScheduler/Operational jurnali allaqachon yoqilgan."
        }
    } catch {
        Write-Host "[!] TaskScheduler/Operational jurnalini yoqib bo'lmadi (admin kerak):"
        Write-Host "    $($_.Exception.Message)"
        Write-Host "    Qo'lda: wevtutil sl Microsoft-Windows-TaskScheduler/Operational /e:true"
    }

    # --- HAQIQATAN QO'YILGAN SOZLAMALARNI CHOP ETAMIZ ------------------------
    # Skript nima SO'RAGANINI emas, Windows nima QABUL QILGANINI
    # ko'rsatamiz. Ilgari RAG vazifasi qo'lda yaratilgani uchun
    # standart (taqiqlovchi) sozlamalarni olgandi va buni hech kim
    # tekshirmagandi.
    $t = Get-ScheduledTask -TaskName $TaskName
    $s = $t.Settings
    Write-Host ''
    Write-Host "--- Qo'yilgan sozlamalar (Windows tasdiqladi) ---"
    Write-Host ("  LogonType                 : {0}" -f $t.Principal.LogonType)
    Write-Host ("  ExecutionTimeLimit        : {0}" -f $s.ExecutionTimeLimit)
    Write-Host ("  Skript byudjeti           : {0}s" -f $(if ($Rag) { 'n/a' } else { $MaxSeconds }))
    Write-Host ("  MultipleInstances         : {0}" -f $s.MultipleInstances)
    Write-Host ("  StartWhenAvailable        : {0}" -f $s.StartWhenAvailable)
    Write-Host ("  WakeToRun                 : {0}" -f $s.WakeToRun)
    Write-Host ("  DisallowStartIfOnBatteries: {0}" -f $s.DisallowStartIfOnBatteries)
    Write-Host ("  StopIfGoingOnBatteries    : {0}" -f $s.StopIfGoingOnBatteries)
    Write-Host ("  StopOnIdleEnd             : {0}" -f $s.IdleSettings.StopOnIdleEnd)
    Write-Host ("  Priority                  : {0}" -f $s.Priority)
    Write-Host ("  RestartCount / Interval   : {0} / {1}" -f $s.RestartCount, $s.RestartInterval)

    # --- UYQU REJIMI HAQIDA HALOL OGOHLANTIRISH ------------------------------
    # Bu mashinada FAQAT Modern Standby (S0) mavjud - `powercfg /a` bilan
    # tekshirilgan (2026-08-30). Unda `WakeToRun` klassik S3 dagidek
    # ishlamaydi, shuning uchun uni "yechim" deb ko'rsatmaymiz.
    #
    # AVTOMATIK ANIQLASH QILINMAYDI - ATAYLAB.
    #
    # Ikki yo'l ham ishonchsiz chiqdi (2026-08-30 da sinaldi):
    #   * `powercfg /a` chiqishi TARJIMA QILINADI (bu mashinada ruscha),
    #     ya'ni matnga tayangan tekshiruv boshqa tilda JIMGINA ishlamay
    #     qo'yardi - shu loyihada takrorlangan nuqson sinfi;
    #   * `CsEnabled` reestr qiymati bu mashinada UMUMAN YO'Q, garchi
    #     Modern Standby yoqilgan bo'lsa ham.
    #
    # Noto'g'ri avtomatik xulosadan ko'ra XOM DALILNI ko'rsatgan yaxshi.
    Write-Host ''
    Write-Host "--- Uyqu holatlari (powercfg /a) ---"
    try {
        (powercfg /a) | Select-Object -First 6 | ForEach-Object { "  $_" }
    } catch {
        Write-Host "  (powercfg o'qilmadi)"
    }
    Write-Host ''
    Write-Host "[i] Agar yuqorida faqat S0 (Modern Standby) ko'rinsa va S3 mavjud"
    Write-Host "    bo'lmasa: -WakeToRun klassik uyg'otishni KAFOLATLAMAYDI."
    Write-Host "    Bu holda tayanch -StartWhenAvailable: o'tkazib yuborilgan"
    Write-Host "    yurish mashina uyg'onishi bilan bajariladi, ETL esa"
    Write-Host "    checkpoint dan DAVOM etadi (noldan boshlamaydi)."

    if ($RunNow) {
        Start-ScheduledTask -TaskName $TaskName
        Write-Host "[i] Darhol bir marta yurgizildi - logni kuzating."
    }
}
