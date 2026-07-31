# Integratsiya — HUJJAT MATNI (TZ P0-2)

Bu hujjatdagi kod **UMUMIY fayllarga tegmasdan** tayyorlangan. Har bir bo'lim
aynan ko'chiriladigan ko'rinishda: qaysi fayl, qaysi joy, qanday kod.

Qo'shilgan mustaqil fayllar (allaqachon joyida, integratsiya talab qilmaydi):

| Fayl | Vazifasi |
|---|---|
| `schema_patch_doctext.sql` | `tender_document_text` jadvali (bazaga qo'llangan) |
| `etl_doc_text.py` | Fayllarni yuklab olib matnini ajratadi |
| `_tests/doctext_test.py` | Sinov |
| `frontend/src/components/DocumentText.jsx` | UI komponenti (hali ulanmagan) |
| `frontend/src/styles/doctext.css` | Uning uslublari |

---

## 0. Kutubxonalar

Venv'ga **o'rnatilgan**. `requirements-api.txt` o'zgartirilmadi — quyidagi
qatorlarni fayl oxiriga qo'shish kerak:

```
# Hujjat matnini ajratish (etl_doc_text.py). Deterministik parserlar, AI emas.
pypdf>=6.0
python-docx>=1.1
openpyxl>=3.1
```

O'rnatilgan aniq versiyalar: `pypdf 6.14.2`, `python-docx 1.2.0`,
`openpyxl 3.1.5` (+ tranzitiv: `lxml 6.1.1`, `et-xmlfile 2.0.0`).

> API'ning O'ZI bu kutubxonalarsiz ham ishlaydi — endpoint faqat bazadan
> o'qiydi. Ular faqat ETL uchun kerak.

---

## 1. `api/queries.py` — ikki so'rov qo'shish

Faylning oxiriga (yoki `DOCUMENT_BY_REF_SQL` dan keyin) qo'ying:

```python
# --- Hujjat matni (P0-2) ---
# LEFT JOIN — matn ajratilmagan hujjat ham ro'yxatda qoladi ('pending'),
# aks holda "hali ishlanmagan" va "o'qib bo'lmadi" farqlanmay qolardi.
TENDER_DOCUMENT_TEXT_SQL = """
SELECT d.file_ref, d.name, d.file_type, d.field_key, d.size_bytes,
       t.status, t.char_count, t.page_count, t.error, t.extractor,
       t.extracted_at,
       left(t.text, %(preview)s) AS preview
FROM tender_document d
LEFT JOIN tender_document_text t
       ON t.tender_id = d.tender_id AND t.file_ref = d.file_ref
WHERE d.tender_id = %(id)s
ORDER BY d.field_key, d.name
"""

# Bitta faylning TO'LIQ matni (?ref=... &full=true)
DOCUMENT_TEXT_FULL_SQL = """
SELECT status, char_count, page_count, error, extractor, extracted_at, text
FROM tender_document_text
WHERE tender_id = %(id)s AND file_ref = %(ref)s
"""
```

---

## 2. `api/main.py` — endpoint qo'shish

`download_document` funksiyasidan **keyin** (ya'ni `@app.get("/stats")` dan
oldin) qo'ying. Yangi import kerak emas — `Query`, `Optional`, `HTTPException`,
`_doc_label`, `queries`, `db`, `_iso` allaqachon faylda bor.

```python
# Nega hujjat matni o'qilmadi — foydalanuvchiga tushunarli sabab.
# TZ P0-2: 'ok' dan boshqa HAR QANDAY status "qo'lda tekshirish talab etiladi"
# toifasiga kiradi, lekin SABABI turlicha va keyingi qadam ham turlicha
# (arxivni ochish / skanni ko'z bilan o'qish / faylni qo'lda yuklab olish).
_DOC_TEXT_REASON = {
    "unreadable":      "Matn chiqmadi — skan qilingan yoki rasm ko'rinishidagi hujjat",
    "unsupported":     "Format qo'llab-quvvatlanmaydi (arxiv yoki eski binar fayl)",
    "too_large":       "Fayl juda katta — avtomatik o'qilmadi",
    "download_failed": "Manbadan yuklab olinmadi",
    "pending":         "Hali qayta ishlanmagan",
}


@app.get("/tenders/{tender_id}/documents/text")
def tender_documents_text(
    tender_id: int,
    ref: Optional[str] = Query(None, description="Bitta faylning matni (file_ref)."),
    full: bool = Query(False, description="ref bilan birga — to'liq matn."),
    preview_chars: int = Query(1500, ge=0, le=50000,
                               description="Ro'yxatdagi matn parchasi uzunligi."),
):
    """Tender hujjatlarining MATN holati (TZ P0-2).

    Matn `etl_doc_text.py` tomonidan oldindan ajratilgan va
    `tender_document_text` da saqlanadi — bu endpoint tarmoqqa CHIQMAYDI.

    `status`:
        ok | unreadable | unsupported | too_large | download_failed | pending
    'ok' dan boshqasi = "qo'lda tekshirish talab etiladi".
    """
    # Bitta faylning to'liq matni
    if ref and full:
        row = db.query_one(queries.DOCUMENT_TEXT_FULL_SQL,
                           {"id": tender_id, "ref": ref})
        if not row:
            raise HTTPException(status_code=404, detail="Hujjat matni topilmadi.")
        return {
            "file_ref": ref,
            "status": row["status"],
            "manual_review": row["status"] != "ok",
            "reason": (None if row["status"] == "ok"
                       else _DOC_TEXT_REASON.get(row["status"], row["status"])),
            "detail": row.get("error"),
            "char_count": row.get("char_count"),
            "page_count": row.get("page_count"),
            "extractor": row.get("extractor"),
            "extracted_at": _iso(row.get("extracted_at")),
            "text": row.get("text"),
        }

    rows = db.query(queries.TENDER_DOCUMENT_TEXT_SQL,
                    {"id": tender_id, "preview": preview_chars})

    docs = []
    counts: dict = {}
    for r in rows:
        # Matn yozuvi umuman yo'q -> ETL bu faylga hali yetib bormagan
        status = r.get("status") or "pending"
        counts[status] = counts.get(status, 0) + 1
        docs.append({
            "file_ref": r["file_ref"],
            "name": r.get("name"),
            "file_type": r.get("file_type"),
            "size_bytes": r.get("size_bytes"),
            "section": _doc_label(r.get("field_key")),
            "status": status,
            "manual_review": status != "ok",
            "reason": (None if status == "ok"
                       else _DOC_TEXT_REASON.get(status, status)),
            "detail": r.get("error"),      # texnik tafsilot (debug uchun)
            "char_count": r.get("char_count"),
            "page_count": r.get("page_count"),
            "extractor": r.get("extractor"),
            "extracted_at": _iso(r.get("extracted_at")),
            "preview": r.get("preview"),
        })

    total = len(docs)
    ok = counts.get("ok", 0)
    return {
        "tender_id": tender_id,
        "summary": {
            "total": total,
            "ok": ok,
            # TZ qabul qilish mezoni: shu raqam "qo'lda tekshirish talab etiladi"
            "manual_review": total - ok,
            "pending": counts.get("pending", 0),
            "by_status": counts,
            "chars": sum(d["char_count"] or 0 for d in docs),
        },
        "documents": docs,
    }
```

### Ixtiyoriy — `/tenders/{id}` javobiga qisqa hisob qo'shish

`get_tender` ichida, `tender["doc_count"] = len(docs)` qatoridan **keyin**:

```python
    # Hujjat matni holati — kartochkada bir qarashda ko'rinishi uchun
    tx = db.query(queries.TENDER_DOCUMENT_TEXT_SQL,
                  {"id": tender_id, "preview": 0})
    n_ok = sum(1 for r in tx if r.get("status") == "ok")
    tender["doc_text"] = {"total": len(tx), "ok": n_ok,
                          "manual_review": len(tx) - n_ok}
```

---

## 3. `frontend/src/api.js` — ixtiyoriy qulaylik

`DocumentText.jsx` `apiUrl()` + `fetch` bilan ishlaydi, shuning uchun bu
**shart emas**. Xohlansa `api` obyektiga qo'shiladi:

```js
  // Hujjat matni holati (P0-2) — deterministik parserlardan, AI emas
  documentsText: (id, params) => request('GET', `/tenders/${id}/documents/text`, { params }),
```

Qo'shilsa, `DocumentText.jsx` da `fetch(apiUrl(...))` ni
`api.documentsText(tenderId)` ga almashtirish mumkin.

---

## 4. `frontend/src/components/TenderDrawer.jsx` — komponentni ulash

Import (fayl boshidagi import bloki oxiriga):

```jsx
import DocumentText from './DocumentText.jsx'
```

Hujjatlar ro'yxati (`document_sections` / `documents`) chiqarilgan joydan
**keyin** — foydalanuvchi avval fayllarni, so'ng ularning matn holatini ko'radi:

```jsx
        <DocumentText tenderId={tender.id} />
```

`tender.id` o'rniga panelda ishlatilayotgan haqiqiy o'zgaruvchi nomi
qo'yiladi (`tenderId`, `t.id` va h.k.). Komponent hujjatsiz tenderda
`null` qaytaradi — shartli ko'rsatish kerak emas.

CSS import qilish **shart emas**: `DocumentText.jsx` o'zi
`../styles/doctext.css` ni import qiladi.

---

## 5. ETL ni muntazam yurgizish

Qo'lda:

```bash
python etl_doc_text.py --limit 300 --quiet
```

`--limit` ataylab qo'yilgan: har yurishda faqat yangi hujjatlar olinadi va
manba serveriga bosim tushmaydi. Ishlangan hujjat `--force` bo'lmasa
QAYTA yuklab olinmaydi.

### `run_etl.py` ga ulash (ixtiyoriy)

`main()` ichida, kategoriyalash qadamidan **oldin** (`if not
args.skip_categorize:` dan yuqorida):

```python
    # Hujjat matnini ajratish (P0-2) — barcha manbalardan keyin, chunki
    # yangi hujjat metama'lumoti shu paytda to'liq bo'ladi. Tender qo'shmaydi,
    # shuning uchun `etl_run` ga loglanmaydi.
    if args.with_docs:
        _ok, _err, _dt, out = run_script("etl_doc_text.py",
                                         ["--limit", "300", "--quiet"])
        emit(["\n===== post: hujjat matni =====", *out])
```

`--with-docs` shartiga bog'lash mantiqiy: hujjat metama'lumoti
(`etl_details.py`) o'sha bayroq bilan yig'iladi.

---

## 6. Bilib turib qabul qilingan qarorlar

1. **`tender_document_text` da FOREIGN KEY YO'Q.** `etl_details.py` har
   yurishda tenderning hujjatlarini `DELETE` qilib qaytadan `INSERT` qiladi.
   `ON DELETE CASCADE` bo'lganda soatlab yig'ilgan matn jimgina o'chib
   ketardi va hamma fayl qaytadan yuklab olinardi. `file_ref` barqaror
   (xt-xarid: fayl uuid, uzex: fayl yo'li) — qayta `INSERT` dan keyin ham
   matn o'sha faylga to'g'ri ulanadi. Yetimlarni tozalash so'rovi
   `schema_patch_doctext.sql` izohida.
2. **Fayl saqlanmaydi** — faqat matni. Diskda joy egallamaydi, huquqiy
   savol tug'ilmaydi.
3. **`.doc`, `.xls`, `.rar`, `.zip` — `unsupported`.** Eski binar formatlar
   uchun sof-Python parser yo'q, arxivlar esa ichidagi fayllarni alohida
   yozuv sifatida talab qiladi. Ikkalasi ham keyingi bosqich.
4. **Skan qilingan PDF — `unreadable`.** OCR (masalan `tesseract`) MVP
   doirasidan tashqarida; TZ aynan shu holatni "qo'lda tekshirish talab
   etiladi" deb belgilashni talab qiladi.
5. **"Matn bor" o'lchovi — belgi soni EMAS, harf soni.** Chizmalardan
   ba'zan `№ № ³ Ø296 Ø83` kabi 30-40 belgi "sizib" chiqadi. Faqat
   uzunlikka qarasak bu `ok` bo'lib qolardi va foydalanuvchi chizmani
   o'qilgan deb o'ylardi. Shuning uchun `MIN_LETTERS = 40` sharti bor.
6. **Ma'lum cheklov:** ba'zi PDF'larda shrift kodlashi buzilgan bo'lib,
   pypdf o'qiy oladigan, lekin ma'nosiz matn beradi
   (`fitLLA4 {-.r6Ol" BEP)KAATO>`). Bu `ok` bo'lib chiqadi. Mojibake'ni
   ishonchli aniqlash alohida ish — hozircha UI'dagi "Matnni ko'rish"
   tugmasi foydalanuvchiga buni darrov ko'rsatadi.
