# Integratsiya — Katalog importi (P0-4) va Ombor qoldig'i tekshiruvi (P0-6)

Bu faylda **UMUMIY fayllarga** (parallel agentlar ishlayotgan) qo'shilishi kerak
bo'lgan o'zgarishlar **aynan ko'chiriladigan** ko'rinishda berilgan.
Yangi fayllar allaqachon yaratilgan va ishlaydi — quyidagilar faqat ULASH qadamlari.

## Yaratilgan (tayyor) fayllar

| Fayl | Vazifasi |
|---|---|
| `schema_patch_stock.sql` | Sxema patch — **bazaga QO'LLANGAN** (idempotent, 2 marta tekshirilgan) |
| `api/importer.py` | Excel/CSV o'qish, validatsiya, qator bo'yicha xatolar, dry-run, upsert |
| `api/stock.py` | P0-6 — pozitsiya ↔ katalog qoldig'i solishtiruvi |
| `frontend/src/components/CatalogImport.jsx` | Fayl yuklash + dry-run hisoboti + tasdiqlash |
| `frontend/src/components/StockCheck.jsx` | P0-6 natijasini ko'rsatish (tender ichida) |
| `frontend/src/styles/import.css` | Ikkala komponentning uslublari (`styles.css` ga TEGILMAGAN) |
| `_tests/import_test.py` | 144 ta tekshiruv — hammasi o'tadi |

---

## 1. Bog'liqliklar

Venv'ga **o'rnatilgan**:

```
python-multipart==0.0.32     # FastAPI UploadFile uchun SHART
openpyxl==3.1.5              # .xlsx o'qish/yozish (allaqachon bor edi)
```

`requirements-api.txt` ga qo'shiladigan qatorlar (**men o'zgartirmadim**):

```
# Excel/CSV import (api/importer.py). Fayl yuklash multipart talab qiladi.
python-multipart>=0.0.20
openpyxl>=3.1
```

---

## 2. `api/main.py`

### 2.1. Import qatori

`main.py` da 36-qator:

```python
from api import ai, ai_gonogo, ai_match, db, matching, queries  # noqa: E402  (load_dotenv dan keyin bo'lishi shart)
```

o'rniga:

```python
from api import (ai, ai_gonogo, ai_match, db, importer, matching, queries,  # noqa: E402
                 stock)  # (load_dotenv dan keyin bo'lishi shart)
```

FastAPI importiga `File`, `UploadFile` qo'shiladi (30-qator):

```python
from fastapi import FastAPI, File, HTTPException, Query, Response, UploadFile
```

`Response` (fastapi.responses) allaqachon `StreamingResponse` bilan bir qatorda
import qilinmagan — shablon qaytarish uchun kerak (31-qator):

```python
from fastapi.responses import (JSONResponse, RedirectResponse, Response as FileResponse,
                               StreamingResponse)
```

> Eslatma: `fastapi.Response` (parametr sifatida ishlatilayotgan, `list_tenders`
> da bor) va `fastapi.responses.Response` (tana qaytaradigan) — **har xil narsa**.
> Shuning uchun ikkinchisi `FileResponse` nomi bilan olinadi, to'qnashuv bo'lmaydi.

### 2.2. Endpointlar

Quyidagi blokni `@app.post("/catalog/seen", ...)` funksiyasidan **keyin**
(ya'ni katalog bo'limi oxirida, `@app.get("/profile")` dan oldin) qo'ying:

```python
# ---------------------------------------------------------------------------
# KATALOG IMPORTI (TZ P0-4) — Excel/CSV/Google Sheets dan mahsulot + qoldiq
# ---------------------------------------------------------------------------
MAX_IMPORT_MB = 5


@app.post("/catalog/import")
def catalog_import(
    file: UploadFile = File(..., description="Excel (.xlsx) yoki CSV fayl."),
    dry_run: bool = Query(True, description="TRUE — faqat tekshirish, bazaga yozilmaydi."),
):
    """Katalog va ombor qoldiqlarini fayldan import qiladi.

    Format xatolari QATOR BO'YICHA qaytadi: bitta qatordagi xato butun
    importni to'xtatmaydi. `dry_run=true` (default) bazaga umuman tegmaydi —
    interfeys avval shu bilan hisobot ko'rsatadi, keyin foydalanuvchi
    tasdiqlaydi.
    """
    data = file.file.read()
    if len(data) > MAX_IMPORT_MB * 1024 * 1024:
        raise HTTPException(status_code=413,
                            detail=f"Fayl {MAX_IMPORT_MB} MB dan katta.")
    try:
        return importer.import_catalog(data, file.filename or "", dry_run=dry_run)
    except importer.ImportFormatError as e:
        # 422 — fayl formatiga oid xato (qatorga emas, butun faylga tegishli)
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/catalog/import/template")
def catalog_import_template(fmt: str = Query("xlsx", pattern="^(xlsx|csv)$")):
    """Namunaviy shablon fayl (sarlavhalar + 3 ta misol qator)."""
    if fmt == "csv":
        return FileResponse(
            content=importer.template_csv(), media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="katalog_shablon.csv"'})
    return FileResponse(
        content=importer.template_xlsx(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="katalog_shablon.xlsx"'})


@app.get("/tenders/{tender_id}/stock-check")
def tender_stock_check(tender_id: int):
    """TZ P0-6 — mos kelgan pozitsiyalar bo'yicha ombor qoldig'ini tekshirish.

    Har bir mos pozitsiya uchun: so'ralgan miqdor, ombordagi qoldiq va
    yetarliligi (yetarli / yetishmaydi / noma'lum). Yetishmayotganlar ALOHIDA
    `shortages` ro'yxatida. Qoldiq yuklanmagan yoki eskirgan bo'lsa natija
    `preliminary: true` ("dastlabki") deb belgilanadi.
    """
    res = stock.check_tender_stock(tender_id)
    if res is None:
        raise HTTPException(status_code=404, detail=f"Tender {tender_id} topilmadi.")
    return res
```

