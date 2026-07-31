# Narx hisobi (P0-7) — integratsiya qadamlari

Bu hujjat **UMUMIY fayllarga** kiritilishi kerak bo'lgan o'zgarishlarni saqlaydi.
Ular parallel ishlanayotgani uchun bevosita tahrir qilinmadi — quyidagi bloklarni
**AYNAN** ko'chirib qo'ying.

Quyidagi fayllar allaqachon yaratilgan va ishlaydi (integratsiya kutmaydi):

| Fayl | Vazifasi |
|---|---|
| `schema_patch_pricing.sql` | `pricing_settings` + `tender_pricing` jadvallari (**bazaga qo'llangan**) |
| `api/pricing.py` | hisob mantig'i — **sof funksiya**, DB'siz sinaladi |
| `frontend/src/pricing.js` | aynan shu formulaning brauzer nusxasi (serversiz qayta hisoblash) |
| `frontend/src/components/PricingPanel.jsx` | panel (pozitsiyalar, parametrlar, formulalar, saqlash) |
| `frontend/src/styles/pricing.css` | panel uslublari (komponentdan import qilinadi) |
| `_tests/pricing_test.py` | 26 sinov, shu jumladan **Python ↔ JavaScript pariteti** |

Sxema patchi qo'llangan. Boshqa muhitda:

```bash
psql "dbname=xtxarid user=postgres host=localhost" -f schema_patch_pricing.sql
```

Patch idempotent (`IF NOT EXISTS`), qayta ishga tushirilsa hech narsa buzilmaydi.

---

## 1. `api/queries.py` — oxiriga qo'shing

```python
# ---------------------------------------------------------------------------
# NARX HISOBI (P0-7) — schema_patch_pricing.sql
# ---------------------------------------------------------------------------
_PS_COLS = ("id, markup_percent, risk_reserve_percent, risk_reserve_fixed, "
            "logistics_percent, logistics_fixed, vat_percent, currency, updated_at")

# Sozlamalar bitta yozuv (id=1) — patch uni INSERT qilib qo'ygan, shuning
# uchun SELECT hech qachon bo'sh qaytarmaydi.
PRICING_SETTINGS_GET_SQL = f"SELECT {_PS_COLS} FROM pricing_settings WHERE id = 1"

PRICING_SETTINGS_UPSERT_SQL = f"""
INSERT INTO pricing_settings (
    id, markup_percent, risk_reserve_percent, risk_reserve_fixed,
    logistics_percent, logistics_fixed, vat_percent, currency, updated_at)
VALUES (1, %(markup_percent)s, %(risk_reserve_percent)s, %(risk_reserve_fixed)s,
        %(logistics_percent)s, %(logistics_fixed)s, %(vat_percent)s,
        %(currency)s, now())
ON CONFLICT (id) DO UPDATE SET
    markup_percent=EXCLUDED.markup_percent,
    risk_reserve_percent=EXCLUDED.risk_reserve_percent,
    risk_reserve_fixed=EXCLUDED.risk_reserve_fixed,
    logistics_percent=EXCLUDED.logistics_percent,
    logistics_fixed=EXCLUDED.logistics_fixed,
    vat_percent=EXCLUDED.vat_percent,
    currency=EXCLUDED.currency,
    updated_at=now()
RETURNING {_PS_COLS}
"""

_TP_COLS = ("tender_id, inputs, result, manual_price, currency, note, "
            "created_at, updated_at")

TENDER_PRICING_GET_SQL = f"SELECT {_TP_COLS} FROM tender_pricing WHERE tender_id = %(id)s"

TENDER_PRICING_UPSERT_SQL = f"""
INSERT INTO tender_pricing (tender_id, inputs, result, manual_price, currency, note)
VALUES (%(tender_id)s, %(inputs)s, %(result)s, %(manual_price)s, %(currency)s, %(note)s)
ON CONFLICT (tender_id) DO UPDATE SET
    inputs=EXCLUDED.inputs, result=EXCLUDED.result,
    manual_price=EXCLUDED.manual_price, currency=EXCLUDED.currency,
    note=EXCLUDED.note, updated_at=now()
RETURNING {_TP_COLS}
"""

# Smeta uchun tenderdan faqat byudjet va valyuta kerak — to'liq tender
# so'rovi (lot/tovar/hujjat bilan) bu yerda ortiqcha yuk bo'lardi.
PRICING_TENDER_SQL = "SELECT id, totalcost, currency FROM tender WHERE id = %(id)s"
```

---

## 2. `api/main.py`

### 2.1 Import (36-qator, mavjud importga `pricing` qo'shiladi)

```python
from api import ai, ai_gonogo, ai_match, db, matching, pricing, queries  # noqa: E402
```

### 2.2 So'rov modellari (boshqa `...In` modellari yoniga, ~115-qator)

```python
class PricingSettingsIn(BaseModel):
    """Narx hisobining odatiy parametrlari (bitta faol yozuv)."""
    markup_percent: float = 15
    risk_reserve_percent: float = 5
    risk_reserve_fixed: float = 0
    logistics_percent: float = 0
    logistics_fixed: float = 0
    vat_percent: float = 12          # O'zbekistonda QQS 12% — lekin tahrirlanadi
    currency: Optional[str] = None


class PricingItemIn(BaseModel):
    name: Optional[str] = None
    unit: Optional[str] = None
    qty: float = 0
    unit_cost: float = 0             # BIZNING tannarximiz
    currency: Optional[str] = None
    ref_price: Optional[float] = None  # buyurtmachi narxi — faqat mo'ljal


class PricingIn(BaseModel):
    """Smetaning kiruvchi holati. Byudjet va minimal marja ATAYLAB YO'Q —
    ularni server bazadan o'zi oladi (mijoz yuborganiga ishonmaydi)."""
    items: List[PricingItemIn] = []
    markup_percent: Optional[float] = None
    risk_reserve_percent: Optional[float] = None
    risk_reserve_fixed: Optional[float] = None
    logistics_percent: Optional[float] = None
    logistics_fixed: Optional[float] = None
    vat_percent: Optional[float] = None
    currency: Optional[str] = None
    manual_price: Optional[float] = None   # broker qo'lda kiritgan narx
    note: Optional[str] = None
```

### 2.3 Shakllantiruvchilar (`_shape_profile` yoniga)

```python
def _pnum(v):
    """NUMERIC -> float (psycopg2 Decimal qaytaradi, JSON uni bilmaydi)."""
    return None if v is None else float(v)


def _shape_pricing_settings(r: Optional[dict]) -> Optional[dict]:
    if not r:
        return None
    return {
        "markup_percent": _pnum(r["markup_percent"]),
        "risk_reserve_percent": _pnum(r["risk_reserve_percent"]),
        "risk_reserve_fixed": _pnum(r["risk_reserve_fixed"]),
        "logistics_percent": _pnum(r["logistics_percent"]),
        "logistics_fixed": _pnum(r["logistics_fixed"]),
        "vat_percent": _pnum(r["vat_percent"]),
        "currency": r["currency"],
        "updated_at": _iso(r["updated_at"]),
    }


def _shape_tender_pricing(r: Optional[dict]) -> Optional[dict]:
    if not r:
        return None
    return {
        "tender_id": r["tender_id"],
        "inputs": r["inputs"],
        "result": r["result"],
        "manual_price": _pnum(r["manual_price"]),
        "currency": r["currency"],
        "note": r["note"],
        "updated_at": _iso(r["updated_at"]),
    }
```

### 2.4 Endpointlar (fayl oxiriga — `/match` dan keyin)

```python
# ---------------------------------------------------------------------------
# NARX HISOBI (P0-7) — tannarx + ustama + xavf zaxirasi -> tavsiya etilgan narx
#
# AI YO'Q: butun mantiq `api/pricing.py` dagi SOF FUNKSIYADA. Endpointlar
# faqat ma'lumot yig'adi, uni chaqiradi va saqlaydi.
# ---------------------------------------------------------------------------
@app.get("/pricing/settings")
def get_pricing_settings():
    """Narx hisobining odatiy parametrlari (har doim mavjud — patch id=1 ni
    yaratib qo'ygan)."""
    return _shape_pricing_settings(db.query_one(queries.PRICING_SETTINGS_GET_SQL))


@app.put("/pricing/settings")
def put_pricing_settings(s: PricingSettingsIn):
    """Odatiy parametrlarni saqlaydi. Ular yangi tenderda boshlang'ich qiymat
    bo'lib ishlatiladi; tenderda o'zgartirilgani `tender_pricing.inputs` da."""
    row = db.execute_returning(queries.PRICING_SETTINGS_UPSERT_SQL, s.model_dump())
    return _shape_pricing_settings(row)


@app.get("/tenders/{tender_id}/pricing")
def get_tender_pricing(tender_id: int):
    """Shu tender uchun saqlangan smeta (yo'q bo'lsa null).

    404 EMAS, null: smeta yo'qligi xato emas — foydalanuvchi hali hisoblamagan.
    `/profile` bilan bir xil uslub.
    """
    return _shape_tender_pricing(
        db.query_one(queries.TENDER_PRICING_GET_SQL, {"id": tender_id}))


@app.post("/tenders/{tender_id}/pricing")
def post_tender_pricing(tender_id: int, body: PricingIn):
    """Smetani QAYTA HISOBLAYDI va saqlaydi.

    Frontend ham brauzerda hisoblaydi (bir xil formula — `pricing.js`), lekin
    bazaga YOZILADIGANI doim serverning natijasi: yagona haqiqat manbai bitta
    bo'lishi kerak.

    Byudjet tenderdan, minimal maqbul foyda esa `company_profile` dan olinadi
    (faqat o'qish — jadval o'zgarmaydi).
    """
    t = db.query_one(queries.PRICING_TENDER_SQL, {"id": tender_id})
    if not t:
        raise HTTPException(status_code=404, detail=f"Tender {tender_id} topilmadi.")

    settings = db.query_one(queries.PRICING_SETTINGS_GET_SQL)
    profile = db.query_one(queries.PROFILE_GET_SQL)
    goods = db.query(queries.TENDER_GOODS_SQL, {"id": tender_id})

    inp = pricing.build_inputs(settings, t, goods, profile, saved=None,
                               override=body.model_dump(exclude={"note"}))
    # `manual_price` ATAYLAB alohida: build_inputs None qiymatni o'tkazib
    # yuboradi, bu yerda esa None "qo'lda narxni O'CHIR" degani.
    inp["manual_price"] = body.manual_price

    result = pricing.calculate(inp)
    if not result["ok"]:
        # Noto'g'ri kiruvchidan chiqqan smetani SAQLAMAYMIZ (masalan valyuta
        # aralashgan) — foydalanuvchi avval tuzatadi.
        raise HTTPException(status_code=400, detail="; ".join(
            e["message"] for e in result["errors"]))

    saved = db.execute_returning(queries.TENDER_PRICING_UPSERT_SQL, {
        "tender_id": tender_id,
        "inputs": json.dumps(inp, ensure_ascii=False),
        "result": json.dumps(result, ensure_ascii=False),
        "manual_price": inp.get("manual_price"),
        "currency": inp.get("currency"),
        "note": body.note,
    })
    return {**_shape_tender_pricing(saved), **result}
```

**Sinalgan** (haqiqiy bazada, `TestClient` bilan; uvicorn ishga tushirilmagan):
`GET/PUT /pricing/settings`, `GET/POST /tenders/{id}/pricing`, qo'lda narx qo'yish
va tozalash, valyuta aralashuvi → 400, mavjud bo'lmagan tender → 404.

---

## 3. `frontend/src/components/TenderDrawer.jsx` — panelni ulash

**3.1** Importlar orasiga (6-qatordan keyin, `GoNoGo` yoniga):

```jsx
import PricingPanel from './PricingPanel.jsx'
```

**3.2** `<GoNoGo tenderId={t.id} />` dan **keyin** (89-qator atrofi):

```jsx
{/* NARX HISOBI — "qatnashaymi?" dan keyingi savol: "qancha narx qo'yamiz?".
    Tannarx + logistika + zaxira + ustama -> tavsiya etilgan taklif narxi.
    Hisob brauzerda bajariladi: har o'zgarishda darhol qayta hisoblanadi. */}
<PricingPanel tender={t} />
```

Panel `tender` obyektidan `id`, `totalcost`, `currency` va `lots[].goods` ni
o'qiydi — `api.tender(id)` javobida hammasi bor, qo'shimcha so'rov kerak emas.

---

## 4. `frontend/src/api.js` — IXTIYORIY

Panel `api.js` ga **bog'liq emas**: u faqat `apiUrl` ni import qiladi va o'z
`req()` yordamchisi bilan ishlaydi (umumiy faylni band qilmaslik uchun).
Chaqiruvlarni bir joyga yig'ishni istasangiz, `api` obyektiga qo'shing:

```js
  // Narx hisobi (P0-7) — sof formula, AI yo'q
  pricingSettings: () => request('GET', '/pricing/settings'),
  savePricingSettings: (body) => request('PUT', '/pricing/settings', { body }),
  tenderPricing: (id) => request('GET', `/tenders/${id}/pricing`),
  saveTenderPricing: (id, body) => request('POST', `/tenders/${id}/pricing`, { body }),
```

So'ngra `PricingPanel.jsx` da `req(...)` chaqiruvlarini shu metodlar bilan
almashtiring va lokal `req()` funksiyasini o'chiring.

---

## 5. Sozlamalar sahifasi — IXTIYORIY (keyingi qadam)

`GET/PUT /pricing/settings` tayyor, lekin ularni tahrirlaydigan alohida ekran
yo'q: hozircha parametrlar har tenderda to'g'ridan-to'g'ri o'zgartiriladi va
smeta bilan birga saqlanadi. Umumiy default larni interfeysdan o'zgartirish
kerak bo'lsa — `CompanyProfile.jsx` ga kichik blok qo'shish yetarli
(u ham parallel ishlanmoqda, shuning uchun bu yerda to'xtatildi).

---

## 6. Nima diqqatda bo'lsin

- **Ikki ijro, bitta formula.** `api/pricing.py` va `frontend/src/pricing.js` —
  ayni bir hisob. Birini o'zgartirsangiz, ikkinchisini ham o'zgartiring:
  `_tests/pricing_test.py::test_javascript_bilan_bir_xil` ularni Node orqali
  yonma-yon ishga tushirib solishtiradi va farq bo'lsa yiqiladi.
- **Valyuta konvertatsiyasi yo'q.** UZS va USD aralashsa hisob **umuman
  bajarilmaydi** (`ok=false`), jimgina qo'shilmaydi.
- **`company_profile` va `catalog_product` ga yozilmaydi.** `min_margin_percent`
  faqat o'qiladi.
- **Sinov:** `.venv/Scripts/python.exe _tests/pricing_test.py` (baza va server
  kerak emas).
