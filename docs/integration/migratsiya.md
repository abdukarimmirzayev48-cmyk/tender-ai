# Migratsiya versiyalash — operator qo'llanmasi

Bu hujjat `schema_patch_*.sql` fayllarini **kuzatiladigan** migratsiyaga
aylantirgan o'zgarishni yig'adi: nima o'lchandi, nima qurildi, va kundalik
ishda nima qilinadi.

---

## 1. Nima muammo edi

Loyihada 53 ta `schema_patch_*.sql` bor edi va qo'llashning yagona usuli shu:

```powershell
Get-ChildItem schema_patch_*.sql | ForEach-Object { psql $env:XT_DB_DSN -f $_.Name }
```

Bazada `schema_migration` degan jadval **yo'q edi** — ya'ni "qaysi patch
qo'llangan" degan savolga javob beradigan hech narsa yo'q edi.

### 1.1 Tartib — o'lchangan, taxmin emas

Fayllardan bog'liqlik grafi chiqarildi (e'lon qilingan `Talab:` sarlavhalari,
raqamli suffikslar, obyekt bog'liqliklari). **Alfavit tartibi bu grafdagi
67 ta yoyni teskari qo'yadi.** Ikkita aniq misol:

| Buziladigan talab | Sabab |
|---|---|
| `notify_subscribers` ← `notify_telegram` | Fayl sarlavhasida "OLDIN `schema_patch_notify_telegram.sql` qo'llanilgan bo'lishi kerak" deb **yozgan**; alfavitda `_subscribers` `_telegram` dan oldin |
| `catalog` ← `categories` | `catalog.sql` `dim_category_uz` ni ishlatadi, uni `categories.sql` yaratadi; alfavitda `catalog` oldin |

Va tartib **natijani belgilaydi**: 8 ta obyektni bir nechta patch yaratadi —
`v_requirement_review` ni **to'rtta**. Oxirgi qo'llangani yutadi.

### 1.2 Qayta qo'llash zararsiz EMAS

Patchlar DDL uchun idempotent, lekin **ma'lumot ko'chirish uchun emas**.
`schema_patch_requirement_8.sql` 1 487 qatorni ko'chirdi va
`requirement_migratsiya_jurnali` ga "oldin/keyin" suratini yozdi. Qayta
yurgizilsa surat yangilanardi va haqiqiy boshlang'ich holat yo'qolardi.

---

## 2. Nega Alembic emas

Bu qaror o'lchovga tayanadi, didga emas:

| Sabab | O'lchov |
|---|---|
| Fayllar sof SQL, qo'lda yozilgan | 53 fayl, ~4 800 satr DDL — hammasini `op.execute()` ga o'rash kerak bo'lardi |
| psql meta-buyruqlari | 4 fayl `\set ON_ERROR_STOP on` ishlatadi; `multitenant.sql` esa `\if :{?tenant_id}` — psql **o'zgaruvchisi**. SQLAlchemy ulanishi orqali yurmaydi |
| `autogenerate` foydasi yo'q | Loyihada ORM modellari yo'q — SQL `api/queries.py` da qo'lda |
| Chiziqli `down_revision` zanjiri | Mavjud emas; uni retroaktiv "tiklash" taxminni fakt qilib ko'rsatish bo'lardi |

Shuning uchun: **minimal jurnal jadvali + yurgizuvchi**. Bu loyihada
allaqachon ishlaydigan naqsh — `etl_run` (`etl_ishonch.py`) aynan shunday
qurilgan.

---

## 3. Nima qo'shildi

| Fayl | Nima |
|---|---|
| `schema_patch_migratsiya.sql` | `schema_migration` jurnali + `v_migratsiya_holat`, `v_migratsiya_uzilgan` |
| `migratsiya.py` | Yurgizuvchi: manifest, checksum, qulf, bootstrap, tekshiruv |
| `migratsiya_manifest.tsv` | **Muzlatilgan** tartib (55 ta yozuv) |
| `_tests/migratsiya_test.py` | 62 ta tekshiruv, 4 ta stsenariy |

### 3.1 Qoidalar CHECK da, izohda emas

Loyihada takrorlangan nuqson: qoida faqat izoh bilan himoyalanadi va keyin
buziladi (1 487 ta soxta `approved` — aynan shu). Shuning uchun:

```sql
CREATE UNIQUE INDEX schema_migration_bir_marta
    ON schema_migration (migratsiya_id)
    WHERE holat IN ('ok', 'bootstrap');
```

