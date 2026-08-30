# Aktor kimligi va audit — arxitektura qarori (ADR, auth-6)

**Sana:** 2026-08-31 · **Holat:** qabul qilindi va joriy etildi

---

## 1. Muammo — o'lchangan

Tender-AI ga **kompaniya** kiradi, odam emas. Bu ataylab
(`schema_patch_auth_2.sql`): hodimlar ERP domenida
(`erp.app_user`). Lekin tizimda **inson qarorlari** bor —
yo'naltirish, talab ko'rish, kodlash — va ular uch xil, bir-biriga
mos kelmaydigan usulda yozilardi:

| Qayerda | Aktor qanday saqlanadi | Manba | Ishonchlimi |
|---|---|---|---|
| `tender_requirement.reviewed_by` | `INT` → `company_account(id)` | sessiya | Ha, lekin bu **kompaniya**, odam emas |
| `kod_qaror.kim` | `TEXT` (sessiya login'i) | sessiya | O'sha muammo |
| `tender_routing.broker_nomi` | `TEXT` | **`body.broker` — mijozdan** | **Yo'q** — ixtiyoriy matn |

Ya'ni eng nozik atribut — "qaysi **kompaniya**". Va bitta yo'lda
(`routing`) aktor umuman tekshirilmasdan mijozdan qabul qilinardi.

**O'lchandi (2026-08-31):** 310 ta `tender_routing` qatoridan
**30 tasida** inson qarori bor, `broker_nomi` esa **0 tasida**
yozilgan. Ya'ni yolg'on yozuv hali yo'q edi, lekin yo'l ochiq edi.

Yana bir teshik: `gate()` da **service kaliti** yo'li bor
(ERP, odam emas) va u ham `company_id_of()` orqali kompaniyaga
yechilardi. `SERVICE_PATHS` ro'yxati hozir qaror endpointlarini
o'z ichiga olmaydi, lekin ro'yxatga bitta yangi yo'l qo'shilishi
buni **jimgina** ochib yuborardi.

---

## 2. ERP chegarasi — nima mumkin, nima yo'q

Chegara **simmetrik, faqat-o'qish va sinov bilan qulflangan**:

```
ERP        public.*                dan O'QIYDI, YOZMAYDI
Tender-AI  erp.v_tender_status,    dan O'QIYDI, YOZMAYDI
           erp.v_stock_balance
```

`_tests/auth_test.py` har yurishda `erp.app_user` sanog'i va
`max(updated_at)` suratini oladi — tender-ai `erp.*` ga yozsa sinov
yiqiladi.

Muhim tafsilotlar (o'lchandi):

- `erp.app_user` **aynan shu bazada**, `erp` sxemasida. Unda haqiqiy
  hodimlar bor (`karimov`/broker, `admin`/admin) va `erp.app_session`
  ham bor — token xeshi bilan, tender-ai'nikiga o'xshash.
- Shartnoma **jadval emas, VIEW** orqali — ataylab, ERP o'z ichini
  o'zgartira olsin.
- **`erp.own_company` bitta qator:** ERP bitta kompaniyaning o'z
  tizimi. Tender-AI esa **ko'p ijarachili**. Ya'ni ERP hodimida
  `company_id` tushunchasi **yo'q**.

Oxirgi nuqta hal qiluvchi: ERP foydalanuvchisini avtomatik ravishda
biror ijarachiga bog'lab bo'lmaydi. Bog'lansa — ko'p ijarachilik
buziladi.

---

## 3. Ko'rib chiqilgan uch yo'l

### A) ERP bergan ishonchli kontekst — qisman

ERP sessiyasini tekshirib, odamni **isbotlash** mumkin. Lekin:

- `erp.app_user` / `erp.app_session` **jadval**lariga bog'lanish
  view-shartnomasini buzardi;
- ERP hodimida ijarachi yo'q, ya'ni "isbot bor" degani "ruxsat bor"
  degani emas.

**Xulosa:** yo'lning o'zi to'g'ri, lekin u **shartnoma-view** va
**xarita** talab qiladi.

### B) Mahalliy sub-foydalanuvchi tizimi — RAD ETILDI

`erp.app_user` ni takrorlash. Bu aynan `schema_patch_auth_2.sql`
olib tashlagan narsa ("IKKI joyda ikki xil"). Parol, sessiya, rol —
hammasi ikkilanardi va ikkisi bir-biridan uzoqlashardi.

### C) Cheklangan integratsiya xaritasi — **TANLANDI**

`actor` jadvali **kimlik ombori emas, xarita**: parol yo'q, token
yo'q, sessiya yo'q, **kirish bermaydi**. U faqat shuni aytadi:
"shu ijarachida shu ERP hodimi shu rol bilan ishlaydi".

Autentifikatsiya **o'zgarmaydi**: kompaniya sessiyasi qanday bo'lsa
shunday qoladi.

---

## 4. Ishonch darajasi — yorliq dalildan oshmaydi

Tender-AI hodimni **o'zi autentifikatsiya qila olmaydi**. Shuning
uchun har atribut yoniga uning **qanchalik ishonchli** ekani ham
yoziladi:

| Daraja | Ma'nosi | `actor_id` |
|---|---|---|
| `erp_sessiya` | Odam **isbotlandi** (ERP sessiyasi tekshirildi) | bor |
| `aktor_elon` | Odam **e'lon qilindi** — ro'yxatdagi aktor ko'rsatildi, o'zi isbotlanmadi | bor |
| `kompaniya_sessiyasi` | Faqat **kompaniya** ma'lum | **yo'q** |
| `servis` | Odam yo'q (ERP kaliti) | yo'q |
| `kuzatuvdan_oldin` | Aktor kuzatuvidan oldin yozilgan | yo'q |

`erp_sessiya` va `aktor_elon` **ataylab ajratilgan**: birinchisi
tekshirilgan, ikkinchisi aytilgan. Ularni bitta qiymatga qo'shish
aynan shu loyihada tuzatilgan xatoni takrorlardi — mashina holati
inson tasdig'i bo'lib ko'rinishi (1 487 ta soxta `approved`).

Bu loyihada allaqachon ishlaydigan naqsh: `ok` / `bootstrap`
(bajarilgan / o'lchangan), `inson_tasdiqladi` / `mashina_ishonchli`.

### ERP shartnoma-view i (hali chop etilmagan)

`erp_sessiya` darajasi ERP quyidagi view ni chop etganda ishlaydi:

```sql
CREATE OR REPLACE VIEW erp.v_tai_actor AS
SELECT u.id          AS erp_user_id,
       u.username    AS login,
       u.full_name   AS ism,
       u.role        AS rol,
       s.token_hash,          -- sha256(xom token), ERP tomonida
       s.expires_at
  FROM erp.app_user u
  JOIN erp.app_session s ON s.user_id = u.id
 WHERE u.active;
```

Tender-AI xom tokenni **ko'rmaydi va saqlamaydi** — u faqat
`X-ERP-Session` sarlavhasidagi tokenning `sha256` ini hisoblab
taqqoslaydi.

**Hozirgi holat:** view **yo'q**. `api/aktor.py:erp_kontekst_ready()`
buni `False` qaytaradi va eng yuqori mavjud daraja `aktor_elon`
bo'lib qoladi. Bu **yashirilmaydi** — `/aktor/holat` uni ochiq
ko'rsatadi.

---

## 5. Ijarachi izolyatsiyasi — kod emas, kompozit FK

`actor` da `UNIQUE (company_id, id)` bor va har qaror jadvali
`(company_id, actor_id)` ni **kompozit FK** bilan bog'laydi:

```sql
FOREIGN KEY (company_id, reviewed_actor_id) REFERENCES actor (company_id, id)
```

Natijada boshqa ijarachining aktorini yozish **jismonan mumkin
emas** — ilova kodi nima qilishidan qat'i nazar. Bu loyihada
qoidani izohda qoldirish qanday tugashini ko'rdik.

`audit_jurnal` da `actor_id` **NULL bo'la oladi** (servis). `MATCH
SIMPLE` bo'yicha bunday holatda FK qo'llanmaydi — bu kutilgan.
Zid holatni `audit_jurnal_aktor_chk` to'sadi: `ishonch` va
`actor_id` bir-biriga mos kelishi shart.

**O'qish ham cheklangan:** FK **yozishni** to'sadi, o'qishni emas.
Shuning uchun `aktor.bitta()` / `royxat()` `company_id` ni **har
doim** SQL shartida saqlaydi — aks holda boshqa ijarachining
xodimlari ro'yxati sizib chiqardi.

---

## 6. Audit — faqat qo'shiladi

`audit_jurnal` har inson o'zgarishini yozadi: `company_id`,
`actor_id`, `ishonch`, `amal`, `entity`, `entity_id`, `oldin`,
`keyin`, `izoh`, `ip`, `user_agent`, `at`.

`UPDATE` va `DELETE` **bazada trigger bilan to'silgan**. Kaskad yo'l
ham to'siladi: `company_account` ni o'chirishga urinish
`ON DELETE CASCADE` orqali audit qatorlariga yetib borganda trigger
yiqitadi.

**Halol cheklov:** superuser triggerni o'chira oladi. Bu har qanday
baza ichidagi himoya uchun o'rinli. To'siq "imkonsiz" degani emas —
"tasodifan yoki oddiy ilova xatosi bilan bo'lmaydi va iz qoldirmay
ketmaydi" degani.

Ustun nomlari `erp.doc_audit` bilan **ma'no jihatidan mos**
(entity / entity_id / action / old / new / actor / created_at) — bu
loyihadagi mavjud naqsh, yangisi o'ylab topilmadi.

---

## 7. Ruxsat matritsasi

| Rol | ko'rish | ko'rib chiqish | tasdiq / rad | sozlama |
|---|---|---|---|---|
| `kuzatuvchi` | ✅ | — | — | — |
| `koruvchi` | ✅ | ✅ | — | — |
| `tasdiqlovchi` | ✅ | ✅ | ✅ | — |
| `admin` | ✅ | ✅ | ✅ | ✅ |

Ikki holat ataylab farqlanadi:

- **`servis`** — odam emas. Inson qarorini **qat'iy** qo'ya olmaydi.
  `gate()` allaqachon `SERVICE_PATHS` bilan cheklaydi; bu
  **ikkinchi qatlam**, chunki ro'yxatga qo'shilgan yangi endpoint
  buni jimgina ochib yuborardi.
- **`kompaniya_sessiyasi`** — aktor ko'rsatilmagan. Ijarachida
  `aktor_majburiy = false` bo'lsa **ruxsat beriladi** va atribut
  shunday yoziladi. `true` bo'lsa aniq aktor talab qilinadi.

`aktor_majburiy` standart **`false`**: bu o'zgarish 23 ta sinov
to'plami va ishlab turgan interfeysga tegadi, majburiyatni darhol
yoqish ularni to'xtatardi. Yoqish — ijarachining **ongli qarori**.

---

## 8. Nima o'zgardi

| Fayl | Nima |
|---|---|
| `schema_patch_aktor.sql` | `actor`, `audit_jurnal`, kompozit FK lar, `ishonch_yaroqli()`, `v_audit_tolik`, `v_atribut_sifati`, `company_account.aktor_majburiy` |
| `api/aktor.py` | Kimlik aniqlash, ruxsat matritsasi, audit yozuvchi, ERP moslik o'lchovi |
| `api/main.py` | `kimlik_of()`, `ruxsat()`, `audit_yoz()`; `/aktor`, `/aktor/holat`, `/audit`; uch qaror endpointi ulandi |
| `api/requirement.py` | `bitta()` (audit uchun "oldin" surati); `review_set`/`review_bulk` da `ishonch` **majburiy** |
| `api/routing.py` | `broker` (mijozdan) → `actor_id`/`ishonch`/`broker_nomi` (serverdan) |
| `api/kodlash.py` | `qaror_yoz` da aktor va ishonch |
| `frontend/` | `X-Actor` sarlavhasi, `AktorTanlash` bloki, uch tilda tarjima |
| `_tests/aktor_test.py` | 63 tekshiruv |

**Yangi parametrlar faqat kalit so'zli (`*`).** O'lchangan sabab:
eski `routing.qaror()` imzosida 5-pozitsiya `broker` (matn) edi va
`qualification_test.py:323` uni pozitsion uzatardi. `actor_id` o'sha
o'ringa tushganda matn **jimgina** aktor id sifatida bog'lanardi.

---

## 9. Tekshirilgan holat

`_tests/aktor_test.py` — **63/63 o'tdi**; to'liq to'plam **23/23**.

| Nima | Natija |
|---|---|
| `actor` da parol/token/sessiya ustuni | **yo'q** (manbadan tekshiriladi) |
| Ijarachilararo aktor — baza | FK rad etadi (talab, yo'naltirish, kodlash, audit) |
| Ijarachilararo aktor — API | 404, va javob id mavjudligini **sizdirmaydi** |
| Boshqa ijarachining aktorini **o'qish** | `bitta()` va `royxat()` bermaydi |
| Audit `UPDATE`/`DELETE`/vaqtni surish | to'silgan |
| Ijarachini o'chirish (kaskad) | audit **saqlanadi**, o'chirish yiqiladi |
| `ishonch` ↔ `actor_id` zidligi | CHECK rad etadi |
| Mashina holatida aktor izi | CHECK rad etadi |
| `servis` inson qarori | rad etiladi (4 ta amal) |
| Rol matritsasi | `kuzatuvchi` tasdiqlay olmaydi, `koruvchi` sozlamaga tegmaydi |
| `aktor_majburiy` | o'chiq — o'tadi; yoqiq — aktorsiz rad etiladi |

Sinovlar **haqiqiy qatorlarda** o'lchaydi. Birinchi urinishda ular
bo'sh to'plamda "rad etildi" degan **yolg'on PASS** bergan edi
(`WHERE company_id=2` — 0 qator); bu tuzatildi va sinov ichida
izohlangan.

---

## 10. Ochiq qolgan ishlar

1. **`erp.v_tai_actor` chop etilmagan** (ERP repozitoriysida).
   Ungacha eng yuqori daraja — `aktor_elon`.
2. **Ishlab chiqarishda aktor ro'yxatga olinmagan.** `erp.own_company`
   = "ZZFIX Kompaniya", ijarachi 2 esa "BARAKA PROFIT MChJ" — ular
   **mos kelmaydi**, shuning uchun ERP hodimlari avtomatik
   xaritalanmadi. Xaritalash — operatorning **aniq qarori**
   (`POST /aktor`), taxmin emas.
3. **30 ta eski yo'naltirish qarori** `kuzatuvdan_oldin` deb
   belgilangan. Ularga aktor **tayinlanmaydi** — kim qilgani
   noma'lum va shunday deb qoladi.
4. **`aktor_majburiy` hech qayerda yoqilmagan.** Yoqilgach
   `/aktor/holat` dagi `nomalum` va `faqat_kompaniya` ustunlari
   nolga intiladi — shu paytgacha ular **atribut qarzining
   o'lchovi** bo'lib turadi.
