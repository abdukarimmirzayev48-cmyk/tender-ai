# Avtomatik yangilash (H bosqich) — aniqlik quvuri

Bu hujjat ETL'ni **soatlik avtomatik** yurishga sozlashni tushuntiradi.
Sozlangach dashboardда "Yangilangan: N daqiqa oldin" real ko'rinadi va
katalog xabarnomasi (yangi mos tender) avtomatik ishlaydi.

## Nima quriladi

| Fayl | Vazifa |
|---|---|
| `run_etl.py` | Orkestrator — barcha manbalarni yangilaydi, `etl_run` jurnaliga yozadi |
| `run_etl.sh` | Cron/launchd wrapper — DSN, venv, lock, log |
| `com.birja.etl.plist` | launchd agent (macOS, soatlik) |
| `etl_run` jadval | Har yurish tarixi (sog'lik + yangi topilganlar soni) |
| `first_seen_at` ustun | Biz tenderni birinchi qachon ko'rdik → aniqlash-kechikishi |

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

## Qo'lда yurgizish (istalgan vaqt)

```bash
export XT_DB_DSN="dbname=xtxarid user=a1234 password=... host=localhost"
python3 run_etl.py              # tez: tenderlar + kategoriyalar
python3 run_etl.py --with-docs  # + hujjatlar (sekinroq)
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
