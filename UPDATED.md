# Tender AI — BAJARILGAN ISHLAR

**Loyiha:** O'zbekiston davlat xaridlari agregatori va broker yordamchisi
**Holat sanasi:** 2026-08-02 · **Asos:** `тз.docx` (PRD/TZ v0.1, MVP), `REJA.md`, `REJA_UX.md`

Bu fayl — **nima qurilgani** ro'yxati. Reja hujjatlari (`REJA.md`, `REJA_UX.md`)
nima qilish kerakligini aytadi; bu yerda esa AYNAN NIMA ISHLAYAPTI, qayerда va
qanday tekshirilgani yozilgan.

---

## 0. Bir qarashda

```
2 platforma → ETL (soatlik) → PostgreSQL → FastAPI (54 endpoint) → React dashboard
                   ↓                            ↓                        ↓
              etl_run jurnali            AI qatlami (Claude)      3 til (uz/ru/en)
                   ↓                            ↓
            bildirishnoma  ←──────  moslik balli (katalog + profil)
          (email + Telegram, platforma tilida)
```

| O'lchov | Qiymat |
|---|---|
| Manbalar | 2 ta (`xt-xarid.uz`, `etender.uzex.uz`) |
| Bazadagi tenderlar | 1 125 ta (uzex 719, xt-xarid 406), shundan **378 tasi ochiq** |
| Lotlar / pozitsiyalar | 1 139 / 4 478 |
| Hujjatlar (metadata + havola) | 4 466 ta |
| Matni ajratilgan hujjatlar | 253 ta `ok`, 44 `unreadable`, 58 `unsupported`, 2 `too_large` |
| Kategoriya bog'lanishlari | 1 408 ta |
| API endpointlari | 54 ta |
| Backend modullari | 18 ta (`api/*.py`) |
| Frontend komponentlari | 28 ta (`.tsx`) |
| Baza patchlari | 22 ta (idempotent `schema_patch_*.sql`) |
| Avtomatlashtirilgan sinovlar | 81 ta test funksiya, 6 ta to'plam |
| Tarjima kalitlari | ~560 ta × 3 til |

---

## 1. Ma'lumot yig'ish (ETL) — P0-1

