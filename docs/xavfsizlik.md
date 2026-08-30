# Ishlab chiqarish xavfsizligi — tahdid modeli, topilmalar, nazoratlar

**Sana:** 2026-08-31 · **Ko'lam:** `api/`, `frontend/`, baza, bog'liqliklar, git tarixi

> **Qoida:** bu hujjat nazoratni FAQAT u kodda yoki sozlamada
> TEKSHIRILGAN bo'lsa "bor" deydi. Tekshirilmagani "tavsiya" bo'limida
> turadi. §7 ikkalasini ATAYLAB ajratadi.

---

## 1. Tahdid modeli

### 1.1 Nimani himoya qilamiz

| Aktiv | Nega qimmat |
|---|---|
| Ijarachi katalogi, narxlari, malaka hujjatlari | Raqobat siri — raqib ko'rsa taklif narxini biladi |
| Kompaniya sessiyasi | Butun ijarachiga kirish |
| Inson qarorlari + audit jurnali | Javobgarlik izi; qayta yozilsa "kim qildi" savoli javobsiz qoladi |
| ERP domeni (`erp.*`) | Boshqa tizimning ma'lumoti; shartnoma bo'yicha faqat o'qiladi |
| `ANTHROPIC_API_KEY`, SMTP, Telegram tokeni, DSN | To'g'ridan-to'g'ri pul va kirish |

### 1.2 Hujumchi modellari

| # | Kim | Imkoniyati | Maqsadi |
|---|---|---|---|
| A1 | Autentifikatsiyasiz internet | HTTP so'rovlar | Ma'lumot olish, DoS |
| A2 | **Boshqa ijarachi** (haqiqiy hisob) | To'liq API | Raqib katalogi/narxi |
| A3 | Ijarachi ichidagi past huquqli odam | Sessiya | Ruxsatsiz tasdiq, audit tozalash |
| A4 | **Hujjat/korpus mazmuni** (prompt injection) | AI kontekstiga matn kiritish | Model orqali begona ma'lumot chiqarish |
| A5 | Yuklangan fayl | `.xlsx`/`.csv` | DoS (zip bomba), parser xatosi |
| A6 | Bog'liqlik zanjiri | npm/PyPI paketi | Kod bajarish |
| A7 | Baza ichidagi hujumchi (SQLi orqali) | SQL | Huquqni oshirish |

### 1.3 Ishonch chegaralari

```
  internet ──▶ [gate: standart YOPIQ] ──▶ FastAPI ──▶ PostgreSQL
                     │                                   │
                     └─ X-Service-Key (ERP)              └─ erp.* (FAQAT view)
  hujjat/korpus ──▶ AI konteksti ──▶ tool (9 ta, FAQAT O'QIYDI)
```

---

## 2. Topilmalar — darajalangan

| # | Daraja | Topilma | Holat |
|---|---|---|---|
| C-1 | **Critical** | Ilova bazaga `postgres` SUPERUSER (`bypassrls=true`) sifatida ulanadi | **Repozitoriyda hal qilindi**, DSN almashtirish operatorda (§4) |
| H-2 | **High** | Javoblarda BIRORTA xavfsizlik sarlavhasi yo'q | **Tuzatildi** |
| H-3 | **High** | Yuklangan fayl BUTUNLAY xotiraga o'qiladi, chegara KEYIN tekshiriladi (3 endpoint) | **Tuzatildi** |
| H-4 | **High** | `.xlsx` zip bombasidan himoya yo'q | **Tuzatildi** |
| H-5 | **High** | `/docs`, `/openapi.json`, `/redoc` ochiq — butun API yuzasi | **Tuzatildi** (standart yopiq) |
| H-6 | **High** | `api/erp_stock.py` `erp.stock_move` **jadvalini** o'qiydi — o'z shartnomasini buzadi | **Tuzatildi** (view ga o'tkazildi) |
| M-6 | Medium | PBKDF2 240 000 iteratsiya (OWASP: 600 000) | **Tuzatildi** + shaffof qayta xeshlash |
| M-7 | Medium | Baza xatosi tafsiloti (host/port/user) mijozga qaytadi | **Tuzatildi** |
| M-8 | Medium | npm: 4 zaiflik (2 high) — `vite` ostida | **Tuzatildi** (vite 5 → 8, `npm audit` = 0) |
| M-9 | Medium | Vite dev-server `host: true` (0.0.0.0) + ngrok | Yumshatildi (§6), sozlama qarori |
| L-10 | Low | `/auth/logout` CSRF dan ozod | Qabul qilindi (§5) |
| L-11 | Low | `CORS_ORIGINS=*` sozlash mumkin | Ta'siri cheklangan (§5) |
| L-12 | Low | Sessiya 14 kun, bo'sh turish chegarasi yo'q | Tavsiya (§7) |

---

## 3. C-1 — nega Critical edi

O'lchandi (2026-08-31):

```
current_user = postgres
rolsuper = true   rolcreatedb = true   rolcreaterole = true   rolbypassrls = true
```

Uchta aniq oqibat:

1. **SQL inyeksiyasi to'liq egallash bo'lardi.** Hozir SQL parametrlangan
   (tekshirildi: `ORDER BY` oq ro'yxat bilan, qolgan interpolatsiyalar
   konstanta ustun ro'yxatlari), lekin bitta kelajakdagi xato butun
   klasterni ochib berardi.
2. **Audit qulfi ilovaning o'zi tomonidan yechilardi.** `audit_jurnal`
   append-only bo'lishi triggerga tayanadi; superuser esa
   `DROP TRIGGER` qila oladi.
3. **ERP chegarasi faqat sinov bilan himoyalangan edi.**
   `_tests/auth_test.py` KEYIN aytadi; huquq esa OLDIN to'sadi.

### Nima qilindi

`schema_patch_huquq.sql` — `tai_app` roli (LOGIN**siz** guruh, parol
repozitoriyaga tushmaydi):

- `public` da CRUD, lekin `CREATE` **yo'q** (sxemani o'zgartira olmaydi)
- `audit_jurnal` da `UPDATE`/`DELETE`/`TRUNCATE` **yo'q** (trigger ustiga
  ikkinchi qatlam)
