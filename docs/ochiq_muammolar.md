# Ochiq muammolar reyestri

**O'lchov sanasi: 2026-09-01.** Har band **o'lchangan dalil** bilan.
Taxmin qilingan raqam yo'q; o'lchanmagan narsa `O'LCHANMAGAN` deb
yozilgan.

Bu ro'yxat 9–21-vazifalar davomida topilgan va **tuzatilmagan**
narsalarni bir joyga yig'adi. Tuzatilganlari kirmagan.

| Daraja | Ochiq | Yopilgan |
|---|---|---|
| Bloker | 2 | 1 (B-2) |
| Ma'lumot butunligi | 2 | 1 (M-1) |
| Qamrov qarzi | 3 | — |
| Operatsiya | 5 | — |
| Sinov jarayoni | 0 | 1 (S-1) |
| Tugallanmagan imkoniyat | 2 | — |
| Kichik | 5 | — |
| **Jami** | **19** | **3** |

**Oxirgi yangilanish: 2026-09-01.** Yopilganlar §9 da.

---

## 1. BLOKERLAR

### B-1. Server yo'q

Joylashtirish artefaktlari (`systemd`, `Caddy`, `deploy.sh`,
`backup.sh`, `restore-test.sh`) **yozilgan va sinovdan o'tgan**
(`deploy_test` 114/114), lekin **hech qachon haqiqiy mashinada
yurgizilmagan**. Ular repozitoriyada tekshiriladi, serverda emas.

**Ta'siri:** birinchi joylashtirish — sinalmagan yo'l.
**Manba:** 14-vazifa.

### ~~B-2. Manba `ref_selection_public` HTTP 400 qaytaradi~~ — YOPILDI, DA'VO NOTO'G'RI EDI

> Qayta o'lchandi: xato **o'tkinchi** edi, doimiy emas (§9.2).
> Quyidagi tavsif TARIXIY.

O'lchandi (2026-09-01, to'g'ridan-to'g'ri chaqiruv):

```
ref_tender_public        OK    (status='open' bo'yicha 6 ta yozuv)
ref_selection_public     XATO  HTTP 400 — doimiy
```

`etl_coverage_test` shu sababdan **butunlay yiqiladi** (xulosa
qatorigacha yetib bormaydi).

**Ta'siri:** "Eng yaxshi taklifni tanlash" reyestri **umuman
olinmayapti**. `ref_tender_public` javob beradi, ya'ni bu qisman
uzilish.

**MUHIM:** bu bizning kodimiz emas — `etl_tenders.py` oxirgi marta
`b3e819f` da o'zgargan (bu sessiyadan ancha oldin). Manba tomonida
so'rov shakli o'zgargan bo'lishi mumkin. **Diagnostika qilinmagan.**

### B-3. Inson halqasi hali bo'sh (pilot tugallanmagan)

`tender_routing` da **310** yozuv, shundan **30** tasida inson
qarori bor. Ya'ni 4 qatlam (kodlash, talab, yo'naltirish, malaka)
inson tasdig'isiz ishlayapti.

**Ta'siri:** aniqlik da'volari inson dalilisiz.
**Manba:** avvalgi sessiyalar; xotirada `pilot-production-gacha-qoldirildi`.

---

## 2. MA'LUMOT BUTUNLIGI

### ~~M-1. 26 ta hujjat DALILSIZ `ok` deb belgilangan~~ — YOPILDI

> Sabab isbotlandi va uch qismli tuzatish qo'llandi (§9.3).
> Quyidagi tavsif TARIXIY.

```sql
SELECT count(*) FROM tender_document d
 WHERE d.holat='ok' AND NOT EXISTS (
   SELECT 1 FROM tender_document_text t
    WHERE t.tender_id=d.tender_id AND t.file_ref=d.file_ref
      AND t.status='ok');
-- 26   (jami `ok` hujjat: 3007)
```

