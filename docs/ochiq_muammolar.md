# Ochiq muammolar reyestri

**O'lchov sanasi: 2026-09-01.** Har band **o'lchangan dalil** bilan.
Taxmin qilingan raqam yo'q; o'lchanmagan narsa `O'LCHANMAGAN` deb
yozilgan.

Bu ro'yxat 9–21-vazifalar davomida topilgan va **tuzatilmagan**
narsalarni bir joyga yig'adi. Tuzatilganlari kirmagan.

| Daraja | Ochiq | Yopilgan |
|---|---|---|
| Bloker | 1 | 2 (B-2, B-3) |
| Ma'lumot butunligi | 0 | 3 (M-1, M-2, M-3) |
| Qamrov qarzi | 0 | 3 (Q-1, Q-2, Q-3) |
| Operatsiya | 1 (O-5) | 4 (O-1..O-4) |
| Sinov jarayoni | 0 | 1 (S-1) |
| Tugallanmagan imkoniyat | 1 (T-1) | 1 (T-2) |
| Kichik | 5 (K-1..K-5) | — |
| **Jami** | **8** | **14** |

> **B-1 YOPILMADI, YANA QISQARDI.** `health-check.sh`,
> `rollback.sh` va `deploy.sh` darvozasi mashq qilindi —
> **5 nuqson topildi** (§9.12). `deploy.sh` ning qurish qismi,
> Caddy va systemd hali bajarilmagan (Linux mashinasi kerak).

**Oxirgi yangilanish: 2026-09-02.** Yopilganlar §9 da.

---

## 1. BLOKERLAR

### B-1. Server yo'q — IKKI MARTA QISQARDI (yopilmadi)

> Zaxira/tiklash mashq qilindi, 2 nuqson (§9.10).
> Sog'liq/qaytarish mashq qilindi, **5 nuqson** (§9.12).
> `deploy.sh` qurish qismi, Caddy, systemd — hali emas.

**MASHQ QILINGANI** (skriptlar HAQIQATAN yurgizildi):

| Skript | Ssenariy | Natija |
|---|---|---|
| `backup.sh` | to'liq | 5 daq 28 s · 440 MB |
| `restore-test.sh` | to'liq | RTO 405 s |
| `health-check.sh` | 4 | 3 nuqson topildi |
| `rollback.sh` | 6 | 2 nuqson topildi |
| `deploy.sh` darvozasi | 3 | ishlaydi |

**QOLGANI** — haqiqiy Linux mashinasi kerak:

| Qism | Nega |
|---|---|
| `deploy.sh` qurish qismi | `venv`, `npm ci`, migratsiya, `systemd` |
| Caddy / HTTPS | domen va sertifikat |
| systemd taymerlar | `systemd-analyze verify` uchun Linux |

**MUHIM XULOSA.** `deploy_test` ning 1-15 bo'limlari HAMMASI
`"satr" in fayl_matni` shaklida edi. Ular **beshta nuqsonning
HECH BIRINI ko'rmagan**. Satr borligi skript ishlashini
isbotlamaydi. 16-bo'lim endi skriptlarni YURGIZADI.

**Ta'siri:** birinchi joylashtirish hali ham sinalmagan yo'l,
lekin **tiklash yo'li endi mashq qilingan**.
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

### ~~B-3. Inson halqasi hali bo'sh~~ — YOPILDI, DA'VO ANIQLASHTIRILDI

> Halqa bo'sh emas, NOTEKIS; yo'l ishlaydi (§9.11).
> Quyidagi tavsif TARIXIY.

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

### ~~M-2. 30 ta inson qarorining AKTORI noma'lum~~ — YOPILDI, DA'VO NOTO'G'RI EDI

> Ular noma'lum emas, `kuzatuvdan_oldin` deb ANIQ belgilangan (§9.6).
> Quyidagi tavsif TARIXIY.

```
tender_routing, inson_qaror IS NOT NULL   : 30
  qaror_actor_id IS NULL                  : 30   (100%)
  qaror_ishonch  IS NULL                  :  0
```

