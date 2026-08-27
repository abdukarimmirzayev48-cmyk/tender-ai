# Tender-AI → ERP — ARXITEKTURA QARORI

Bu hujjat ERP modulini **qayerda** va **qanday chegaralar bilan** qurish
to'g'risidagi qarorni, uning sabablarini va keyin ajratib olish yo'lini
belgilaydi. Bosqichlar `erp_bosqichlar.md` da, 1-bosqichning aynan
ko'chiriladigan kodi `erp_integratsiya.md` da.

---

## 1. Qaror

**ERP hozirgi loyiha ichida, lekin qat'iy chegaralangan alohida modul
sifatida quriladi ("modulli monolit").** Alohida servis emas.

| Mezon | Ichida (modul) | Alohida servis |
|---|---|---|
| Tender ma'lumotiga kirish | to'g'ridan-to'g'ri, bitta baza | REST/nusxa, sinxronizatsiya |
| Mavjud panellar (Narx, Cheklist, Qoldiq, Go/No-Go) | `tender_id` bilan darhol ishlaydi | qayta ulash kerak |
| Autentifikatsiya | hozir yo'q — muammo emas | servislararo token shart |
| Deploy | bitta uvicorn + bitta Vite | ikkita + CORS + ikkita `.env` |
| Hozirgi ish uslubi (agent = modul + integratsiya hujjati) | mos | yangi jarayon |
| Keyin ajratish | sxema/prefiks/papka saqlansa — oson | — |

Qaror **qayta ko'riladi** quyidagilardan kamida ikkitasi paydo bo'lganda:

- foydalanuvchi login va rollar (broker / rahbar / mijoz);
- mijoz korxonalar tizimga o'zlari kiradigan bo'ldi;
- buxgalteriya/ombor tenderdan kelmaydigan operatsiyalar bilan yashay boshladi;
- ERP'ni Tender-AI'siz alohida mahsulot sifatida berish rejasi.

---

## 2. Chegaralar (buzilmas qoidalar)

### 2.1. Baza — alohida sxema `erp`

```
public.*          ← Tender-AI (tender, lot, tender_item, tender_document,
                     company_profile, catalog_product, notify_*, pricing_*, ...)
erp.*             ← ERP (opportunity, client_company, broker,
                     opportunity_history, opportunity_task, ...)
```

- `erp.*` jadvallari `public.*` ga **faqat `tender_id` bilan** ishora qiladi.
- **FOREIGN KEY YO'Q** `erp.opportunity.tender_id → public.tender.id` ga.
  Sabab — `doctext.md` 6.1 dagi bilan bir xil: ETL tender qismlarini
  `DELETE`+`INSERT` qiladi, manba tenderni o'chirishi mumkin. Ishga olingan
  tender kartasi manbadagi o'zgarishdan **yo'qolmasligi** kerak.
- `public.*` ga ERP tomonidan **hech qachon yozilmaydi**.

### 2.2. Snapshot, havola emas

Opportunity yaratilganda tenderning 9 ta maydoni **nusxalanadi**:

```
source_platform, tender_ref (tender va lot raqami), customer_name, title,
start_price, currency, deadline_at, region_name, source_url
```

Keyin tender o'zgarsa karta o'zgarmaydi — bu **ataylab**. Kartada
"Tenderda yangilanish bor" belgisi ko'rsatish uchun `tender_id` orqali
jonli tender bilan solishtirish mumkin (2-bosqichdan keyin).

Hujjatlar nusxalanmaydi: `tender_document` + `tender_document_text`
`tender_id` orqali jonli ko'rsatiladi (matn `doctext` modulida allaqachon
bor).

### 2.3. Kod — alohida papkalar, alohida prefiks

```
api/erp/
  __init__.py
  opportunity.py      # mantiq + SQL (queries.py ga QO'SHILMAYDI)
  clients.py          # 2-bosqich
  stats.py            # rahbar hisoboti
frontend/src/components/erp/
  OpportunityBoard.jsx   # Kanban
  OpportunityTable.jsx   # jadval
  OpportunityCard.jsx    # karta (drawer)
  TakeTenderDialog.jsx   # "Ishga olish" formasi
frontend/src/styles/erp.css
```