Muvaffaqiyatli migratsiya **ikkinchi marta yozilmaydi** — kod nima
qilishidan qat'i nazar. Yana 6 ta CHECK bor: holat lug'ati, tugash vaqti
majburiyligi, `xato` uchun **dalil** majburiyligi, `bootstrap` uchun **izoh**
majburiyligi, checksum shakli (64 hex), musbat tartib. Hammasi bo'sh bazada
sinab ko'rilgan — 11 tadan 11 tasi rad etadi.

### 3.2 Holat lug'ati

| Holat | Ma'nosi |
|---|---|
| `boshlandi` | Yurgizish boshlandi, natija yo'q. **Jarayon o'ldirilsa shu holatda qoladi.** |
| `ok` | psql 0 bilan tugadi — fayl **yurgizildi** |
| `xato` | psql nolga teng bo'lmagan kod qaytardi (psql chiqishi saqlanadi) |
| `bootstrap` | Fayl **YURGIZILMADI**. Obyektlari bazada borligi tekshirildi. |
| `otkazildi` | Odam ataylab o'tkazib yubordi (izoh majburiy) |

`ok` va `bootstrap` **ataylab farqli atalgan**: birinchisi bajarilgan,
ikkinchisi o'lchangan. Ular bir xil emas va jurnal buni yashirmaydi.

---

## 4. Kundalik ish

```powershell
# Nima qo'llangan, nima yo'q
.venv\Scripts\python.exe migratsiya.py --holat

# Butunlik: checksum, yetim fayl, uzilgan migratsiya
.venv\Scripts\python.exe migratsiya.py --tekshir

# Nima yuriladi (yurgizmaydi)
.venv\Scripts\python.exe migratsiya.py --reja

# Qo'llash
.venv\Scripts\python.exe migratsiya.py --qolla
```

### 4.1 Yangi patch qo'shish

1. `schema_patch_<nom>.sql` yozing.
2. `migratsiya_manifest.tsv` oxiriga qator qo'shing (tartib raqami oldingisidan
   katta; qadam 10 — orasiga qo'yish uchun joy qolsin).
3. `--reja` bilan ko'ring, `--qolla` bilan yurgizing.

`--manifest-yasa` tartibni bog'liqliklardan qayta chiqaradi, lekin **natijani
ko'zdan kechiring**: chiqarish jadval darajasida ishlaydi (§6.2 ga qarang).

### 4.2 Qo'llangan faylni tahrirlash — QILMANG

