# Avtomatik yangilash (H bosqich) — aniqlik quvuri

Bu hujjat ETL'ni **soatlik avtomatik** yurishga sozlashni tushuntiradi.
Sozlangach dashboardда "Yangilangan: N daqiqa oldin" real ko'rinadi va
katalog xabarnomasi (yangi mos tender) avtomatik ishlaydi.

## Nima quriladi

| Fayl | Vazifa |
|---|---|
| `run_etl.py` | Orkestrator — barcha manbalarni yangilaydi, `etl_run` jurnaliga yozadi |
| `run_etl.sh` | Cron/launchd wrapper (macOS/Linux) — DSN, venv, lock, log |
| `com.birja.etl.plist` | launchd agent (macOS, soatlik) |
| `register_task.ps1` | **Windows** Task Scheduler vazifasini ro'yxatdan o'tkazadi (soatlik) |
| `etl_run` jadval | Har yurish tarixi (sog'lik + yangi topilganlar soni) |
| `first_seen_at` ustun | Biz tenderni birinchi qachon ko'rdik → aniqlash-kechikishi |

## Orkestrator nimani yangilaydi

Har platforma **bir emas, bir nechta** ochiq reyestr chop etadi — faqat
bittasini yig'ish ochiq lotlarning katta qismini yo'qotadi. `run_etl.py`
har platforma uchun barcha reyestrlarni chaqiradi:

| Platforma | Qadamlar | `tender.type` |
|---|---|---|
| xt-xarid | `etl_tenders.py --ref ref_tender_public` | `tender` |
| xt-xarid | `etl_tenders.py --ref ref_selection_public` | `selection` |
| uzex | `etl_uzex.py --type-id 2` | `tender` |
| uzex | `etl_uzex.py --type-id 1` | `selection` |

**Parallellik qoidasi:** platformalar o'zaro parallel yuriladi (turli hostlar),
platforma ICHIDAGI qadamlar esa ketma-ket — bitta hostga parallel urilish manba
rate-limitini hurmat qilmaslik bo'lar edi. `etl_run` jurnaliga har platforma
uchun BITTA qator yoziladi, shuning uchun dashboard "Yangilangan" ko'rsatkichi
avvalgidek ishlaydi.

> Diqqat: uzex `TypeId=1` da ~650 yozuv bor va har biriga alohida `GetTrade`
> so'rovi ketadi → to'liq yurish **~21 daqiqa** oladi (o'lchangan: xt-xarid 7s,
> uzex TypeId=2 101s, uzex TypeId=1 1196s; guruhlar parallel). Soatlik interval
> bunga yetadi. Sinov uchun `python run_etl.py --limit 3` ishlating.

## ⚠️ AVVAL — huquqiy tekshiruv (TZ NFT talabi)

Bu hujjatlashtirilmagan ichki API'larни **uzluksiz** so'raydi. TZ buni
"Yuqori" xavf deb belgilagan: **ishga tushirishdan oldin har platformaning
foydalanish shartlarini huquqiy tekshirish zarur** yoki operator bilan rasmiy
kelishuv. Avtomatik soatlik yurishни yoqishdan oldin shuni hal qiling.

---

## Variant A — launchd (macOS, TAVSIYA)

launchd cron'dan ishonchliroq (kompyuter uxlagandан keyin ham ushlab qoladi).

```bash
cd ~/Downloads/Birja

# 1) plist'ni to'g'ri joyga
cp com.birja.etl.plist ~/Library/LaunchAgents/

# 2) yoqish
launchctl load ~/Library/LaunchAgents/com.birja.etl.plist

# 3) tekshirish (ro'yxatда ko'rinadimi)
launchctl list | grep birja

# Darhol bir marta sinash (soat kutmasdan):
launchctl start com.birja.etl
tail -f ~/Downloads/Birja/etl_cron.log
```

**O'chirish:**
```bash
launchctl unload ~/Library/LaunchAgents/com.birja.etl.plist
```

---

## Variant B — cron

```bash
crontab -e
```
Quyidagi qatorni qo'shing (har soat boshida):
```
0 * * * * /Users/a1234/Downloads/Birja/run_etl.sh
```

> Eslatma: macOS'да cron'ga "Full Disk Access" kerak bo'lishi mumkin
> (System Settings → Privacy → Full Disk Access → `/usr/sbin/cron`).

---

## Variant C — Windows Task Scheduler (TAVSIYA, Windows uchun)

`run_etl.sh` va launchd faqat macOS/Linux uchun. Windows'da `register_task.ps1`
ishlatiladi — u soatlik vazifani ro'yxatdan o'tkazadi, chiqishni
`etl_cron.log` ga qo'shib yozadi va bir vaqtda faqat bitta nusxa ishlashini
kafolatlaydi (`MultipleInstances = IgnoreNew` — `run_etl.sh` dagi mkdir-lock
ning Windows ekvivalenti).

```powershell
cd "D:\MVP projects\tender-ai"

# 0) Quruq sinov — nima qilinishini ko'rsatadi, hech narsa yozmaydi
powershell -NoProfile -ExecutionPolicy Bypass -File .\register_task.ps1 -WhatIf

# 1) Ro'yxatdan o'tkazish (soatlik)
powershell -NoProfile -ExecutionPolicy Bypass -File .\register_task.ps1

# Variantlar:
#   -IntervalMinutes 30   -> yarim soatlik
#   -WithDocs             -> hujjatlarni ham yig'adi (sekinroq)
#   -RunNow               -> ro'yxatdan o'tgach darhol bir marta yurgizadi
```

**Tekshirish:**
```powershell
Get-ScheduledTask     -TaskName TenderAI-ETL-Hourly
Get-ScheduledTaskInfo -TaskName TenderAI-ETL-Hourly   # oxirgi yurish + natija kodi
Start-ScheduledTask   -TaskName TenderAI-ETL-Hourly   # soat kutmasdan sinash
Get-Content .\etl_cron.log -Tail 40 -Wait
```

**O'chirish:**
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\register_task.ps1 -Unregister
```

> **Skriptni tahrirlaganda:** `register_task.ps1` FAQAT ASCII belgilardan
> iborat bo'lishi shart. PowerShell 5.1 BOM'siz `.ps1` faylni UTF-8 emas,
> tizim ANSI kodlash sahifasi deb o'qiydi — uzun tire (`—`) yoki egri
> qo'shtirnoq kabi belgilar qatorni buzadi va skript ishlamay qoladi.

> **Eslatma:** vazifa `LogonType = Interactive` bilan yaratiladi, ya'ni
> foydalanuvchi tizimga kirgan holatda yuriladi (administrator huquqi shart
> emas). Kompyuter qulflangan/chiqilgan holatda ham yurishi kerak bo'lsa,
> vazifani Task Scheduler UI'da "Run whether user is logged on or not" ga
> o'tkazing (parol yoki S4U kerak bo'ladi).

---

## Qo'lда yurgizish (istalgan vaqt)

DSN endi `.env` dan avtomatik o'qiladi (`run_etl.py` `load_dotenv()` chaqiradi),
shuning uchun `export`/`set` qilish shart emas.

```bash
python run_etl.py                 # tez: barcha reyestrlar + kategoriyalar
python run_etl.py --with-docs     # + hujjat MATNI (sekinroq)
python run_etl.py --only-rag      # FAQAT RAG quvuri (manba ETL siz)
python run_etl.py --limit 3       # SINOV: har manbadan 3 yozuv (tez)
python run_etl.py --sequential    # parallelsiz (nosozlikni izlashda)
```

### RAG quvuri — chat YANGI tenderni ko'rishi uchun

Chat hujjatga tayanadi. Hujjat matni chiqarilmasa, bo'lakka bo'linmasa
yoki vektorlanmasa — chat o'sha tender haqida HECH NARSA bilmaydi.

```bash
python run_etl.py --only-rag --vector-budget 1000
```

Uch qadam ketma-ket: hujjat matni -> bo'laklash -> vektorlash
(+ tender darajasidagi vektorlar).

| Bayroq | Ma'nosi |
|---|---|
| `--with-rag` | RAG qadamlarini oddiy yurishga qo'shadi |
| `--only-rag` | FAQAT RAG: manba ETL, kategoriya, bildirishnoma o'tkaziladi |
| `--vector-budget N` | bir yurishda N ta bo'lak (standart 3000). 0 = vektorlashsiz |
| `--docs-catalog` | ESKI tor qamrov (2026-08 da amalda tugagan) |

**Nega alohida vazifa:** vektorlash ~3 bo'lak/s, ya'ni soatlar oladi.
Soatlik yurishga qo'shilsa BILDIRISHNOMA o'shancha kechikadi.

**Nega byudjet:** tanlash sharti `embedding IS NULL` — uzilgan yurish
qolganidan davom etadi. 1000 bo'lak ~5 daqiqa; soat sayin yurgizilsa
kuniga 24 000, ya'ni tekis yuk.

**Bir vaqtda ikki yurish:** `pg_try_advisory_lock` himoya qiladi —
ikkinchisi kutmasdan chiqadi. Ketma-ket 3 martadan ko'p o'tkazilsa
jurnalga `!! OGOHLANTIRISH` yoziladi (osilib qolgan jarayon belgisi).

**Sinov to'plami:**
```bash
.venv\Scripts\python.exe _tests\etl_coverage_test.py
.venv\Scripts\python.exe _tests\etl_coverage_test.py --offline   # tarmoqsiz
```

---

## Monitoring

```bash
# Oxirgi yurishlar (sog'lik + yangi topilganlar)
psql "dbname=xtxarid user=a1234 host=localhost" -c \
  "SELECT source_platform, status, found, new, finished_at,
          round(extract(epoch from (finished_at-started_at)))||'s' AS davomiylik
   FROM etl_run ORDER BY started_at DESC LIMIT 10;"

# Dashboard: yuqori o'ng burchakdagi 'Yangilangan: …' ko'rsatkichi
# (yashil=yangi+xatosiz, sariq=eskirgan, qizil=ETL xatosi)
```

## Sozlash

- **Chastota:** `com.birja.etl.plist` da `StartInterval` (soniyada). 3600 = soatlik.
- **Hujjatlar va RAG:** alohida vazifa sifatida yurgiziladi (yuqoriga
  qarang), soatlik yurishga qo'shilmaydi — aks holda bildirishnoma
  kechikadi.
- **Windows jadvali:**
  ```
  TenderAI-ETL-Hourly   soat boshida   run_etl.py
  TenderAI-RAG          soat :30 da    run_etl.py --only-rag --vector-budget 3000
  ```
  `:30` ATAYLAB: advisory qulf ikkita RAG yurishini himoya qiladi,
  lekin manba ETL bilan CPU raqobatini emas.

  **Ikkalasi ham `register_task.ps1` DAN ro'yxatdan o'tkaziladi:**

  ```powershell
  .\register_task.ps1                          # ETL, soat boshida
  .\register_task.ps1 -Rag -VectorBudget 3000  # RAG, soat :30 da
  ```

  RAG vazifasi avval QO'LDA yaratilgan edi va shu sababli STANDART
  sozlamalarni olgan: `DisallowStartIfOnBatteries=True`,
  `StopIfGoingOnBatteries=True`, `WakeToRun=False`. Noutbuk rozetkadan
  uzilishi bilan yurish o'lardi. Jurnalda uchta "RAG boshlandi" bor
  edi, **bitta ham "RAG tugadi" yo'q**, va vektorlash 38 242 da
  muzlab qolgandi. Endi sozlama bir manbadan keladi.

  **Byudjet 1000 dan 3000 ga oshirildi.** O'lchandi: to'liq RAG
  yurishi 1000 lik byudjet bilan 5 daqiqa (vektorlash 2.8 daqiqa),
  ya'ni 50 daqiqalik oynaning 90% i behuda turardi. 3000 bilan ~9
  daqiqa va navbat 37 soat o'rniga ~12 soatda tugaydi. Vektorlash
  uzilsa xavf yo'q: `embedding IS NULL` sharti tanlaydi, ya'ni
  keyingi yurish qolganidan davom etadi.

- **CHEKLOV — `LogonType = Interactive`.** Ikkala vazifa ham FAQAT
  siz tizimga kirgan holda yuradi. Tizimdan chiqilsa yoki seans
  uzilsa bola-jarayonlar `0xC000013A` bilan o'ladi. Jurnalda bu
  14 kunda 100 marta uchradi (~10% yurish, uchta har xil skriptda,
  kunning har soatida) — ehtimoliy sabab aynan shu, lekin **isbotlanmagan**.

  Doimiy ishlashi uchun ADMIN huquqi kerak:

  ```powershell
  .\register_task.ps1 -RunWhenLoggedOff          # ETL
  .\register_task.ps1 -Rag -RunWhenLoggedOff     # RAG
  ```

  Vaqtinchalik yumshatish: `run_etl.py` majburan to'xtatilgan bolani
  BIR MARTA qayta urinadi (haqiqiy `Ctrl+C` bo'lmasa).
- **Buzilish ogohlantirishi:** `etl_run.status='error'` bo'lsa dashboard
  ko'rsatkichi qizil bo'ladi. Email/Telegram ogohlantirish — keyingi qadam.
