# Interfeys qulayligi rejasi — saqlangan qidiruv, kategoriya, xabarnoma

**Sana:** 2026-07-22 · **Kontekst:** foydalanuvchi so'rovi — kategoriyalar,
xizmat/mahsulot bo'yicha umumlashtirish, izlash+saqlashni optimallashtirish,
saqlangan bo'yicha xabarnoma. · **AI kaliti:** hali YO'Q.

---

## 0. Asosiy g'oya

Hozir: bitta **profil** (kalit so'zlar) → `/match` tartiblaydi.
Kerak: bir nechta **saqlangan qidiruv** → har biri o'z filtri + mos tenderlar
soni + yangi tender chiqsa xabarnoma.

```
Saqlangan qidiruv "Kompyuter texnikasi"
   ├─ kalit so'zlar: kompyuter, monoblok, printer
   ├─ kategoriya: kompyuter-texnika        (AI bo'lsa)
   ├─ hudud: Toshkent shahri
   ├─ narx: 1–500 mln
   └─ → 12 ta mos (3 tasi YANGI) → 🔔 xabarnoma
```

---

## 1. AI KALITIGA BOG'LIQLIK (eng muhim qaror)

| Funksiya | Kalitsiz | Kalit bilan |
|---|---|---|
| Saqlangan qidiruv (A) | ✅ To'liq | ✅ (o'zgarmaydi) |
| Kategoriya filtri (B) | 🟡 Faqat mc.uz qurilish turlari | ✅ 3 platforma birlashgan (22 kanonik teg) |
| Yangi-mos belgisi (C) | ✅ To'liq | ✅ (aniqroq — sinonimlar bilan) |
| Qidiruv UX (D) | ✅ To'liq | ✅ |