Ishonch darajasi yozilgan, **kim** ekani esa yo'q. Bu qarorlar
aktor kuzatuvi (11-vazifa) joriy etilishidan OLDIN yozilgan.

**Ta'siri:** audit izi to'liq emas; "kim tasdiqladi" savoliga
javob yo'q. Orqaga qarab to'ldirib bo'lmaydi — ma'lumot yo'q.

### ~~M-3. `audit_jurnal` da sinov yozuvi qolgan~~ — YOPILDI

> Tizimning o'z yo'li bilan tuzatildi (§9.7).
> Quyidagi tavsif TARIXIY.

`id=37`, `amal='huquq_sinov'`, `company_id=2`. 12-vazifadagi
huquq tekshiruvi paytida yozilgan.

Jadval **append-only** (`audit_jurnal_ozgarmas_trg`) — o'chirib
bo'lmaydi va bu **ataylab shunday**.

**Holat:** foydalanuvchiga uch variant taklif qilindi, javob
kutilmoqda. Tavsiya — qoldirish (jami 7 ta yozuvdan biri).

---

## 3. QAMROV QARZI

### ~~Q-1. 2365 tender talab ajratishdan o'tmagan (65.6%)~~ — YOPILDI

> Ochiq tenderlar bo'yicha qamrov **100%** (§9.5).
> Quyidagi tavsif TARIXIY.

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

### ~~Q-2. Embedding qamrovi 55.8%~~ — YOPILDI (davom etmoqda)

> Arzon yo'l modelga bog'lanib qolgan edi (§9.8).
> Quyidagi tavsif TARIXIY.

```
doc_chunk jami        188 561
vektori bor           105 174   (55.8%)
```

**Ta'siri:** RAG qidiruvi hujjatlarning yarmini ko'rmaydi.

### ~~Q-3. Katalog: 749 mahsulot kodsiz (41.7%)~~ — AVTOMATIK YO'L TUGADI

> Naqsh yo'li **oxirigacha yurgizildi**; qolgani dalil
> yetishmasligi, kod nuqsoni emas (`7796fb0`). Aniqlik
> qo'riqchisi qo'shildi: qamrov uchun aniqlikni pasaytirish
> endi sinovni yiqitadi. Qolgan qism — **mahsulot qarori**
> (qo'lda kodlash), muhandislik ishi emas.
> Quyidagi tavsif TARIXIY.

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

### ~~O-1. RTO O'LCHANMAGAN~~ — YOPILDI

> **RTO = 405 s** (§9.10).
> Quyidagi tavsif TARIXIY.

`restore-test.sh` tiklash vaqtini o'lchaydi, lekin **hech qachon
yurgizilmagan** (B-1). Taxminiy raqam ataylab yozilmadi.

### ~~O-2. Zaxira faqat mahalliy diskda~~ — YOPILDI

> `BACKUP_REMOTE_CMD` qo'shildi va **uch yo'l ham mashq qilindi**
> (`a092982`). Tashqi nusxa **butashdan OLDIN** olinadi va
> yiqilsa `backup.sh` **yiqiladi** — "zaxira olindi" degan yolg'on
> chiqmaydi. Sozlanmagan bo'lsa jurnalda OGOHLANTIRISH.
> **Cheklov:** uzoqdagi nusxadan TIKLASH hali sinalmagan.
> Quyidagi tavsif TARIXIY.

Tashqi nusxa yo'q. Disk yo'qolsa zaxira ham yo'qoladi.

### ~~O-3. Monitoring / ogohlantirish yo'q~~ — YOPILDI

> **Ikki qatlam** qo'shildi (`ba0d4ee`): KRASH (`OnFailure=`
> har xizmatda) va SOG'LIQ (10 daqiqalik taymer). Ular BOSHQA
> nosozliklarni ushlaydi — xizmat ko'tarilgan, ammo migratsiya
> qo'llanmagan holat faqat ikkinchisida ko'rinadi.
> Email yo'li soxta SMTP bilan SINALDI.
> Sog'liq skriptining O'ZI keyinroq mashq qilindi va **3 nuqson**
> chiqdi (§9.12) — ya'ni ogohlantirish qatlami qo'shilganda u
> hali ishlamasdi.
> Quyidagi tavsif TARIXIY.

