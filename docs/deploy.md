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

**Majburiy:** `APP_PUBLIC_URL`, `XT_DB_DSN`, `XT_DB_DSN_OWNER`.

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
3. **Muhit fayli o'qiladi** (`/etc/tenderai/<muhit>.env`) va
   `APP_ENV` beriladi — **qurilmadan oldin**, chunki frontend
   qurilmasi ham muhit qiymatlariga muhtoj (§10)
4. `frontend/.env.production` yoziladi → `npm ci && npm run build`
   → `frontend/dist`, so'ng **qurilmada mahalliy manzil bor-yo'qligi
   tekshiriladi** (topilsa to'xtaydi)
5. **Migratsiya** (egasi roli bilan)
6. `ln -sfn` → `current` (**atomar**)
7. `systemctl restart tenderai-api@<muhit>` + timer'lar
8. **Sog'liq tekshiruvi** — o'tmasa **avtomatik orqaga qaytariladi**
9. Eski relizlar: oxirgi 5 tasi qoladi

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

**Yagona manba: `api/ommaviy_url.py`.** Qabul qiluvchi bosadigan
har qanday havola shu moduldan quriladi.

### Muhit o'zgaruvchisi

| Nom | Holat |
|---|---|
| `APP_PUBLIC_URL` | **asosiy** |
| `PUBLIC_BASE_URL` | eski (ishlaydi, ogohlantirish yozadi) |

Ikkalasi ham berilib, qiymatlari **boshqa** bo'lsa — xizmat ishga
tushmaydi. "Qaysi biri to'g'ri" degan savolga taxmin bilan javob
berish ikkita haqiqat manbai demak.

`localhost` ga ruxsat **faqat** `APP_ENV=dev` da. Alohida "ruxsat
bayrog'i" ataylab qo'shilmadi: uni ishlab chiqarishga ham yozib
qo'yish mumkin bo'lardi va qo'riqchi o'z-o'zini o'chirardi.

### To'rt qatlam

1. **Ishga tushish** — `ommaviy_url.ishga_tushishda_tekshir()`
   `api/main.py` dagi `lifespan` da va `notify_new.py` da (ETL
   yuborish yo'li). `staging`/`production` da manzil berilmagan
   yoki mahalliy bo'lsa **xizmat ko'tarilmaydi**.
2. **Tanlash** — bazadagi ijarachi qiymati mahalliy bo'lsa va
   muhitda haqiqiysi bo'lsa, **muhit yutadi** (ogohlantirish bilan).
3. **Qurish** — `ommaviy_url.havola()` yagona quruvchi. Email
   matni, email HTML va Telegram uchalasi shundan o'tadi, ya'ni
   yangi kanal qo'shilganda tekshiruvni unutib bo'lmaydi.
4. **Yozish** — sozlama shaklida **aniq berilgan** mahalliy qiymat
   `dev` dan boshqa muhitda rad etiladi. Jimgina almashtirilmaydi:
   "saqladim" deb ko'rsatib boshqa narsani saqlash yolg'on bo'lardi.

### Frontend qurilmasi (o'lchangan nosozlik)

Reliz `git archive` bilan yasaladi, `frontend/.env` esa
kuzatilmagan fayl — u **relizga tushmaydi**. Shu sababli qurilma
`VITE_API_BASE` siz yurardi va zaxira qiymat singib qolardi:

```
dist/assets/index-*.js:  localhost:8000  x1   butun API
dist/assets/index-*.js:  localhost:5173  x3   sozlama shakli
```

Ya'ni ishlab chiqarish sahifasidagi **har so'rov** foydalanuvchi
brauzerida `localhost:8000` ga ketardi va qurilma muvaffaqiyatli
tugardi.

Endi uch qatlam:

1. Manbada qotirilgan mahalliy manzil **yo'q** (`VITE_API_BASE`
   zaxirasi `/api` — same-origin, cookie shuni talab qiladi).
2. `deploy.sh` muhit faylidan `frontend/.env.production` ni
   **yozadi** va `APP_ENV` ni beradi.
3. `vite.config.ts` dagi qo'rovul plagin `staging`/`production` da
   sozlama yaroqsiz bo'lsa **qurilmani to'xtatadi**; `deploy.sh`
   esa qurilma natijasini `grep` bilan tekshiradi.

> `VITE_*` qiymatlari ta'rifi bo'yicha brauzerga tushadi — ular
> **ommaviy**. Sir hech qachon `VITE_` prefiksi bilan berilmasin.

### Sinov

`_tests/ommaviy_url_test.py` — 96 tekshiruv (`dev`/`staging`/
`production` xulqi, eski nom va ziddiyat, uchala kanalning ayni
havolasi, frontend manbasi va qurilma qo'rovuli).

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

---

## 12b. TASHQI NUSXA — bitta disk yetarli emas (O-2)

`backup.sh` zaxirani **mahalliy** diskka yozadi. Disk yo'qolsa
(yoki shifrlovchi dastur tegsa) **zaxira ham u bilan ketadi**.

`BACKUP_REMOTE_CMD` — **buyruq shabloni**, manzil emas:

```bash
BACKUP_REMOTE_CMD='rclone copy {fayl} uzoq:tenderai/'
BACKUP_REMOTE_CMD='aws s3 cp {fayl} s3://chelak/tenderai/'
BACKUP_REMOTE_CMD='rsync -a {fayl} zaxira@host:/srv/tenderai/'
```

**Nega shablon, manzil emas:** nusxalash usuli har joyda boshqacha.
Manzilga qarab usulni taxmin qilish **noto'g'ri buyruqni jimgina
yurgizardi**.

| Holat | Xulq |
|---|---|
| Sozlanmagan | **ogohlantirish** yoziladi, zaxira davom etadi |
| Sozlangan, muvaffaqiyatli | dump **va** `.sha256` yuboriladi |
| Sozlangan, **yiqildi** | skript **exit 1** — "zaxira bor" yolg'on xulosa bo'lmasin |

**Tartib muhim:** tashqi nusxa **tozalashdan oldin**. Aks holda
mahalliy fayl o'chirilib, uzoqqa hech narsa ketmagan bo'lishi
mumkin edi.

Uchala yo'l ham **mashq qilib ko'rildi** (2026-09-01).

> **Halol cheklov:** tashqi nusxaning tiklanishi hali sinalmagan.
> `restore-test.sh` **mahalliy** fayldan tiklaydi; uzoqdagi nusxa
> o'qilishini alohida tekshirish kerak.

---

## 13. MASHQ — skriptlar HAQIQATAN yurgizildi (B-1)

**O'lchov: 2026-09-01.** Joylashtirish skriptlari shu paytgacha
**hech qachon, hech qayerda bajarilmagan** edi — ular faqat
`deploy_test` da **matn** sifatida tekshirilardi. Mashq
o'tkazildi va u **birinchi qadamdayoq haqiqiy nuqson topdi**.

### 13.1 Topilgan nuqson: bitta fayl, ikki parser

`XT_DB_DSN` muhit namunasida **tirnoqsiz** edi:

```
XT_DB_DSN=dbname=tenderai_production user=tai_service password=REPLACE host=127.0.0.1 port=5432
```

| O'quvchi | Natija |
|---|---|
| systemd `EnvironmentFile=` | butun qatorni oladi — **to'g'ri** |
| shell `. envfile` | birinchi bo'shliqda **kesadi** |

Ya'ni API xizmati to'g'ri DSN olardi, `backup.sh` /
`restore-test.sh` / `deploy.sh` esa `dbname=tenderai_production`
ni — **user, parol va host yo'qolgan holda**. Qolgani
(`user=...`, `password=...`) shellda **o'zgaruvchi tayinlash**
bo'lib ketardi, ya'ni **xato ham bermasdi**.

Tuzatildi: qiymatlar tirnoqqa olindi. `deploy_test` buni
`shlex` bilan (POSIX so'z ajratish qoidasi) qo'riqlaydi.

### 13.2 Topilgan nuqson: `XT_DB_DSN_OWNER` namunada YO'Q edi

`deploy.sh` va `restore-test.sh` uni **talab qiladi** (`:?`) va
`docs/deploy.md` §3 uni **majburiy** deb yozadi — lekin
namunada u yo'q edi. Namunaga qarab tayyorlangan server
birinchi joylashtirishda to'xtardi. Qo'shildi.

### 13.3 O'lchangan raqamlar

Mashq **haqiqiy 1.5 GB baza** ustida yurgizildi:

| Amal | Natija |
|---|---|
| `backup.sh` | **5 daq 28 s** · dump **440 MB** · 74 jadval · SHA-256 yozildi |
| `restore-test.sh` | **RTO = 405 s (6 daq 45 s)** |
| Tiklashdan keyin tekshiruv | jadval 53 · tender 3 608 · bo'lak 189 787 · migratsiya 67 · pgvector **bor** |
| Vaqtinchalik baza | **tashlandi** (nom qo'riqchisi ishladi) |

> **RTO endi o'lchangan raqam** — O-1 shu bilan yopildi. Taxminiy
> qiymat hech qachon yozilmagan edi va bu to'g'ri edi.

### 13.4 Qanday mashq qilinadi

Skriptlar muhit faylini `/etc/tenderai/<muhit>.env` dan o'qiydi.
Mashq uchun yo'l **almashtiriladi**:

```bash
export TENDERAI_ENVFILE=/tmp/mashq.env
export PATH="/usr/lib/postgresql/18/bin:$PATH"   # Windows'da PostgreSQL/18/bin
bash deploy/bin/backup.sh mashq
bash deploy/bin/restore-test.sh mashq
```

`mashq.env` da `XT_DB_DSN`, `XT_DB_DSN_OWNER`, `BACKUP_DIR`
bo'lishi yetadi. `restore-test.sh` **vaqtinchalik** bazaga
tiklaydi va nomi asosiy baza bilan bir xil bo'lsa **to'xtaydi**.

### 13.5 HALI MASHQ QILINMAGANI

Rostini aytish kerak — quyidagilar **hali ham bajarilmagan**:

| Qism | Nega |
|---|---|
| `deploy.sh` to'liq | `systemd`, `sudo`, `git archive` reliz repozitoriysi kerak |
| `rollback.sh` | `current` simvolik havolasi va systemd kerak |
| `health-check.sh` | ishlab turgan xizmat va reverse-proxy kerak |
| Caddy / HTTPS | domen va sertifikat kerak |
| systemd taymerlar | Linux kerak |

Ya'ni **B-1 yopilmadi, qisqardi**: zaxira va tiklash yo'li
sinaldi, qolgan qism hali noma'lum.