Checksum farq qilsa yurgizuvchi to'xtaydi va sabab aytadi. Agar o'zgarish
sxemaga **tegmasa** (izoh, bo'shliq), qayta muhrlang:

```powershell
.venv\Scripts\python.exe migratsiya.py --checksum-yangila 0042_requirement_7 `
    --izoh "faqat izoh tuzatildi, DDL o'zgarmadi"
```

Eski qator **o'chirilmaydi** — `otkazildi` ga o'tkaziladi, ya'ni qayta
muhrlash tarixda ko'rinadi. `--izoh` majburiy.

Sxemaga tegsa — **yangi patch fayli yozing**.

### 4.3 Uzilgan migratsiya

```sql
SELECT * FROM v_migratsiya_uzilgan;   -- BO'SH BO'LISHI KERAK
```

Bo'sh bo'lmasa yurgizuvchi yangi migratsiya boshlamaydi. Ko'rinish
`nima_qilish` ustunida aynan nima qilishni aytadi, va u **faylning
tranzaksionligiga qarab farq qiladi**:

| `tranzaksion` | Holat | Nima qilish |
|---|---|---|
| `true` | PostgreSQL DDL ni **to'liq qaytargan**, baza toza | Qatorni `xato` ga o'tkazing va qayta yurgizing |
| `false` | **Yarim qo'llangan bo'lishi mumkin** | Avval baza holatini **qo'lda** tekshiring |

O'lchandi: 55 patchdan **27 tasi** o'z `BEGIN`/`COMMIT` ini olib yuradi,
28 tasi `--single-transaction` bilan o'raladi. Ya'ni **hammasi atomar**.

```sql
UPDATE schema_migration
   SET holat = 'xato', tugadi_at = now(),
       xato = 'qo''lda yopildi: jarayon uzilgan'
 WHERE migratsiya_id = '<id>' AND holat = 'boshlandi';
```

---

## 5. Mavjud bazani ro'yxatga olish (bootstrap)

```powershell
.venv\Scripts\python.exe migratsiya.py --bootstrap --quruq   # avval ko'ring
.venv\Scripts\python.exe migratsiya.py --bootstrap
```

Har patch uchun uning obyektlari **bazada borligi tekshiriladi** va faqat
shunda "qo'llangan" deb yoziladi. Yetishsa — **jimgina yozilmaydi**, ro'yxat
chiqadi. Dalilsiz yorliq qo'yilmaydi.

Ikkita nozik joy hisobga olingan (ikkalasi ham haqiqiy holat):

- Patch **o'zi** yaratgan yordamchi obyektni **o'zi** tashlashi mumkin —
  `multitenant.sql` `tai_add_company_id()` ni yaratadi, 6 ta jadvalga
  qo'llaydi va 371-satrda tashlaydi.
- **Keyingi** patch oldingisining obyektini ataylab tashlashi mumkin —
  `auth.sql` `app_user`/`app_session` yaratadi, `auth_2.sql` ularni tashlaydi
  (hisoblar `erp.app_user` ga ko'chgan).

**Bajarildi:** `xtxarid` bazasi 2026-08-31 da ro'yxatga olindi — 55/55,
yetishmaydigan 0 ta.

---

## 6. Ma'lum cheklovlar — ochiq yozilgan

### 6.1 `multitenant.sql` bo'sh bazada TO'XTAYDI

U sof DDL emas: mavjud ma'lumotni **qaysi kompaniyaga** biriktirishni bilishi
kerak va buni faol `company_account` dan oladi. Bo'sh bazada faol hisob yo'q.

Yurgizuvchi buni **oldindan** tekshiradi va tushunarli xabar beradi (xom psql
xatosi emas), migratsiyani **umuman boshlamaydi** — yarim holat yaratilmaydi.
Shart bajarilgach `--qolla` shu yerdan davom etadi.

```powershell
# Aniq ko'rsatish (tavsiya etiladi)
.venv\Scripts\python.exe migratsiya.py --qolla --var tenant_id=2
```

Avtomatik tanlanmaydi, chunki patch o'z izohida yozgan: eng kichik `id`
o'chirilgan sinov hisobiga tegishli bo'lishi mumkin.

### 6.2 Tartib chiqarish JADVAL darajasida

Graf `ALTER TABLE t ADD COLUMN c` bilan qo'shilgan **ustunga** bog'liqlikni
ko'rmaydi. Bo'sh bazada qurish sinovi buni ochdi
(`multiplatform.sql` → `source_platform`). Bunday yoylar `migratsiya.py`
dagi `QOLDA_YOY` ro'yxatida — har biri **aynan bitta psql xatosidan** chiqqan
va o'sha xato yoniga yozilgan.

Shuning uchun `--manifest-yasa` natijasi **bo'sh bazada qurib** tekshirilishi
kerak.

### 6.3 `erp` sxemasi — REPOZITORIYALARARO old shart

`auth_2.sql` `public.app_user` ni faqat `erp.app_user` **mavjud va bo'sh
emas** bo'lsa tashlaydi. `schema_patch_erp_6.sql` **boshqa repozitoriyda**.

Natija: toza qurilgan bazada `app_user`/`app_session` **qoladi** (ishlab
chiqarishda yo'q, chunki u yerda `erp.app_user` da 6 qator bor). Bu patchning
**himoya xulqi** — ERP hali to'ldirilmagan bo'lsa ma'lumotni tashlamaydi.

Migratsiya kuzatuvi bu old shartni **majburlay olmaydi** — u boshqa
repozitoriyda.

---

## 7. Tekshirilgan holat

`_tests/migratsiya_test.py` — **62/62 o'tdi** (2026-08-31).

| Stsenariy | Natija |
|---|---|
| Bo'sh baza → joriy sxema | 55/55 qo'llandi. Ishlab chiqarishdagi **har** jadval, ko'rinish va ustun qurilgan bazada bor — **0 ta yetishmaydi** |
| Mavjud baza → qayta qo'llash yo'q | `--qolla` hech narsa qilmadi; **52 jadvalning hammasida** qator soni o'zgarmadi |
| Uzilgan migratsiya | Yurgizuvchi to'xtadi (kod 2); tranzaksionlikka qarab boshqa-boshqa maslahat berdi |
| Checksum o'zgarishi | To'xtadi; izohsiz qayta muhrlash rad etildi; eski qator audit izi sifatida saqlandi |

Bazali stsenariylar **`--offline` da yurmaydi** — ular baza **yaratadi va
tashlaydi**, bu esa kundalik sinov yurishi uchun og'ir amal:

```powershell
.venv\Scripts\python.exe run_tests.py --online --only migratsiya
.venv\Scripts\python.exe _tests\migratsiya_test.py            # to'g'ridan-to'g'ri
```

Sinov o'z bazasini (`xt_migratsiya_sinov`) yaratadi va oxirida tashlaydi.
Nom ishlab chiqarish bazasiga teng bo'lsa **sinov yiqiladi** — jimgina
o'tmaydi.
