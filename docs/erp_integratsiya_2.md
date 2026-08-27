# Integratsiya — ERP 2-BOSQICH: mijoz korxonalar bazasi va korxona passporti

`erp_bosqichlar.md` 2-bosqichining bajarilgan holati. Uslub 1-bosqich bilan
bir xil: mustaqil fayllar + umumiy fayllarga aynan ko'chiriladigan qatorlar
(`ULASH.md`).

**Maqsad:** broker qaysi korxona nomidan qatnashayotganini to'liq biladi;
tender cheklisti (P0-8) **mijoz** hujjatlariga qarab ishlaydi.

Yangi kutubxona kerak emas. AI chaqiruvi yo'q. `public.*` ga yozilmaydi.

---

## 1. Fayllar

| Fayl | Holat | Vazifasi |
|---|---|---|
| `schema_patch_erp_2.sql` | yangi | passport ustunlari + `client_contact` + `client_document` |
| `api/erp/clients.py` | yangi | passport CRUD, aloqalar, hujjatlar, cheklist manbasi |
| `api/erp/stats.py` | o'zgardi | `by_client` ga `win_rate` qo'shildi |
| `_tests/erp2_test.py` | yangi | 60 tekshiruv, bazani tozalaydi |
| `frontend/src/components/erp/ClientsPage.tsx` | yangi | mijozlar ro'yxati |
| `frontend/src/components/erp/ClientCard.tsx` | yangi | passport kartasi (4 tab) |
| `frontend/src/components/erp/OpportunityCard.tsx` | o'zgardi | cheklist tabi `client_id` uzatadi |
| `frontend/src/components/erp/erpShared.tsx` | o'zgardi | `SchemaMissing` qaysi patch kerakligini aytadi |

Umumiy fayllar: `api/main.py`, `api/compliance.py`, `frontend/src/api.ts`,
`types.ts`, `App.tsx`, `Sidebar.tsx`, `CompliancePanel.tsx`, 3 ta locale —
hammasi `ULASH.md` da.

---

## 2. Baza

`erp.client_company` ga 14 ta ustun qo'shiladi (INN, OKED, tashkiliy shakl,
soliq rejimi, yuridik/faktik manzil, bank nomi/MFO/hisob raqami, rahbar,
telefon, email, izoh, `updated_at`). Hammasi **ixtiyoriy**: 1-bosqichda
yaratilgan mijozlar buzilmaydi, passport keyin to'ldiriladi.

```sql
CREATE UNIQUE INDEX IF NOT EXISTS client_company_inn_uq
    ON erp.client_company (inn) WHERE inn IS NOT NULL;
```

**Nega qisman indeks:** INN hali kiritilmagan korxonalar ko'p bo'ladi, SQL'da
esa `NULL = NULL` yolg'on — oddiy `UNIQUE` ularni cheklamaydi, lekin bo'sh
satr (`''`) cheklaydi. Shuning uchun kodda `''` har doim `NULL` ga aylanadi
(`_clean`), indeks esa faqat to'ldirilganlarini tekshiradi.

Ikki yangi jadval: `erp.client_contact` (bir korxonada bir nechta odam) va
`erp.client_document`. **Muhim:** `client_document` ustunlari
`public.company_document` bilan **aynan bir xil** nomlanadi — cheklist
mantig'i (`build_checklist`) ikkala manbani ham o'zgarishsiz o'qiydi.

---

## 3. Cheklist ulanishi — 2-bosqichning yuragi

`erp_bosqichlar.md` da signatura `compliance.check(tender_id, client_id=None)`
deb rejalashtirilgan edi. **Amalda `check(tender_id, docs=None)` qilindi.**

Sabab — `erp_arxitektura.md` 2.4 dagi buzilmas qoida: `api/compliance.py`
`api.erp` ni bilmasligi kerak. `client_id` qabul qilsa, u `erp.client_document`
dan o'qishi kerak bo'lardi va bog'liqlik ikki tomonlama bo'lib qolardi.
Hujjatlarni KIM olishini chaqiruvchi hal qiladi:

```python
# api/main.py
docs = _erp(erp_clients.docs_for_compliance, client_id) if client_id else None
res = compliance.check(tender_id, docs=docs)
res["client_id"] = client_id
res["doc_source"] = "client" if client_id else "company"
```

Natija: `GET /tenders/{id}/compliance?client_id=N` mijoz hujjatlariga qarab
ishlaydi, parametrsiz esa xatti-harakat 1-bosqichdagidek qoladi. Qoidalar
(`detect_required`, `build_checklist`, `DOC_TYPES`) **umuman o'zgarmadi**.

