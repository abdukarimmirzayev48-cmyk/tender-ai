# Bildirishnoma tili — xabar PLATFORMA TILIDA ketadi

Talab: *"Bildirishnomalar platforma qaysi tilda bo'lsa, shu tilda ma'lumot
yuborishi shart."*

Interfeys uch tilda ishlaydi (`uz` / `ru` / `en`). Endi **email va Telegram
xabarlari ham** o'sha tilda keladi: mavzu, maydon nomlari, moslik sabablari,
summa ajratgichi va sana formati.

| Fayl | Vazifasi |
|---|---|
| `schema_patch_notify_lang.sql` | `notify_settings.lang` ustuni (idempotent) |
| `api/i18n.py` | xabar matnlari lug'ati (uz/ru/en) + `t()` |
| `api/notify.py` | xabarni tanlangan tilda quradi |
| `api/matching.py` | sabablarni struktura (`reason_keys`) bilan qaytaradi |
| `frontend/src/App.tsx` | tanlangan tilni serverga yozadi |

---

## 1. Baza

```bash
psql "dbname=xtxarid user=postgres host=localhost" -f schema_patch_notify_lang.sql
```

Patch **qo'llanmasa ham tizim ishlaydi**: `api/notify.py` ustun borligini
tekshiradi va yo'q bo'lsa xabar standart tilда (o'zbekcha) ketadi. Interfeys
esa `lang_ready: false` ni ko'rib "patch kerak" deb ogohlantiradi — jimgina
"til o'zgardi" deb ko'rsatmaydi.

## 2. Til qayerdan olinadi

```
Foydalanuvchi yon paneldagi sozlamalar menyusida tilni tanlaydi
        ↓  (localStorage — interfeys uchun)
App.tsx:  PUT /notify/settings {"lang": "ru"}     ← FAQAT farq bo'lsa
        ↓
notify_settings.lang = 'ru'
        ↓
notify_new.py (ETL dan keyin) → api/notify.py → api/i18n.py lug'ati
        ↓
Email + Telegram — rus tilida
```

**Nega bazada, brauzerda emas:** xabarni server yuboradi — soatlik jadval
bo'yicha, foydalanuvchi ilovani ochmagan bo'lsa ham. Server brauzerdagi
tanlovni ko'rmaydi.

**Nega interfeysда alohida "xabar tili" tanlagichi yo'q:** til bitta joyda
tanlanadi va interfeys ham, xabar ham unga bo'ysunadi. Ikkinchi tanlagich
"interfeys ruscha, xat o'zbekcha" holatini keltirib chiqarardi.

## 3. Nima tarjima qilinadi, nima yo'q

Tarjima qilinadi: mavzu, "Buyurtmachi/Summa/Muddat/Hudud" yorliqlari, ball
so'zi (rus tilida ko'plik ham: *1 балл / 2 балла / 5 баллов*), moslik
sabablari, tugma matni, izohlar, summa ajratgichi (`1 234 567` — uz/ru,
`1,234,567` — en) va sana (`31.07.2026` — uz/ru, `2026-07-31` — en, chunki
`07/31` va `31/07` ni ajratib bo'lmaydi).

Tarjima qilinmaydi (bu — MA'LUMOT, matn emas): tender nomi, buyurtmachi,
hudud nomi, valyuta kodi, kartochka havolasi. Telegramда maydon nomlari
o'rniga emoji (🏢 💰 ⏳ 📍) — ular tilga bog'liq emas.

## 4. Sabablar qanday tarjima qilinadi

`api/matching.py` endi ikki ko'rinishda qaytaradi:

```python
"reasons":     ["2 ta kalit so‘z mos: nasos, quvur"]          # tayyor matn (interfeys)
"reason_keys": [{"key": "reason.keywords",
                 "vars": {"n": 2, "items": "nasos, quvur"}}]   # struktura (xabar)
```

`reasons` **o'zgarmagan** — `/match` javobini ko'radigan interfeys uchun hech
narsa buzilmaydi. Xabar esa `reason_keys` dan quriladi, ya'ni tarjima tayyor
matnni "qidirib almashtirish" bilan emas, manbadan bo'ladi.

## 5. Sinov xabari

*Akkaunt → Bildirishnoma → Sinov xabari* tugmasi **bitta** xabar yuboradi —
**platforma tilida**, xuddi haqiqiy bildirishnoma kabi (email ham, Telegram
ham). Sinovning mohiyati "haqiqiy xabar qanday keladi" ni ko'rsatishда,
shuning uchun u haqiqiysidan na tili, na soni bilan farq qilmaydi.

Tarjimalarni solishtirish kerak bo'lsa: tilni almashtiring va tugmani qayta
bosing — yangi xabar yangi tilда keladi (til `PUT /notify/settings` bilan
darhol saqlanadi).

Sinov xabari `notify_sent` ga **yozilmaydi** va `telegram_enabled` ni talab
qilmaydi — yoqishdan oldin tekshirish uchun. Javobdagi `lang` maydoni xabar
qaysi tilda ketganini aytadi (interfeys shuni ko'rsatadi).

## 6. Tekshirish

```bash
# 1) Til saqlanadimi
curl -X PUT http://localhost:8000/notify/settings \
  -H 'Content-Type: application/json' -d '{"lang":"ru"}'
curl http://localhost:8000/notify/settings      # -> "lang":"ru","lang_ready":true

# 2) Xabar shu tilda quriladimi (hech narsa yuborilmaydi)
python notify_new.py --dry-run --since-hours 168

# 3) Sinovlar (ichida til sinovlari ham bor)
.venv/Scripts/python.exe _tests/notify_test.py
```

Interfeysda: yon panel → sozlamalar menyusi → tilni almashtiring →
**Akkaunt → Bildirishnoma** bo'limida joriy til ko'rinadi → *Sinov xabari*
tugmasi (email va Telegram) o'sha tilda xabar yuboradi.