**Xulosa:** A, C, D — darhol quriladi. B — ikki qavatli: kalitsiz mc.uz
turlari, kalit kelgach 5a taksonomiyasi avtomatik ulanadi (kod bir xil,
faqat ma'lumot boyiydi).

---

## 2. Ma'lumot modeli — yangi jadvallar

```sql
-- A: saqlangan qidiruvlar (profil'ning ko'p-nusxali kengaytmasi)
saved_search(
    id           SERIAL PK,
    company_id   BIGINT,          -- auth kelganда (hozir NULL = yagona foydalanuvchi)
    name         TEXT,            -- "Kompyuter texnikasi"
    keywords     TEXT[],
    categories   TEXT[],          -- kanonik teglar (AI) yoki mc turlari
    regions      TEXT[],          -- area kodlari
    currency     TEXT,
    min_cost     NUMERIC,
    max_cost     NUMERIC,
    notify       BOOLEAN DEFAULT true,   -- xabarnoma yoqilganmi
    last_seen_at TIMESTAMPTZ,     -- C uchun: shu vaqtdan keyin kelgani "yangi"
    created_at   TIMESTAMPTZ DEFAULT now()
)

-- C: xabarnoma jurnali (takror yubormaslik + tarix)
search_hit(
    saved_search_id INT REFERENCES saved_search(id) ON DELETE CASCADE,
    tender_id       BIGINT REFERENCES tender(id) ON DELETE CASCADE,
    score           INT,
    first_seen_at   TIMESTAMPTZ DEFAULT now(),
    notified_at     TIMESTAMPTZ,     -- email yuborilganmi (H bosqich)
    PRIMARY KEY (saved_search_id, tender_id)
)

-- B: kategoriya lug'ati (dropdown + normalizatsiya)
dim_category_uz(
    code       TEXT PK,          -- 'kompyuter-texnika' (AI taksonomiyasi bilan bir xil)
    name_uz    TEXT,             -- "Kompyuter texnikasi"
    icon       TEXT,             -- ixtiyoriy
    sort_order INT
)
```

Mavjud `profile` jadvali → `saved_search`ning bitta yozuviga migratsiya
qilinadi (yo'qolmaydi).

---

## 3. Bosqichlar

### A — Saqlangan qidiruvlar  *(kalitsiz, poydevor)*
**Backend:**
- `saved_search` CRUD: `GET/POST/PUT/DELETE /searches`
- `GET /searches/{id}/match` — o'sha qidiruv bo'yicha `/match` (mavjud matching qayta ishlatiladi)
- Har `GET /searches` javobida `match_count` (nechta mos)

**Frontend:**
- Sidebar'да "Saqlangan qidiruvlar" ro'yxati (nom + mos soni)
- "Joriy filtrni saqlash" tugmasi (nom so'raydi)
- Bosilsa → filtr qo'llanadi + "Sizga mos" ko'rinishi
- Tahrirlash / o'chirish

**Natija:** foydalanuvchi bir nechta qidiruvni saqlaydi va bir bosishда qайtadi.

### B — Kategoriyalar  *(ikki qavatli)*
**Ma'lumot manbai:**
- `tender_category(tender_id, code, source)` — normalizatsiyalangan teg
  - `source='mc'`: mc.uz service_type/object_type → kanonik teg (qo'lda xarita)
  - `source='ai'`: 5a `category_tags` (kalit kelgach `etl_ai_summary` to'ldiradi)
- Yagona `GET /categories` → dropdown (dim_category_uz'dan, faqat mavjud teglar)

**Backend:**
- `/tenders` va `/match` ga `category` filtri (`tender_category` bo'yicha EXISTS)

**Frontend:**
- Filtrlar qatoriga **kategoriya dropdown/chiplar**
- Saqlangan qidiruvда ham kategoriya tanlanadi

**Kalitsiz holat:** faqat mc tenderlarida kategoriya bo'ladi (qurilish turlari).
xt-xarid/etender "kategoriyasiz" — ular kalit kelgach to'ladi.

### C — Yangi-mos belgisi + xabarnoma  *(kalitsiz, A ga bog'liq)*
**Mexanizm:**
- Har ETL yurgandan keyin (yoki so'ralganда) har `saved_search` uchun mos
  tenderlarni hisoblab `search_hit`ga yozadi
- `first_seen_at > last_seen_at` bo'lganlar = **YANGI**
- Foydalanuvchi qidiruvni ochsa `last_seen_at = now()` (yangi belgisi tozalanadi)

**Backend:**
- `POST /searches/refresh` — barcha qidiruvlarni qayta hisoblaydi (ETL'dan keyin)
- `GET /searches` javobida `new_count`

**Frontend:**
- Sidebar'да saqlangan qidiruv yonида **qizil belgi** ("3 ta yangi")
- Umumiy "yangi" hisoblagichi (sarlavhада 🔔)

**Email (H bosqich, keyin):** SMTP + cron. `search_hit.notified_at` takrorni
oldini oladi. Hozir faqat ilova-ichi.

### D — Qidiruv UX  *(kalitsiz, kichik)*
- Tezkor filtr chiplar ("Bugun", "Yaqin deadline", "Yuqori summa")
- Qidiruv maydonida oxirgi qidiruvlar (localStorage)
- Filtrlarni URL'да saqlash (allaqachon qisman bor) — ulashish uchun

---

## 4. Tartib va bog'liqlik

```
A (saqlangan qidiruv) ──► C (yangi-mos belgisi)
        │                        │
        └──► B (kategoriya) ◄─────┘   (kalit kelgach boyiydi)
        │
        └──► D (UX bezaklari)  — mustaqil, istalgan vaqtда
```

**A birinchi** — C va B unga bog'lanadi (qidiruv ichida kategoriya, xabarnoma
qidiruvga tegishli).

---

## 5. Bloklovchi / ochiq savollar

| Savol | Ta'sir |
|---|---|
| AI kaliti qachon bo'ladi? | B ning to'liqligini belgilaydi (hozir mc-only) |
| Email xabarnoma kerakmi yoki ilova-ichi yetarlimi (MVP)? | C ning ko'lami (SMTP + cron = H bosqich) |
| Auth qachon? (hozir yagona foydalanuvchi) | saved_search.company_id — hozir NULL, keyin bo'linadi |
| mc service_type/object_type → kanonik teg xaritasi kim tasdiqlaydi? | B kalitsiz sifati |

---

## 6. Tavsiya qilingan boshlash

**A bosqich** (saqlangan qidiruvlar) — hech narsaga bog'liq emas, C va B
uning ustiga quriladi. Undan keyin **C** (yangi-mos belgisi), keyin **B**
(kategoriya, kalitsiz mc-only holatда), oxirida **D** (bezaklar).

Kalit kelganда: `etl_ai_summary` yurgiziladi → B avtomatik boyiydi (kod
o'zgarmaydi), qidiruv/moslashtirish AI sinonimlari bilan aniqlashadi.