Javobga `doc_source` qo'shildi va interfeys uni ko'rsatadi ("Alfa Trade MChJ
hujjatlari") — cheklist kimning hujjatlariga qaraganini foydalanuvchi
bilishi shart, aks holda "hammasi bor" degan javob boshqa korxonaga tegishli
bo'lib chiqishi mumkin.

Yo'q `client_id` — **404**, bo'sh javob emas: aks holda cheklist "hamma
hujjat yetishmayapti" deb ko'rsatardi va xato sezilmasdi.

---

## 4. Endpointlar (9 ta yangi)

| Metod | Yo'l | Vazifasi |
|---|---|---|
| GET | `/erp/clients?q=&active_only=` | ro'yxat: passport + natijalar (2-patch bo'lmasa qisqa ro'yxat) |
| GET | `/erp/clients/{id}` | passport + aloqalar + hujjatlar + kartalar + xulosa |
| POST | `/erp/clients` | yaratish (INN takrori -> 409 + `client_id`) |
| PUT | `/erp/clients/{id}` | passportni saqlash |
| POST | `/erp/clients/{id}/contacts` | aloqa shaxsi qo'shish |
| PUT/DELETE | `/erp/client-contacts/{id}` | tahrirlash / o'chirish |
| GET/POST | `/erp/clients/{id}/documents` | hujjatlar |
| PUT | `/erp/client-documents/{id}` | hujjatni tahrirlash |
| DELETE | `/erp/client-documents/{id}` | 204 |

`POST /erp/clients` **orqaga mos**: "+ yangi" formasidan keladigan
`{"name": "..."}` avvalgidek ishlaydi, qolgan maydonlar ixtiyoriy.
2-bosqich patchi qo'llanmagan bazada esa endpoint 1-bosqichdagi oddiy
yaratishga tushib qoladi — tugma ishlamay qolmaydi.

Aloqa shaxsi bilan bog'liq amallar **yangilangan mijoz kartasini** qaytaradi
(204 emas): interfeys ro'yxatni qayta so'ramasin.

---

## 5. Frontend

- **"Mijoz korxonalar" bo'limi** (`ClientsPage.tsx`): ro'yxatda passport
  to'liqligi ochiq ko'rsatiladi ("3 maydon yetishmaydi" — nimasi yetishmasa
  `title` da), hujjatlar soni, kartalar soni va yutish foizi. Qidiruv nom
  **va INN** bo'yicha.
- **Passport kartasi** (`ClientCard.tsx`, drawer): 4 tab — Passport,
  Aloqa shaxslari, Hujjatlar, Kartalar. Hujjat qo'shishda tur ro'yxati
  `/company/document-types` dan, ya'ni kompaniya hujjatlari bilan bir xil
  kanonik ro'yxat.
- **Opportunity kartasi**: "Cheklist" tabi endi kartaning mijozini uzatadi.
  Mijoz tanlanmagan bo'lsa — broker kompaniyasining hujjatlari (eski holat).
- `SchemaMissing` endi qaysi patch kerakligini aytadi (1- yoki 2-bosqich).

---

## 6. Sinov

```
.venv/Scripts/python.exe _tests/erp2_test.py     # 60 tekshiruv
```

Qamrov: INN normallashuvi va formati, takror INN (409 + mavjud id),
INN'siz ikki mijoz yonma-yon, passport to'liqligi, aloqa shaxslari va
hujjatlar CRUD, **cheklist ikki manbadan** (mijoz / kompaniya), hujjatsiz
mijozda hamma band "yo'q", yo'q mijoz -> 404, mijoz sahifasidagi yutish
foizi, `/erp/stats` dagi mijoz kesimi, qidiruv.

Chegara sinovi: `public.tender`, **`public.company_document`**,
`public.company_profile` — qator soni va oxirgi vaqti o'zgarmaydi. Ya'ni
mijoz bazasi broker kompaniyasining hujjatlari o'rnini bosmaydi.

---

## 7. Nima QILINMADI (2-bosqich chegarasi)

Shartnoma, to'lov, mijoz portali, **fayl yuklash** (hujjat hali `file_ref` —
havola yoki yo'l), mijozga avtomatik xabar. Mijoz hujjatlari uchun **shablon
import/eksport** ham yo'q (kompaniya hujjatlarida bor) — 3-bosqichga
qoldirildi.