Endpointlar: **`/erp/...`** prefiksi ostida. `api/main.py` ga faqat
`include_router` (yoki endpoint bloki) qo'shiladi.

### 2.4. Bog'liqlik bir tomonlama

```
Tender-AI  ──(o'qish)──▶  ERP          ✔
ERP        ──(yozish)──▶  Tender-AI    ✘
Tender-AI  ──(import)──▶  api.erp      ✘   (tender moduli ERP haqida bilmaydi)
```

`api/erp/*` `api.db`, `api.queries` ni import qiladi. `api/main.py`,
`api/compliance.py`, `api/pricing.py` va boshqalar `api.erp` ni **import
qilmaydi**. `TenderDrawer.jsx` dagi "Ishga olish" tugmasi — yagona ulanish
nuqtasi, u `api.erp*` chaqiruvini qiladi, xolos.

### 2.5. Mavjud modullar bilan integratsiya — `tender_id` orqali

Opportunity kartasida "Narx hisobi", "Hujjatlar cheklisti", "Ombor qoldig'i"
tablari **mavjud komponentlarni `tenderId` bilan chaqiradi**:

```jsx
<PricingPanel tender={t} />            // pricing.md
<CompliancePanel tenderId={t.id} />    // compliance.md
<StockCheck tenderId={t.id} />         // import.md
```

Bu modullar opportunity haqida bilmaydi va bilishi shart emas.

---

## 3. Ma'lumotlar modeli (1-bosqich)

```
erp.broker                 erp.client_company
  id PK                      id PK
  full_name                  name
  email, phone               inn (2-bosqich)
  active                     ... passport (2-bosqich)
      ▲                          ▲
      │ broker_id                │ client_id
      │                          │
erp.opportunity ──────────────────┘
  id PK
  tender_id            (public.tender.id — FK YO'Q)
  -- snapshot --
  source_platform, tender_ref, customer_name, title,
  start_price, currency, deadline_at, region_name, source_url
  -- xodim kiritadi --
  broker_id, client_id, priority, win_probability, note, next_task, next_task_at
  -- holat --
  status, status_changed_at, closed_at
  created_at, updated_at, created_by
  UNIQUE (tender_id, client_id)
      │
      │ opportunity_id
      ▼
erp.opportunity_history
  id, opportunity_id, from_status, to_status, changed_at, changed_by, note
```

### Statuslar (9 ta, TZ bo'yicha)

| Kod | Nomi | Turi |
|---|---|---|
| `new` | Yangi | ochiq |
| `reviewing` | Ko'rib chiqilmoqda | ochiq |
| `sent_to_client` | Mijozga yuborildi | ochiq |
| `confirmed` | Qatnashish tasdiqlandi | ochiq |
| `preparing` | Taklif tayyorlanmoqda | ochiq |
| `submitted` | Topshirildi | ochiq |
| `won` | Yutildi | **yakuniy** |
| `lost` | Yutqazildi | **yakuniy** |
| `rejected` | Rad etildi | **yakuniy** |

Qoidalar:
- Kanbanda **istalgan** ochiq statusdan istalgan ochiq statusga ko'chirish
  mumkin (qat'iy ketma-ketlik 1-bosqichda yo'q — ish jarayoni hali
  shakllanmagan, uni cheklash erta).
- Yakuniy statusga o'tish `closed_at` ni qo'yadi. Yakuniydan qaytish
  **faqat izoh bilan** (`note` majburiy) — tarixda qoladi.
- Har o'tish `opportunity_history` ga yoziladi — hisobot va "har bosqichda
  qancha turdi" shundan.

### Ustuvorlik va ehtimol

- `priority`: `low | medium | high`.
- `win_probability`: `0..100` butun son, ixtiyoriy. Bu **xodimning
  bahosi**, Go/No-Go yoki moslik balli emas — ular alohida ko'rsatiladi,
  aralashtirilmaydi.