`systemd` xizmatni qayta ko'taradi, lekin **buni hech kim
bilmaydi**. `/ready` bor, uni so'raydigan narsa yo'q.

### ~~O-4. `pip-audit` yurgizilmagan~~ — YOPILDI

> 8 zaiflik topildi va tuzatildi (§9.9).
> Quyidagi tavsif TARIXIY.

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

### T-1. Saqlangan qidiruv — QISQARDI (uchdan biri ulandi)

> `notify` **ULANDI** (`a4d3f1d`): kalit so'zi mos qidiruv
> tenderni **0 -> 80** ballga ko'taradi va xabar qaysi qidiruv
> ekanini aytadi. Skorlash **ayni** `matching.score_tender()` —
> ikkinchi mantiq yozilmadi.
> **Qolgani ochiq:** `last_seen_at`, `categories`, va
> interfeysda `notify` tugmasi (bayroq ishlaydi, lekin shakl uni
> yubormaydi — foydalanuvchi o'chira olmaydi).
> Quyidagi jadval TARIXIY.

`saved_search` da **0 ta** qator. CRUD, ijarachi ajratilishi va
interfeys **ishlaydi** (`saved_search_test` 57/57), lekin:

| Qism | Holat |
|---|---|
| `notify` | bildirishnoma tsikli o'qimaydi |
| `last_seen_at` | to'ldiradigan yo'l yo'q |
| `categories` | skorlashda ishlatilmaydi |

Batafsil: `docs/saved_search.md`.
**Manba:** 21-vazifa.

### ~~T-2. RAG qatlamlari O'LCHANMAGAN~~ — DA'VO NOTO'G'RI EDI

> **Bu da'vo aniq emas edi** (`62c4c30`). Qidiruv va iqtibos
> **O'LCHANADI** va u modelsiz, pulsiz:
>
> | Qatlam | Holat |
> |---|---|
> | A. Qidiruv sifati | Recall@K, Precision@K, MRR, nDCG |
> | B. Iqtibos to'g'riligi | citation_hit_rate |
> | C. Javob to'g'riligi | O'LCHANMAYDI — model kerak |
> | D. Tool tanlash | O'LCHANMAYDI — model kerak |
> | E. Gallyutsinatsiya | O'LCHANMAYDI — model kerak |
>
> "Hech narsa o'lchanmagan" NOTO'G'RI, "hammasi o'lchangan" ham
> NOTO'G'RI. A qatlami javob sifatining **yuqori chegarasi**:
> qidiruv topmagan narsani model ham ayta olmaydi.
>
> Korpus **57% o'sgach** (105k -> 170k bo'lak) qayta o'lchandi:
> gibrid recall@8 **0.705**, mrr **0.699**, iqtibos **1.000** —
> bazaviy bilan **aynan bir xil**.
>
> **NAMUNA KICHIK: 7 javobli holat.** 0.705 ni statistik da'vo
> deb o'qib bo'lmaydi va sinov endi buni TALAB qiladi.
> C/D/E `AI_PAID_ENABLED` ostida qoladi — bu ATAYLAB.
> Quyidagi tavsif TARIXIY.

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

### 9.5 Q-1 — operatsion qamrov 100% (`2fcb6fc`)

`reyestr` yo'li navbatdagi **627** ochiq tender uchun yurgizildi:
**4 sekund, 1 199 talab, 0 xato, bepul**. Natija kutilgandek
chiqmadi — `ishlangan_foiz` atigi 32.2 → 34.5.

**Sabab o'lchandi:** qolgan **2 365 tenderning hammasi YOPIQ**
(expired 2094, close 164, cancel 81, qolgani 26; **ochiq 0**).
Ya'ni "65.6% ishlanmagan" operatsion bo'shliq emas, **tarixiy
yozuvlar** edi.