- `erp.*` dan **faqat** `v_tender_status`, `v_stock_balance`,
  `v_tai_actor` — ya'ni chegara endi **huquq bilan** qulflangan
- `NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOREPLICATION`

### Empirik tekshiruv (haqiqiy ulanish bilan, 13/13)

| Amal | Natija |
|---|---|
| `public` dan o'qish / yozish | ruxsat |
| `erp.app_user` o'qish / yozish | **rad etildi** |
| `erp.opportunity` o'qish | **rad etildi** |
| `erp.v_tender_status` o'qish | ruxsat |
| `audit_jurnal` INSERT | ruxsat |
| `audit_jurnal` UPDATE / DELETE | **rad etildi** |
| audit triggerini o'chirish / tashlash | **rad etildi** |
| `CREATE TABLE` / `DROP TABLE` | **rad etildi** |

**To'liq sinov to'plami shu rol bilan yurgizildi: 24/24 o'tdi.** Ya'ni
almashtirish ilovani buzmaydi — bu tekshirilgan, taxmin emas.

---

## 4. Operator qadami — DSN almashtirish

Repozitoriya parolni saqlay olmaydi, shuning uchun bu qadam **kodda emas**:

```sql
-- Bazada (bir marta):
CREATE ROLE tai_service LOGIN PASSWORD '<kuchli tasodifiy parol>';
GRANT tai_app TO tai_service;
```

```ini
# .env
XT_DB_DSN=dbname=xtxarid user=tai_service password=<parol> host=localhost port=5432
```

**Migratsiyalar boshqa rol bilan.** `tai_app` da DDL yo'q va bu ataylab:

```powershell
$env:XT_DB_DSN_OWNER = "... user=postgres ..."
.venv\Scripts\python.exe migratsiya.py --qolla --dsn $env:XT_DB_DSN_OWNER
```

Tekshirish:

```sql
SELECT * FROM v_huquq_tekshiruv;   -- `qiymat <> kutilgan` qatori BO'LMASIN
```

`_tests/xavfsizlik_test.py` almashtirilmaguncha **ogohlantirish** chiqaradi
(sinov yiqilmaydi — rol tayyor, DSN esa infratuzilma qarori).

### ERP tomonidan kutilayotgan ish