Tekshirilgan namunalarda `tender_document_text` da qator **umuman
yo'q** (`matn_holati = NULL`) — ya'ni "matn ajratildi" degan
belgi bor, matn esa yo'q.

Bu loyihaning takrorlanuvchi nuqson sinfi: **dalilsiz yorliq**.

`doc_qamrov_test` buni ushlaydi (79/80) — **lekin faqat `--online`
rejimda** (S-1 ga qarang).

### M-2. 30 ta inson qarorining AKTORI noma'lum

```
tender_routing, inson_qaror IS NOT NULL   : 30
  qaror_actor_id IS NULL                  : 30   (100%)
  qaror_ishonch  IS NULL                  :  0
```

Ishonch darajasi yozilgan, **kim** ekani esa yo'q. Bu qarorlar
aktor kuzatuvi (11-vazifa) joriy etilishidan OLDIN yozilgan.

**Ta'siri:** audit izi to'liq emas; "kim tasdiqladi" savoliga
javob yo'q. Orqaga qarab to'ldirib bo'lmaydi — ma'lumot yo'q.

### M-3. `audit_jurnal` da sinov yozuvi qolgan

`id=37`, `amal='huquq_sinov'`, `company_id=2`. 12-vazifadagi
huquq tekshiruvi paytida yozilgan.

Jadval **append-only** (`audit_jurnal_ozgarmas_trg`) — o'chirib
bo'lmaydi va bu **ataylab shunday**.

**Holat:** foydalanuvchiga uch variant taklif qilindi, javob
kutilmoqda. Tavsiya — qoldirish (jami 7 ta yozuvdan biri).

---

## 3. QAMROV QARZI

### Q-1. 2365 tender talab ajratishdan o'tmagan (65.6%)

```
tender                    3605
talab topildi             1161   32.2%
YAROQLI, lekin NAVBATDA   2365   65.6%
hujjat yopiq, navbatda      79    2.2%
hisobga olinmagan             0
```

Ishlangan tenderlarning **100%** ida talab topilgan — ya'ni
**sifat muammo emas, o'tkazuvchanlik muammo**.

`reyestr` yo'li bepul va modelsiz, ya'ni yurgizish arzon.
**Manba:** 18-vazifa.

### Q-2. Embedding qamrovi 55.8%

```
doc_chunk jami        188 561
vektori bor           105 174   (55.8%)
```

**Ta'siri:** RAG qidiruvi hujjatlarning yarmini ko'rmaydi.

### Q-3. Katalog: 749 mahsulot kodsiz (41.7%)

```
mahsulot   1797
aniq kod    467   25.99%
keng kod    581
kodsiz      749   41.68%
```

Kodsizlar **ataylab** shunday: dalil yetarli bo'lmaganda kod
qo'yilmaydi (aniqlik qamrovdan muhim). Navbat
`v_catalog_kod_navbat` da.
**Manba:** 15-vazifa.

---

## 4. OPERATSIYA

### O-1. RTO O'LCHANMAGAN

`restore-test.sh` tiklash vaqtini o'lchaydi, lekin **hech qachon
yurgizilmagan** (B-1). Taxminiy raqam ataylab yozilmadi.

### O-2. Zaxira faqat mahalliy diskda

Tashqi nusxa yo'q. Disk yo'qolsa zaxira ham yo'qoladi.

### O-3. Monitoring / ogohlantirish yo'q

`systemd` xizmatni qayta ko'taradi, lekin **buni hech kim
bilmaydi**. `/ready` bor, uni so'raydigan narsa yo'q.

### O-4. `pip-audit` yurgizilmagan

Bog'liqliklardagi ma'lum zaifliklar **tekshirilmagan**.
12-vazifada aytilgan, bajarilmagan.

### O-5. HTTPS majburiy emas

`APP_PUBLIC_URL` `http://` bo'lsa `production` da faqat
**ogohlantirish** yoziladi, xato emas. Ichki TLS tugatgichi
ortida bu qonuniy bo'lishi mumkin — shuning uchun ataylab
yumshoq qoldirilgan.
**Manba:** 19-vazifa.

