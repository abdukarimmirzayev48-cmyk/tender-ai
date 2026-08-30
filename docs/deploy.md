# Joylashtirish — staging birinchi

**Sana:** 2026-08-31 · **Maqsad:** ishlab chiqarishga **faqat staging'dan
o'tgan** kod tushsin

---

## 1. Arxitektura — eng kichik saqlab turiladigan shakl

```
                    Internet
                       │  HTTPS (avtomatik sertifikat)
                       v
            ┌──────────────────────┐
            │  Caddy               │  bitta konfiguratsiya fayli
            │  staging.example.uz  │  → basic_auth ortida
            │  tender.example.uz   │
            └──────┬───────────────┘
       /api/*      │      /  (statik)
                   │
      ┌────────────┴────────────┐        ┌──────────────────────┐
      │ uvicorn 127.0.0.1:8000  │        │ frontend/dist        │
      │ tenderai-api@production │        │ (npm run build)      │
      │ Restart=always          │        └──────────────────────┘
      └────────────┬────────────┘
                   │
      ┌────────────┴────────────┐   ┌──────────────────────────────┐
      │ PostgreSQL + pgvector   │   │ systemd timer'lar            │
      │ rol: tai_app (DDL yo'q) │   │  etl@          soatiga 1     │
      └─────────────────────────┘   │  backup@       har kuni 02:30│
                                    │  restore-test@ yakshanba 04:00│
                                    └──────────────────────────────┘
```

### Nega shunday

| Qaror | Sabab |
|---|---|
| **systemd**, Docker emas | Bitta VPS, bitta ilova. Konteyner qatlami bu yerda foyda bermay, `pgvector`, model keshi (~470 MB) va GPU'siz CPU ip sozlamalari uchun qo'shimcha murakkablik qo'shardi. |
| **Caddy**, nginx+certbot emas | HTTPS sertifikati avtomatik olinadi va yangilanadi. nginx bir xil natijaga ikkita harakatlanuvchi qism bilan yetadi. |
| **Shablon birlik** (`@`) | Staging va production uchun ikkita deyarli bir xil fayl — ular ajralib ketishining eng qisqa yo'li. |
| **systemd timer**, cron emas | Odam kirmagan bo'lsa ham ishlaydi; `Persistent=true` o'tkazib yuborilgan yurishni bajaradi; jurnal `journalctl` da. |
| **`current` simvolik havolasi** | Orqaga qaytarish bitta atomar amal (`ln -sfn`) — "yarmi eski, yarmi yangi" holati yuzaga kelmaydi. |

---

## 2. Bir marta: serverni tayyorlash

```bash
# Talablar: Debian/Ubuntu, Python 3.11+, Node 20+, PostgreSQL 16+, Caddy, git
sudo apt install -y python3-venv postgresql postgresql-contrib caddy git curl

# Repozitoriyani serverga oling (bare repo — push shu yerga)
sudo -u tenderai git init --bare /opt/tenderai/repo.git   # bootstrap.sh o'zi qiladi

# Katalog, rol, systemd birliklari, sudo qoidalari
sudo deploy/bin/bootstrap.sh staging
sudo deploy/bin/bootstrap.sh production
```

`bootstrap.sh` **sir yaratmaydi va so'ramaydi**. U faqat tuzilmani
qo'yadi va `/etc/tenderai/<muhit>.env` ni namunadan nusxalaydi
(`0640`, `root:tenderai`).

---

## 3. Sirlar

**Repozitoriyaga hech qachon tushmaydi.** `.gitignore` da
`deploy/env/*.env` chetlatilgan, faqat `*.env.example` kuzatiladi;
`_tests/deploy_test.py` buni har yurishda tekshiradi.

```bash
sudo -e /etc/tenderai/staging.env      # qiymatlarni to'ldiring
sudo chmod 0640 /etc/tenderai/staging.env
sudo chown root:tenderai /etc/tenderai/staging.env
```

**Majburiy:** `PUBLIC_BASE_URL`, `XT_DB_DSN`, `XT_DB_DSN_OWNER`.

---

## 4. Baza

```sql
CREATE DATABASE tenderai_staging;
\c tenderai_staging
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
```

Migratsiyalar **egasi** roli bilan yuriladi (`XT_DB_DSN_OWNER`), ilova
esa **eng kam huquqli** `tai_app` bilan (`schema_patch_huquq.sql`,
`docs/xavfsizlik.md` §4):