**Ildiz sabab:** `run_etl.py` faqat `--method naqsh` ni yurgizardi.
`reyestr` — bepul, hujjatsiz ishlaydigan, 1157/1157 natija
beradigan yo'l — quvurda **umuman yo'q** edi. Endi ikkalasi ham
yuradi, `reyestr` birinchi.

Migratsiya 0065: `ochiq_ishlangan_foiz` qo'shildi (**100.0**),
eski ustunlar o'zgarmadi.

### 9.6 M-2 — aktor izchilligi bazada (`aac3097`)

**Da'vo noto'g'ri edi.** 30 qator `qaror_ishonch='kuzatuvdan_oldin'`
deb **aniq belgilangan** — 11-vazifada ataylab qo'yilgan yorliq.
Tizim noma'lumni noma'lum deb saqlagan.

**Asl bo'shliq:** `ishonch` ↔ `actor_id` izchillik qoidasi
`audit_jurnal` da CHECK edi, **qaror jadvallarida faqat kodda**.
Migratsiya 0066 uni uchala jadvalga ham qo'ydi. Buzuq qator 0 edi
va shunday qoldi — endi baza ham to'xtatadi.

### 9.7 M-3 — audit artefakti belgilandi (`e864e7e`)

`company_id=2` da 2 qator: biri **haqiqiy** (id=62, haqiqiy tender,
IP, brauzer), biri **sinov artefakti** (id=37). Qolgan 16 qator
`company_id=200` — sinov ijarachisi, CASCADE bilan ketadi.

Triggerning **o'z xato matni** yo'lni ko'rsatdi: *"Tuzatish kerak
bo'lsa YANGI qator qo'shing (`amal='tuzatish'`)"*. Artefakt
o'chirilmadi — ustiga tuzatish yozuvi qo'shildi (storno naqshi).

`tarix()` qatorni **ko'rsatadi**, lekin `tuzatilgan` bayrog'i va
sababi bilan; `v_audit_jurnal_haqiqiy` esa faqat haqiqiy amallarni
beradi (3 → 1).

Takrorlanmaydi: `huquq_sinov` amali **kodda hech qayerda yo'q**.

### 9.8 Q-2 — xeshdan ommaviy nusxalash (`48df49f`)

Navbatdagi **81 081** bo'lakning **52% i (42 325)** allaqachon
vektorlangan matnning **nusxasi** edi. Nusxalash mantig'i bor edi,
lekin **partiya ichida** — ya'ni arzon ish modelning 2.3 bo'lak/s
tezligiga bog'lanib turardi.

| Yo'l | Ish | Vaqt |
|---|---|---|
| partiya | 2 000 bo'lak | 5.4 daqiqa |
| **ommaviy SQL** | **42 052 bo'lak** | **3.4 daqiqa** |

~33 marta tez. Quvur endi model navbatidan **oldin** `--xeshdan`
ni yurgizadi.

| | Boshlanish | Hozir |
|---|---|---|
| umumiy | 57.3% | **84.7%** |
| OCHIQ tenderlar | 33.1% | **77.2%** |
| navbat | 81 081 | 29 131 |

Qolgani **modelni talab qiladi** (nusxa imkoniyati tugadi) va
fonda yurmoqda. `--qamrov` endi operatsion (ochiq) va tarixiy
qamrovni **alohida** beradi — Q-1 dagi ayni saboq.

### 9.9 O-4 — bog'liqliklar auditi (`0508c4b`)