---

## 5. SINOV JARAYONI

### ~~S-1. `run_tests.py` standart holatda BAZASIZ yuradi~~ — YOPILDI

> Ikki mustaqil bayroq joriy etildi; +527 tekshiruv (§9.1).
> Quyidagi tavsif TARIXIY.

`--offline` standart. Bazali tekshiruvlar **umuman
bajarilmaydi**, va "o'tkazib yuborilgan sinov — sinov emas".

**Bu allaqachon zarar keltirdi:** `review_butunlik_test` dagi
ikkita tekshiruv **11-vazifadan beri** (fikstura eskirgani
sababli) yiqilib turgan va **hech kim ko'rmagan**. Tuzatildi
(`f5c1348`), lekin sabab — jarayon.

Ikki rejim farqi o'lchandi:

| Rejim | Natija | Vaqt |
|---|---|---|
| `--offline` (standart) | 33 to'plam, 33 o'tdi | 246 s |
| `--online` | 33 to'plam, **31 o'tdi, 2 yiqildi** | 502 s |

Yiqilganlar: `doc_qamrov_test` (M-1), `etl_coverage_test` (B-2).

**Tavsiya:** CI da `--online` yuritish yoki kamida bazali
rejimni alohida yurgizish.

---

## 6. TUGALLANMAGAN IMKONIYATLAR

### T-1. Saqlangan qidiruv — uch qism ulanmagan

`saved_search` da **0 ta** qator. CRUD, ijarachi ajratilishi va
interfeys **ishlaydi** (`saved_search_test` 57/57), lekin:

| Qism | Holat |
|---|---|
| `notify` | bildirishnoma tsikli o'qimaydi |
| `last_seen_at` | to'ldiradigan yo'l yo'q |
| `categories` | skorlashda ishlatilmaydi |

Batafsil: `docs/saved_search.md`.
**Manba:** 21-vazifa.

### T-2. RAG qatlamlari O'LCHANMAGAN

Sifat o'lchovi pullik AI chaqiruvini talab qiladi, u esa
`AI_PAID_ENABLED` bilan bloklangan (ataylab). Ya'ni RAG
javoblarining aniqligi **noma'lum**.

---

## 7. KICHIK

### K-1. Tarjimalar ko'rib chiqilmagan

105 xato kodining ruscha va inglizcha tarjimalari **ona tilida
so'zlashuvchi ko'rmagan**.

### K-2. `params` bog'lanishi tur bilan qo'riqlanmaydi

Server `{daqiqa}` yubormasa, foydalanuvchi qavsli kalitni
ko'radi. Sinov matn darajasida tekshiradi (`xato.test.ts`), tur
tizimi emas.

### K-3. Holat lug'ati ikki joyda

`requirement_holat()` SQL funksiyasi va sinovdagi ro'yxat.
Sinov mosligini tekshiradi, lekin takrorlanish qoladi.

### K-4. `AI_SKIPPED` params'ida o'zbekcha matn

`sabab` bazadan keladi va o'zbekcha. Tarjimada
**ishlatilmaydi**, lekin javobda ko'rinadi.

### K-5. `VITE_ERP_WEB` mahalliy qurilmaga tushadi

Ishlab chiquvchining `.env` idagi `http://localhost:5174`
uning **mahalliy** qurilmasiga singadi. Joylashtirishda bo'sh
qoladi va qo'rovul uni ushlaydi — ya'ni ishlab chiqarishga
tushmaydi.

---

## 8. TUZATILGAN DA'VONI TO'G'RILASH

20-vazifa hisobotida `tender_requirement` CHECK cheklovi
"to'g'ri to'ldirilgan inson tasdig'ini ham rad etyapti" deb
yozilgan edi va u **ma'lumot yo'qotishi** deb baholangan.