> **DIQQAT — marshrut tartibi:** `/catalog/import` `POST`, `/catalog/{product_id}`
> esa `PUT`/`DELETE` — usullar boshqacha, to'qnashuv **yo'q**.
> `/catalog/import/template` `GET` — mavjud `GET /catalog` bilan ham
> to'qnashmaydi (yo'l uzunroq va aniq).

### 2.3. `_shape_product` (ixtiyoriy, lekin tavsiya etiladi)

Katalog ro'yxatida qoldiq ko'rinishi uchun `_shape_product` ga 4 ta maydon
qo'shiladi (820-qatordagi funksiya):

```python
def _shape_product(r: dict) -> dict:
    return {
        "id": r["id"], "name": r["name"],
        "category_code": r["category_code"], "keywords": r["keywords"] or [],
        "unit": r["unit"], "price": _num(r["price"]), "currency": r["currency"],
        "notify": r["notify"], "created_at": _iso(r["created_at"]),
        # --- P0-4/P0-6: ombor qoldig'i ---
        "stock_qty": _num(r.get("stock_qty")),
        "stock_unit": r.get("stock_unit"),
        "stock_updated_at": _iso(r.get("stock_updated_at")),
        "cost_price": _num(r.get("cost_price")),
    }
```

`.get()` ishlatilgani muhim: `CATALOG_INSERT_SQL`/`CATALOG_UPDATE_SQL`
`RETURNING` da bu ustunlar yo'q, `.get()` bo'lsa `KeyError` chiqmaydi.

---

## 3. `api/queries.py`

`_CP_COLS` ga yangi ustunlarni qo'shish kifoya (620-qator) — shunda
`GET /catalog` qoldiqni ham qaytaradi:

```python
_CP_COLS = ("id, name, category_code, keywords, unit, price, currency, "
            "notify, created_at, updated_at, "
            "stock_qty, stock_unit, stock_updated_at, cost_price")
```

> `INSERT`/`UPDATE` SQL lariga tegish **shart emas**: qo'lda kiritishda qoldiq
> to'ldirilmaydi, `RETURNING {_CP_COLS}` esa yangi ustunlarni avtomatik
> qaytaradi (yuqoridagi `.get()` bilan xavfsiz).

---

## 4. `frontend/src/api.js`

`export const api = { ... }` ichiga:

```js
  // Ombor qoldig'ini tekshirish (P0-6) — mos pozitsiyalar bo'yicha
  stockCheck: (id) => request('GET', `/tenders/${id}/stock-check`),
```

> `POST /catalog/import` ATAYIN qo'shilmaydi: `request()` JSON yuboradi,
> fayl yuklash esa `FormData` talab qiladi. `CatalogImport.jsx` shu sababli
> `fetch` ni o'zi chaqiradi, lekin bazaviy manzilni baribir `apiUrl()` dan
> oladi — sozlama bitta joyda qoladi.
> `StockCheck.jsx` ham hozir `fetch` ishlatadi; yuqoridagi qator qo'shilsa,
> uni `api.stockCheck(tenderId)` ga o'tkazish mumkin (majburiy emas).

---

## 5. `frontend/src/components/CatalogView.jsx`

**5.1.** Faylning boshiga import:

```js
import CatalogImport from './CatalogImport.jsx'
```

**5.2.** Komponent ichida (9-qatordagi `useState` lar yoniga):

```js
  const [importing, setImporting] = useState(false)
```

**5.3.** Sarlavha blokidagi tugmalar (33–35-qatorlar) o'rniga:

```jsx
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn--ghost btn--icon" onClick={() => setImporting((v) => !v)}>
            <Icon name="download" size={14} /> Excel/CSV dan import
          </button>
          <button className="btn btn--primary btn--icon" onClick={() => setEditing('new')}>
            <Icon name="plus" size={14} /> Mahsulot qo‘shish
          </button>
        </div>
```

**5.4.** `{error && ...}` qatoridan keyin:

```jsx
      {importing && (
        <CatalogImport
          onImported={onChanged}
          onClose={() => setImporting(false)}
        />
      )}
```

