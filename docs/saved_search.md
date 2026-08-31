# Saqlangan qidiruv — holat va chegara

**Xulosa:** CRUD **ishlaydi** va interfeysda **topiladi**. Uchta e'lon
qilingan qism esa **KEYINGA QOLDIRILGAN** va ular ishlayotgandek
ko'rsatilmaydi.

O'lchov sanasi: **2026-09-01**. Bazadagi `saved_search` qatorlari:
**0 ta**.

---

## 1. Nol ishlatishning ikki ma'nosi

**0 ta** qator ikki xil narsani anglatishi mumkin va ular
aralashtirilmasin:

| Ma'no | Kim hal qiladi |
|---|---|
| "kerak emas ekan" | mahsulot qarori |
| "ishlamaydi yoki topilmaydi" | muhandislik nuqsoni |

`_tests/saved_search_test.py` ikkinchisini **inkor etadi**: yaratish,
o'qish, tahrirlash, o'chirish, ijarachi ajratilishi va filtr
saqlanishi **haqiqiy HTTP so'rovlar** bilan tekshiriladi. Shundan
keyingina nol ishlatish mahsulot savoli bo'lib qoladi.

> Nol ishlatish **muvaffaqiyatli qabul EMAS**. Bu hujjat aynan shu
> xulosa chiqmasligi uchun yozilgan.

---

## 2. Ishlaydigan qism

| Amal | Yo'l | Holat |
|---|---|---|
| Yaratish | `POST /searches` | ishlaydi |
| Ro'yxat + mos tenderlar soni | `GET /searches` | ishlaydi |
| Tahrirlash (**qisman**) | `PUT /searches/{id}` | ishlaydi |
| O'chirish | `DELETE /searches/{id}` | ishlaydi |
| Qo'llash ("bajarish") | interfeys, `applySearch()` | ishlaydi |

**Interfeysda topiladi:** yon panelda `Saqlangan qidiruvlar` bo'limi,
yonida `+` tugmasi, har element ustida tahrirlash va o'chirish.
Bo'sh holatda `nav.noSearches` matni ko'rinadi.

**Ijarachi ajratilishi baza darajasida:**

```
company_id NOT NULL
company_id -> company_account(id) ON DELETE CASCADE
```

Har SQL `WHERE company_id = %(company_id)s` bilan cheklangan. Sinov
ikkinchi ijarachi nomidan o'qish, tahrirlash va o'chirishga urinadi
— uchalasi ham **404** beradi.

---

## 3. KEYINGA QOLDIRILGAN — saqlanadi, lekin HECH NARSA QILMAYDI

Uchala qism jadvalda va API javobida **bor**, ya'ni ular "tayyor"dek
ko'rinadi. Aslida ulanmagan:

### 3.1 `notify`

Bayroq saqlanadi (standart `true`), lekin **bildirishnoma tsikli uni
o'qimaydi**. `api/notify.py` nomzodlarni `company_profile` dan
oladi (`PROFILE_SQL = queries.PROFILE_GET_SQL`), `saved_search` ga
umuman murojaat qilmaydi.

Shu sababli bayroq **interfeysda ko'rsatilmaydi** — ishlamaydigan
tugmani ko'rsatish yolg'on va'da bo'lardi.

### 3.2 `last_seen_at`

Ustun bor, lekin uni to'ldiradigan yo'l **yo'q**. "Oxirgi ko'rgandan
keyingi yangi moslar" belgisi mavjud emas.

Uni to'ldiradigan `SEARCH_SEEN_SQL` `api/queries.py` da **bor edi**,
lekin **chaqiruvchisi yo'q edi** — o'lik SQL "imkoniyat bor" degan
yolg'on taassurot berardi. U **olib tashlandi**. Ustun jadvalda
qoldi (ma'lumot yo'qotmaslik uchun).

### 3.3 `categories`

Saqlanadi va API javobida qaytadi, lekin **skorlashda ishlatilmaydi**:
`_search_to_profile()` faqat `keywords`, `regions`, `currency`,
`min_cost`, `max_cost` ni uzatadi. Interfeys shakli ham kategoriya
tanlagichini ko'rsatmaydi.

---

## 4. Tuzatilgan nuqsonlar (2026-09-01)

### 4.1 Tahrirlash berilmagan maydonni JIMGINA tozalardi

`ProfileForm.tsx` shakli `categories` va `notify` ni **yubormaydi**.
`PUT` esa to'liq almashtirish edi, ya'ni pydantic standart qiymatlari
(`[]` va `true`) bazaga yozilardi. Foydalanuvchi nomni o'zgartirsa,
kategoriyalari **yo'qolardi** va buni hech qayerda ko'rmasdi.

Endi `SavedSearchPatchIn` — har maydon ixtiyoriy, `exclude_unset=True`
bilan joriy qiymat ustiga qo'yiladi. Bu `notify_settings` dagi bilan
bir xil naqsh (u yerda `{"enabled": false}` yuborish SMTP sozlamasini
o'chirib yuborardi).

### 4.2 O'chirish xatosi yashirilardi

```ts
try { await api.deleteSearch(s.id) } catch { /* ignore */ }
```

O'chirish muvaffaqiyatsiz bo'lsa ham interfeys "o'chdi" deb
ko'rsatardi, ro'yxat yangilanganda element **qayta paydo bo'lardi** —
sababsiz. Endi xato ko'rsatiladi va ro'yxat yangilanmaydi.

---

## 5. Nima qilish kerak (agar imkoniyat davom ettirilsa)

Tartib — qiymati bo'yicha:

1. **`notify` ni ulash.** Bildirishnoma tsikli har saqlangan qidiruv
   bo'yicha ham skorlasin, nafaqat `company_profile` bo'yicha. Bu
   imkoniyatning **asosiy qiymati**: "shu filtrga mos tender chiqsa
   xabar ber".
2. **`last_seen_at`.** "Ko'rildi" endpointi + yon panelda yangi
   moslar soni.
3. **`categories`.** Skorlashga qo'shish va shaklga tanlagich.

Ulanish qo'shilganda `_tests/saved_search_test.py` dagi 6-bo'lim
**yiqiladi** — u hozirgi holatni ataylab qulflaydi va hujjatni
yangilashga majbur qiladi.

---

## 6. Sinov

`_tests/saved_search_test.py`:

| Bo'lim | Nimani tekshiradi |
|---|---|
| 1 | har SQL ijarachi bilan cheklangan, o'lik SQL yo'q, qisman yangilash |
| 2 | shu hujjat bor va bajarilmagan qismlarni aniq nomlaydi |
| 3 | interfeysda topiladi, o'chirish xatosi yashirilmaydi |
| 4 | bazadagi son hujjatdagi bilan mos, chegara baza darajasida |
| 5 | **haqiqiy CRUD** + ijarachi ajratilishi + filtr saqlanishi |
| 6 | `notify` / `last_seen_at` **ulanmaganini** ataylab tasdiqlaydi |
