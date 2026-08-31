# API xato kodlari — shartnoma

**Yagona manba:** [`api/xatolar.py`](../api/xatolar.py) dagi `KODLAR`.
Tarjimalar: `frontend/src/locales/{uz,ru,en}.ts` da `err.<KOD>` kaliti.

---

## 1. Nima uchun

**O'lchangan holat (2026-09-01).** Interfeys uch tilli, server
xatolari esa faqat o'zbekcha matn edi:

```
api/main.py da 75 ta `HTTPException`
  shundan 28 tasi `detail=str(e)`
```

Ikki zarar:

1. **Til yo'qolardi.** Rus yoki ingliz tilida ishlayotgan
   foydalanuvchi xatoni o'zbekcha ko'rardi — aynan noto'g'ri
   ketganda.
2. **Ichki tafsilot oshkor bo'lardi.** `str(e)` SQL patch
   nomlarini, jadval nomlarini, SMTP host/portni va modul
   chegaralarini javobga chiqarardi.

**Yechim:** kod — shartnoma, matn — ko'rinish.

---

## 2. Javob shakli

```json
{
  "error": {
    "code": "TENDER_NOT_FOUND",
    "params": { "id": 4211 },
    "diagnostic_id": "fbda112f1c344c60976a86080e196571"
  },
  "detail": "TENDER_NOT_FOUND"
}
```

| Maydon | Ma'no |
|---|---|
| `error.code` | **Barqaror**, ASCII, KATTA HARF. Shartnoma shu. |
| `error.params` | Tarjimaga qo'yiladigan **son va atama** (tayyor jumla emas). |
| `error.diagnostic_id` | `X-Request-Id` bilan bir xil — jurnalga ulanish. |
| `detail` | Eski o'quvchilar uchun; u ham **kod**, o'zbekcha jumla emas. |

422 (maydon tekshiruvi) da qo'shimcha:

```json
"fields": [{ "field": "smtp_port", "code": "FIELD_PORT_RANGE" }]
```

Maydon nomi — **sxema nomi**, ya'ni tildan mustaqil.

---

## 3. Ichki tafsilot qayerda

Javobda **yo'q**. U server jurnalida:

```
WARNING api.xatolar: [fbda112f] xato SMTP_SEND_FAILED (502): SMTP xatosi (mail.uz:587)
```

Foydalanuvchi `diagnostic_id` ni aytsa, jurnaldan aynan o'sha
so'rov topiladi. Ya'ni tafsilotni javobdan olib tashlash yordamni
**qiyinlashtirmaydi**.

`5xx` — `error` darajasida, qolgani `warning`: mijoz xatosi (404,
400) server nosozligi emas.

---

## 4. Yangi kod qo'shish

1. `api/xatolar.py:KODLAR` ga kod va **standart HTTP holati**.
   Ro'yxatda bo'lmagan kod bilan `Xato` yaratib bo'lmaydi —
   imlo xatosi ishlab chiqishda chiqadi.
2. Uchala lug'atga `err.<KOD>` tarjimasi. **Ikki mustaqil to'siq**
   uni majburlaydi: `tsc` (`ru`/`en` — `Record<TKey, string>`) va
   `_tests/xato_kodlari_test.py`.
3. Ko'tarish:

```python
raise xatolar.Xato("FILE_TOO_LARGE", {"max_mb": 25})
```

`params` kaliti tarjimadagi `{max_mb}` bilan mos bo'lsin —
`frontend/src/xato.test.ts` buni tekshiradi.

**Chegarada** (ichki istisnoni HTTP ga aylantirishda):

```python
except ValueError as e:
    raise xatolar.kodli(e, "FIELD_INVALID")
```

`kodli()` xato **allaqachon kodli bo'lsa uni o'zgartirmaydi** —
modul bergan aniq kod (`TELEGRAM_TOKEN_MISSING`) umumiy kod bilan
almashib ketmaydi.

---

## 5. Modul istisnolari

`AuthError`, `NotifyError`, `TelegramError`, `ImportFormatError`,
`RuxsatXato`, `AIUnavailable` — hammasi `kod=` argumentini oladi.
Xabar matni **server jurnali uchun** qoladi, javobga tushmaydi.

`_tests/xato_kodlari_test.py` har modulda **kodsiz `raise` qolmaganini**
sanaydi.

`xatolar.Xato` `ValueError` **va** `LookupError` dan meros oladi:
loyihadagi mavjud `except ValueError` / `except LookupError`
qo'riqchilari jimgina o'chib qolmasin (bu o'lchangan — `chat_test`
aynan shu sababdan yiqilgan edi).

---

## 6. Interfeys tomoni

`frontend/src/api.ts` javobdan kodni oladi va matnni **foydalanuvchi
tilida** yig'adi:

```ts
detail = xatoMatni(kod, params)
throw new ApiError(detail, res.status, raw, retryAfter,
                   kod, params, fields, tashxis)
```

Shu tufayli xatoni ko'rsatadigan **24 ta komponent o'zgarmasdan**
uch tilli bo'ldi — ular avvalgidek `e.message` ni chizadi.

`xatoMatni()` tarjima topilmasa **kodni** qaytaradi, bo'sh matn emas:
ekranda `TENDER_NOT_FOUND` ko'rinsa muammo darhol ko'zga tashlanadi.

Til `localStorage` dan o'qiladi (`readLang()`), chunki `fetch`
javobi React daraxtidan tashqarida qayta ishlanadi.

---

## 7. Sinovlar

| Fayl | Nimani qo'riqlaydi |
|---|---|
| `_tests/xato_kodlari_test.py` | ro'yxat butunligi, tarjima to'liqligi, kodsiz `raise` yo'qligi, **haqiqiy javoblarda** kirill/o'zbek jumla yo'qligi, `Accept-Language` kodni o'zgartirmasligi |
| `frontend/src/xato.test.ts` | server ro'yxati ↔ lug'at mosligi, `{belgi}` lar uchala tilda bir xil va server `params` ida uchrashi, **bitta kod → uch xil matn** |
| `tsc` | uchala lug'atning to'liqligi |
