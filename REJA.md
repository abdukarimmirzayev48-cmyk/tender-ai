# VESCO Tender Intelligence — TZ ga o'tish rejasi

**Sana:** 2026-07-22 · **Asos:** `тз.docx` (PRD/TZ v0.1, MVP) · **Holat:** kelishuv uchun

---

## 0. Qayerdamiz va qayerga boryapmiz

**Hozir:** tenderlarni topish va ko'rish uchun **agregator**.
**TZ:** brokerning ish jarayonini avtomatlashtirish — agregatsiya u yerda faqat *kirish*.

```
HOZIRGI:   platformalar → ETL → PostgreSQL → FastAPI (ochiq) → dashboard
                                                              (ko'rish)

TZ TALAB QILADI:
platformalar → Scout (soatlik + sog'liq) → DB
                                            ↓
                          Document Analyzer (yuklab olish → matn → AI)
                                            ↓
                          Requirement Extractor (talablar + ishonch darajasi)
                                            ↓
   kompaniya Excel katalogi → Inventory → MATCHING ENGINE (talab ↔ katalog)
                                            ↓
                          Cost Calculator → tavsiya narx
                                            ↓
                          Compliance cheklist
                                            ↓
              FastAPI (AUTENTIFIKATSIYA + ko'p-ijarachi) → broker dashboard
                                            ↓
                          Email bildirishnoma
```

**Tub farq:** mahsulotning qiymati endi *"tender topish"* emas, *"bu tenderга ariza berish
foydalimi va nechi pulga?"* degan savolga javob berish.

---

## 1. Arxitekturaviy o'zgarishlar (kod yozishdan oldingi qarorlar)

| # | O'zgarish | Nega majburiy |
|---|---|---|
| A1 | **Autentifikatsiya + ko'p-ijarachilik (multi-tenancy)** | Ombor qoldig'i, tannarx, ustama — **kompaniya siri**. TZ: "uchinchi shaxslarga uzatilmaydi". Hozir API butunlay ochiq. Barcha yangi jadvallar `company_id` bilan bo'linadi |
| A2 | **Fayl saqlash qatlami** | TZ asl fayllarni saqlashni talab qiladi. Hozir faqat **havola** saqlaymiz. Kerak: lokal disk (MVP) yoki S3-mos ombor |
| A3 | **Fon-ishchi (background worker)** | Hujjat yuklab olish → matn ajratish → AI — sekin (daqiqalar). Web-so'rovni bloklamasligi kerak. Navbat + holat kerak |
| A4 | **AI qatlamining kengayishi** | Hozirgi 5a — *ko'rish* uchun xulosa. Kerak: **hujjatga asoslangan** talab ajratish + **ishonch darajasi** (TZ: gallyutsinatsiya = moliyaviy xavf) |
| A5 | **Dashboard qayta yo'naltirish** | Hozir tadbirkorga. Kerak: brokerga — % moslik bo'yicha saralash, ish jarayoni holati, solishtiruv natijasi ekrani |

---

## 2. Ma'lumot modeli — yangi jadvallar