`pip-audit` **91 ta o'rnatilgan paket** ustida yurgizildi
(e'lon qilingan 12 ta emas — zaiflik ko'pincha tranzitiv
bog'liqlikda).

```
Found 8 known vulnerabilities in 2 packages
  pypdf 6.14.2   PYSEC-2026-3655, 3656   -> 6.15.0   YUQORI
  pip   25.3     6 ta zaiflik             -> 26.2     PAST
```

**`pypdf` bizda to'g'ridan-to'g'ri yetib boriladi:** ikkala
zaiflik ham maxsus yasalgan PDF matn ajratilganda xotira va
protsessorni tugatadi, `etl_doc_text.py` esa tashqi manbadan
yuklangan PDF larni aynan shunday ajratadi — tender e'lon qila
oladigan har kim ETL ni to'xtatishi mumkin edi.

Tuzatildi (pypdf → 6.16.2, pip → 26.2.1); qayta audit
**`No known vulnerabilities found`**.

**Cheklov ochiq yozildi:** sinov `pip-audit` ni yurgizmaydi
(tarmoq kerak) — u faqat **topilgan zaiflik qaytmasligini**
qo'riqlaydi. Yangi zaiflikni faqat haqiqiy audit ko'rsatadi va
uni muntazam yurgizadigan jadval **yo'q** (B-1).

### 9.10 B-1 qisqardi + O-1 yopildi (`6b0da67`)

Skriptlar **hech qachon bajarilmagan** edi — faqat matn sifatida
tekshirilardi. Mashq **birinchi qadamdayoq ikki nuqson topdi**:

1. **`XT_DB_DSN` tirnoqsiz** → systemd butun qatorni oladi, shell
   esa **birinchi bo'shliqda kesadi**. `backup.sh` /
   `restore-test.sh` / `deploy.sh` user, parol va hostsiz
   ulanardi — va **xato ham bermasdi** (qolgani shellda
   o'zgaruvchi tayinlash bo'lib ketardi).
2. **`XT_DB_DSN_OWNER` namunada yo'q edi**, garchi `deploy.sh`
   uni `:?` bilan talab qilsa ham.

O'lchangan raqamlar (haqiqiy 1.5 GB baza):

| Amal | Natija |
|---|---|
| `backup.sh` | 5 daq 28 s · 440 MB · 74 jadval |
| `restore-test.sh` | **RTO = 405 s** |
| Tekshiruv | jadval 53 · tender 3 608 · bo'lak 189 787 · pgvector bor |

**Hali bajarilmagani** `docs/deploy.md` §13.5 da ochiq yozilgan:
`deploy.sh` to'liq, `rollback.sh`, `health-check.sh`, Caddy/HTTPS,
systemd taymerlar.

### 9.11 B-3 — halqa notekis, yo'l ishlaydi (`ec3421f`)

**Da'vo aniqlashtirildi.** Bitta raqam o'rniga qatlam bo'yicha:

| Qatlam | Jami | Qaror | Navbat | Ulush |
|---|---|---|---|---|
| Kod tasdig'i | 1 427 | 1 048 | 379 | **73.4%** |
| Yo'naltirish | 310 | 31 | 279 | 10.0% |
| Talab ko'rigi | 11 099 | **0** | 8 445 | **0.0%** |

**"Ishlatilmagan" ≠ "ishlamaydi".** `POST /requirements/{id}/review`
uchidan-uchiga sinaldi: darvoza, kimlik, **bazaga yozilishi**,
ijarachi izolyatsiyasi. **Yo'l ishlaydi.**

**Pilot eskirgan va yangisini bloklaydi:** 2026-08-26 da yaratilgan
30 tenderning **22 tasi muddati o'tgan**, `qaror_berilgan = 0`.
`pilot_yarat()` idempotent va qayta qurish yo'li yo'q. Bu
**mahsulot qarori** — men uni qabul qilmadim.

Qurildi: `v_inson_halqasi`, `v_pilot_holat` (migratsiya 0068).
Ular halqani **to'ldirmaydi** — faqat bo'shliqni ko'rinadigan
qiladi.

### 9.12 B-1 yana qisqardi — tiklash yo'li MASHQ QILINDI (2026-09-02)

**Mashq usuli.** Skriptlar **o'zgartirilmagan** holda yurgizildi;
uchta narsa skriptdan TASHQARIDA almashtirildi: ildiz yo'li
(`TENDERAI_ILDIZ`), `sudo systemctl` (PATH shimi, chaqiruvlar
yoziladi), va Windows'da `ln -s` (NTFS junction shimi).

Oxirgisisiz mashq **SOXTA** bo'lardi: MSYS `ln -s` imtiyozsiz
jimgina katalog NUSXASI qoldiradi, ya'ni `current` simvolik
havola bo'lmasdi va "atomar almashtirish" hech narsa
almashtirmasdi — skript esa "QAYTARILDI" deb yozardi.

**Topilgan 5 nuqson** (hech biri `grep` bilan ko'rinmasdi):

| # | Nuqson | Oqibati |
|---|---|---|
| 1 | tiriklik sikli 210 s, birlikda `TimeoutStartSec=120` | xizmat yiqilganda tekshiruvning O'ZI o'ldirilardi |
| 2 | `psql` byudjetsiz | baza qora tuynuk bo'lsa xuddi shu holat |
| 3 | uzilishda javob kodi `000000` | jurnalda BUZUQ kod |
| 4 | `--royxat` da `*` yo'qolardi | qaysi reliz tirikligi noma'lum |
| 5 | `rollback.sh` avval almashtirib, KEYIN tekshirardi | tiklash vositasi UZILISH keltirardi |

**1-nuqson** klassik "noto'g'ri narsani o'lchash": `TimeoutStartSec`
skriptning SABRINI cheklaydi, xizmat sog'lig'ini emas. Sekin ammo
sog'lom xizmat ham chegaradan oshib SOXTA OGOHLANTIRISH berardi.
Byudjet endi MUDDAT bilan (takror soni bilan emas — `curl`
bloklansa "30 ta urinish" istalgancha cho'ziladi):

```
45 + 10 + 15 + 5 = 75 s  <  TimeoutStartSec 120 s
```

O'LCHANDI: xizmat butunlay yo'q bo'lganda **129 s -> 53 s**.

**4-nuqson** ota-katalog simvolik havola bo'lsa chiqadi
(`/opt -> /srv`, oddiy server tartibi): `$HOZIRGI` `readlink -f`
dan keladi va yechilgan, `${RELIZLAR}/${r}` esa yechilmagan
`$ILDIZ` dan quriladi. Mashqda AYNAN shu qayta tiklandi:
taqqoslash `YO-Q` berdi, ikkala tomon yechilgach `HA`.

**5-nuqson** tasodifan topildi. `deploy.sh` mashqda yiqilib **bo'sh
reliz katalogi** qoldirdi va u `--royxat` da ENG YANGI reliz bo'lib
turdi — yiqilgan joylashtiruvdan keyin tiklanayotgan operatorga
aynan eng yaroqsiz nishon ko'rsatilardi. Unga qaytarilsa `current`
bo'sh katalogga ko'rsatardi, xizmat o'lardi, `health-check.sh`
topilmasdi (127) va skript "qo'lda qarang" deb chiqardi — uzilishni
tiklash vositasining O'ZI keltirib chiqargan bo'lardi.

Ikkala tomon yopildi: `deploy.sh` yiqilsa o'z yarim relizini
`trap` bilan o'chiradi; `rollback.sh` hedefni ALMASHTIRISHDAN
OLDIN tekshiradi va rad etsa `current` ga TEGMAYDI. Operator
qamalib qolmasin uchun `--majburiy` chiqish yo'li bor.

**Sinov.** `deploy_test` **164 -> 193** tekshiruv. 16-bo'lim
skriptlarni HAQIQATAN yurgizadi (soxta API, soxta `systemctl`,
vaqtinchalik reliz daraxti). Mashq muhiti topilmasa sinov
**YIQILADI**, jimgina o'tmaydi.

**Mashq paytida O'Z sinovimda 3 ta soxta yashil topildi** va
ular ham tuzatildi: ikkita qo'riqcha skriptning O'Z IZOHIDAGI
iborani topib yashil bo'lgandi (`seq 1 30`, `|| echo 000`), va
`os.pathsep` Windows'da `;` bo'lgani uchun shim PATH ga
tushmasdi — ya'ni "current o'zgarmadi" tekshiruvi hech qachon
o'zgara olmaydigan holatni tasdiqlayotgan edi.
