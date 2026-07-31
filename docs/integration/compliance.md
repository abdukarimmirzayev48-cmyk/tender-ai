# Integratsiya — HUJJATLAR TO'LIQLIGI CHEKLISTI (TZ P0-8)

Bu hujjatdagi kod **UMUMIY fayllarga tegmasdan** tayyorlangan. Har bo'lim
aynan ko'chiriladigan ko'rinishda: qaysi fayl, qaysi joy, qanday kod.

Qo'shilgan mustaqil fayllar (allaqachon joyida, integratsiya talab qilmaydi):

| Fayl | Vazifasi |
|---|---|
| `schema_patch_compliance.sql` | `company_document` jadvali (**bazaga qo'llangan**) |
| `api/compliance.py` | Aniqlash qoidalari, cheklist mantig'i, SQL matnlari |
| `_tests/compliance_test.py` | Sinov (79 ta tekshiruv, hammasi o'tadi) |
| `frontend/src/components/CompliancePanel.jsx` | Tender panelidagi cheklist (hali ulanmagan) |
| `frontend/src/components/CompanyDocuments.jsx` | Hujjatlar bazasini boshqarish (hali ulanmagan) |
| `frontend/src/styles/compliance.css` | Ularning uslublari (komponentlar o'zi import qiladi) |

Yangi kutubxona **kerak emas** — `requirements-api.txt` o'zgarmaydi.
AI/model chaqiruvi **yo'q**: modul sof qoidaga asoslangan (TZ talabi).

---

## 0. Baza

`schema_patch_compliance.sql` bazaga **allaqachon qo'llangan** (idempotent,
qayta ishga tushirsa ham xavfsiz):

```
psql "dbname=xtxarid user=postgres host=localhost" -f schema_patch_compliance.sql
```

`company_profile` ga **TEGILMADI** — hujjatlar alohida `company_document`
jadvalida (profil 1 qator, hujjatlar esa ro'yxat).

---

## 1. `api/main.py` — import qatoriga qo'shish

36-qatordagi importga `compliance` qo'shiladi:

```python
from api import ai, ai_gonogo, ai_match, compliance, db, matching, queries  # noqa: E402
```

---

## 2. `api/main.py` — so'rov modeli

`CatalogItemIn` klassidan **keyin** (yoki boshqa `...In` modellar yoniga):

```python
class CompanyDocumentIn(BaseModel):
    """Kompaniya hujjati. Sanalar ixtiyoriy: `valid_until` bo'sh bo'lsa
    hujjat MUDDATSIZ deb qaraladi ("ma'lumot yo'q" emas)."""
    doc_type: str
    name: str
    number: Optional[str] = None
    issued_at: Optional[date] = None
    valid_until: Optional[date] = None
    file_name: Optional[str] = None
    file_ref: Optional[str] = None
    note: Optional[str] = None
```

Bunga fayl boshidagi importга `date` kerak:

```python
from datetime import date
```

---

## 3. `api/main.py` — endpointlar

`@app.post("/catalog/seen")` bloqidan **keyin** (profil endpointlaridan
oldin) qo'yiladi. Barcha SQL `api/compliance.py` ichida — `queries.py`
o'zgartirilmaydi.

```python
# ---------------------------------------------------------------------------
# HUJJATLAR TO'LIQLIGI (REJA.md P0-8) — kompaniya hujjatlari + tender cheklisti
#
# STATIK cheklist: hujjat BORLIGI va MUDDATI tekshiriladi, mazmunining
# huquqiy to'g'riligi EMAS (AI chaqirilmaydi). Bu ongli soddalashtirish —
# noto'g'ri huquqiy kafolat hissini yaratmaslik uchun.
# ---------------------------------------------------------------------------
@app.get("/company/document-types")
def company_document_types():
    """Kanonik hujjat turlari — formadagi dropdown shundan to'ladi."""
    return [{"code": d["code"], "label": d["label"], "hint": d["hint"],
             "base": d["base"]} for d in compliance.DOC_TYPES]


@app.get("/company/documents")
def company_documents():
    """Kompaniya hujjatlari + har birining muddat holati."""
    return [compliance.shape_document(r) for r in db.query(compliance.DOCS_LIST_SQL)]


@app.post("/company/documents", status_code=201)
def create_company_document(d: CompanyDocumentIn):
    row = db.execute_returning(compliance.DOC_INSERT_SQL, d.model_dump())
    return compliance.shape_document(row)


@app.put("/company/documents/{doc_id}")
def update_company_document(doc_id: int, d: CompanyDocumentIn):
    row = db.execute_returning(compliance.DOC_UPDATE_SQL,
                               {**d.model_dump(), "id": doc_id})
    if not row:
        raise HTTPException(status_code=404, detail="Hujjat topilmadi.")
    return compliance.shape_document(row)


@app.delete("/company/documents/{doc_id}", status_code=204)
def delete_company_document(doc_id: int):
    row = db.execute_returning(compliance.DOC_DELETE_SQL, {"id": doc_id})
    if not row:
        raise HTTPException(status_code=404, detail="Hujjat topilmadi.")
    return None


@app.get("/tenders/{tender_id}/compliance")
def tender_compliance(tender_id: int):
    """Tender bo'yicha hujjatlar cheklisti: majburiy hujjatlar ro'yxati +
    har biri uchun "kompaniya bazasida bor / yo'q" va muddat holati."""
    if not db.query_one("SELECT 1 AS x FROM tender WHERE id = %(id)s",
                        {"id": tender_id}):
        raise HTTPException(status_code=404, detail="Tender topilmadi.")
    return compliance.check(tender_id)
```

### Javob shakli — `GET /tenders/{id}/compliance`

```jsonc
{
  "tender_id": 7886728,
  "text_sources": ["Tender nomi", "Tender izohi (anno)", "..."],
  "items": [
    {
      "doc_type": "conformity_certificate",
      "label": "Muvofiqlik sertifikati",
      "hint": "Tovarning standart/texnik reglamentga muvofiqligi sertifikati.",
      "required_by": "tender",          // "tender" | "bazaviy"
      "evidence": "…Наличие сертификата соответствия на поставляемый…",
      "evidence_source": "Biriktirilgan hujjat matni",
      "confidence": 90,
      "in_base": true,                  // KOMPANIYA BAZASIDA BOR / YO'Q
      "document": { "id": 3, "name": "...", "valid_until": "2026-07-25",
                    "status": "expired", "days_left": -3, "...": "..." },
      "status": "expired",              // ok | expiring_soon | expired | missing
      "days_left": -3
    }
  ],
  "extra_documents": [ /* bazada bor, lekin bu tenderда talab qilinmagan */ ],
  "summary": {
    "total": 8, "ready": 2, "missing": 4, "expired": 1, "expiring_soon": 1,
    "blocking": 5,
    "detected_from_tender": true, "detected_count": 5,
    "note": "Tender matnidan 5 ta hujjat talabi aniqlandi. …",
    "disclaimer": "Cheklist hujjat BORLIGINI va MUDDATINI tekshiradi, …"
  }
}
```

---

## 4. `frontend/src/api.js` — chaqiruvlar

`api` obyektiga (masalan `catalogSeen` dan keyin) qo'shiladi:

```js
  // Hujjatlar to'liqligi cheklisti (P0-8)
  compliance: (id) => request('GET', `/tenders/${id}/compliance`),
  documentTypes: () => request('GET', '/company/document-types'),
  companyDocuments: () => request('GET', '/company/documents'),
  createCompanyDocument: (body) => request('POST', '/company/documents', { body }),
  updateCompanyDocument: (id, body) => request('PUT', `/company/documents/${id}`, { body }),
  deleteCompanyDocument: (id) => request('DELETE', `/company/documents/${id}`),
```

---

## 5. `frontend/src/components/TenderDrawer.jsx` — cheklistni ko'rsatish

**5.1.** Import (6-qator, `GoNoGo` dan keyin):

```jsx
import CompliancePanel from './CompliancePanel.jsx'
```

**5.2.** Komponent imzosiga `onOpenDocuments` qo'shiladi (9-qator):

```jsx
export default function TenderDrawer({ id, match, onClose, onOpenDocuments }) {
```

**5.3.** `<GoNoGo tenderId={t.id} />` dan **keyin**:

```jsx
            {/* HUJJATLAR TO'LIQLIGI — "ariza to'plamim tayyormi?"
                Go/No-Go qatnashish qarorini beradi, bu esa qatnashish uchun
                qaysi hujjat yetishmayotganini aniq aytadi. */}
            <CompliancePanel tenderId={t.id} onOpenDocuments={onOpenDocuments} />
```

> `onOpenDocuments` ixtiyoriy: berilmasa cheklist ishlaydi, faqat
> "Hujjatlarim bo'limiga o'tish" tugmasi ko'rinmaydi.

---

## 6. `frontend/src/components/Sidebar.jsx` — yangi bo'lim

`NAV` massiviga (`catalog` dan keyin) qo'shiladi:

```js
  { key: 'documents', icon: 'clip', label: 'Hujjatlarim' },
```

(`clip` ikoni `Icon.jsx` da allaqachon bor — yangi ikon kerak emas.)

---

## 7. `frontend/src/App.jsx` — sahifani ulash

**7.1.** Import (boshqa komponent importlari yoniga):

```jsx
import CompanyDocuments from './components/CompanyDocuments.jsx'
```

**7.2.** Holat (`const [view, setView] = useState('tenders')` yoniga):

```jsx
  // Cheklistdan "hujjatlarim" ga o'tilganda qaysi tur formasi ochilsin
  const [docFocus, setDocFocus] = useState(null)
```

**7.3.** O'tish funksiyasi (`goto` funksiyasidan keyin):

```jsx
  // Tender cheklistidagi "Hujjatlarim bo'limiga o'tish" — kerakli hujjat
  // turi formasi darhol ochiladi (foydalanuvchi qidirib yurmasin).
  function openDocuments(docType) {
    setDocFocus(docType || null)
    setSelected(null)          // tender panelini yopamiz
    setView('documents'); setOffset(0)
  }
```

**7.4.** Sahifa (`{view === 'account' && ...}` yoniga):

```jsx
        {view === 'documents' && <CompanyDocuments focusType={docFocus} />}
```

**7.5.** Drawer'ga uzatish (fayl oxiridagi `<TenderDrawer .../>`):

```jsx
        <TenderDrawer id={selected.id} match={selected.match}
                      onClose={() => setSelected(null)}
                      onOpenDocuments={openDocuments} />
```

---

## 8. Sinov

```
.venv/Scripts/python.exe _tests/compliance_test.py
```

Sinov `company_document` ga vaqtinchalik yozuvlar qo'yadi va **oxirida
o'chiradi** (`finally` blokida tozalash + tekshiruv). Uvicorn ishga
tushirilmaydi — modul to'g'ridan-to'g'ri chaqiriladi.

---

## 9. Nima QILINMAYDI (ongli chegara)

- Fayl **yuklash** yo'q — `file_ref` tashqi havola/yo'l saqlaydi.
- Hujjat **mazmuni** tekshirilmaydi (huquqiy to'g'rilik, imzo, muhr).
- Tender matni hujjat talablarini ko'pincha **yozmaydi** — shunda cheklist
  buni ochiq aytadi va bazaviy ro'yxatni ko'rsatadi (jim turmaydi).
- Kelajakda foydalanuvchi tahrirlaydigan qoidalar kerak bo'lsa:
  `doc_requirement_rule` jadvali qo'shiladi va `compliance.DOC_TYPES`
  **ustiga qo'shimcha** sifatida o'qiladi (o'rniga emas) — sabab
  `schema_patch_compliance.sql` oxiridagi izohda.