```
-- A1: ko'p-ijarachilik
company(id, name, tin, created_at)
company_account(id, username, company_name, password_hash, ...)
-- ESLATMA: hodim hisoblari BU YERDA EMAS - ular ERP da (erp.app_user).

-- P0-4: katalog va qoldiqlar
catalog_product(id, company_id, sku, name, unit, cost_price, currency,
                attrs JSONB, stock_qty, stock_updated_at)
import_batch(id, company_id, filename, rows_total, rows_ok, rows_error, created_at)
import_error(batch_id, row_no, column_name, message)      -- qator bo'yicha xato

-- P0-2: hujjat matni
document_text(tender_id, file_ref, status, text, pages, extracted_at, error)
   status: ok | unreadable | too_large | manual_check

-- P0-3: ajratilgan talablar
tender_requirement(id, tender_id, lot_id, source, position_no, name, attrs JSONB,
                   qty, unit, delivery_days, is_mandatory, confidence, raw_snippet)
   source: api | document      is_mandatory: GOST/sertifikat kabi
   confidence: 0..1            raw_snippet: shaffoflik uchun asl matn

-- P0-5, P0-6: solishtirish
match_run(id, company_id, tender_id, created_at, catalog_snapshot_at, status)
match_line(run_id, requirement_id, product_id, score, status,
           stock_qty, stock_enough, reason)
   status: full | partial | none

-- P0-7: narx
pricing(match_run_id, cost_total, margin_pct, risk_pct, price_total,
        params JSONB, edited_by, updated_at)

-- P0-8: cheklist
company_document(company_id, kind, name, valid_until)     -- kompaniya hujjatlar bazasi
tender_checklist(tender_id, company_id, item, required, present)

-- P0-11: ish jarayoni (qarorni FAQAT inson qabul qiladi)
tender_decision(company_id, tender_id, status, decided_by, decided_at, note)
   status: new | evaluating | decided_go | decided_skip

-- P0-1 NFT: kuzatuv sog'ligi
etl_run(id, source_platform, started_at, finished_at, status, found, new, error)

-- P0-10: bildirishnoma
notify_setting(company_id, min_score, email)
notification(id, company_id, tender_id, kind, channel, sent_at)
```

Mavjud jadvallar (`tender`, `tender_lot`, `tender_item`, `tender_document`, `dim_*`)
**o'zgarmaydi** — ular umumiy (kompaniyaga bog'liq emas) ma'lumot.

---

## 3. Bosqichlar

Tartib **bog'liqlik** bo'yicha: har bosqich o'zidan oldingisiga tayanadi.

### A — Poydevor: auth + ko'p-ijarachilik  *(P0-11 qisman)*

> **HOLAT (bajarildi, qisman):** kirish mexanizmi bor —
> `schema_patch_auth_2.sql` (`company_account`, `company_session`),
> `api/auth.py`, `/auth/*` endpointlari, `create_company.py` CLI.
> Sinov: `_tests/auth_test.py` (43 tekshiruv).
>
> Quyidagi reja `app_user` ni SHU YERDA ko'zlagan edi — bu o'zgardi:
> **hodimlar ERP niki** (`erp.app_user`), bu yerda esa KOMPANIYA hisobi.
> Sabab: odam — ERP ning tushunchasi. Batafsil:
> `tender erp/docs/erp_auth.md` 1-bo'lim.
>
> **AUTH-2 (bajarildi):** kirish ekrani (uz/ru/en) va **global darvoza**
> qo'shildi — `FastAPI(dependencies=[Depends(gate)])`. Endpointlar
> YOPIQ holatda boshlanadi; ochiq qolganlar `PUBLIC_PATHS` da sanalgan
> (health, login, Swagger, bo'sh shablonlar, hujjat yuklab olish).
> ERP bu yerga `X-Service-Key` bilan keladi va kalit faqat 6 endpointni
> ochadi. Batafsil: `tender erp/docs/erp_auth.md` 8-bo'lim.
>
> **AUTH-3:** `api/erp_status.py` qo'shildi — tender panelidagi ERP bloki
> endi ERP backendiga HTTP yubormaydi, `erp.v_tender_status` view ini
> o'qiydi (faqat o'qish). Chegara simmetrik: har ikki tomon bir-birining
> sxemasidan O'QIYDI, hech biri YOZMAYDI.
>
> Qolgani (`company_id` bo'yicha ko'p-ijarachilik filtri) — keyingi
> bosqich; hozir bitta kompaniya rejimi.

