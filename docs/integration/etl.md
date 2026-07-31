# ETL integratsiyasi — P0-1 ("platformalarni soatiga bir marta kuzatish")

Bu hujjat **ETL agenti** kiritgan o'zgarishlarni va **boshqa agentlar** (API /
frontend) tomonidan bajarilishi kerak bo'lgan qadamlarni yig'adi.

> ETL agenti quyidagi UMUMIY fayllarga **tegmagan**:
> `api/main.py`, `api/queries.py`, `requirements-api.txt`, `frontend/**`.
> Ularga tegishli har qanday o'zgarish shu yerda aynan ko'chiriladigan
> ko'rinishda yozilgan.

---

## 1. Nima o'zgardi (ETL tomonida)

| Fayl | O'zgarish |
|---|---|
| `etl_tenders.py` | `--ref` parametri qo'shildi (standart `ref_tender_public`). Endi `ref_selection_public` ni ham shu skript yig'adi. `--limit` (sinov uchun) qo'shildi. |
| `etl_uzex.py` | `tender.type` endi `TypeId` dan olinadi (`TYPE_BY_ID = {1:'selection', 2:'tender'}`). Ilgari `"tender"` qattiq yozilgan edi. |
| `run_etl.py` | `.env` o'qiladi (`load_dotenv`); bola-jarayon chiqishi UTF-8 dekodlanadi; platformalar **parallel**, platforma ichidagi qadamlar **ketma-ket**; yangi qadamlar (2-reyestr + TypeId=1); `--limit`, `--sequential`, `--skip-categorize` bayroqlari. |
| `schema_patch_etl_coverage.sql` | **YANGI** — `dim_status` ga `tech_check_docs` va `agree_objections` qo'shadi (idempotent). **Bazaga allaqachon qo'llangan.** |
| `register_task.ps1` | **YANGI** — Windows Task Scheduler soatlik vazifasi (ASCII-only). **Hali ro'yxatdan o'tkazilmagan** (pastga qarang). |
| `_tests/etl_coverage_test.py` | **YANGI** — qamrov/statuslar/ID to'qnashuvi/orkestrator sinovi. |
| `AVTOMATLASHTIRISH.md` | Windows bo'limi qo'shildi. |

### Manba haqidagi asosiy fakt

Har platforma **bir emas, ikki** ochiq reyestr chop etadi. Faqat bittasini
yig'ish ochiq lotlarning katta qismini yo'qotadi:

