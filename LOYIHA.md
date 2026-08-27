# Tender AI — loyihaning to'liq texnik hujjati

> **Nima bu:** O'zbekiston davlat xaridlari (tender) platformalaridan ma'lumot
> yig'ib, uni broker/tadbirkor uchun **qarorga aylantiradigan** tizim.
> Savol "tender bormi?" emas — **"bu tenderga ariza berish foydalimi va nechi pulga?"**
>
> **Holat:** MVP. Ma'lumot bazasi, ETL, backend API, dashboard, AI tahlil,
> narx hisobi, hujjat cheklisti, bildirishnoma va kompaniya autentifikatsiyasi ishlaydi.
>
> **Til:** butun kod, izoh va interfeys — o'zbekcha (lotin). Interfeys uz/ru/en.
> **Sana:** 2026-08-23 · **Tarmoq:** `main`

---

## Mundarija

1. [Loyiha haqida](#1-loyiha-haqida)
2. [Arxitektura](#2-arxitektura)
3. [Texnologiyalar steki](#3-texnologiyalar-steki)
4. [Katalog tuzilishi](#4-katalog-tuzilishi)
5. [Ma'lumotlar modeli — barcha jadvallar](#5-malumotlar-modeli--barcha-jadvallar)
6. [Backend modullari va funksiyalari](#6-backend-modullari-va-funksiyalari)
7. [API endpointlar to'liq ro'yxati](#7-api-endpointlar-toliq-royxati)
8. [ETL qatlami](#8-etl-qatlami)
9. [Frontend](#9-frontend)
10. [Konfiguratsiya (.env)](#10-konfiguratsiya-env)
11. [Ishga tushirish](#11-ishga-tushirish)
12. [Sinovlar](#12-sinovlar)
13. [Xavfsizlik modeli](#13-xavfsizlik-modeli)
14. [ERP bilan chegara](#14-erp-bilan-chegara)
15. [Loyiha holati va keyingi qadamlar](#15-loyiha-holati-va-keyingi-qadamlar)

---

## 1. Loyiha haqida

### 1.1 Muammo

O'zbekistonda davlat xaridi bir necha platformada e'lon qilinadi
(`xt-xarid.uz`, `etender.uzex.uz`). Broker yoki yetkazib beruvchi har kuni
ularni qo'lda kuzatishi, PDF hujjatlarni ochib o'qishi, o'z omboriga
solishtirishi va narx hisoblashi kerak. Bu — kunlik qo'l mehnati va
o'tkazib yuborilgan imkoniyatlar.

### 1.2 Yechim

Tizim quyidagi zanjirni avtomatlashtiradi:

```
Platformalar → ETL (soatlik) → PostgreSQL
                                   ↓
                      Hujjat matni (PDF/DOCX/XLSX → matn)
                                   ↓
                      AI tahlil (xulosa · moslik · Go/No-Go)
                                   ↓
   Kompaniya Excel katalogi → Ombor qoldig'i tekshiruvi
                                   ↓
                      Narx hisobi (tannarx → tavsiya narx)
                                   ↓
                      Hujjatlar cheklisti (bor / yo'q / muddati tugagan)
                                   ↓
              FastAPI (kompaniya autentifikatsiyasi) → React dashboard
                                   ↓
                      Email + Telegram bildirishnoma
```

### 1.3 Asosiy dizayn tamoyillari

| Tamoyil | Ma'nosi |
|---|---|
| **Manba API ga to'g'ridan-to'g'ri ulanmaymiz** | Backend faqat O'Z bazasidan o'qiydi. Platformaga faqat ETL boradi. |
| **Xom javob saqlanadi** | Asosiy jadvallarda `raw_json` bor — sxema o'zgarsa ma'lumot yo'qolmaydi. |
| **Qora quti bo'lmasin** | Har ball, har formula, har AI xulosasi **sababi bilan** ko'rsatiladi (`evidence`, `steps[]`, `reasons[]`). |
| **Qarorni faqat inson qabul qiladi** | AI tavsiya beradi, tizim hech qachon avtomatik ariza bermaydi. |
| **Jimgina o'tkazib yuborilmaydi** | O'qilmagan fayl → aniq status; buzilgan ETL → `etl_run.status='error'`. |
| **Darvoza yopiq holatda boshlanadi** | Yangi endpoint avtomatik himoyalanadi; ochiqlar `PUBLIC_PATHS` da sanalgan. |
| **AI ixtiyoriy** | Kalit bo'lmasa tizim to'liq ishlaydi — AI faqat qo'shimcha qatlam. |

### 1.4 Hozirgi ko'lam

- **2 platforma:** `xt-xarid` (JSON-RPC), `uzex` (REST)
- **~863 protsedura**, **~2595 hujjat** metadata + yuklab olish havolasi
- **21 kategoriya** daraxti (2 daraja), NACE/ИКПУ kodidan deterministik
- **11 kanonik hujjat turi**, **11 Go/No-Go mezoni**
- **3 til:** uz / ru / en (interfeys ham, bildirishnoma ham)

---

## 2. Arxitektura

### 2.1 Qatlamlar

```
┌──────────────────────────────────────────────────────────────┐
│  FRONTEND — React 18 + Vite + Tailwind 4 + shadcn/ui         │
│  :5173   dashboard, filtrlar, tender paneli, katalog, hujjat │
└───────────────────────────┬──────────────────────────────────┘
                            │ HTTP (HttpOnly cookie sessiya + CSRF)
┌───────────────────────────▼──────────────────────────────────┐
│  BACKEND — FastAPI (api/)                                    │
│  :8000   gate() darvozasi → 60+ endpoint                     │
│  ┌──────────┬──────────┬──────────┬──────────┬────────────┐  │
│  │ queries  │ matching │ pricing  │ stock    │ compliance │  │
│  │ auth     │ ai/ai_*  │ importer │ notify   │ telegram   │  │
│  └──────────┴──────────┴──────────┴──────────┴────────────┘  │
└───────────────────────────┬──────────────────────────────────┘
                            │ psycopg2 ThreadedConnectionPool
┌───────────────────────────▼──────────────────────────────────┐
│  PostgreSQL "xtxarid"                                        │
│  public.*  — tender ma'lumoti + kompaniya ma'lumoti          │
│  erp.*     — ERP sxemasi (FAQAT O'QIYMIZ)                    │
└───────────────────────────▲──────────────────────────────────┘
                            │ INSERT / UPSERT
┌───────────────────────────┴──────────────────────────────────┐
│  ETL — run_etl.py orkestratori (soatlik, Task Scheduler)     │
│  etl_tenders · etl_uzex · etl_details · etl_lots ·           │
│  etl_dims · etl_doc_text · etl_categorize · etl_ai_summary   │
│  → notify_new.py (email + Telegram)                          │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Bitta tenderning hayoti

| # | Qadam | Skript / modul | Natija jadvali |
|---|---|---|---|
| 1 | Ro'yxatni yig'ish | `etl_tenders.py`, `etl_uzex.py` | `tender`, `tender_lot`, `tender_good` |
| 2 | Tafsilot va fayllar | `etl_details.py` | `tender_detail`, `tender_document` |
| 3 | Lot pozitsiyalari | `etl_lots.py` | `tender_item` |
| 4 | Hujjat matni | `etl_doc_text.py` | `tender_document_text` |
| 5 | Kategoriyalash | `etl_categorize.py` | `tender_category` |
| 6 | AI xulosa | `etl_ai_summary.py` | `ai_analysis` (`summary_v1`) |
| 7 | Bildirishnoma | `notify_new.py` | `notify_sent` |
| 8 | Talab bo'yicha tahlil | API endpointlar | `ai_analysis` (`match_v2`, `gonogo_v2`), `tender_pricing` |

---

## 3. Texnologiyalar steki

### Backend

| Komponent | Tanlov | Nega |
|---|---|---|
| Web framework | **FastAPI** | Avtomatik Swagger, Pydantic validatsiya |
| DB drayver | **psycopg2** (`ThreadedConnectionPool`) | FastAPI sync-endpointni threadpool'da yurgizadi |
| ORM | **YO'Q** — sof SQL (`api/queries.py`) | Barcha so'rov bir joyda, ko'rinadigan va tez |
| AI | **Anthropic Claude** (`claude-opus-5`, `claude-opus-4-8`) | Strukturali JSON chiqish (`json_schema`) |
| Fayl parseri | `pypdf`, `python-docx`, `openpyxl`, stdlib `HTMLParser` | Deterministik, OCR yo'q |
| Parol | **pbkdf2_sha256**, 240 000 iteratsiya | Tashqi bog'liqliksiz (`hashlib`) |
| Email | stdlib `smtplib` | Sozlamalar bazada, parol `.env` da |
| Telegram | Bot API (`requests`) | `api/telegram.py` — yagona transport nuqtasi |

### Frontend

| Komponent | Tanlov |
|---|---|
| Framework | React 18 + TypeScript 7 |
| Bundler | Vite 5 |
| Stil | Tailwind CSS 4 + `tw-animate-css` |
| Komponentlar | shadcn/ui (Radix UI ustida) — 16 ta primitiv |
| Grafik | Recharts (faqat `StatsView`, alohida lazy chunk) |
| Ikonlar | O'z to'plami (`Icon.tsx`) + `lucide-react` (faqat ui ichida) |
| i18n | **Kutubxonasiz** — ~60 qator + `Intl.PluralRules` |
| Holat (state) | React hooks (Redux/Zustand yo'q) |

---

## 4. Katalog tuzilishi

```
tender-ai/
├── api/                        # FastAPI backend (20 modul)
│   ├── main.py                 # 2217 qator — barcha endpointlar + gate()
│   ├── db.py                   # connection pool
│   ├── queries.py              # barcha SQL matnlari (769 qator)
│   ├── auth.py                 # kompaniya hisobi, sessiya, bloklash (552)
│   ├── matching.py             # deterministik skorlash 0–100 (143)
│   ├── ai.py                   # AI xulosa + kategoriya teglari (264)
│   ├── ai_match.py             # AI moslik: mos / qisman / mos_emas (257)
│   ├── ai_gonogo.py            # AI Go/No-Go, 11 mezon (387)
│   ├── ai_docs.py              # hujjat matnini promptga tayyorlash (296)
│   ├── ai_chat.py              # AI-Chat: RAG + tool-calling (ULANMAGAN)
│   ├── importer.py             # Excel/CSV katalog importi (732)
│   ├── stock.py                # ombor qoldig'i tekshiruvi (430)
│   ├── pricing.py              # narx formulasi, AI yo'q (556)
│   ├── compliance.py           # hujjatlar cheklisti (1456)
│   ├── notify.py               # bildirishnoma mantiqi (1345)
│   ├── telegram.py             # Bot API transporti (266)
│   ├── i18n.py                 # server tomonidagi xabar matnlari (251)
│   ├── translit.py             # lotin ↔ kirill qidiruv (182)
│   ├── categories.py           # kategoriya taksonomiyasi (97)
│   ├── erp_status.py           # ERP dan o'qish — tender holati (79)
│   └── erp_stock.py            # ERP dan o'qish — ombor qoldig'i (111)
│
├── frontend/src/
│   ├── App.tsx                 # asosiy ilova, ko'rinishlar (467)
│   ├── api.ts                  # backend qatlami — barcha so'rovlar (330)
│   ├── types.ts                # backend javob turlari (515)
│   ├── pricing.ts              # narx formulasining JS nusxasi (412)
│   ├── format.ts               # pul/sana/deadline formatlash (154)
│   ├── i18n.tsx · theme.tsx    # til va mavzu providerlari
│   ├── locales/                # uz.ts · ru.ts · en.ts (~600 kalit)
│   └── components/             # 33 komponent + ui/ (16 primitiv)
│
├── etl_*.py                    # 8 ta ETL skripti
├── run_etl.py                  # ETL orkestratori (parallel + jurnal)
├── notify_new.py               # ETL dan keyingi bildirishnoma
├── create_company.py           # kompaniya hisobini yaratish (CLI)
├── status_counts.py · diag_refs.py · discover_dims.py   # diagnostika
│
├── xt_xarid_schema.sql         # bazaviy sxema
├── schema_patch_*.sql          # 24 ta migratsiya patchi
│
├── _tests/                     # 7 fayl, 83 sinov funksiyasi
├── docs/                       # integratsiya va ERP hujjatlari (12 fayl)
│
├── run_all.ps1                 # backend + frontend + ngrok bitta buyruqda
├── run_api.ps1                 # faqat API
├── register_task.ps1           # soatlik Windows Task Scheduler vazifasi
├── run_etl.sh · com.birja.etl.plist   # macOS ekvivalenti
│
├── REJA.md                     # TZ ga o'tish rejasi (bosqichlar A–I)
├── UPDATED.md · AVTOMATLASHTIRISH.md · REJA_UX.md
└── LOYIHA.md                   # ⬅ shu hujjat
```

---

## 5. Ma'lumotlar modeli — barcha jadvallar

Baza: **PostgreSQL `xtxarid`**. Sxema ikki qismdan iborat:

- **Umumiy (platforma) ma'lumoti** — kompaniyaga bog'liq emas, hamma ko'radi
- **Kompaniya ma'lumoti** — sir: katalog, tannarx, hujjatlar, sozlamalar

### 5.1 Dimension (reestr) jadvallari

#### `dim_area` — hudud ierarxiyasi
| Ustun | Tur | Izoh |
|---|---|---|
| `area_id` | TEXT PK | `'2140'` (yaproq) yoki `'33'` (ildiz) |
| `parent_id` | TEXT FK → `dim_area` | ota tugun |
| `name_uz`, `name_ru` | TEXT | nomi |
| `level` | SMALLINT | 0=respublika, 1=viloyat, 2=tuman |
| `full_path` | TEXT | `'33.2137.2138.2140'` |
| `has_children` | BOOLEAN | kaskad dropdown uchun |

#### `dim_status` — status lug'ati
| Ustun | Tur | Izoh |
|---|---|---|
| `status_code` | TEXT | `open`, `expired`, `not_realized`, … |
| `domain` | TEXT | `tender` / `reduction` / `ad` / `selection` |
| `name_uz`, `name_ru` | TEXT | ko'rsatiladigan nom |
| `is_terminal` | BOOLEAN | tugallanganmi (dashboard filtri) |
| `status_id` | INTEGER | manba ID si |
| | | **PK:** (`status_code`, `domain`) |

#### `dim_category` — manba tovar klassifikatori
`category_uid` (UUID PK), `code` (`'28.41.24.190'`), `title_ru`, `title_uz`

#### `dim_category_uz` — bizning yagona kategoriya daraxti
| Ustun | Tur | Izoh |
|---|---|---|
| `code` | TEXT PK | `'qurilish'`, `'qurilish/yol'`, `'mashina'` |
| `parent` | TEXT FK | 2-daraja uchun ota kod |
| `name_uz` | TEXT | o'zbekcha nom |
| `sort_order` | INTEGER | interfeys tartibi |

> Daraxt **`api/categories.py` `CATEGORY_TREE`** dan ekiladi — yagona manba.
> 21 ta kategoriya: qurilish, transport, mashina, elektronika, elektr,
> tibbiyot, kimyo, metall, mebel, oziq, qishloq, it, konsalting, talim,
> kommunal, boshqa (+ ichki turlar).

### 5.2 Tender ma'lumoti

#### `tender` — asosiy fakt jadvali
| Guruh | Ustunlar |
|---|---|
| Kimlik | `id` (BIGINT PK), `source_platform` (`'xt-xarid'`/`'uzex'`), `source_id` — **UNIQUE (source_platform, source_id)** |
| Asosiy | `type` (`tender`/`reduction`/`shop`), `name`, `status` |
| Moliya | `totalcost` NUMERIC(18,2), `currency` CHAR(3) — **hardcode qilinmaydi**, `lang` |
| Struktura | `is_new_multilot`, `lot_count`, `good_count`, `part_count`, `participants_of_joint_purchase`, `green` |
| Hudud | `area_path`, `area_leaf_id` FK → `dim_area` |
| Buyurtmachi | `buyer_org_id`, `company_name` — **manba platformadagi tashkilot**, ijarachi emas |
| Shartnoma | `contract_num`, `contract_number`, `contract_id` |
| Sanalar (barchasi NULLABLE) | `created_at`, `inserted_at`, `publicated_at`, `starting_date`, `agree_at`, `close_at`, `ends_at`, `close_docs_objections_at` |
| Qolgan vaqt | `docs_objections_remain_time`, `remain_time` (sekund, snapshot) |
| ETL/audit | `raw_json` JSONB, `fetched_at`, `first_seen_at`, `source_ref` |

**Indekslar:** status, area_leaf, company, created, currency, type, source_platform, close_at, (status, close_at), first_seen_at

#### `tender_lot` — lotlar
`tender_id` + `lot_id` (PK), `title`, `item_count`, `total_sum_lot`

#### `tender_good` — tovarlar (`meta.good_maps[]` dan)
`tender_id`, `lot_id`, `good_code` (PK), `name`, `unit`, `amount`,
`price`, `totalcost_item`, `category_uid`

#### `tender_item` — lot pozitsiyalari (`get_items` dan, boyroq)
| Ustun | Izoh |
|---|---|
| `item_id` | manba pozitsiya ID si (PK qismi) |
| `product_code` | `'28.99.30.000_00069'` |
| `name`, `unit` | nomi va o'lchov birligi |
| `amount_text`, `price_text`, `totalcost_text` | **xom, formatlangan matn** (`'2.00 dona'`) |
| `delivery_period`, `guarantee` | kunda |
| `prod_year`, `country_of_origin`, `delivery_address` | talablar |
| `spec` | `'Texnik topshiriqga asosan'` |
| `properties` | JSONB `[{prop_name, val_name}]` — texnik xarakteristikalar |
| `raw_json`, `fetched_at` | audit |

#### `tender_detail` — tafsilot (`get_proc` javobi)
`tender_id` (PK), `anno`, `method_marks`, `company_details`, `director`,
`close_time`, `proc_lang`, `offer_period`, `doc_count`, `raw_json`, `fetched_at`

#### `tender_document` — biriktirilgan fayllar
`tender_id` + `file_ref` (PK), `file_id` UUID, `file_path`, `name`,
`size_bytes`, `content_type`, `file_type`, `field_key`, `field_path`,
`source_platform`, `fetched_at`

> `file_ref` universal kalit: xt-xarid da UUID, uzex da yo'l (`file_path`).

#### `tender_document_text` — ajratilgan matn (P0-2)
| Ustun | Izoh |
|---|---|
| `tender_id` + `file_ref` | PK |
| `text` | ajratilgan matn (max 400 000 belgi) |
| `status` | `ok` · `unreadable` · `unsupported` · `too_large` · `download_failed` · `empty` |
| `char_count`, `page_count` | hajm ko'rsatkichlari |
| `error` | qisqartirilgan xato matni |
| `extractor` | `pypdf` / `python-docx` / `openpyxl` / `plain` |
| `extracted_at` | vaqt |

**FTS indeks:** `gin (to_tsvector('simple', left(text, 1000000)))`

#### `tender_category` — tender ↔ kategoriya
`tender_id` + `code` (PK), FK → `dim_category_uz`

### 5.3 AI natijalari

#### `ai_analysis` — keshli AI natijalari
| Ustun | Izoh |
|---|---|
| `tender_id` + `kind` | **PK** |
| `kind` | `summary_v1` · `match_v2` · `gonogo_v2` |
| `content_hash` | kirish matnining SHA-256 — **kesh shu bilan boshqariladi** |
| `result` | JSONB — Claude qaytargan strukturali javob |
| `model` | `claude-opus-5` / `claude-opus-4-8` |
| `input_tokens`, `output_tokens` | xarajat hisobi |
| `created_at` | vaqt |

**GIN indeks:** `(result -> 'category_tags')`

> **Xarajat nazorati:** kirish matni o'zgarmagan bo'lsa AI **chaqirilmaydi**.

### 5.4 Kompaniya hisobi va sessiya

#### `company_account` — kompaniya hisobi
`id` SERIAL PK, `username` UNIQUE, `company_name`, `password_hash`,
`email`, `active`, `last_login_at`, `created_at`, `updated_at`

> **Hodimlar bu yerda EMAS** — ular ERP da (`erp.app_user`). Tender-AI ga
> KOMPANIYA kiradi, odam emas.

#### `company_session` — faol sessiyalar
`id`, `account_id` FK, `token_hash` UNIQUE, `csrf_token`, `expires_at`,
`user_agent`, `created_at`, `last_seen_at`

> Token bazada **xesh** ko'rinishida — dump qo'lga tushsa ham tiklab bo'lmaydi.
> `csrf_token` — sessiya tokenidan farqli: u sahifaga ochiq va faqat
> "so'rovni bizning sahifamiz yubordimi" degan savolga javob beradi.

#### `login_attempt` — kirish urinishlari jurnali
`id` bigserial, `username`, `ip` inet, `ok` boolean, `user_agent`, `created_at`

> Bloklash **shu jadvaldan hisoblanadi** — alohida hisoblagich ustuni yo'q.
> Parol saqlanmaydi. Muvaffaqiyatli kirish xatolar zanjirini uzadi.

### 5.5 Kompaniya profili va qidiruv

#### `company_profile` — kompaniya passporti
| Guruh | Ustunlar |
|---|---|
| Qidiruv | `keywords` TEXT[], `regions` TEXT[], `currency`, `min_cost`, `max_cost` |
| Tavsif | `name`, `about` |
| Malaka | `certificates` TEXT[], `clearances` TEXT[], `experience_years` |
| Salohiyat | `max_contract_value` + `max_contract_currency`, `employees`, `capacity_note`, `lead_time_days` |
| Mezon | `min_margin_percent`, `constraints_note` |
| Aloqa | `contact_name`, `email`, `phone`, `position` |

> `min_cost/max_cost` — **qidiruv filtri**; `max_contract_value` —
> Go/No-Go uchun **real moliyaviy chegara**. Ikkalasi ataylab alohida.

#### `saved_search` — saqlangan qidiruvlar
`id`, `company_id`, `name`, `keywords[]`, `categories[]`, `regions[]`,
`currency`, `min_cost`, `max_cost`, `notify`, `last_seen_at`, `created_at`, `updated_at`

### 5.6 Katalog va ombor

#### `catalog_product` — mahsulot katalogi
| Ustun | Izoh |
|---|---|
| `id`, `company_id` | kimlik |
| `name` | mahsulot nomi (majburiy) |
| `category_code` | FK → `dim_category_uz` (NULL = faqat nom bo'yicha) |
| `keywords` TEXT[] | qo'shimcha moslik so'zlari |
| `unit` | sotuv birligi |
| `price` | **sotuv** narxi |
| `cost_price` | **tannarx** (xarid/ishlab chiqarish) — import shablonidagi "tannarx" |
| `currency` | valyuta |
| `stock_qty` | qoldiq. **NULL = kiritilmagan**, 0 = mavjud emas — bu farq muhim |
| `stock_unit` | qoldiq o'lchov birligi (sotuv birligidan alohida) |
| `stock_updated_at` | eskirganlik ogohlantirishi shundan (`STOCK_STALE_DAYS`, default 14) |
| `notify` | yangi mos tenderda xabar ketsinmi |
| `import_batch_id` | oxirgi import partiyasi (qo'lda kiritilganda NULL) |

#### `catalog_import_batch` — import partiyalari
`id` UUID PK, `company_id`, `filename`, `source` (`xlsx`/`csv`),
`rows_total`, `rows_ok`, `rows_error`, `inserted`, `updated`,
`errors` JSONB (**qator bo'yicha xatolar**), `created_at`

#### `catalog_state` — "oxirgi ko'rilgan" belgisi
`id`=1 (singleton), `last_seen_at` — yangi mos tenderlar nishoni uchun

### 5.7 Hujjatlar

#### `company_document` — kompaniyaning o'z hujjatlari bazasi
`id`, `doc_type` (kanonik kod — `api/compliance.py DOC_TYPES`), `name`,
`number`, `issued_at`, `valid_until` (**NULL = muddatsiz**), `file_name`,
`file_ref`, `note`, `created_at`, `updated_at`

### 5.8 Narx

#### `pricing_settings` — odatiy parametrlar (singleton `id=1`)
`markup_percent` (15), `risk_reserve_percent` (5), `risk_reserve_fixed` (0),
`logistics_percent` (0), `logistics_fixed` (0), `vat_percent` (12), `currency`

#### `tender_pricing` — tender bo'yicha smeta
`tender_id` PK, `inputs` JSONB (**natijani qayta tiklash uchun yetarli**),
`result` JSONB (**har bosqich formulasi bilan**), `manual_price`,
`currency`, `note`, `created_at`, `updated_at`

### 5.9 Bildirishnoma

#### `notify_settings` — sozlamalar (singleton `id=1`)
| Ustun | Izoh |
|---|---|
| `enabled` | email kanali yoqilganmi |
| `email` | qabul qiluvchi |
| `min_score` | moslik chegarasi 0–100 (default 70) |
| `smtp_host`, `smtp_port`, `smtp_user`, `smtp_use_tls`, `from_email` | SMTP. **PAROL BU YERDA EMAS** — `.env` |
| `base_url` | frontend manzili; havola = `base_url + /?tender=ID` |
| `telegram_enabled`, `telegram_chat_id` | Telegram kanali (email'dan mustaqil) |
| `lang` | `uz` / `ru` / `en` — xabar tili |

#### `notify_sent` — yuborilgan xabarlar jurnali
`tender_id` + `kind` (**PK**), `sent_at`, `email`, `score`

> `kind`: `'new_match'` = email, `'new_match_tg:<chat_id>'` = Telegram obunachisi.
> PK tufayli **bir tender haqida har obunachiga bir marta** xabar ketadi.

#### `notify_telegram_subscriber` — Telegram obunachilari
`chat_id` PK, `title`, `chat_type`, `username`, `enabled`,
`source` (`'link'` = tasdiqlangan / `'legacy'`), `first_seen_at`, `last_seen_at`

#### `notify_telegram_link` — bir martalik ulash tokenlari
`token` PK, `created_at`, `expires_at` (TTL 30 daqiqa), `chat_id`, `used_at`

> Foydalanuvchi `https://t.me/<bot>?start=<token>` ni bosadi; bot tokenni
> xabar matnida oladi va `api/notify.py` uni obunachiga aylantiradi.

### 5.10 ETL sog'ligi

#### `etl_run` — har yurish jurnali
`id`, `source_platform`, `started_at`, `finished_at`,
`status` (`running` / `ok` / `error`), `found`, `new`, `error`

> Buzilish **jimgina o'tkazib yuborilmaydi** — `status='error'` qoladi va
> `/freshness` endpointi uni ko'rsatadi.

### 5.11 ERP sxemasi (faqat o'qish)

| View | Kim o'qiydi | Nima beradi |
|---|---|---|
| `erp.v_tender_status` | `api/erp_status.py` | shu tender ishga olinganmi, kim mas'ul |
| `erp.v_stock_balance` | `api/erp_stock.py` | `{product_id: {qty, reserved, available, unit}}` |
| `erp.stock_move` | `api/erp_stock.py` (`in_use()`) | ombor ishga tushganmi |

> Chegara **simmetrik**: har ikki tomon bir-birining sxemasidan O'QIYDI,
> hech biri YOZMAYDI.

### 5.12 Migratsiya patchlari (qo'llash tartibi)

```
xt_xarid_schema.sql                 # bazaviy: dim_*, tender, tender_lot, tender_good
schema_patch_dims.sql               # dim_* ga qo'shimcha ustunlar
schema_patch_source.sql             # tender.source_platform
schema_patch_multiplatform.sql      # tender.source_id + UNIQUE, tender_document.file_ref
schema_patch_documents.sql          # tender_detail, tender_document
schema_patch_lots.sql               # tender_lot.title, tender_item
schema_patch_doctext.sql            # tender_document_text + FTS
schema_patch_categories.sql         # dim_category_uz, tender_category
schema_patch_ai.sql                 # ai_analysis
schema_patch_freshness.sql          # tender.first_seen_at, etl_run
schema_patch_expired.sql            # 'expired' statusi + indeks
schema_patch_etl_coverage.sql       # yetishmayotgan statuslar
schema_patch_profile.sql            # company_profile
schema_patch_gonogo.sql             # company_profile ga passport ustunlari
schema_patch_saved_search.sql       # saved_search
schema_patch_catalog.sql            # catalog_product, catalog_state
schema_patch_stock.sql              # catalog_import_batch + qoldiq ustunlari
schema_patch_compliance.sql         # company_document
schema_patch_pricing.sql            # pricing_settings, tender_pricing
schema_patch_notify.sql             # notify_settings, notify_sent
schema_patch_notify_telegram.sql    # telegram ustunlari
schema_patch_notify_subscribers.sql # notify_telegram_subscriber
schema_patch_notify_link.sql        # notify_telegram_link
schema_patch_notify_lang.sql        # notify_settings.lang
schema_patch_auth.sql               # (eskirgan) app_user — ERP ga ko'chdi
schema_patch_auth_2.sql             # company_account, company_session
schema_patch_auth_3.sql             # company_session.csrf_token
schema_patch_auth_4.sql             # login_attempt
```

Barcha patchlar **idempotent** (`IF NOT EXISTS`, `ON CONFLICT DO NOTHING`).

---

## 6. Backend modullari va funksiyalari

### 6.1 `api/db.py` — ma'lumot bazasi qatlami

`.env` dagi `XT_DB_DSN` dan o'qiydi (ETL bilan bir xil o'zgaruvchi).
`psycopg2.ThreadedConnectionPool` + `RealDictCursor`.

| Funksiya | Vazifa |
|---|---|
| `init_pool()` | Pool yaratadi — `main.py` lifespan startup'da |
| `close_pool()` | Pool yopadi — lifespan shutdown'da |
| `get_conn()` | Context manager: pooldan connection oladi/qaytaradi |
| `query(sql, params) -> List[dict]` | Ko'p qatorli SELECT |
| `query_one(sql, params) -> dict\|None` | Bitta qator |
| `scalar(sql, params) -> Any` | Bitta qiymat |
| `execute_returning(sql, params)` | YOZISH (INSERT/UPDATE … RETURNING) + commit |
| `class DBUnavailable(RuntimeError)` | API buni **503** ga aylantiradi |

### 6.2 `api/queries.py` — barcha SQL matnlari

**Xavfsizlik:** barcha foydalanuvchi qiymatlari named-param (`%(x)s`) orqali
uzatiladi → SQL-injection yo'q. Faqat `ORDER BY` ustuni **oq ro'yxat** bilan
tekshiriladi (ustun nomini parametrlashtirib bo'lmaydi).

| Funksiya | Vazifa |
|---|---|
| `build_column_search(col, q, param)` | Bitta ustun bo'yicha **alifbodan qat'i nazar** qidiruv sharti |
| `build_text_search(q, param)` | Erkin matnli qidiruv (nom + buyurtmachi + tovar) |
| `build_product_filter(products, param)` | Faqat **tovar nomi** bo'yicha filtr |
| `kind_predicate(kind)` | `'service'` / `'product'` → NACE bo'limi bo'yicha SQL sharti |
| `build_tender_filters(...)` | To'liq `WHERE` bo'lagi + parametrlar |
| `build_order_by(sort)` | `sort` / `-sort` → xavfsiz `ORDER BY` (whitelist: `close_at`, `publicated_at`, `totalcost`, `id`) |
| `tenders_sql`, `tenders_count_sql`, `tender_by_id_sql` | Ro'yxat / son / bitta tender |
| `match_candidates_sql(where, cap)` | Skorlash uchun nomzodlar (cap = 3000) |
| `products_sql(where_extra, kind)` | Tovar/xizmat nomlari chastota bo'yicha |

Plus ~40 ta nomlangan SQL konstanta: `TENDER_LOTS_SQL`, `AI_ANALYSIS_SQL`,
`DOCUMENT_BY_REF_SQL`, `PROFILE_GET_SQL`, `CATALOG_LIST_SQL`,
`PRICING_SETTINGS_GET_SQL`, `FRESHNESS_SQL`, `STATUSES_SQL`, …

### 6.3 `api/auth.py` — kimlik (kompaniya hisobi)

**Konstantalar:**
`ITERATIONS=240000` · `SESSION_DAYS=14` · `ATTEMPT_WINDOW_MIN=15` ·
`MAX_PER_USER=5` · `MAX_PER_IP=25` · `ATTEMPT_KEEP_DAYS=90` ·
`PASSWORD_MIN=10` · `PASSWORD_MAX=200` · `WEAK_PASSWORDS` (qora ro'yxat)

| Funksiya | Vazifa |
|---|---|
| `hash_password(password, *, iterations, salt)` | `pbkdf2_sha256$<iter>$<salt>$<hash>` — **algoritm ustunda**, migratsiyasiz almashtiriladi |
| `verify_password(password, stored)` | `hmac.compare_digest` — vaqt bo'yicha hujumdan himoya |
| `check_password(password, username)` | Yangi parol talabga mosmi (uzunlik, zaiflik, login bilan bir xilmi) |
| `login(username, password, *, user_agent, ip)` | To'liq kirish: bloklash tekshiruvi → parol → sessiya + CSRF token |
| `verify(token)` | Token → hisob. Muddati o'tgan/bekor qilingan bo'lsa `AuthError(401)` |
| `logout(token)` | Sessiyani o'chiradi |
| `set_password(account_id, password, *, current, keep_token)` | Parol almashtirish — **joriy parol majburiy**, boshqa sessiyalar yopiladi |
| `create_account(username, company_name, password, *, email)` | Yangi kompaniya hisobi |
| `update_account(account_id, data)` | Nom / email / faollik |
| `accounts()` | Barcha hisoblar |
| `record_attempt(username, ip, ok, *, user_agent)` | Urinishni jurnalga — **parol yozilmaydi** |
| `guard_attempts(username, ip)` | Bloklangan bo'lsa `AuthError(429)` — **parol tekshirilmasdan oldin** |
| `attempts(hours, limit, only_failed)` | "Kim, qayerdan, qachon urindi" |
| `schema_ready()`, `_attempts_ready()` | Patch qo'llanmagan bo'lsa ilova **yiqilmaydi** |
| `verify_service(key)`, `service_ready()` | ERP `X-Service-Key` — doimiy vaqtli solishtirish |
| `shape(r)` | Parol xeshi javobga **hech qachon** tushmaydi |

### 6.4 `api/matching.py` — deterministik skorlash

Butun "aql" bitta funksiyada. Ball tarkibi **0–100, shaffof**:

| Vazn | Konstanta | Mezon |
|---|---|---|
| 0–60 | `W_KEYWORD` | Profil kalit so'zlari tender matnida (nom + buyurtmachi + tovarlar) |
| 0–20 | `W_REGION` | Hudud mos keladimi |
| 0–15 | `W_BUDGET` | Byudjet oralig'ida |
| 0–5 | `W_CURRENCY` | Valyuta mos keladimi |

| Funksiya | Vazifa |
|---|---|
| `_norm(s)` | Kichik harf + alifbo yig'ish (lotin/kirill birlashtiriladi) |
| `_hits(term, blob)` | Term matnda bormi — **alifbodan qat'i nazar** |
| `score_tender(tender, profile)` | `{score, reasons[], parts{}}` |

> **Kelajakda AI:** faqat SHU funksiya almashtiriladi — endpoint, DB va
> frontend o'zgarmaydi.

### 6.5 `api/translit.py` — lotin ↔ kirill qidiruv

**Muammo:** manba aralash alifboda — `"Спектрометр"`, `"Listlarni bukish"`,
`"Ўткир юрак"`, hatto gomoglif aralashmasi (`"Реryлятор"` — kirill Р-е + lotin r-y).
`nasos` so'rovi oddiy ILIKE bilan **0 ta**, `насос` — 15 ta topadi.

| Funksiya | Vazifa |
|---|---|
| `sql_fold(col)` | SQL bo'lagi: ustunni yig'ilgan shaklga keltiradi |
| `fold_cyr(s)` | Kirillni yig'ilgan shaklga (`SQL_FOLD` bilan **aynan bir xil natija**) |
| `to_lat(s)` | Kirill → lotin (eng ehtimolli o'qilish) |
| `variants(q)` | So'rovning barcha ehtimoliy yozuvlari (max `MAX_VARIANTS=6`) |
| `norm_text(s)` | Python tomonda solishtirishga tayyorlash |

Noaniq harflar tarmoqlanadi: `ts → ц|тс`, `c → ц|к`.

### 6.6 `api/categories.py` — kategoriya taksonomiyasi

AI'siz, deterministik: tovar kodi (`good_code`) 2-xonali prefiksi =
milliy klassifikator (ИКПУ/ОКЭД, NACE bo'limi) → kategoriya.

| Obyekt | Vazifa |
|---|---|
| `CATEGORY_TREE` | 21 ta kategoriya (parent + ichki), `dim_category_uz` shundan ekiladi |
| `OKED_MAP` | NACE bo'limi (`'01'`, `'28'`, …) → yaproq kategoriya kodi |
| `code_for_division(division)` | 2-xonali prefiks → kod (`'boshqa'` agar noma'lum) |
| `parent_of(code)` | `'qurilish/yol'` → `'qurilish'` |

### 6.7 `api/ai.py` — AI xulosa (5a bosqich)

**Model:** `claude-opus-4-8` · **kind:** `summary_v1` · **max_tokens:** 8000

**Nega kerak:** `matching.py` kalit so'z bo'yicha ILIKE qiladi. "kompyuter"
so'rovi bazadagi "Моноблок", "МФУ", "Ноутбук" ni **topmaydi**.

**Natija sxemasi:** `summary_uz`, `category_tags[]`, `keywords_uz[]`,
`keywords_ru[]`, `supplier_profile`, `key_points[]`

| Funksiya | Vazifa |
|---|---|
| `build_input(t)` | Tender ma'lumotidan ixcham matn (lot, pozitsiya, xususiyat) |
| `content_hash(text)` | Barqaror SHA-256 — **kesh shu bilan boshqariladi** |
| `get_client()` | Anthropic mijozi (lazy); kalit yo'q bo'lsa aniq xato |
| `analyze(tender, effort)` | Bitta tenderni tahlil qiladi (kesh mantiqi chaqiruvchida) |
| `class AIUnavailable` | Kalit yo'q yoki chaqiruv muvaffaqiyatsiz |

### 6.8 `api/ai_docs.py` — hujjat matnini AI tahliliga berish

**Muammo:** hujjatlar 400 000 belgigacha, promptga hammasi sig'maydi.
**Yechim:** talab o'zaklari atrofidagi **oynalarni** kesib olish.

**Byudjet:** `AI_DOC_CHARS=45000` · `MIN_PER_DOC=1500` · `WINDOW_PAD=700` · `MAX_DOCS=8`

| Funksiya | Vazifa |
|---|---|
| `anchors()` | Talab o'zaklarining barcha alifbo yozuvlari |
| `hit_positions(raw)` | O'zaklar xom matnning qaysi pozitsiyalarida |
| `excerpts(raw, budget)` | O'zaklar atrofidagi oynalarni birlashtiradi |
| `context(tender_id, budget)` | Tender hujjatlaridan matn + **halol hisobot** (qamrov) |
| `prompt_block(text, meta)` | Promptga qo'yiladigan bo'lim + **QAMROV OGOHLANTIRISHI** |

> Frontendda `AiDocsNote.tsx` shu hisobotni ko'rsatadi: tahlil deyarli
> har doim **qisman** ma'lumotga asoslanadi — foydalanuvchi buni biladi.

### 6.9 `api/ai_match.py` — AI moslik tahlili

**Model:** `claude-opus-5` · **kind:** `match_v2` · **max_tokens:** 6000

`ai.py` dan farqi: u tenderni **mustaqil** tahlil qiladi, bu esa
**munosabatni** baholaydi — tender ↔ foydalanuvchi katalogi/profili.

**Natija:** `verdict` (`mos` / `qisman` / `mos_emas`), `score`, `reason_uz`,
`matched_items[]`, `requirements[]`, `risks[]`

| Funksiya | Vazifa |
|---|---|
| `_fmt_catalog(products)` | Katalogni ixcham matnga — **tartib barqaror** (hash bejiz o'zgarmasin) |
| `build_input(tender, products, profile, docs)` | To'liq prompt matni |
| `content_hash(text)` | Kesh kaliti — tender **va** katalogni qamraydi |
| `analyze(...)` | Tenderni katalogga nisbatan baholaydi |

### 6.10 `api/ai_gonogo.py` — Go / No-Go tavsiyasi

**Model:** `claude-opus-5` · **kind:** `gonogo_v2` · **max_tokens:** 10000 ·
**effort:** `high`

**Qaror:** `go` · `review` (inson tekshiruvi kerak) · `no_go`
**Mezon holati:** `ok` · `risk` · `fail` · `malumot_yoq`

**11 mezon:**

| # | Kalit | Nomi |
|---|---|---|
| 1 | `majburiy_talablar` | Majburiy talablar |
| 2 | `faoliyat_mosligi` | Faoliyat mosligi |
| 3 | `sertifikat` | Sertifikat / litsenziya |
| 4 | `moliyaviy_salohiyat` | Moliyaviy salohiyat |
| 5 | `tajriba` | Tajriba |
| 6 | `deadline` | Muddat (deadline) |
| 7 | `geografik_cheklov` | Geografik cheklov |
| 8 | `resurs_yetarliligi` | Resurs yetarliligi |
| 9 | `xavfsizlik_ruxsatnomalari` | Xavfsizlik ruxsatnomalari |
| 10 | `tender_qiymati` | Tender qiymati |
| 11 | `foyda_xarajat` | Foyda va xarajat |

**Natija:** `decision`, `confidence`, `summary_uz`, `criteria[]`,
`blockers[]`, `next_steps[]`, `missing_data[]`

| Funksiya | Vazifa |
|---|---|
| `_facts(tender, profile, now)` | Hisoblangan faktlar (muddatgacha kun, byudjet nisbati) |
| `build_input(...)` | Tender + hujjatlar + katalog + kompaniya + faktlar |
| `normalize(result)` | Yetishmagan mezonni `malumot_yoq` bilan to'ldiradi, tartibni tiklaydi |
| `analyze(...)` | To'liq tavsiya |

### 6.11 `api/importer.py` — katalog importi (P0-4)

**Shablon ustunlari:** `name`, `keywords`, `unit`, `stock_qty`, `cost_price`,
`price`, `category_code`, `currency`
**Majburiy:** faqat `name`

| Funksiya | Vazifa |
|---|---|
| `norm_header(s)` | Sarlavhani solishtirishga tayyorlaydi (apostrof, bo'shliq, registr) |
| `detect_columns(headers)` | `{maydon: ustun indeksi}` + tanilmagan sarlavhalar |
| `parse_number(raw)` | Matn/katakdan son (`'1 200,50'` → `Decimal`) + xato |
| `_split_keywords(raw)` | `"монитор; стол, 24 dyum"` → ro'yxat (takrorsiz) |
| `read_table(data, filename)` | Fayl baytlaridan xom jadval (xlsx/csv, kengaytma bo'yicha) |
| `_find_header(rows, limit)` | Sarlavha qatorini topadi (fayl boshida izohlar bo'lishi mumkin) |
| `parse_rows(...)` | Tozalangan yozuvlar + **qator bo'yicha xatolar** + ogohlantirishlar |
| `import_catalog(data, filename, *, dry_run)` | Asosiy kirish nuqtasi; `dry_run` da bazaga tegmaydi |
| `template_xlsx()`, `template_csv()` | Namunaviy shablon (CSV — BOM bilan, kirill buzilmasin) |
| `class ImportFormatError` | Butun faylga tegishli xato — import boshlanmaydi |

> **TZ talabi:** bitta qatordagi xato **butun importni to'xtatmaydi** —
> xatolar `catalog_import_batch.errors` JSONB da qator raqami bilan saqlanadi.

### 6.12 `api/stock.py` — ombor qoldig'i tekshiruvi (P0-6)

**Statuslar:** `yetarli` · `yetishmaydi` · `nomalum`
**`STALE_DAYS`** (default 14): qoldiq shundan eski bo'lsa ogohlantirish.

| Funksiya | Vazifa |
|---|---|
| `parse_amount_text(raw)` | `tender_item.amount_text` (`'2.00 dona'`) → miqdor |
| `norm_unit(u)` | Birlikni kanonik shaklga (`dona`/`шт`/`компл.` …) |
| `match_product(position, products)` | Pozitsiyaga eng mos katalog bandi |
| `build_check(tender, rows, products, *, source)` | **Sof hisob** (bazadan ajratilgan — sinov uchun) |
| `check_tender_stock(tender_id)` | Baza bilan to'liq tekshiruv |

> **NULL vs 0:** `stock_qty IS NULL` = "kiritilmagan" → `nomalum`;
> `0` = "mavjud emas" → `yetishmaydi`. Bu farq ataylab saqlanadi.
> Qoldiq birligi pozitsiya birligiga mos kelmasa — natija `nomalum`.

### 6.13 `api/pricing.py` — narx hisobi (P0-7)

**AI YO'Q. Bu sof formula** — har raqam kiruvchi ma'lumotdan arifmetika bilan chiqadi.

**Hisob bosqichlari (`steps[]` — har biri formulasi bilan qaytadi):**

| # | Kalit | Formula |
|---|---|---|
| 1 | `cost_base` | Σ (miqdor × birlik tannarxi) |
| 2 | `logistics` | tannarx × logistika% + logistika (belgilangan) |
| 3 | `risk_reserve` | (tannarx + logistika) × zaxira% + zaxira (belgilangan) |
| 4 | `total_cost` | tannarx + logistika + xavf zaxirasi |
| 5 | `markup` | jami xarajat × ustama% |
| 6 | `price_ex_vat` | jami xarajat + ustama |
| 7 | `vat` | taklif narxi (QQSsiz) × QQS% |
| 8 | `recommended_price` | taklif narxi (QQSsiz) + QQS |
| 9 | `final_price` | qo'lda kiritilgan narx (bo'lmasa — tavsiya etilgan) |
| 10 | `final_ex_vat` | yakuniy narx ÷ (1 + QQS%) |
| 11 | `profit` | yakuniy narx (QQSsiz) − jami xarajat |
| 12 | `profit_percent` | foyda ÷ yakuniy narx (QQSsiz) × 100 |
| 13 | `over_budget` | tender byudjetiga nisbat (ogohlantirish) |

| Funksiya | Vazifa |
|---|---|
| `round2(x)` | 2 kasr, **half-up** (noldan uzoqlashtirib) |
| `calculate(inp)` | Smetani hisoblaydi va **har bosqichni formulasi bilan** qaytaradi |
| `parse_amount_text(text)` | `'2.00 dona'` → `2.0`; son topilmasa `None` (**0 emas**) |
| `positions_from_goods(goods)` | `tender_good` qatorlaridan smeta pozitsiyalari |
| `build_inputs(settings, tender, goods, profile, saved, override)` | Kiruvchi obyekt (ustunlik: keyingisi oldingisini bosadi) |

> **Formula ikki joyda:** `api/pricing.py` va `frontend/src/pricing.ts`.
> Sabab: TZ "parametr o'zgarganda sahifa qayta yuklanmasdan qayta hisoblansin"
> deydi. `_tests/pricing_test.py::test_javascript_bilan_bir_xil` Node orqali
> JS ni yurgizib, natijani Python bilan **aynan** solishtiradi — ikki nusxa
> bir-biridan chetga chiqsa shu yerda ushlanadi.

### 6.14 `api/compliance.py` — hujjatlar cheklisti (P0-8)

**MVP cheklovi (ongli):** bu **statik cheklist**. Tender matnidan hujjat
talablari qidiriladi va kompaniya bazasi bilan solishtiriladi. Hujjat
**mazmunining huquqiy to'g'riligi tekshirilmaydi** — bu ataylab.

**11 kanonik hujjat turi:**

| Kod | Nomi | Bazaviy |
|---|---|---|
| `reg_certificate` | Davlat ro'yxatidan o'tganlik guvohnomasi | ✅ |
| `power_of_attorney` | Ishonchnoma | ✅ |
| `license` | Litsenziya / faoliyat ruxsatnomasi | ✅ |
| `conformity_certificate` | Muvofiqlik sertifikati | ✅ |
| `guarantee_letter` | Kafolat xati | ✅ |
| `bank_details` | Bank rekvizitlari | ✅ |
| `tax_reference` | Soliq ma'lumotnomasi (qarzdorlik yo'qligi) | — |
| `charter` | Ustav / ta'sis hujjatlari | — |
| `financial_report` | Moliyaviy hisobot / balans | — |
| `technical_proposal` | Texnik taklif | — |
| `price_offer` | Narx taklifi | — |

> "Bazaviy" = biznes-jarayonning odatiy ariza to'plami — tender matnida
> topilmasa ham cheklistga kiradi.

**Holatlar:** `ok` · `expiring_soon` (30 kun) · `expired` · `missing`

| Funksiya | Vazifa |
|---|---|
| `canon(s)` | Matnning kanonik shakli (naqsh va matn uchun **bir xil quvur**) |
| `_stem_variants(stem)` | O'zakning barcha alifbo yozuvlari (lru_cache) |
| `_match_alternative(blob, stems, exclude)` | Variant matnda bormi (+ istisnolar) |
| `_evidence(raw, idx, lo, hi)` | **Dalil bo'lagi** — foydalanuvchi ASL matnni ko'radi |
| `detect_required(tender_texts)` | Tender matnidan majburiy hujjatlarni aniqlaydi |
| `doc_status(doc, today)` | Bitta hujjatning muddat holati |
| `_pick_best(docs, today)` | Bir turdagi bir necha hujjatdan **eng yaroqlisi** |
| `build_checklist(detected, company_docs, today)` | Bazaviy ro'yxat + tenderda topilganlari |
| `tender_texts(tender_id)` | Tenderning barcha matn manbalari (manba nomi bilan) |
| `check(tender_id, docs)` | To'liq cheklist — endpoint shuni qaytaradi |

**Hujjat shabloni (import/eksport):**

| Funksiya | Vazifa |
|---|---|
| `match_doc_type(raw)` | `"Muvofiqlik sertifikati"` → `conformity_certificate` |
| `parse_date(raw)` | Katakdan sana; `(sana, xato, muddatsizmi)` — 6 format + "muddatsiz" so'zlari |
| `template_xlsx()` / `template_csv()` | Shablon: 1-varaq hujjatlar, 2-varaq yo'riqnoma |
| `parse_document_rows(...)` | Xom jadvaldan hujjatlar + xatolar + ogohlantirishlar |
| `parse_document_file(data, filename)` | **Bazaga tegmasdan** o'qiydi va tekshiradi (ERP uchun xizmat) |
| `import_documents(data, filename, *, dry_run)` | Kompaniya hujjatlariga yozadi |
| `_is_example_row(row, mapping)` | Shablonning o'zgartirilmagan misol qatorini o'tkazib yuboradi |

### 6.15 `api/notify.py` — bildirishnoma (P0-10)

**Ikki kanal:** Email (SMTP) va Telegram (Bot API). **Mustaqil yoqiladi va
mustaqil ishlaydi** — biri buzilsa ikkinchisi ketaveradi.

**Xabar tili = platforma tili** (`notify_settings.lang`): mavzu, maydon
nomlari, moslik sabablari — hammasi `api/i18n.py` lug'atidan.

| Guruh | Funksiya | Vazifa |
|---|---|---|
| Sozlama | `get_settings()` / `save_settings(data)` | Singleton yozuv (id=1) |
| | `smtp_config()` / `smtp_ready()` | `.env` dagi SMTP; parol **qaytmaydi** |
| | `recipient(st)` | Qabul qiluvchi manzil (yo'q bo'lsa aniq xato) |
| | `telegram_columns_ready()`, `lang_column_ready()` | Patch qo'llanganmi (keshlanadi) |
| Nomzod | `last_cycle_since()` | Oxirgi ETL tsikli boshlangan payt |
| | `_fetch_candidates(since)` | Shundan keyin **birinchi marta ko'rilgan** ochiq tenderlar |
| | `score_candidate(cand, products, profile)` | Ikki manba: katalog mosligi (kategoriya=100, nom=70) **va** profil balli → **kattasi** |
| | `find_candidates(...)` | Chegaradan yuqorilar, ball bo'yicha kamayish tartibida |
| | `sent_ids(kind)` | Shu kanalda allaqachon xabar ketganlar |
| Matn | `render(tenders, base_url, threshold, lang)` | `(mavzu, matn, html)` — foydalanuvchi tilida |
| | `render_telegram(...)` | `(sarlavha, bloklar[], izoh)` |
| | `card_url(base_url, tender_id)` | **TZ talabi:** kartochkaga havola |
| | `_money`, `_dt`, `_score`, `_reasons` | Tilga bog'liq formatlash |
| Yuborish | `send(st, to, subj, text, html)` | SMTP orqali |
| | `send_telegram(chat_id, ...)` | Bitta obunachiga |
| | `mark_sent(tender_id, email, score, kind)` | Jurnal (`ON CONFLICT` = takror yo'q) |
| | `send_test(st)` / `send_telegram_test(st, chat_id)` | Sinov — **jurnalga yozmaydi** |
| Telegram | `subscribers()` / `enabled_subscribers()` | Obunachilar |
| | `create_link()` / `link_status(token)` / `consume_links()` | Bir martalik ulash (TTL 30 daq) |
| Tsikl | `run(min_score, limit, dry_run, force, since_hours)` | **Bitta to'liq tsikl** |

### 6.16 `api/telegram.py` — Bot API transporti

**Faqat transport:** token oladi, HTTP yuboradi, xatoni o'zbekcha
`TelegramError` ga aylantiradi. **Xabar matni bu yerda qurilmaydi** — u
`notify.py` ning ishi.

`API_ROOT='https://api.telegram.org'` · `MAX_MESSAGE=4096` ·
`SAFE_MESSAGE=3600` · `HTTP_TIMEOUT=20`

| Funksiya | Vazifa |
|---|---|
| `token()` / `token_set()` / `require_token()` | Bot tokeni **faqat `.env` dan** |
| `call(method, params)` | Bot API metodi → `result` |
| `get_me()` | Bot username (interfeys "qaysi botga yozish kerak" deb ko'rsatadi) |
| `esc(v)` | HTML rejimi uchun escape |
| `send_message(chat_id, text, preview)` | Bitta HTML xabar |
| `send_blocks(chat_id, header, blocks, footer)` | Bloklarni 4096 chegarasiga sig'diradi |
| `discover_chats()` | `getUpdates` — botga yaqinda yozgan suhbatlar va **matni** |
| `_uz_error(...)` | Telegram xatosini **foydalanuvchi tuzata oladigan** matnga |

### 6.17 `api/i18n.py` — server tomonidagi matnlar

`LANGS = ('uz','ru','en')` · `DEFAULT_LANG = 'uz'`

| Funksiya | Vazifa |
|---|---|
| `norm_lang(v)` | Har qanday qiymatni yaroqli til kodiga |
| `_plural(lang, n)` | Son shakli toifasi (CLDR ning kerakli qismi) |
| `t(lang, key, **vars)` | Kalitni matnga (interpolatsiya bilan) |

> Nega server: xabarni brauzer emas, **server** yuboradi (`notify_new.py`
> ETL dan keyin, foydalanuvchi ilovani ochmagan bo'lsa ham).

### 6.18 `api/erp_status.py` va `api/erp_stock.py` — ERP dan o'qish

**`erp_status.py`** — `erp.v_tender_status` view idan:
`ready()`, `for_tender(tender_id)` → ERP kartalari (ERP yo'q bo'lsa bo'sh ro'yxat).

**`erp_stock.py`** — `erp.v_stock_balance` view idan:

| Funksiya | Vazifa |
|---|---|
| `ready()` | View bormi |
| `balances()` | `{product_id: {qty, reserved, available, unit, updated_at}}` |
| `in_use()` | Ombor ishga tushganmi (`erp.stock_move` da harakat bormi) |
| `apply_to_products(products, *, bal)` | Katalog qoldig'ini **ERP hisobiga almashtiradi** |

> **Qaror:** qoldiqning EGASI — ERP. `catalog_product.stock_qty` — Excel
> importidan qolgan **surat** va u endi haqiqat manbai emas.

### 6.19 `api/main.py` — endpointlar va darvoza

#### `gate()` — kimlik darvozasi

Endpointlar **bitta joyda** yopiladi: `FastAPI(dependencies=[Depends(gate)])`.
Har funksiyaga `Depends()` qo'shilmaydi — 60+ endpoint bor, birortasi
e'tibordan chetda qolishi aniq edi.

**Ikki kirish yo'li:**
1. **Kompaniya sessiyasi** — brauzerdan (`HttpOnly` cookie yoki `Authorization: Bearer`)
2. **Service kaliti** — ERP dan (`X-Service-Key`), odam nomidan emas

**Ochiq yo'llar (`PUBLIC_PATHS`):**
`/health` · `/auth/login` · `/docs` · `/openapi.json` · `/redoc` ·
`/catalog/import/template` · `/company/documents/template`
**Ochiq prefiks:** `/documents/` (brauzerdagi `<a href>` sarlavha yubora olmaydi)

**ERP service kaliti FAQAT 7 endpointni ochadi (`SERVICE_PATHS`):**
`GET /tenders/{id}` · `GET /tenders/{id}/pricing` · `GET /tenders/{id}/stock-check` ·
`POST /tenders/{id}/compliance` · `GET /company/document-types` ·
`POST /company/documents/parse` · `POST /notify/send`

**CSRF:** `SameSite=Lax` + `X-CSRF-Token` sarlavhasi. Faqat o'zgartiruvchi
metodlar (`POST/PUT/PATCH/DELETE`) uchun va faqat **cookie** bilan kelganda.
Istisno: `/auth/logout` (eskirgan token bilan chiqa olmay qolish zararliroq).

#### Pydantic modellari

| Model | Vazifa |
|---|---|
| `LoginIn` | `username`, `password` |
| `AccountIn` | `company_name`, `password`, `current_password`, `email`, `active` |
| `ProfileIn` | Aloqa + qidiruv + salohiyat (21 maydon) |
| `SavedSearchIn` | `name`, `keywords[]`, `categories[]`, `regions[]`, `currency`, `min/max_cost`, `notify` |
| `CatalogItemIn` | `name`, `category_code`, `keywords[]`, `unit`, `price`, `currency`, `notify` |
| `CatalogMatchIn` | `region`, `currency`, `products[]`, `services[]`, `limit`, `offset` |
| `PricingSettingsIn` | 7 parametr + oraliq validatsiyasi (`_PERCENT_MAX`) |
| `PricingItemIn` | `name`, `unit`, `qty`, `unit_cost`, `currency`, `ref_price` |
| `PricingIn` | `items[]` + parametrlar + `manual_price` + `note` |
| `NotifySettingsIn` | Email + Telegram + til; **sirlar yo'q** |
| `CompanyDocumentIn` | Hujjat + validatsiya (muddat berilishdan keyin bo'lsin) |
| `ComplianceDocsIn` | ERP yuboradigan hujjatlar |
| `NotifySendIn` | `subject`, `text`, `html`, `channels[]` |
| `SubscriberIn` | `enabled` — yagona tahrirlanadigan maydon |
| `MatchIn` | `profile` + filtrlar |

#### Yordamchi funksiyalar

`_shape_tender(r)` · `_shape_document(r, tender_id)` · `_shape_profile(r)` ·
`_shape_search(r)` · `_shape_product(r)` · `_shape_pricing_settings(r)` ·
`_shape_tender_pricing(r)` · `_num(v)` (Decimal→float) · `_iso(v)` (datetime→ISO) ·
`_product_matches(cand, product)` · `_catalog_candidates(...)` ·
`_count_matches(candidates, prof)` · `client_ip(request)` (`TRUST_PROXY` bilan)

---

## 7. API endpointlar to'liq ro'yxati

> Barchasi himoyalangan, ochiqlari `🔓` bilan belgilangan.
> ERP service kaliti ochadigan endpointlar `🔑` bilan.

### Kimlik

| Metod | Yo'l | Vazifa |
|---|---|---|
| POST | 🔓 `/auth/login` | Kompaniya hisobi bilan kirish → cookie + CSRF |
| POST | `/auth/logout` | Chiqish (cookie har holda tozalanadi) |
| GET | `/auth/me` | Kim kirgan + CSRF tokeni |
| GET | `/auth/attempts` | Kirish urinishlari (`hours`, `limit`, `only_failed`) |
| GET | `/auth/account` | Hisob ma'lumotlari |
| PUT | `/auth/account` | Nom / email |
| PUT | `/auth/password` | Parol almashtirish (joriy parol majburiy) |

### Tenderlar

| Metod | Yo'l | Vazifa |
|---|---|---|
| GET | 🔓 `/health` | Baza ulanishi |
| GET | `/tenders` | Filtrlanadigan ro'yxat; jami — `X-Total-Count` header'da |
| GET | 🔑 `/tenders/{id}` | Bitta tender + lotlar + tovarlar + AI xulosa |
| GET | `/tenders/{id}/documents` | Hujjatlar ro'yxati + yuklab olish havolalari |
| GET | `/tenders/{id}/documents/text` | Hujjat matni holati (`ref`, `full`, `preview_chars`) |
| GET | `/tenders/{id}/erp-status` | Tender ERP da ishga olinganmi |
| GET | 🔓 `/documents/{tender_id}/download?ref=` | Fayl yuklab olish proksisi |
| GET | `/stats` | Dashboard ko'rsatkichlari (valyutalar **alohida**) |
| GET | `/regions` | Hudud dropdown (`parent_id` bilan kaskad) |
| GET | `/statuses` | Status dropdown |
| GET | `/categories` | Kategoriya daraxti (2 daraja) + tender soni |
| GET | `/products` | Tovar/xizmat nomlari (`q`, `kind`, `status`, `limit`) |
| GET | `/freshness` | Ma'lumot yangiligi + ETL sog'ligi |

**`/tenders` filtrlari:** `status`, `region`, `currency`, `source`, `q`,
`category`, `product[]`, `service[]`, `sort`, `limit`, `offset`

### AI

| Metod | Yo'l | Vazifa |
|---|---|---|
| POST | `/tenders/{id}/ai-match` | AI moslik tahlili (`refresh=true` — keshni chetlab o'tish) |
| POST | `/tenders/{id}/ai-gonogo` | Go / Review / No-Go, 11 mezon |

### Katalog va ombor

| Metod | Yo'l | Vazifa |
|---|---|---|
| GET | `/catalog` | Katalog + har birida mos ochiq tenderlar soni |
| POST | `/catalog` | Mahsulot qo'shish |
| PUT | `/catalog/{id}` | Tahrirlash |
| DELETE | `/catalog/{id}` | O'chirish |
| POST | `/catalog/import` | Excel/CSV import (`dry_run`, max 5 MB) |
| GET | 🔓 `/catalog/import/template?fmt=xlsx\|csv` | Bo'sh shablon |
| POST | `/catalog/match` | Katalogga mos ochiq tenderlar |
| GET | `/catalog/new-count` | Xabarnoma nishoni: yangi mos tenderlar |
| POST | `/catalog/seen` | "Ko'rildi" deb belgilash |
| GET | 🔑 `/tenders/{id}/stock-check` | Pozitsiyalar bo'yicha ombor qoldig'i |

### Narx

| Metod | Yo'l | Vazifa |
|---|---|---|
| GET | `/pricing/settings` | Odatiy parametrlar |
| PUT | `/pricing/settings` | Saqlash |
| GET | 🔑 `/tenders/{id}/pricing` | Saqlangan smeta (yo'q bo'lsa `null`, 404 emas) |
| POST | `/tenders/{id}/pricing` | Qayta hisoblaydi va saqlaydi |

### Hujjatlar va cheklist

| Metod | Yo'l | Vazifa |
|---|---|---|
| GET | 🔑 `/company/document-types` | 11 kanonik tur (dropdown) |
| GET | `/company/documents` | Hujjatlar + muddat holati |
| POST | `/company/documents` | Qo'shish |
| PUT | `/company/documents/{id}` | Tahrirlash |
| DELETE | `/company/documents/{id}` | O'chirish |
| GET | 🔓 `/company/documents/template?fmt=` | Shablon (talab ro'yxati bilan) |
| POST | `/company/documents/import` | To'ldirilgan shablonni yuklash |
| POST | 🔑 `/company/documents/parse` | **Parser xizmat sifatida** — bazaga tegmaydi |
| GET | `/tenders/{id}/compliance` | Cheklist (o'z hujjatlarimizga qarab) |
| POST | 🔑 `/tenders/{id}/compliance` | **Cheklist xizmat sifatida** — hujjatlar chaqiruvchida |

### Bildirishnoma

| Metod | Yo'l | Vazifa |
|---|---|---|
| GET | `/notify/settings` | Sozlamalar + `smtp_password_set` / `telegram_token_set` |
| PUT | `/notify/settings` | Qisman saqlash mumkin |
| POST | `/notify/test` | Email sinov (jurnalga yozmaydi) |
| POST | 🔑 `/notify/send` | **Xabar yuborish xizmat sifatida** (ERP uchun) |
| POST | `/notify/run` | Tsiklni qo'lda yurgizish (default `dry_run=true`) |
| GET | `/notify/telegram/bot` | Bot username |
| GET | `/notify/telegram/subscribers` | Obunachilar |
| POST | `/notify/telegram/link` | Bir martalik ulash havolasi |
| GET | `/notify/telegram/link/{token}` | Havola bosildimi |
| PUT | `/notify/telegram/subscribers/{chat_id}` | Yoqish/o'chirish |
| DELETE | `/notify/telegram/subscribers/{chat_id}` | O'chirish |
| POST | `/notify/telegram/test` | Telegram sinov |

### Profil va qidiruv

| Metod | Yo'l | Vazifa |
|---|---|---|
| GET | `/profile` | Faol kompaniya profili |
| PUT | `/profile` | Saqlash |
| POST | `/match` | Profilga qarab tenderlarni ballab tartiblaydi |
| GET | `/searches` | Saqlangan qidiruvlar + mos tenderlar soni |
| POST | `/searches` | Yaratish |
| PUT | `/searches/{id}` | Tahrirlash |
| DELETE | `/searches/{id}` | O'chirish |

---

## 8. ETL qatlami

### 8.1 `run_etl.py` — orkestrator

Cron / launchd / Task Scheduler **shu skriptni** chaqiradi.

```
python run_etl.py [--with-docs] [--with-rag] [--only-rag]
                  [--vector-budget N] [--all-statuses] [--limit N]
                  [--sequential] [--skip-categorize] [--skip-notify]
                  [--stale-hours 2.0]
```

**Guruhlar (platformalar parallel, guruh ichi ketma-ket):**

| Platforma | Qadamlar |
|---|---|
| `xt-xarid` | `etl_tenders.py --ref ref_tender_public` → `--ref ref_selection_public` → (`--with-docs` bo'lsa) `etl_details.py` |
| `uzex` | `etl_uzex.py --type-id 2` → `--type-id 1` |

**Post-qadamlar (barcha platformadan keyin):**
1. Muddati o'tganlarni supurish (`open` → `expired`)
2. `etl_categorize.py` — kategoriyalash
3. `etl_doc_text.py` (faqat `--with-docs` bilan)
4. `notify_new.py` — bildirishnoma

| Funksiya | Vazifa |
|---|---|
| `close_stale_runs(stale_hours)` | Muzlab qolgan `running` yozuvlarni yopadi (yurish **boshida**) |
| `expire_stale_tenders(platforms)` | Muddati o'tgan `open` → `expired` |
| `run_script(script, extra_args)` | Bola-jarayon + o'qiladigan xato sababi |
| `run_group(platform, steps, log)` | Bitta platforma ketma-ketligi + `etl_run` jurnali |
| `build_groups(args)` | Platforma → qadamlar ro'yxati |
| `emit(lines)` | Parallel guruhlar chiqishini **atomar** yozadi |

### 8.2 ETL skriptlari

#### `etl_tenders.py` — xt-xarid asosiy ETL
**Manba:** `POST https://api.xt-xarid.uz/rpc` (JSON-RPC 2.0)
**Ikki reestr:** `ref_tender_public` va `ref_selection_public` — **ID fazolari
kesishmaydi**, ikkalasi ham kerak.
`PAGE_LIMIT=51` · `REQUEST_DELAY=1.0` · `MAX_RETRIES=4` · backoff 2.0

| Funksiya | Vazifa |
|---|---|
| `rpc_call(session, params, req_id)` | Bitta chaqiruv + retry/backoff |
| `fetch_all_tenders(statuses, ref)` | limit+offset bilan to'liq sahifalash |
| `precise_close_at(raw, remain_time, fetched_at)` | Sana ko'rinishidagi muddatni **aniq vaqtga** aylantiradi |
| `transform(rec, fetched_at)` | `(tender, lots, goods, categories)` |
| `dedupe_by_key(rows, key_cols, label)` | PK bo'yicha takrorlarni olib tashlaydi |
| `load_to_db(dsn, ...)` | UPSERT |

#### `etl_uzex.py` — UzEx adapteri (2-manba)
**Manba:** `POST /api/common/TradeList`, `GET /api/common/GetTrade/{id}/0`
**`UZEX_OFFSET = 20000000000`** — ID to'qnashuvining oldini oladi.

| Funksiya | Vazifa |
|---|---|
| `jparse(v)` | UzEx ba'zi maydonlarni **JSON-string** sifatida qaytaradi |
| `to_days(term, period_name)` | `Guarantee_Term=1` + `'Год (лет)'` → 365 kun |
| `region_for(name)` | Viloyat nomi → kanonik `(area_path, area_leaf_id)` |
| `scan_documents(detail, tender_id)` | Fayl guruhlari: `<prefiks>_path` + `_name`/`_ext`/`_sizes` |
| `sync_region_names(conn)` | **Bonus:** UzEx lotincha nomlarni beradi → `dim_area.name_uz` |

#### `etl_details.py` — tafsilot va fayllar
**Manba:** `POST https://api.xt-xarid.uz/urpc`, metod `get_proc`

| Funksiya | Vazifa |
|---|---|
| `looks_like_file(node)` | `{id:<uuid>, meta:{...}}` → fayl obyekti |
| `scan_files(fields)` | `fields` ichidagi barcha fayllarni **rekursiv** topadi |
| `fval(fields, key)` | `fields[key].value` ni xavfsiz olish |
| `save(conn, detail, docs)` | Har tenderdan keyin commit (uzun yurish uzilsa ish yo'qolmaydi) |

#### `etl_lots.py` — lot nomlari va pozitsiyalar
**Nega muhim:** ko'p lotli tender nomi foydasiz (`"Многолотовая процедура"`),
lekin lot nomi aniq (`"Оборудование лазерной резки металлов 6,12,30 кВт"`).
Metodlar: `get_lots`, `get_items` (sahifa 101).

#### `etl_dims.py` — reestrlar
`ref_status_tender` (o'z metodi), `ref_area` (rekursiv, `AREA_ROOT='33'`,
`MAX_DEPTH=3`). Kuniga bir marta yetadi.

#### `etl_doc_text.py` — hujjat matni (P0-2)

| Chegara | Qiymat |
|---|---|
| `MAX_BYTES` | 25 MB |
| `MAX_CHARS` | 400 000 |
| `MIN_CHARS` / `MIN_LETTERS` | 20 / 40 (shundan kam → `empty`) |
| `PDF_MAX_PAGES` | 300 |
| `XLSX_MAX_ROWS` | 5000 |

**Qo'llab-quvvatlanadi:** `pdf` (pypdf) · `docx`/`docm` (python-docx) ·
`xlsx`/`xlsm` (openpyxl) · `txt`/`csv`/`html`/`xml`/`json`/`md` (stdlib)
**Qo'llab-quvvatlanmaydi (aniq belgilanadi):** `rar`, `zip`, `7z`, `doc`,
`xls`, `ppt`, rasm formatlari, `dwg`, `sig`, `p7s` …

> **Skanerlangan PDF:** MVP da **OCR yo'q** → `unreadable`.

| Funksiya | Vazifa |
|---|---|
| `download(session, row)` | Faylni manbadan (`_BROWSER_UA` kerak bo'lgan platformalar uchun) |
| `sniff_ext(row)` | Kengaytma: `file_type` → nom → `content_type` |
| `extract_pdf/docx/xlsx/plain(data)` | `(matn, sahifa, extractor, xato)` |
| `clean(text)` | Ortiqcha bo'shliq/qator |
| `process(session, row)` | **Har doim status bilan** qator qaytaradi |

#### `etl_categorize.py` — kategoriyalash
`seed_tree(conn)` — daraxtni `api/categories.py` dan ekadi;
`categorize(row)` — tovar kodi prefiksidan kategoriya to'plami.

#### `etl_ai_summary.py` — AI xulosa
`fetch_candidates(conn, only_open, limit)` → `ai.analyze()` → `ai_analysis`.
**Xarajat nazorati:** `content_hash` mos kelsa AI **chaqirilmaydi**.

#### `notify_new.py` — bildirishnoma
ETL dan keyin: oxirgi tsiklda **birinchi marta ko'rilgan** tenderlar orasidan
chegaradan yuqorilarini email va/yoki Telegramga yuboradi.

### 8.3 Diagnostika skriptlari

| Skript | Vazifa |
|---|---|
| `status_counts.py` | Platformadagi status taqsimoti |
| `diag_refs.py` | Qaysi reestr nomi/parametr shakli ishlaydi |
| `discover_dims.py` | Reestr strukturasini ko'rsatadi |
| `create_company.py` | Kompaniya hisobini yaratish / parol almashtirish (CLI) |

### 8.4 Rejalashtirish

| Platforma | Vosita |
|---|---|
| Windows | `register_task.ps1` → Task Scheduler, soatlik, `MultipleInstances=IgnoreNew` |
| macOS | `com.birja.etl.plist` + `run_etl.sh` (mkdir-lock) |

Jurnal: `etl_cron.log` (qo'shib yoziladi).

---

## 9. Frontend

### 9.1 `App.tsx` — asosiy ilova

**Ko'rinishlar:** `tenders` · `match` · `catalog` · `documents` · `stats` ·
`profile` · `account`

**Holat:** filtrlar, sahifalash (`PAGE_SIZE=25`), avtomatik yangilanish
(`REFRESH_MS=180000`), sessiya, tanlangan tender, manba chiplari.

**Lazy chunklar:**
- `StatsView` — Recharts (~400 KB) faqat statistika ochilganda
- `TenderDrawer` — AI, narx, cheklist, ombor panellari faqat qatorga bosilganda

**Sessiya holati uch qiymatli:** `undefined` (tekshirilmoqda) · `null`
(kirilmagan) · obyekt. Ajratilmasa sahifa har yangilanganda kirish ekrani
bir lahza chaqnab ketardi.

### 9.2 `api.ts` — backend qatlami

**Kimlik:** sessiya tokeni `localStorage` da **emas**, `HttpOnly` cookie'da.
CSRF tokeni esa ochiq cookie'da va har o'zgartiruvchi so'rovga sarlavha
sifatida qo'shiladi.

| Funksiya | Vazifa |
|---|---|
| `setCsrf` / `readCsrf` / `getToken` / `setToken` | Token boshqaruvi |
| `authHeaders()` | So'rov sarlavhalari |
| `setUnauthorizedHandler(fn)` | 401 → kirish ekraniga qaytish |
| `apiUrl(path)` | `VITE_API_BASE` (default `localhost:8000`) |
| `errMatn(detail)` | Backend xatosini o'qiladigan matnga |
| `class ApiError` | Status + detail |
| `api.*` | ~50 ta metod — barcha endpointlar |

### 9.3 Komponentlar

#### Navigatsiya va tartib
| Komponent | Vazifa |
|---|---|
| `Sidebar` | Chap navigatsiya, akkaunt bloki, nishonlar |
| `PrefsMenu` | Til va mavzu (bitta menyuda) |
| `Icon` | O'z monoxrom ikonlar to'plami (`currentColor`) |
| `ErrorBoundary` | Render xatosi **butun ilovani o'chirmasin** |
| `Pagination` | `X-Total-Count` dan hisoblangan sahifalar |

#### Tenderlar
| Komponent | Vazifa |
|---|---|
| `TenderTable` | Asosiy jadval, ball rozetkasi, deadline rangi |
| `TenderDrawer` | Yon panel — barcha tahlil bloklari |
| `Filters` | Status, hudud, valyuta, saralash, erkin qidiruv |
| `CategoryFilter` | Ikki darajali kategoriya (qidiruv + tender soni) |
| `ProductFilter` | Mahsulot/xizmat — `q` dan **ataylab alohida** |
| `SourceChips` | Manba platformasi chiplari |
| `StatsStrip` | Jadval ustidagi ixcham statistika (**animatsiyasiz**) |
| `StatsView` | To'liq statistika sahifasi (Recharts) |
| `Freshness` | Ma'lumot yangiligi + ETL sog'ligi |

#### Tahlil panellari (drawer ichida)
| Komponent | Vazifa |
|---|---|
| `AiMatch` | AI moslik — **talab bo'yicha**, avtomatik emas (har tahlil = Claude chaqiruvi) |
| `GoNoGo` | 11 mezon bo'yicha tavsiya |
| `AiDocsNote` | Tahlil qaysi hujjatlarga tayangani (**qamrov ogohlantirishi**) |
| `DocumentText` | Har fayl uchun "matni o'qildimi" |
| `StockCheck` | Pozitsiyalar bo'yicha ombor qoldig'i |
| `PricingPanel` | Narx hisobi — parametr o'zgarsa **sahifa qayta yuklanmasdan** |
| `CompliancePanel` | Hujjatlar cheklisti |
| `ErpLink` | "Bu tender ERP da ishga olinganmi" |

#### Katalog va kompaniya
| Komponent | Vazifa |
|---|---|
| `CatalogView` | Katalog jadvali + tahrirlash |
| `CatalogImport` | Fayl → **avtomatik dry-run** → ko'rish → tasdiqlash |
| `CompanyDocuments` | Hujjatlar bazasi |
| `DocumentTemplate` | Shablon orqali ommaviy kiritish |
| `CompanyProfile` | Akkaunt + profil (4 bo'lim, to'ldirilganlik ko'rsatkichi) |
| `ProfileForm` | Saqlangan qidiruv formasi |
| `AccountSettings` | Kategoriyalarga bo'lingan sozlama menyusi |
| `PasswordPanel` | Parol almashtirish (joriy parol majburiy) |
| `NotifySettings` | Email + Telegram sozlamalari |
| `LoginPage` | Kirish ekrani (uz/ru/en) |

#### `ui/` — shadcn primitivlari
`badge` · `button` · `card` · `chart` · `checkbox` · `confirm-dialog` ·
`empty` · `input` · `popover` · `progress` · `select` · `sheet` ·
`skeleton` · `slider` · `switch` · `table`

### 9.4 Yordamchi modullar

| Fayl | Vazifa |
|---|---|
| `types.ts` | Backend javob turlari — **mantiq yo'q**; backend maydonni o'zgartirsa xato **kompilyatsiyada** chiqadi |
| `format.ts` | `money`, `shortMoney`, `dateFmt`, `fileSize`, `sourceUrl`, `ago`, `deadline` — **`t` va `locale` ni parametr sifatida oladi** |
| `pricing.ts` | `api/pricing.py` ning aynan nusxasi (brauzer uchun) |
| `i18n.tsx` | `I18nProvider`, `useT`, `translate` — `Intl.PluralRules` bilan |
| `theme.tsx` | Yorug'/qorong'i/tizim; ranglar CSS o'zgaruvchilarida |
| `locales/uz\|ru\|en.ts` | ~600 kalit. `ru`/`en` — `Record<keyof typeof uz, string>`: kalit qo'shilib tarjima qilinmasa **`tsc` xato beradi** |

---

## 10. Konfiguratsiya (.env)

| O'zgaruvchi | Default | Vazifa |
|---|---|---|
| `XT_DB_DSN` | — | PostgreSQL DSN (**majburiy**, ETL ham shuni o'qiydi) |
| `DB_POOL_MIN` / `DB_POOL_MAX` | 1 / 8 | Connection pool |
| `ANTHROPIC_API_KEY` | — | Claude kaliti. **Bo'sh bo'lsa AI o'chadi, tizim ishlaydi** |
| `AI_EFFORT` | `medium` | Xulosa uchun reasoning darajasi |
| `AI_MATCH_EFFORT` | `medium` | Moslik tahlili |
| `AI_GONOGO_EFFORT` | `high` | Go/No-Go |
| `AI_DOC_CHARS` | `45000` | Hujjat matni byudjeti |
| `CORS_ORIGINS` | — | Bo'sh bo'lmasa CORS yoqiladi |
| `SMTP_HOST` / `PORT` / `USER` / `PASSWORD` / `FROM` / `TLS` | — / 587 / … / 1 | Email. **Parol faqat shu yerda** |
| `TELEGRAM_BOT_TOKEN` | — | Bot tokeni. **Bazada saqlanmaydi** |
| `ERP_SERVICE_KEY` | — | ERP service kaliti. Bo'sh bo'lsa `verify_service` **har doim false** |
| `AUTH_COOKIE_SECURE` | `1` | HTTPS talab qiladi (lokal ishda `0`) |
| `AUTH_SESSION_DAYS` | `14` | Sessiya muddati |
| `AUTH_ATTEMPT_WINDOW_MIN` | `15` | Bloklash oynasi |
| `AUTH_MAX_ATTEMPTS` | `5` | Login bo'yicha chegara |
| `AUTH_MAX_ATTEMPTS_IP` | `25` | IP bo'yicha chegara |
| `AUTH_ATTEMPT_KEEP_DAYS` | `90` | Jurnal saqlash muddati |
| `AUTH_PASSWORD_MIN` | `10` | Minimal parol uzunligi |
| `TRUST_PROXY` | `0` | `X-Forwarded-For` ga ishonilsinmi |
| `STOCK_STALE_DAYS` | `14` | Qoldiq eskirganlik chegarasi |

**Frontend (`frontend/.env`):** `VITE_API_BASE` — backend manzili.

> **Sirlar qoidasi:** SMTP paroli va Telegram tokeni **bazada saqlanmaydi**.
> API faqat `smtp_password_set` / `telegram_token_set` (bor/yo'q) qaytaradi.

---

## 11. Ishga tushirish

### 11.1 Baza

```bash
createdb xtxarid
psql xtxarid -f xt_xarid_schema.sql
for f in schema_patch_*.sql; do psql xtxarid -f "$f"; done
```

### 11.2 Backend

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-api.txt
cp .env.example .env          # va XT_DB_DSN ni to'ldiring
.venv/Scripts/uvicorn api.main:app --reload --port 8000
# Swagger: http://localhost:8000/docs
```

### 11.3 Kompaniya hisobi

```bash
.venv/Scripts/python create_company.py alfa "Alfa Savdo MChJ"
.venv/Scripts/python create_company.py alfa --password    # parol almashtirish
.venv/Scripts/python create_company.py --list
```

### 11.4 Frontend

```bash
cd frontend
npm install
npm run dev          # :5173
npm run build        # tsc -b --noEmit && vite build
npm run typecheck
```

### 11.5 Hammasi bitta buyruqda (Windows)

```powershell
.\run_all.ps1              # backend + frontend + ngrok tunnel
.\run_all.ps1 -NoTunnel    # faqat mahalliy
.\run_all.ps1 -Stop        # to'xtatish
```

> Arxitektura: `brauzer → ngrok → Vite :5173 → (/api proksi) → FastAPI :8000`.
> Backend tashqariga ochilmaydi, shuning uchun CORS ham kerak emas.

### 11.6 ETL

```bash
python run_etl.py                    # tez yurish
python run_etl.py --with-docs        # hujjatlar + matn (sekin)
python run_etl.py --limit 50         # sinov
python run_etl.py --sequential       # ketma-ket (nosozlik qidirishda)
```

Soatlik vazifa (Windows):
```powershell
.\register_task.ps1 -IntervalMinutes 60
```

---

## 12. Sinovlar

Baza va server **kerak emas** — sinovlar sof funksiyalarni to'g'ridan-to'g'ri
chaqiradi.

| Fayl | Sinovlar | Nimani tekshiradi |
|---|---|---|
| `_tests/pricing_test.py` | 26 | Narx formulasi + **Python ↔ JavaScript aynanligi** (Node orqali) |
| `_tests/notify_test.py` | 29 | Bildirishnoma: nomzod tanlash, tillar, Telegram bloklari, jurnal |
| `_tests/import_test.py` | 11 | Katalog importi: sarlavha aniqlash, son parseri, qator xatolari |
| `_tests/compliance_test.py` | 5 | Cheklist: talab aniqlash, muddat holati, dalil |
| `_tests/doctext_test.py` | 5 | Matn ajratish: PDF/DOCX/XLSX/HTML, chegaralar |
| `_tests/etl_coverage_test.py` | 5 | ETL qamrovi, status lug'ati to'liqligi |
| `_tests/auth_test.py` | 43 tekshiruv | Parol, sessiya, CSRF, bloklash |

```bash
.venv/Scripts/python _tests/pricing_test.py
.venv/Scripts/python -m pytest _tests/ -q      # pytest bo'lsa
```

> **Eng muhim sinov:** `test_javascript_bilan_bir_xil` — narx formulasi ikki
> tilda yozilgan, bu sinov ular chetga chiqishini ushlaydi.

---

## 13. Xavfsizlik modeli

| Qatlam | Yechim |
|---|---|
| **Parol** | pbkdf2_sha256, 240 000 iteratsiya, algoritm ustunda saqlanadi (migratsiyasiz almashtirish) |
| **Sessiya tokeni** | Bazada **xesh**; brauzerda `HttpOnly` cookie — XSS bo'lsa ham JS o'qiy olmaydi |
| **CSRF** | `SameSite=Lax` + `X-CSRF-Token` sarlavhasi; faqat o'zgartiruvchi metodlar va faqat cookie uchun |
| **Bloklash** | 15 daqiqada 5 urinish (login) / 25 (IP) → **429, parol tekshirilmasdan** |
| **Jurnal** | `login_attempt` — parol yozilmaydi; muvaffaqiyatli kirish zanjirni uzadi |
| **SQL injection** | Barcha qiymat named-param; `ORDER BY` — whitelist |
| **Darvoza** | Yopiq holatda boshlanadi; ochiqlar sanoqli va sababi yozilgan |
| **ERP kaliti** | Faqat 7 endpoint; `403` (401 emas) — kimligi ma'lum, huquqi yetmaydi |
| **Sirlar** | SMTP paroli va bot tokeni **faqat `.env`**; API "bor/yo'q" qaytaradi |
| **Doimiy vaqt** | `hmac.compare_digest` — parol ham, service kaliti ham, CSRF ham |
| **Proksi** | `TRUST_PROXY=0` bo'lsa `X-Forwarded-For` ga ishonilmaydi |

---

## 14. ERP bilan chegara

Tender-AI va ERP — **ikki mustaqil loyiha**, bitta bazada ikki sxema.

```
tender-ai (public.*)              ERP (erp.*)
     │                                 │
     ├── erp.v_tender_status ─────O'QIYDI
     ├── erp.v_stock_balance ─────O'QIYDI
     │                                 │
     │◄──── X-Service-Key bilan 7 endpoint
     │      (cheklist, parser, xabar, tender, narx, ombor)
```

| Kim | Nima qiladi |
|---|---|
| **Tender-AI → ERP** | Faqat **O'QIYDI**: `v_tender_status`, `v_stock_balance`, `stock_move` |
| **ERP → Tender-AI** | `X-Service-Key` bilan 7 endpoint: tender ma'lumoti, narx, ombor moslashuvi, cheklist qoidasi, hujjat parseri, xabar yuborish |
| **Hech biri** | Bir-birining jadvaliga **YOZMAYDI** |

**Tushunchalar taqsimoti:**
- **Odam** — ERP niki (`erp.app_user`, `erp.broker`). Kim mas'ul, kim shartnoma imzoladi.
- **Kompaniya** — Tender-AI niki (`company_account`). Kim tizimga kiradi.
- **Ombor qoldig'i** — ERP niki (harakatlar jurnali u yerda). Bizdagi `stock_qty` — Excel importidan qolgan surat.

Batafsil: `docs/erp_arxitektura.md`, `docs/erp_texnik.md`, `docs/erp_bosqichlar.md`.

---

## 15. Loyiha holati va keyingi qadamlar

### 15.1 Bajarilgan (REJA.md bosqichlari)

| Bosqich | Nima | Holat |
|---|---|---|
| **A** | Auth + kompaniya hisobi, sessiya, CSRF, bloklash | ✅ Bajarildi (multi-tenancy filtri qolgan) |
| **B** | Ombor katalogi, Excel import, qator xatolari, eskirganlik | ✅ Bajarildi |
| **C** | Hujjat matni (PDF/DOCX/XLSX/HTML) | ✅ Bajarildi (OCR yo'q) |
| **D** | Talab ajratish (strukturali `tender_requirement`) | ⚠️ Qisman — AI hujjat matnini o'qiydi, lekin alohida jadval yo'q |
| **E** | Matching Engine (talab ↔ katalog) | ⚠️ Qisman — `stock-check` + `ai-match` bor, `match_run`/`match_line` yo'q |
| **F** | Narx hisobi | ✅ Bajarildi |
| **G** | Hujjatlar cheklisti | ✅ Bajarildi |
| **H** | Soatlik ETL + `etl_run` + bildirishnoma | ✅ Bajarildi |
| **I** | Broker dashboard | ⚠️ Qisman — saralash/filtr bor, ish jarayoni holati (`tender_decision`) yo'q |

### 15.2 Ataylab qilinmagan (MVP chekloviari)

| Nima | Nega |
|---|---|
| **OCR** | Skanerlangan PDF ulushi o'lchanmagan; ulush yuqori chiqsa qo'shiladi |
| **Fayl saqlash** | Hozir faqat **havola** saqlanadi, faylning o'zi emas (A2) |
| **Fon-ishchi (queue)** | Hujjat qayta ishlash ETL ichida, web-so'rovda emas |
| **Huquqiy tekshiruv** | Cheklist hujjat **mazmunini** tekshirmaydi — bu ataylab |
| **Multi-tenancy filtri** | `company_id` ustunlari bor, lekin hozir **bitta kompaniya rejimi** |

### 15.3 Keyingi qadamlar

1. **`tender_requirement`** jadvali — AI ajratgan talablarni `confidence` va
   `raw_snippet` bilan saqlash (D bosqich to'liq)
2. **`match_run` / `match_line`** — solishtiruv natijasini saqlash va tarixni
   ko'rish (E bosqich to'liq)
3. **`tender_decision`** — ish jarayoni holati (`new` / `evaluating` /
   `decided_go` / `decided_skip`) va aniq tasdiqlash tugmasi (I bosqich)
4. **`company_id` filtri** — barcha kompaniya jadvallarida (A bosqichning qolgani)
5. **Fayl saqlash qatlami** — lokal disk yoki S3-mos ombor (A2)
6. **AI kengaytmasi (J1–J9)** — semantik qidiruv va AI-Chat.
   Reja: [reja_ai_chat.md](reja_ai_chat.md) · Sxema: `schema_patch_ai_chat.sql` ·
   Kod: [api/ai_chat.py](api/ai_chat.py). **Tanqidiy yo'l:** J1 (`company_id`
   filtri) → J2 (embedding) → J4 (chat endpointlari).

### 15.4 Ochiq savollar (REJA.md 6-bo'lim)

| Savol | Kimga | Nimani bloklaydi |
|---|---|---|
| Real broker Excel faylida qanday ustunlar bor? | Buyurtmachi | Katalog shabloni (B) |
| Pilot broker kim, ombor/narx ma'lumotini qachon beradi? | Buyurtmachi | B, E — sifatni o'lchash |
| Platformalar foydalanish shartlari huquqiy tekshiruvi | Legal | **Ishga tushirish** |
| Bildirishnoma uchun qaysi % "yuqori"? | Product | H (standart qiymat) |
| Hujjatlarni saqlash muddati | Legal/Product | A2, C (ombor hajmi) |

### 15.5 Xavflar

| Xavf | Daraja | Yumshatish |
|---|---|---|
| **Rasmiy API yo'q** — hujjatlashtirilmagan ichki API | Yuqori | Ishga tushirishdan oldin **huquqiy tekshiruv majburiy** |
| Platforma tuzilishi o'zgaradi | O'rta-yuqori | `etl_run` monitoring + buzilishda xabar. **Allaqachon uchradik:** har xil kalit registri, brauzer User-Agent talabi |
| AI talab ajratishda xato | Yuqori (moliyaviy) | `confidence` + dalil bo'lagi + inson tasdig'i |
| Skanerlangan hujjatlar | O'rta | MVP da OCR yo'q → aniq status |
| Narx formulasining ikki nusxasi chetga chiqadi | O'rta | Node bilan solishtiruvchi sinov |

---

## Qo'shimcha hujjatlar

| Fayl | Mazmuni |
|---|---|
| `REJA.md` | TZ ga o'tish rejasi — bosqichlar A–I, ochiq savollar, xavflar |
| `reja_ai_chat.md` | AI kengaytmasi — semantik qidiruv va AI-Chat (J1–J9) |
| `UPDATED.md` | O'zgarishlar tarixi |
| `AVTOMATLASHTIRISH.md` | ETL avtomatlashtirish qo'llanmasi |
| `REJA_UX.md` | Interfeys rejasi |
| `docs/erp_arxitektura.md` | ERP moduli qayerda va qanday chegaralar bilan quriladi |
| `docs/erp_texnik.md` | ERP ning texnik qurilishi |
| `docs/erp_bosqichlar.md` | ERP bosqichlari: maqsad → qilinadi → QILINMAYDI → mezon |
| `docs/erp_integratsiya*.md` | ERP integratsiya qadamlari |
| `docs/integration/*.md` | Har modul uchun integratsiya qadamlari (compliance, doctext, etl, import, notify, notify_lang, notify_telegram, pricing) |