```sql
CREATE ROLE tai_service LOGIN PASSWORD '<kuchli tasodifiy parol>';
GRANT tai_app TO tai_service;
```

`tai_app` da **DDL huquqi ataylab yo'q** — ilova sxemani o'zgartira
olmasligi kerak.

---

## 5. Joylashtirish

```bash
# 1) STAGING — har doim birinchi
git push server main:refs/heads/main          # yoki: git push server v1.2.3
deploy/bin/deploy.sh staging v1.2.3

# 2) Tekshiring: interfeys, chat, ETL
journalctl -u tenderai-api@staging -f
systemctl list-timers 'tenderai-*'

# 3) PRODUCTION — faqat AYNAN SHU ref staging'da o'tgan bo'lsa
deploy/bin/deploy.sh production v1.2.3
```

`deploy.sh production` **staging tasdig'isiz ishlamaydi**:
`/opt/tenderai/staging/.verified` faylida saqlangan ref bilan
solishtiriladi va **boshqa ref bo'lsa to'xtaydi**. Tasdiqni staging
joylashtiruvi **sog'liq tekshiruvidan o'tgach** o'zi yozadi.

### Joylashtirish qadamlari

1. `git archive` → yangi reliz katalogi (`releases/<vaqt>-<ref>`)
2. `python -m venv` + `pip install -r requirements-api.txt`
3. `npm ci && npm run build` → `frontend/dist`
4. **Migratsiya** (egasi roli bilan)
5. `ln -sfn` → `current` (**atomar**)
6. `systemctl restart tenderai-api@<muhit>` + timer'lar
7. **Sog'liq tekshiruvi** — o'tmasa **avtomatik orqaga qaytariladi**
8. Eski relizlar: oxirgi 5 tasi qoladi

---

## 6. Sog'liq, tayyorlik, ETL yangiligi

To'rt tekshiruv **ataylab ajratilgan** — ular boshqa-boshqa narsani
o'lchaydi:

| Endpoint | Nima | Muvaffaqiyatsizlik |
|---|---|---|
| `/health` | Jarayon javob beryaptimi (+ baza) | Xizmat o'lgan |
| `/ready` | Baza **va migratsiya** holati | **503** — proksi trafik yubormaydi |
| `/freshness` | ETL ma'lumoti qancha eski | Ogohlantirish |
| `psql` | Baza to'g'ridan-to'g'ri | Ulanish yo'q |

Ularni bittaga qo'shish "**tirik = ishlayapti**" degan yolg'on
berardi: jarayon ko'tarilgan, lekin migratsiya qo'llanmagan holat
**haqiqiy** va u faqat `/ready` da ko'rinadi.

`/ready` **ochiq** (proksi va systemd token ushlab turolmaydi),
lekin javobi **tafsilotsiz**: faqat `ok | ogohlantirish | xato`.
Sabablar server jurnaliga yoziladi.

```bash
deploy/bin/health-check.sh staging
curl -s https://staging.example.uz/api/ready | jq
```

---

## 7. Orqaga qaytarish

```bash
deploy/bin/rollback.sh production --royxat     # mavjud relizlar
deploy/bin/rollback.sh production              # oldingisiga
deploy/bin/rollback.sh production 20260831-...-v1_2_2
```

**Baza migratsiyasi qaytarilmaydi** va bu ataylab:

- Migratsiyalar **qo'shimcha** (additive): yangi ustun eski kodga
  xalaqit bermaydi — eski kod ularni bilmaydi, xolos.
- Avtomatik `down` skript **ma'lumot yo'qotishning eng qisqa yo'li**
  bo'lardi va u aynan falokat paytida ishga tushardi.
- Migratsiya haqiqatan buzuvchi bo'lsa — **zaxiradan** tiklanadi, va
  bu yo'l **har hafta mashq qilinadi**.

---

## 8. Zaxira va tiklash

```bash
systemctl start tenderai-backup@production          # qo'lda
systemctl start tenderai-restore-test@production    # mashq
journalctl -u tenderai-restore-test@production -n 50
```

**Zaxira o'zi yetarli emas.** `backup.sh` uch narsa qiladi: dump
oladi, **darhol `pg_restore --list` bilan ochilishini tekshiradi**
(buzuq faylni haftalab saqlab yurmaslik uchun), va SHA-256 yozadi.
Jadval soni 10 dan kam bo'lsa dump **o'chiriladi** — shubhali.

**Sinalmagan zaxira — zaxira emas.** `restore-test.sh` har hafta:

1. eng oxirgi zaxirani oladi va SHA-256 ni tekshiradi;
2. **vaqtinchalik** bazaga tiklaydi (nom ishlab chiqarish bazasiga
   teng bo'lsa **to'xtaydi**);
3. jadval soni, `tender`/`doc_chunk` qatorlari, migratsiya jurnali va
   **pgvector kengaytmasi** tiklanganini tekshiradi;
4. **tiklash vaqtini o'lchaydi** — bu **RTO** uchun haqiqiy raqam,
   taxmin emas;
5. vaqtinchalik bazani tashlaydi.

> **Hali o'lchanmagan:** RTO raqami faqat mashq birinchi marta
> yurgandan keyin ma'lum bo'ladi. Bu yerda taxminiy raqam
> yozilmaydi.

---

## 9. Jurnal

```bash
journalctl -u tenderai-api@production -f
journalctl -u tenderai-etl@production --since today
journalctl -u tenderai-api@production -o cat | jq 'select(.daraja=="ERROR")'
```

`LOG_FORMAT=json` — bir qator = bir JSON obyekt. Har so'rovda
`sorov_id` bor va u javobning `X-Request-Id` sarlavhasida ham
qaytadi: foydalanuvchi xato haqida aytganda o'sha id bo'yicha
jurnalni topish mumkin.

**Sirlar niqoblanadi** — `password`, `token`, `api_key`, `dsn`,
`cookie` nomli maydonlar `***` bilan almashtiriladi (nom bo'yicha,
mazmun bo'yicha emas: nom bo'yicha aniq, mazmun bo'yicha ehtimolli).

`/health` va `/ready` so'rovlari **yozilmaydi** (faqat xato bo'lganda)
— ular har 30 soniyada keladi va haqiqiy hodisalarni ko'mib
tashlardi.

---

## 10. Ommaviy havolalar `localhost` bo'lmasin

**O'lchangan holat:** bazada `notify_settings.base_url =
'http://localhost:5173'` yozilgan edi (haqiqiy ijarachi uchun).
Bildirishnoma o'chiq bo'lgani uchun buzuq havola hali yuborilmagan.

Endi uch qatlam:

1. `PUBLIC_BASE_URL` — **muhit** o'zgaruvchisi (joylashtirish xossasi).
2. Bazadagi qiymat **mahalliy** bo'lsa va muhitda haqiqiysi bo'lsa —
   **muhit yutadi** (jurnalga ogohlantirish yoziladi).
3. `url_tekshir()` — `APP_ENV != dev` da mahalliy havola bo'lsa
   **yuborishni to'xtatadi**. Jimgina almashtirmaydi: to'g'ri manzil
   noma'lum, taxmin qilish yana bir buzuq havola berardi.

Tekshiruv `card_url()` ichida, ya'ni **uchala ko'rinish** (email
matni, email HTML, Telegram) avtomatik qamrab olinadi.

---

## 11. Kundalik amallar

```bash
systemctl status tenderai-api@production
systemctl list-timers 'tenderai-*'
systemctl restart tenderai-api@production

# ETL ni qo'lda yurgizish
systemctl start tenderai-etl@production

# Migratsiya holati (egasi roli bilan)
sudo -u tenderai /opt/tenderai/production/current/.venv/bin/python \
     /opt/tenderai/production/current/migratsiya.py --holat --dsn "$XT_DB_DSN_OWNER"
```

---

## 12. Hali bajarilmagan (ochiq)

1. **Server hali yo'q.** Bu yerdagi hamma narsa repozitoriyada
   tayyor va sinovdan o'tgan (`_tests/deploy_test.py` 103/103), lekin
   **haqiqiy mashinada yurgizilmagan**. Birinchi `bootstrap.sh` dan
   keyin domen, sertifikat va RTO raqamlari aniqlashadi.
2. **Domenlar namunaviy** (`staging.example.uz`,
   `tender.example.uz`) — `Caddyfile` da almashtirilishi kerak.
3. **Staging `basic_auth` xeshi namunaviy** — `caddy hash-password`
   bilan o'zingiznikini qo'ying.
4. **Zaxira faqat mahalliy diskda.** Tashqi nusxa (S3 yoki boshqa
   mashina) yo'q — disk yo'qolsa zaxira ham yo'qoladi.
5. **Monitoring/ogohlantirish yo'q.** `systemd` xizmatni qayta
   ko'taradi, lekin buni **hech kim bilmaydi**. `OnFailure=` bilan
   xabar yuborish keyingi qadam.