| Skript | Nima qiladi |
|---|---|
| `etl_tenders.py` | xt-xarid.uz ochiq reyestrlari (`ref_tender_public`, `ref_selection_public`) |
| `etl_details.py` | Tender tafsiloti va biriktirilgan hujjatlar ro'yxati |
| `etl_lots.py` | Lot nomlari, pozitsiya xususiyatlari, yetkazish/kafolat muddatlari |
| `etl_dims.py` | `dim_status`, `dim_area` — status va hudud taksonomiyasi |
| `etl_uzex.py` | etender.uzex.uz adapteri (2-manba), bir xil sxemaga keltiradi |
| `etl_doc_text.py` | Hujjatlardan MATN ajratish (PDF / DOCX / XLSX / ZIP) |
| `etl_categorize.py` | Tenderlarni yagona kategoriyaga bog'lash (deterministik, AI'siz) |
| `etl_ai_summary.py` | AI xulosa + kategoriya normalizatsiyasi (kalit bo'lganda) |
| `run_etl.py` | **Orkestrator** — hamma manbani yurgizadi, `etl_run` jurnaliga yozadi |

**Bajarilgan talablar:**
- Har platforma bir nechta reyestr chop etadi — hammasi yig'iladi (bittasini olish
  ochiq lotlarning katta qismini yo'qotardi).
- `etl_run` jadvali: har yurishning boshlanishi, tugashi, holati, topilgan/yangi soni.
  Hozircha **24 ta muvaffaqiyatli yurish** qayd etilgan (uzex 12, xt-xarid 12).
- `tender.first_seen_at` — biz tenderni birinchi qachon ko'rganimiz. Bildirishnoma
  aynan shu ustunga tayanadi.
- Lotin/kirill farqi (`api/translit.py`): profilга "nasos" yozilsa "Насос" ham topiladi.
- **Soatlik jadval:** `register_task.ps1` (Windows), `com.birja.etl.plist` (macOS),
  `run_etl.sh` (cron). Batafsil — `AVTOMATLASHTIRISH.md`.

**Nazorat:** `_tests/etl_coverage_test.py` (5 ta test) — qamrov yo'qolmaganini tekshiradi.

---

## 2. Hujjat matni — P0-2

- `tender_document_text` jadvali: `ok | unreadable | unsupported | too_large`.
- O'qib bo'lmagan fayl **jimgina tashlab ketilmaydi** — holat bilan belgilanadi va
  interfeysда "qo'lda tekshirish kerak" bo'lib ko'rinadi (TZ chegaraviy holati).
- Skanerlangan PDF uchun OCR MVP da yo'q — `unreadable` bo'lib qoladi.
- Interfeys: `DocumentText.tsx` — matnni kartochka ichida ochib o'qish.

**Nazorat:** `_tests/doctext_test.py` (5 ta test) · Hujjat: `docs/integration/doctext.md`

---

## 3. AI qatlami (Claude)

| Modul | Vazifasi |
|---|---|
| `api/ai.py` | Tender xulosasi + kanonik kategoriya teglari (5a) |
| `api/ai_docs.py` | **Biriktirilgan hujjat matnini** AI tahliliga qo'shish — AI endi faqat kartochkani emas, hujjat ichini ham ko'radi |
| `api/ai_match.py` | "Bu tender sizga mos keladimi?" — profil/katalog bo'yicha tahlil |
| `api/ai_gonogo.py` | **GO / NO-GO tavsiyasi** — 11 mezon bo'yicha uchta qarordan biri |

Qaror **har doim odamniki**: AI tavsiya beradi, sabablarini ko'rsatadi, tanlovni
foydalanuvchi qiladi. Interfeys: `AiMatch.tsx`, `GoNoGo.tsx`, `AiDocsNote.tsx`.

---

## 4. Katalog va ombor — P0-4, P0-6

- **Excel/CSV import** (`api/importer.py`): shablon yuklab olish, **qator bo'yicha xato
  ko'rsatish** (TZ talabi — qaysi qatorда, qaysi ustunда, nima xato).
- `catalog_product`: nom, kategoriya, kalit so'zlar, qoldiq, tannarx, `notify` bayrog'i.
- **Ombor tekshiruvi** (`api/stock.py`): tender pozitsiyalari ↔ qoldiq; yetishmayotganlar
  alohida ko'rsatiladi.
- Interfeys: `CatalogView.tsx`, `CatalogImport.tsx`, `StockCheck.tsx`.

**Nazorat:** `_tests/import_test.py` (11 ta test) · Hujjat: `docs/integration/import.md`

---

## 5. Moslashtirish (matching)

Ikki mustaqil manba, **kattasi olinadi** — biri bo'sh bo'lsa ikkinchisi ishlaydi:

| Manba | Shkala |
|---|---|
| **Katalog** (`/catalog/match`) | kategoriya mosligi = 100, faqat nom/kalit so'z = 70 |
| **Profil** (`api/matching.py`) | kalit so'z 60 + hudud 20 + byudjet 15 + valyuta 5 = 0–100 |

- Ball **shaffof**: har komponentning hissasi (`breakdown`) va o'qiladigan sabablar
  (`reasons`) qaytadi — foydalanuvchi "nega bu tender?" degan savolga javob oladi.
- Sabablar endi **struktura** (`reason_keys`) sifatida ham qaytadi — shu tufayli
  bildirishnoma ularni istalgan tilda qayta chizadi.
- Saqlangan qidiruvlar (`saved_search`): bir nechta filtr to'plami, har birida mos
  tenderlar soni.

---

## 6. Narx hisobi — P0-7

- `api/pricing.py`: tannarx + logistika + xavf zaxirasi + ustama + QQS → tavsiya narx.
- Formula **ko'rinadi va tahrirlanadi**; parametr o'zgarsa sahifa qayta yuklanmasdan
  qayta hisoblanadi (`PricingPanel.tsx`, `frontend/src/pricing.ts`).
- Standart parametrlar `pricing_settings` da, har tender uchun hisob `tender_pricing` da.

**Nazorat:** `_tests/pricing_test.py` (26 ta test) · Hujjat: `docs/integration/pricing.md`

---

## 7. Hujjatlar cheklisti — P0-8

- `api/compliance.py`: tender talablaridan kelib chiqadigan hujjatlar ro'yxati
  ↔ `company_document` (kompaniya hujjatlar bazasi) → **bor / yo'q / muddati o'tgan**.
- Hujjat turlari shabloni, Excel import, muddat kuzatuvi.
- Interfeys: `CompliancePanel.tsx`, `CompanyDocuments.tsx`, `DocumentTemplate.tsx`.

**Nazorat:** `_tests/compliance_test.py` (5 ta test) · Hujjat: `docs/integration/compliance.md`

---

## 8. Bildirishnoma — P0-10

**Ikki kanal, bitta mantiq:** nomzodlar bir marta hisoblanadi, so'ng har kanal
o'z jurnali (`notify_sent.kind`) bo'yicha filtrlanadi.

| Kanal | Yoqish | Manzil |
|---|---|---|
| **Email** | `notify_settings.enabled` | foydalanuvchi emaili yoki kompaniya profilidan |
| **Telegram** | `notify_settings.telegram_enabled` | `/start` bosgan obunachilar |

**Qabul qilish mezonlari (TZ):**
- ✅ Soatlik kuzatish tsikli davomida keladi — `first_seen_at` oxirgi `etl_run` tsiklidan keyin.
- ✅ Xabarда **tizimdagi kartochkaga havola** — email matni, email HTML va Telegram
  versiyalarida (`?tender=<id>` → drawer ochiladi).
- ✅ Takrorlanmaydi — `notify_sent` PK `(tender_id, kind)`.

**Telegramni ulash — bir martalik havola:** platforma token yaratadi
(`https://t.me/<bot>?start=<token>`), foydalanuvchi bosadi, bot tokenli xabarni
oladi va **aynan o'sha suhbat** obunachi bo'ladi. Tokensiz `/start` bosgan begona
odam obunachi BO'LMAYDI — bu xavfsizlik mezoni sinov bilan qulflangan.

**Sirlar bazada emas:** `SMTP_PASSWORD` va `TELEGRAM_BOT_TOKEN` faqat `.env` da.
Yo'q bo'lsa tizim **aniq xato** beradi, jimgina "yuborildi" demaydi.

**Nazorat:** `_tests/notify_test.py` (29 ta test — soxta SMTP va soxta Bot API, haqiqiy
xabar yuborilmaydi) · Hujjat: `docs/integration/notify.md`, `notify_telegram.md`

---

## 9. Ko'p tillilik — interfeys VA bildirishnoma

**Interfeys** (`frontend/src/i18n.tsx`): uz / ru / en, kutubxonasiz (~60 qator).
To'liqlik **tur tizimida kafolatlangan**: o'zbekchaga kalit qo'shilib ruschaga
qo'shilmasa `tsc` xato beradi. Rus tilining ko'plik shakli `Intl.PluralRules` orqali.

**Bildirishnoma ham platforma tilida** (`api/i18n.py`):

```
Til tanlanadi (yon panel) → PUT /notify/settings {"lang":"ru"} → notify_settings.lang
                                                                        ↓
                                        notify_new.py → email + Telegram, ruscha
```

Til **bazada** turadi, brauzerда emas — xabarni server yuboradi (ETL dan keyin,
ilova ochiq bo'lmaganда ham).

Tarjima qilinadi: mavzu, maydon nomlari, ball so'zi (ruscha ko'plik: *1 балл /
2 балла / 5 баллов*), moslik sabablari, summa ajratgichi (`1 234 567` ↔ `1,234,567`),
sana (`31.07.2026` ↔ ISO `2026-07-31`).
Tarjima qilinmaydi (bu — ma'lumot): tender nomi, buyurtmachi, hudud, valyuta, havola.

**Mavzu (theme)** — `frontend/src/theme.tsx`: yorug' / qorong'i / tizim.

Hujjat: `docs/integration/notify_lang.md`

---

## 10. Interfeys

| Ko'rinish | Komponent | Nima beradi |
|---|---|---|
| Tenderlar | `TenderTable.tsx`, `Filters.tsx` | ro'yxat, filtr, saralash, sahifalash |
| Sizga mos | `App.tsx` (`/match`, `/catalog/match`) | moslik balli bo'yicha tartib |
| Katalog | `CatalogView.tsx` | mahsulotlar, import, qoldiq |
| Hujjatlar | `CompanyDocuments.tsx` | kompaniya hujjatlari bazasi |
| Statistika | `StatsView.tsx` | grafiklar (alohida chunk — Recharts) |
| Akkaunt | `AccountSettings.tsx` | profil, narx sozlamalari, bildirishnoma |
| Tender paneli | `TenderDrawer.tsx` | AI, narx, cheklist, ombor, hujjat matni |

- **Kod bo'lish:** statistika va tender paneli alohida chunk'да — ro'yxatni ochgan
  foydalanuvchi Recharts (~370 KB) ni yuklab olmaydi.
- **Chuqur havola:** `/?tender=123` — bildirishnomadagi havola aynan o'sha kartochkani ochadi.
- Yangilik belgisi, ma'lumot yangiligi ko'rsatkichi (`Freshness.tsx`), manba chiplari.

---

## 11. Sifat va nazorat

| To'plam | Testlar | Nimani qulflaydi |
|---|---|---|
| `notify_test.py` | 29 | chegara, takrorlanmaslik, havola, dry-run, til, Telegram xavfsizligi |
| `pricing_test.py` | 26 | narx formulasi, chegaraviy holatlar |
| `import_test.py` | 11 | Excel import, qator bo'yicha xatolar |
| `compliance_test.py` | 5 | cheklist mantiqi |
| `doctext_test.py` | 5 | matn ajratish holatlari |
| `etl_coverage_test.py` | 5 | ETL qamrovi yo'qolmasligi |

Sinovlar **tarmoqqa chiqmaydi**: SMTP va Telegram Bot API soxta transport bilan
almashtiriladi, sinovdan keyin baza yozuvlari tozalanadi.

Ishga tushirish:

```bash
.venv/Scripts/python.exe _tests/notify_test.py     # (har to'plam alohida)
cd frontend && npx tsc -b --noEmit && npm run build
```

---

## 12. Ishga tushirish

```bash
# 1) Baza patchlari (idempotent, tartib muhim emas — har biri mustaqil)
psql "dbname=xtxarid user=postgres" -f schema_patch_notify.sql
psql "dbname=xtxarid user=postgres" -f schema_patch_notify_telegram.sql
psql "dbname=xtxarid user=postgres" -f schema_patch_notify_subscribers.sql
psql "dbname=xtxarid user=postgres" -f schema_patch_notify_link.sql
psql "dbname=xtxarid user=postgres" -f schema_patch_notify_lang.sql
# ... qolgan 17 tasi ham shunday (schema_patch_*.sql)

# 2) .env — 13 ta sozlama
#    XT_DB_DSN, DB_POOL_MIN/MAX, ANTHROPIC_API_KEY, AI_EFFORT, CORS_ORIGINS,
#    SMTP_HOST/PORT/USER/PASSWORD/FROM/TLS, TELEGRAM_BOT_TOKEN

# 3) API + interfeys
./run_api.ps1
cd frontend && npm run dev

# 4) ETL (soatlik jadval uchun: register_task.ps1)
python run_etl.py
python notify_new.py --dry-run      # nima ketishini ko'rsatadi
```

---

## 13. Bajarilmagan / keyingi qadamlar

Bular **ataylab** qilinmagan — TZ bosqichlari bo'yicha keyingi ishlar:

| # | Nima | Nega hozir yo'q |
|---|---|---|
| A | **Autentifikatsiya va ko'p-ijarachilik** (`company`, `app_user`) | Hozir yagona foydalanuvchi rejimi; API ochiq. Katalog, tannarx, ombor — kompaniya siri, ular `company_id` bo'yicha bo'linishi kerak |
| D | **Talab ajratish** (`tender_requirement`, `confidence`, `raw_snippet`) | Hujjat matni (C) tayyor, ajratish qatlami hali qurilmagan |
| — | **OCR** skanerlangan PDF uchun | MVP qamrovidan tashqarida — hozir `unreadable` deb belgilanadi |
| — | **Fon-ishchi (navbat)** | Hujjat tahlili hozir so'rov ichida; hajm oshsa navbat kerak bo'ladi |
| — | **Ish jarayoni holati** (`yangi / baholanmoqda / qaror qabul qilingan`) | P0-11 ning qolgan qismi |
| — | Server xato matnlari tarjimasi | Bildirishnoma tarjima qilingan; API xatolari hamon o'zbekcha |

**Sozlash bo'yicha eslatma:** `notify_settings.base_url` hozir `http://localhost:5173`.
Bildirishnomadagi havolalar telefondan ochilishi uchun uni serverning tashqi
manziliga o'zgartirish kerak.

---

## 14. Hujjatlar xaritasi

| Fayl | Nima haqida |
|---|---|
| `REJA.md` | TZ ga o'tish rejasi — bosqichlar, ma'lumot modeli, xavflar |
| `REJA_UX.md` | Saqlangan qidiruv, kategoriya, xabarnoma rejasi |
| `AVTOMATLASHTIRISH.md` | Soatlik ETL jadvali (Windows / macOS / Linux) |
| `docs/integration/etl.md` | ETL integratsiya qadamlari |
| `docs/integration/import.md` | Katalog importi |
| `docs/integration/doctext.md` | Hujjat matni |
| `docs/integration/pricing.md` | Narx hisobi |
| `docs/integration/compliance.md` | Hujjatlar cheklisti |
| `docs/integration/notify.md` | Email bildirishnoma |
| `docs/integration/notify_telegram.md` | Telegram kanali |
| `docs/integration/notify_lang.md` | Bildirishnoma tili |
| `UPDATED.md` | **shu fayl** — bajarilgan ishlar ro'yxati |