Hech qanday kompaniya ma'lumoti usiz kirita olmaydi.
- `company`, `app_user` jadvallari; parol hash (bcrypt/argon2)
- Sessiya yoki JWT; barcha yangi endpointlar `company_id` bo'yicha filtrlanadi
- Mavjud ochiq endpointlar (tender ko'rish) ochiq qolishi mumkin — qaror kerak
- **Natija:** kompaniya ro'yxatdan o'tadi va kiradi

### B — Ombor katalogi  *(P0-4)*
- Standart Excel/CSV shablon: `nomi, xususiyatlar, o'lchov birligi, qoldiq, tannarx`
- Import endpoint + **qator bo'yicha xato ko'rsatish** (TZ talabi)
- `stock_updated_at` → N kundan eski bo'lsa interfeysda **ogohlantirish**, solishtiruv "dastlabki" deb belgilanadi (TZ chegaraviy holat)
- **Natija:** broker o'z katalogini yuklaydi va ko'radi

### C — Hujjat matnini o'qish  *(P0-2)*
- Fayllarni yuklab olish va saqlash (A2)
- Matn ajratish: PDF (`pypdf`/`pdfplumber`), DOCX (zip+XML), XLSX (`openpyxl`), ZIP/RAR ichini ochish
- **O'qib bo'lmaydigan fayl → `manual_check`**, jimgina o'tkazib yuborilmaydi (TZ chegaraviy holat)
- Skanerlangan PDF: MVP da OCR **yo'q** → `manual_check`
- **Natija:** 2595 hujjatning matni bazada

### D — Talab ajratish  *(P0-3)*
- Claude: hujjat matni + API pozitsiya ma'lumoti → **tuzilgan talablar**
- Har talabda: `is_mandatory` (GOST/sertifikat) va **`confidence`**
- Past ishonch → "past ishonch" holati, **bo'sh natija emas** (TZ talabi)
- `raw_snippet` saqlanadi — shaffoflik uchun ("qora quti bo'lmasin")
- **Natija:** har tenderда tuzilgan talablar ro'yxati

### E — Matching Engine  *(P0-5, P0-6)*  ⭐ mahsulotning yuragi
- Talab ↔ katalog: nom + xususiyat + o'lchov birligi bo'yicha
- Har pozitsiyada **% moslik** va holat: `to'liq / qisman / mos emas`
- Qoldiq yetarliligi; **yetishmayotganlar alohida ro'yxatda**
- Solishtiruv qaysi ma'lumotga asoslanganini ko'rsatish
- **Natija:** "bu tenderда 8 pozitsiyadan 6 tasi bor, 2 tasi yetishmaydi"

### F — Narx hisobi  *(P0-7)*
- `tannarx + ustama % + xavf zaxirasi %`
- Formula **ko'rinadi va tahrirlanadi**; parametr o'zgarsa sahifa qayta yuklanmasdan qayta hisoblanadi

### G — Hujjatlar cheklisti  *(P0-8)*
- Talablardan kelib chiqadigan majburiy hujjatlar ro'yxati (MVP da **statik**, huquqiy tekshiruvsiz)
- `company_document` bilan solishtirib "bor / yo'q"

### H — Avtomatlashtirish + bildirishnoma  *(P0-1, P0-10)*
- Har platforma uchun **soatlik** cron/systemd
- `etl_run` sog'liq jadvali; **buzilish → mas'ulga xabar** (TZ: jimgina o'tkazib yuborilmasin)
- Moslik chegarasidan yuqori yangi tender → **email**, kartochkaga havola bilan

### I — Broker dashboard  *(P0-9 qayta yo'naltirish, P0-11)*
- % moslik va topshirish muddati bo'yicha saralash/filtr
- Ish jarayoni holati: `yangi / baholanmoqda / qaror qabul qilingan`
- **Aniq tasdiqlash tugmasi** — qarorni faqat inson qabul qiladi
- Solishtiruv natijasi ekrani (E+F+G birga)

---

## 4. Tartib bo'yicha izoh

**Nega A birinchi:** B dan boshlab hamma narsa kompaniya maxfiy ma'lumoti. Auth'siz
qurish — keyin hamma endpointni qayta yozish demak.

**Nega C, D dan oldin:** talab ajratish uchun matn kerak. Matn yo'q — ajratadigan narsa yo'q.

**Nega E markazda:** B (katalog) va D (talablar) — uning ikki kirishi. Ikkalasisiz E ma'nosiz.
TZ ning butun qiymat gipotezasi shu bosqichда tekshiriladi.

**F, G, H, I — E dan keyin** istalgan tartibda; ular mustaqil.

---

## 5. Bizda bor va saqlanadi

- 3 platforma ETL (TZ 1–2 talab qiladi — ortiqchasi zarar qilmaydi, lekin **yangisini qo'shmaymiz**)
- 863 protsedura, 2595 hujjat **metadata + yuklab olish havolasi** (C uchun tayyor kirish)
- Lot nomlari, pozitsiya xususiyatlari, yetkazish/kafolat muddatlari (D uchun qimmatli)
- Birlashtirilgan hudud taksonomiyasi
- 5a AI xulosa/teglar — **saqlanadi**, lekin bu *ko'rish* uchun; D *qaror* uchun alohida quriladi

---

## 6. Bloklovchi ochiq savollar

Bularsiz tegishli bosqichni **boshlab bo'lmaydi**:

| Savol | Kimga | Nimani bloklaydi |
|---|---|---|
| Excel katalog shabloni — **real broker faylida qanday ustunlar bor?** | Buyurtmachi | **B** — taxmin bilan qurish = qayta yozish |
| Pilot broker kim, ombor/narx ma'lumotini qachon beradi? | Buyurtmachi | **B, E** — real ma'lumotsiz moslashtirish sifatini o'lchab bo'lmaydi |
| Platformalarning foydalanish shartlari huquqiy tekshiruvi | Legal | **Ishga tushirish** (texnik emas, huquqiy) |
| Email bildirishnoma uchun qaysi % "yuqori"? | Product | **H** (standart qiymat) |
| Hujjatlarni saqlash muddati | Legal/Product | **A2, C** (ombor hajmi) |
| Ochiq tender ko'rish qismi autentifikatsiyasiz qolsinmi? | Product | **A** (qamrov) |

---

## 7. Xavflar (TZ dan + o'zimizniki)

| Xavf | Daraja | Yumshatish |
|---|---|---|
| **Rasmiy API yo'q** — hujjatlashtirilmagan ichki API'lardan foydalanamiz | Yuqori | TZ: ishga tushirishdan oldin **huquqiy tekshiruv majburiy**. Platforma operatori bilan rasmiy kelishuv afzal |
| Platforma tuzilishi o'zgaradi | O'rta-yuqori | `etl_run` monitoring + buzilishда xabar (H bosqichda hal bo'ladi). **Allaqachon uchradik**: platformalar texnik xususiyatlarni har xil kalit registrida qaytaradi; ba'zilari brauzer User-Agent'ini talab qiladi |
| AI talab ajratishда xato | Yuqori (moliyaviy) | `confidence` + `raw_snippet` + inson tasdig'i (D, I) |
| Skanerlangan hujjatlar o'qilmaydi | O'rta | MVP da OCR yo'q → `manual_check`. Ulush yuqori chiqsa OCR qo'shiladi |
| Katalog shabloni noma'lum | O'rta | B ni real fayl kelmaguncha boshlamaslik |

---

## 8. Keyingi qadam

1. 6-bo'limdagi **bloklovchi savollarni** kelishish (avvalo katalog shabloni va pilot broker)
2. **A bosqich** (auth + ko'p-ijarachilik) — u hech narsaga bog'liq emas, darhol boshlanishi mumkin
3. Parallel: **C bosqich** (hujjat matni) — u ham kompaniya ma'lumotiga bog'liq emas

> A va C — yagona bosqichlarki, ochiq savollarga javob **kutmasdan** boshlash mumkin.