**5.5.** (ixtiyoriy) Jadvalga qoldiq ustuni — `<th className="num">Narx</th>`
dan keyin:

```jsx
              <th className="num">Qoldiq</th>
```

va mos `<td>` (`{p.price != null ? ...}` katagidan keyin):

```jsx
                <td className="num">
                  {p.stock_qty != null
                    ? <>{p.stock_qty}<span className="muted-cell"> {p.stock_unit || ''}</span></>
                    : <span className="muted-cell">—</span>}
                </td>
```

Buning ishlashi uchun 2.3 va 3-bo'limdagi o'zgarishlar kerak.

---

## 6. `frontend/src/components/TenderDrawer.jsx` (P0-6 ni ko'rsatish)

**6.1.** Import (6-qatordan keyin):

```js
import StockCheck from './StockCheck.jsx'
```

**6.2.** `<GoNoGo tenderId={t.id} />` (89-qator) dan **keyin**:

```jsx
            {/* P0-6 — mos pozitsiyalar bo'yicha ombor qoldig'i.
                GoNoGo "qatnashamizmi" degan umumiy qarorni beradi; bu esa
                aniq savolga javob: SO'RALGAN MIQDOR OMBORDA BORMI. */}
            <h3 className="drawer__section">Ombor qoldig‘i</h3>
            <StockCheck tenderId={t.id} />
```

---

## 7. Javob formati (qisqacha)

### `POST /catalog/import?dry_run=true`

```json
{
  "dry_run": true,
  "filename": "katalog.xlsx",
  "format": "xlsx",
  "batch_id": null,
  "header_row": 2,
  "columns": {
    "detected": {"Nomi": "Наименование", "Qoldiq": "Остаток", "Tannarx": "Себестоимость"},
    "unknown": ["Ombor ID"],
    "missing": []
  },
  "rows_total": 8, "rows_ok": 2, "rows_error": 6,
  "inserted": 2, "updated": 0,
  "errors": [
    {"row": 4, "column": "Qoldiq", "field": "stock_qty", "value": "ko‘p",
     "message": "Qoldiq — son emas: “ko‘p”."},
    {"row": 6, "column": "Nomi", "field": "name", "value": "Printer HP",
     "message": "Nom faylda takrorlangan (2-qatorda ham bor). Qatorlarni birlashtiring."}
  ],
  "warnings": [
    {"row": 9, "column": "Kategoriya", "field": "category_code", "value": "yoq-bunday",
     "message": "“yoq-bunday” kategoriyasi ma’lumotnomada yo‘q — mahsulot kategoriyasiz qo‘shildi."}
  ],
  "preview": [{"row": 2, "name": "Printer HP", "keywords": ["lazerli"],
               "unit": "шт", "stock_qty": 5.0, "cost_price": 1200000.0}]
}
```

`dry_run=false` da qo'shimcha: `batch_id` (UUID), haqiqiy `inserted`/`updated`.
Format xatosi (butun faylga tegishli) → **HTTP 422**, `detail` da o'zbekcha sabab.

### `GET /tenders/{id}/stock-check`

```json
{
  "tender_id": 7886728, "tender_name": "...", "source": "tender_item",
  "stock": {"loaded": true, "updated_at": "2026-07-28T...", "age_days": 0,
            "stale": false, "stale_after_days": 14, "products_used": 2,
            "warning": null},
  "preliminary": false,
  "summary": {"positions": 11, "matched": 4, "unmatched": 7,
              "ok": 2, "short": 1, "unknown": 1},
  "items": [{
    "lot_id": 1, "item_id": 3, "name": "Мышь компьютерная", "unit": "шт",
    "amount_text": " 500.00 шт", "required_qty": 500.0, "qty_note": null,
    "product": {"id": 35, "name": "Sichqoncha", "stock_qty": 200.0,
                "stock_unit": "шт", "stock_updated_at": "...", "stock_age_days": 0},
    "available_qty": 200.0, "shortfall_qty": 300.0,
    "unit_match": true, "unit_note": null,
    "status": "yetishmaydi", "status_label": "Yetishmayapti",
    "reason": "300 шт yetishmayapti."
  }],
  "shortages": [ /* faqat status = yetishmaydi bo'lganlar */ ],
  "unmatched": [ /* katalogda mos mahsulot topilmagan pozitsiyalar */ ]
}
```

`status`: `yetarli` | `yetishmaydi` | `nomalum`.

---

## 8. Muhit o'zgaruvchisi (ixtiyoriy)

`.env` ga qo'shish mumkin (default bor, majburiy emas):

```
# Ombor qoldig'i necha kundan keyin "eskirgan" hisoblanadi (P0-6 ogohlantirishi)
STOCK_STALE_DAYS=14
```

---

## 9. Sinov

```
.venv/Scripts/python.exe _tests/import_test.py
```

Uvicorn ishga tushirilmaydi — endpointlar `fastapi.testclient.TestClient` bilan
sinaladi. Sinov oxirida baza tozalanadi (`ZZTEST ` prefiksli yozuvlar).