`api/erp_stock.py` "ombor ishga tushganmi" belgisini endi
`erp.v_stock_balance` dan oladi (ilgari `erp.stock_move` **jadvalini**
o'qirdi — shartnoma buzilishi, H-6). To'g'ri yechim: ERP shu belgini
view da chop etsin (`ombor_faol` maydoni yoki alohida view).

---

## 5. Tekshirilgan nazoratlar (kodda tasdiqlangan)

### AUTH

| Nazorat | Qayerda tasdiqlandi |
|---|---|
| PBKDF2-HMAC-SHA256, **600 000** iteratsiya, 16 baytli tasodifiy tuz | `auth.ITERATIONS`, `hash_password()` |
| Doimiy vaqtli solishtirish | `hmac.compare_digest` (parol, CSRF, service kalit) |
| Eski xesh kirish paytida **shaffof ko'chiriladi** | `_rehash_kerakmi()` + `login()` |
| Sessiya tokeni 32 bayt (`secrets`), bazada **faqat SHA-256** | `login()`, `_token_hash()` |
| **Session fixation yo'q** — token har kirishda serverda yasaladi, mijozdan olinmaydi | `login()` |
| Parol almashsa **qolgan sessiyalar o'chadi** | `SESSION_KILL_OTHERS_SQL` |
| Chiqishda sessiya bazadan o'chadi | `logout()` |
| Brute-force: login+IP uchun 5, IP uchun 25 / 15 daq; **xeshlashdan OLDIN** | `guard_attempts()` |
| Hisob yo'q bo'lsa ham xesh hisoblanadi (vaqt bo'yicha sizish yo'q) | `login()` |
| Cookie: `HttpOnly` (sessiya), `Secure` (standart **yoqiq**), `SameSite=Lax` | `_set_auth_cookies()` |
| CSRF: ikki tomonlama token, faqat cookie yo'lida, `compare_digest` | `gate()` |
| Darvoza **standart yopiq**, ochiq yo'llar 8 ta va sanoqli | `PUBLIC_PATHS` |
| Service kaliti oq ro'yxat bilan cheklangan, sozlanmasa **har doim False** | `SERVICE_PATHS`, `verify_service()` |

### HTTP

| Sarlavha | Qiymat |
|---|---|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Content-Security-Policy` | `default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'; sandbox` |
| `Referrer-Policy` | `no-referrer` |
| `Permissions-Policy` | kamera/mikrofon/geolokatsiya va h.k. o'chirilgan |
| `Cross-Origin-Opener-Policy` / `-Resource-Policy` | `same-origin` |

`/docs` yoqilganda unga CSP **qo'yilmaydi** — aks holda Swagger buzilib,
"CSP bor" degan yolg'on taassurot qolardi.

**CORS:** `allow_credentials` **qo'yilmagan** (standart `False`) — ya'ni
cookie'lar saytlararo yuborilmaydi va autentifikatsiya faqat same-origin
ishlaydi. `CORS_ORIGINS=*` sozlansa ham kirish ma'lumoti oqmaydi (L-11).

### SQL / ijarachi izolyatsiyasi

- Barcha so'rovlar parametrlangan; `ORDER BY` **oq ro'yxat** orqali
  (`_SORT_WHITELIST`), inyeksiya urinishlari sinovda tekshirilgan.
- `company_id` har so'rov shartida; `tender_requirement`, `tender_routing`,
  `kod_qaror` da `(company_id, actor_id)` **kompozit FK** — boshqa
  ijarachining aktorini yozish jismonan mumkin emas (`docs/erp_kimlik.md`).
- `audit_jurnal` append-only: trigger + huquq (ikki qatlam).

### AI (A4 — prompt injection)

- **`company_id` HECH BIR tool sxemasida yo'q** — 9 tadan 9 tasida
  tekshirilgan. Ijarachi kontekstdan (`ChatContext`) keladi, model uni
  o'zgartira olmaydi. Bu **arxitekturaviy** himoya; prompt himoyasi
  ehtimolli bo'lardi.
- **9 ta tool ham FAQAT O'QIYDI** — manba tahlili bilan tekshirilgan
  (`INSERT`/`UPDATE`/`DELETE` yo'q). Ya'ni hujjat ichidagi injection
  eng ko'pi bilan **o'sha ijarachining o'z ma'lumotini** o'qitadi.
- Pullik model chaqiruvlari `AI_PAID_ENABLED` bilan qulflangan
  (standart o'chiq) va `ai_quota` bilan cheklangan.

### FAYLLAR

- Yuklash chegarasi **5 MB**, bo'laklab o'qiladi va oshgan zahoti 413.
- Zip bomba: ochilgan hajm > 80 MB yoki nisbat > 200:1 → rad
  (sinovda 298 KB → 300 MB bomba **rad etildi**, haqiqiy `.xlsx` o'tdi).
- `/documents/.../download` — yuqori oqim fayli `Content-Disposition:
  attachment` bilan uzatiladi (inline render qilinmaydi) + `nosniff`.
- Fayl tizimida yo'l traversiyasi **yo'q**: yuklab olish DB dagi
  `file_ref`/`file_path` bo'yicha ishlaydi, yuqori oqim manzili esa
  qat'iy xaritadan.

### SIRLAR

- `.env`, `frontend/.env`, `ngrok.yml` — **kuzatilmaydi** (tekshirildi).
- **Git tarixi tozalandi deb tekshirildi:** 112 442 ta qo'shilgan satr
  skanerlandi (`sk-ant-`, Telegram tokeni, AWS, shaxsiy kalit, parolli
  DSN) — **haqiqiy sir topilmadi**; faqat sinov fixture parollari
  (`zzSinov12345`) va parametr nomlari.
- Loglarda sir yo'q (`api.*.log`, `etl_cron.log` tekshirildi).
- Kod DSN/token/kalitni **loglamaydi**.
- Kuzatilgan 363 faylda sir naqshi yo'q — regressiya sinovi bilan
  qo'riqlanadi.

### BOG'LIQLIKLAR

- `npm audit` → **0 zaiflik** (vite 5 → 8 yangilandi; `npm run build`
  va `tsc -b` o'tadi).
- Python paketlari yangi (`fastapi 0.140`, `starlette 1.3.1`,
  `urllib3 2.7`, `requests 2.34`, `certifi 2026.7`).

> **Halol cheklov:** `pip-audit` bu muhitda o'rnatilmagan va PyPI
> maslahat bazasiga so'rov yuborilmadi. Ya'ni Python bog'liqliklari
> **versiya bo'yicha yangi** deb tasdiqlandi, lekin **CVE bo'yicha
> tekshirilmadi**. Buni CI ga qo'shish — §7.

---

## 6. Infratuzilma talab qiladigan nazoratlar (kodda emas)

| Nazorat | Nega kodda emas | Nima qilish |
|---|---|---|
| **TLS / HTTPS** | Sertifikat va terminator server tomonida | nginx/Caddy; `AUTH_COOKIE_SECURE=1` allaqachon standart |
| **HSTS** | Yoqish domenni HTTPS ga **qulflaydi**; TLS'siz saytni yo'q qiladi | TLS tayyor bo'lgach `HSTS_MAX_AGE=31536000` yoki terminatorda |
| **So'rov tanasi chegarasi** | Ilova baytni ko'rgunicha tarmoq qatlami to'sishi kerak | nginx `client_max_body_size 8m;` |
| **Tezlik cheklovi (login'dan tashqari)** | Ilova darajasida holat kerak | nginx `limit_req` yoki Cloudflare |
| **Zaxira va tiklash** | Bu ilovaning vazifasi emas | `pg_dump` jadval bo'yicha; **tiklash muntazam MASHQ qilinsin** — sinalmagan zaxira zaxira emas |
| **Vite dev-server** | `host: true` (0.0.0.0) + ngrok | Ishlab chiqarishda `npm run build` + statik host; dev-serverni tunnelga **chiqarmang** |
| **Sirlarni aylantirish** | Kalitlar `.env` da | `ANTHROPIC_API_KEY`, `ERP_SERVICE_KEY`, SMTP, Telegram — muntazam almashtirish |
| **`TRUST_PROXY`** | Proksi ortida IP `X-Forwarded-For` dan | Proksi ortida **1**, aks holda **0** (standart 0 — to'g'ri) |

---

## 7. Tavsiyalar (bajarilmagan — ATAYLAB ajratilgan)

1. **`pip-audit` ni CI ga qo'shish.** Hozir Python bog'liqliklari CVE
   bo'yicha tekshirilmagan (yuqorida ochiq yozildi).
2. **Sessiya bo'sh turish chegarasi** (L-12). Hozir 14 kun mutlaq;
   `last_seen_at` bor, ya'ni amalga oshirish oson.
3. **`aktor_majburiy` ni yoqish** — inson qarorlari haqiqiy odamga
   bog'lansin (`docs/erp_kimlik.md` §10).
4. **`/auth/logout` uchun CSRF** (L-10). Hozir ozod: majburiy chiqarish
   hujumi bezovta qiladi, lekin ma'lumot oshkor qilmaydi.
5. **Content-Type oq ro'yxati** yuklashda (hozir kengaytma + ZIP imzosi
   bo'yicha aniqlanadi).
6. **Row-Level Security (RLS)** — kompozit FK ijarachini yozishda
   qulflaydi; RLS o'qishda ham qulflardi. Katta o'zgarish, alohida ish.

---

## 8. Tekshirilgan holat

`_tests/xavfsizlik_test.py` — **95/95** (offline) / **105/105** (baza bilan).
To'liq to'plam: **24/24**, chiqish kodi 0.

Sinov **teatrdan qochadi**: sarlavhalar haqiqiy javobdan o'qiladi, parol
xeshi haqiqatan hisoblanadi, zip bomba haqiqatan yasaladi. Manbadan
o'qish faqat kodning **o'zi qoida** bo'lgan joyda ishlatiladi (masalan
"tool sxemasida `company_id` yo'q").