| Platforma | Reyestr | `tender.type` | Hajm (2026-07-28 o'lchov) |
|---|---|---|---|
| xt-xarid | `ref_tender_public` | `tender` | ochiq 6 |
| xt-xarid | `ref_selection_public` | `selection` | ochiq 125 (jami 3009) |
| uzex | `TradeList TypeId=2` | `tender` | faol 60 |
| uzex | `TradeList TypeId=1` | `selection` | faol 653 |

ID fazolari **kesishmaydi** (manba darajasida tekshirilgan, sinovда avtomatik
qayta tekshiriladi), shuning uchun ikkala reyestr bitta `tender` jadvalida
xavfsiz yashaydi.

**Natija:** bazada ochiq lotlar **66 -> 850** ga, jami yozuvlar **342 -> 1125**
ga ko'tarildi (783 yangi yozuv).

---

## 2. API agenti uchun — HECH NARSA QILISH SHART EMAS

`api/queries.py` va `api/main.py` o'zgarishsiz to'g'ri ishlaydi:

* `STATUSES_SQL` (`/statuses`) `dim_status` dan o'qiydi, ya'ni ikkita yangi
  status **avtomatik** chiqadi (`COALESCE(name_uz, name_ru)` to'ldirilgan).
* `LEFT JOIN dim_status ... AND s.domain='tender'` — yangi qatorlar ham
  `domain='tender'` bilan kiritilgan, join buzilmaydi.
* `t.type` maydoni allaqachon `SELECT` da bor; endi u `'selection'` qiymatini
  ham qaytaradi. Hech qanday `CHECK`/`FK` cheklovi yo'q.
* `FRESHNESS_SQL` (`DISTINCT ON (source_platform)`) — orkestrator har
  platforma uchun **bitta** `etl_run` qatori yozadi (qadamlar ko'p bo'lsa ham),
  shuning uchun "Yangilangan: ..." ko'rsatkichi avvalgidek 2 qator beradi.

`requirements-api.txt` ham o'zgarish talab qilmaydi — `python-dotenv>=1.2`
allaqachon ro'yxatda (`run_etl.py` shundan foydalanadi).

---

## 3. Frontend agenti uchun — MAJBURIY o'zgarish YO'Q

Tekshirilgan:

* `frontend/src/format.js` dagi havola quruvchi **to'g'ri ishlaydi**:
  ```js
  'xt-xarid': (id) => `https://xt-xarid.uz/procedure/${id}/core`,
  ```
  xt-xarid SPA'sining o'z kodida havola universal tarzda quriladi
  (`procedure_url: "/procedure/" + model.proc_id + "/core"`), ya'ni
  `selection` protseduralari ham xuddi shu manzilda ochiladi.
* `type` maydoni frontendda hech qayerda ko'rsatilmaydi, shuning uchun yangi
  `'selection'` qiymati hech narsani buzmaydi.

### Ixtiyoriy (tavsiya) — protsedura turini ko'rsatish

Endi katalogda ikki xil protsedura aralash keladi. Foydalanuvchiga farqni
ko'rsatish uchun `frontend/src/format.js` ga quyidagini qo'shish mumkin:

```js
// Protsedura turi (tender.type) -> foydalanuvchiga ko'rinadigan nom
export const TYPE_LABEL = {
  tender:    'Tender',
  selection: 'Eng yaxshi taklifni tanlash',
  contest:   'Tanlov',
}
export const typeLabel = (t) => TYPE_LABEL[t] || t || '—'
```

va kartochkada (`CatalogView.jsx` / `TenderDrawer.jsx`) nishon sifatida:

```jsx
{t.type && <span className="badge badge--type">{typeLabel(t.type)}</span>}
```

### TEKSHIRILMAGAN (frontend agenti hal qilsin)

`frontend/src/format.js` dagi uzex havolasi:

```js
'uzex': (id) => `https://etender.uzex.uz/lot/${id}`,
```

TypeId=2 (tender) uchun to'g'ri. **TypeId=1 ("eng yaxshi taklifni tanlash")
yozuvlari uchun bu manzil brauzerda tekshirilmagan** — etender.uzex.uz SPA
istalgan yo'lda bir xil HTML qaytaradi, shuning uchun HTTP orqali aniqlab
bo'lmadi. Bitta `selection` lotini qo'lda ochib tasdiqlang; agar boshqa yo'l
kerak bo'lsa, havolani `t.type` ga qarab tanlang.

---

## 4. Boshqa agentlar uchun — `run_etl.py` ga yangi qadam qo'shish

`run_etl.py` ikki xil qadamni ajratadi:

* **Manba qadami** — `build_groups()` dagi platforma ro'yxatiga qo'shiladi.
  Bir platformaning qadamlari KETMA-KET yuriladi (bitta hostga parallel
  urilmaslik uchun) va butun guruh uchun BITTA `etl_run` qatori yoziladi.
* **Post-qadam** — barcha manbalar tugagach `main()` da yurgiziladi.
  Tender qo'shmaydi, shuning uchun `etl_run` ga loglanmaydi.
  Hozir shunday qadam bitta: `etl_categorize.py`.

Yangi post-qadam (masalan `notify_new.py`, `etl_doc_text.py`) qo'shish uchun
`main()` da `etl_categorize.py` chaqirig'ining yonига qo'shing:

```python
    if not args.skip_categorize:
        _ok, _err, _dt, out = run_script("etl_categorize.py", [])
        emit(["\n===== post: kategoriyalash =====", *out])

    # YANGI post-qadam shu yerga:
    _ok, _err, _dt, out = run_script("notify_new.py", [])
    emit(["\n===== post: bildirishnoma =====", *out])
```

`run_script()` bola-jarayonni UTF-8 bilan dekodlaydi va
`PYTHONIOENCODING=utf-8` beradi — bu qatorlarni takrorlamang, `run_script` ni
ishlating, aks holda kirill chiqishi Windows'da yo'qoladi.

**Tartib muhim:** bildirishnoma qadami `tender.first_seen_at` ga tayanadi va u
faqat manba qadamlaridan KEYIN to'g'ri bo'ladi, shuning uchun post-qadamlar
parallel emas, ketma-ket yuriladi.

---

## 5. DevOps / operator uchun — QOLGAN QADAMLAR

1. **Soatlik vazifani ro'yxatdan o'tkazish** (skript tayyor, sintaksisi
   tekshirilgan, lekin ATAYLAB ro'yxatdan o'tkazilmagan):

   ```powershell
   cd "D:\MVP projects\tender-ai"
   powershell -NoProfile -ExecutionPolicy Bypass -File .\register_task.ps1 -WhatIf   # quruq sinov
   powershell -NoProfile -ExecutionPolicy Bypass -File .\register_task.ps1           # haqiqiy
   ```

   O'chirish: `.\register_task.ps1 -Unregister`

2. **Huquqiy tekshiruv** (TZ NFT, "Yuqori" xavf): hujjatlashtirilmagan ichki
   API'larni uzluksiz so'rash shartlari `AVTOMATLASHTIRISH.md` da yozilgan.
   Soatlik yurishni yoqishdan oldin hal qilinishi kerak.

3. **To'liq yurish uzoq — o'lchangan**: uzex `TypeId=1` da ~650 yozuv bor va
   har biriga alohida `GetTrade` so'rovi ketadi.

   | Qadam | O'lchangan vaqt |
   |---|---|
   | xt-xarid (2 reyestr) | 7 s |
   | uzex TypeId=2 (60 yozuv) | 101 s |
   | uzex TypeId=1 (653 yozuv) | 1196 s (~20 daq) |
   | **Jami (parallel)** | **~21,5 daqiqa** |

   Soatlik interval bunga yetadi (21 daq < 60 daq), `ExecutionTimeLimit`
   2 soat qilib qo'yilgan va `MultipleInstances=IgnoreNew` tufayli yurishlar
   ustma-ust tushmaydi. Agar `--with-docs` yoqilsa vaqt yana oshadi —
   o'shanda intervalni 2 soatga chiqarish yoki hujjatlarni alohida, kamroq
   chastotali vazifaga ajratish kerak bo'ladi.