**Bu noto'g'ri edi.** Tekshirildi: cheklov to'g'ri ishlayapti,
**sinov fiksturasi** eskirgan edi — u 11-vazifada qo'shilgan
`reviewed_ishonch` ustunini yozmasdi. Ilova yo'li (`review_set`)
uni har doim uzatadi, ya'ni ma'lumot yo'qolishi bo'lmagan.

Tuzatildi: `f5c1348`. Haqiqiy nuqson — S-1 (bazali sinovlar
yurmasligi).

---

## 9. YOPILGAN BANDLAR (2026-09-01)

### 9.1 S-1 — sinovlar endi baza bilan yuradi (`e5f0361`)

`--bazasiz` va `--tarmoqsiz` ajratildi; `--offline` eski ma'nosini
saqlab qoldi. Standart rejim endi `--tarmoqsiz`.

| | Tekshiruv |
|---|---|
| Eski standart (`--offline`) | 1951 |
| Yangi standart (`--tarmoqsiz`) | **2478** |
| Farq | **+527 (+27%)** |

Darhol ikki eskirgan sinov oshkor bo'ldi: `paid_guard_test`
(`needs_review` ni yiqilish deb hisoblardi) va `doc_qamrov_test`
(M-1 ni ko'rsatdi).

### 9.2 B-2 — manba xatosi diagnostika qilinadi (`7da3732`)

**Da'vo noto'g'ri edi.** Qayta o'lchandi: `limit` 2–51, `offset`
0–153 — hammasi HTTP 200; `fetch_all_tenders` 149 ta yozuv qaytardi.
Xato **o'tkinchi** edi. "Doimiy" so'zi manbadan emas, bizning
tasniflagichimizdan kelgan va men uni dalil deb o'qidim.

Asl nuqson boshqa ekan va u ikkita:

1. **Sabab yo'qolardi** — `tasnifla()` javob tanasini olmasdi.
   Endi 220 belgigacha saqlanadi.
2. **Bitta uzilish 57 ta tekshiruvni o'ldirardi.** Simulyatsiya
   bilan tekshirildi: oldin 0 tekshiruv va traceback, keyin 48/50
   va ikkita nomli FAIL.

Tasnif siyosati **o'zgarmadi**: 4xx hali ham qayta urinilmaydi.
Bitta tushuntirilmagan kuzatuvga qarab siyosat o'zgartirilmaydi.

### 9.3 M-1 — dalilsiz `ok` (`f948d90`)

**Sabab isbotlandi:** `doctext_test:test_cache` haqiqiy hujjat
matnini `"sinov"` bilan almashtirar, so'ng matn qatorini o'chirar,
`holat='ok'` esa qolardi. O'lchov: sinovdan oldin 29, keyin 30.

Uch qismli tuzatish: sinov soxta qatorga o'tkazildi · mavjud zarar
tiklandi (`ok` 3014 → 2984) · **baza darajasida qo'rovul**
(`hujjat_ok_dalil_trg`) — endi hech qanday yo'ldan o'tmaydi.

`v_hujjat_dalil_nomuvofiq`: `ok_dalilsiz 0`,
`ok_status_qarama_qarshi 0`, `yetim_matn 392` (tarixiy).

### 9.4 Yo'l-yo'lakay tuzatilganlar

| Nuqson | Commit |
|---|---|
| `review_butunlik_test` fiksturasi 11-vazifadan beri eskirgan | `f5c1348` |
| `paid_guard_test` `needs_review` ni yiqilish deb hisoblardi | `e5f0361` |
| `doc_qamrov_test` fikstura tartibi qo'rovulga zid | `f948d90` |

Uchalasi ham bitta sinf: **sinov eskirgan, lekin buni hech narsa
ko'rsatmagan** — chunki u yurmasdi.

---

## 10. YANGI KUZATUV

**`etl_ishonch_test` to'liq to'plamda BIR MARTA yiqildi**, alohida
yurgizilganda 179/179 o'tdi. Sabab aniqlanmagan — tashqi
bog'liqlikdagi beqarorlik. Takrorlansa, endi manba javobi xato
matnida bo'ladi (§9.2).