---

## 4. Oqimlar

### "Ishga olish"

```
TenderDrawer ("Ishga olish")
   │  api.erpTakeTender(tender_id, {broker_id, client_id, priority, ...})
   ▼
POST /erp/opportunities
   │  1) tender'ni o'qiydi (public) → snapshot
   │  2) UNIQUE (tender_id, client_id) → bor bo'lsa 409 + mavjud id
   │  3) INSERT erp.opportunity (status='new')
   │  4) INSERT erp.opportunity_history (NULL → 'new')
   ▼
Drawer'da "Ishga olingan · Yangi · <broker>" nishoni; "Kartaga o'tish" havolasi
```

### Status o'zgarishi

```
Kanban drag / karta tugmasi
   ▼
PATCH /erp/opportunities/{id}/status {status, note?}
   │  yakuniy → ochiq bo'lsa note majburiy (400)
   │  UPDATE status, status_changed_at, closed_at
   │  INSERT history
   ▼
javob: yangilangan karta
```

### Rahbar hisoboti

`GET /erp/stats` — bitta so'rovda: status bo'yicha soni va summa, broker
bo'yicha, mijoz bo'yicha, 7 kun ichidagi deadline'lar, oy bo'yicha
yutish/yutqazish. Hisob **bazada** (`GROUP BY`), frontendda emas.

---

## 5. Qarorlar va sabablari

1. **Auth hozir yo'q, `created_by`/`changed_by` — matn.** Broker tanlash
   dropdown'dan, "kim o'zgartirdi" — o'sha tanlangan broker nomi.
   Login kiritilganda ustunlar `user_id` ga o'tadi, tarix yo'qolmaydi.
2. **`erp.broker` va `erp.client_company` 1-bosqichdayoq jadval**, matn
   maydoni emas. 2-bosqich (mijoz passporti) shu jadvalni kengaytiradi —
   migratsiya kerak bo'lmaydi.
3. **Bitta tender — bir mijoz uchun bir opportunity.** Broker kompaniyasi
   bitta tenderga ikki mijoz nomidan kirishi mumkin (ikki karta), bitta
   mijoz uchun ikki marta — yo'q.
4. **Go/No-Go, moslik balli, narx hisobi kartaga ko'chirilmaydi.** Ular
   tenderga tegishli va jonli; karta ularni `tender_id` orqali ko'rsatadi.
5. **Bildirishnomaga tegilmaydi.** "Ishga olingan tenderning deadline'i
   yaqin" xabari — 3-bosqich; u `notify.py` ga emas, `api/erp/` ichiga
   alohida skript sifatida keladi va mavjud kanallardan (email/Telegram
   transporti) foydalanadi.
6. **Soft delete yo'q, umuman delete yo'q.** Noto'g'ri ishga olingan
   tender `rejected` statusiga o'tkaziladi va izoh yoziladi. Tarix —
   rahbar uchun ma'lumot.

---

## 6. Keyin ajratish yo'li (agar kerak bo'lsa)

Chegaralar saqlangan bo'lsa:

1. `erp` sxemasini `pg_dump -n erp` bilan alohida bazaga ko'chirish.
2. `api/erp/` ni alohida FastAPI ilovasiga olib chiqish; `api.db` o'rniga
   o'z ulanishi.
3. `opportunity.py` dagi **bitta** funksiya — `_tender_snapshot(tender_id)`
   — SQL o'rniga `GET /tenders/{id}` chaqiruviga almashadi. Boshqa hech
   narsa tender bazasiga tegmaydi.
4. Frontendda `components/erp/` o'z ilovasiga; `TenderDrawer` dagi tugma
   tashqi URL ga aylanadi.

Bu ro'yxat qisqa ekani — chegaralar to'g'ri qo'yilganining belgisi.
Agar ajratishda ro'yxat uzayib ketsa, demak chegara qayerdadir buzilgan.
