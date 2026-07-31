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
python run_etl.py --with-docs     # + hujjatlar (sekinroq)
python run_etl.py --limit 3       # SINOV: har manbadan 3 yozuv (tez)
python run_etl.py --sequential    # parallelsiz (nosozlikni izlashda)
```

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
- **Hujjatlar ham:** wrapper `run_etl.py` ni `--with-docs` bilan chaqirishi uchun
  `run_etl.sh` da o'zgartiring (sekinroq bo'ladi).
- **Buzilish ogohlantirishi:** `etl_run.status='error'` bo'lsa dashboard
  ko'rsatkichi qizil bo'ladi. Email/Telegram ogohlantirish — keyingi qadam.
