-- =====================================================================
-- MIGRATSIYA VERSIYALASH — QO'LLANGAN PATCHLAR JURNALI
-- =====================================================================
--
-- O'LCHANGAN MUAMMO (2026-08-31, `xtxarid` bazasi tekshirildi):
--
--   Loyihada 53 ta `schema_patch_*.sql` bor va ULARNING QAYSI BIRI
--   QO'LLANGANINI HECH NARSA BILMAYDI. Bazada `schema_migration`
--   degan jadval yo'q edi; yagona "qo'llash" usuli:
--
--       Get-ChildItem schema_patch_*.sql | ForEach-Object { psql -f $_ }
--
--   Bu uch narsani jimgina buzadi:
--
--   1. TARTIB. `Get-ChildItem` ALFAVIT bo'yicha beradi, alfavit esa
--      bog'liqlikni bilmaydi. O'LCHANDI: fayllardan chiqarilgan
--      bog'liqlik grafida alfavit tartibi 67 TA YOYNI teskari
--      qo'yadi. Ikkita aniq misol:
--
--        `schema_patch_notify_subscribers.sql` sarlavhasida "OLDIN
--        `schema_patch_notify_telegram.sql` qo'llanilgan bo'lishi
--        kerak" deb YOZGAN, alfavitda esa `_subscribers`
--        `_telegram` dan oldin keladi.
--
--        `schema_patch_catalog.sql` `dim_category_uz` ni ishlatadi,
--        uni `schema_patch_categories.sql` yaratadi; alfavitda
--        `catalog` `categories` dan oldin.
--
--      Va bu natijaga ta'sir qiladi: 8 ta obyektni bir nechta patch
--      yaratadi (`v_requirement_review` ni TO'RTTA patch), ya'ni
--      oxirgi qo'llangani yutadi.
--
--   2. QAYTA QO'LLASH. Patchlar idempotent bo'lgani uchun qayta
--      yurgizish "zararsiz" deb hisoblanardi. Lekin idempotentlik
--      DDL uchun ishlaydi, MA'LUMOT ko'chirish uchun emas:
--      `schema_patch_requirement_8.sql` 1 487 ta qatorni ko'chirdi va
--      `requirement_migratsiya_jurnali` ga "oldin/keyin" suratini
--      yozdi. Qayta yurgizilsa surat YANGILANARDI va haqiqiy boshlang'ich
--      holat YO'QOLARDI.
--
--   3. FARQ. Fayl o'zgartirilsa, bazadagi holat bilan repozitoriydagi
--      matn orasidagi farqni HECH NARSA ko'rsatmasdi.
--
-- NEGA ALEMBIC EMAS
-- -----------------
--   Alembic bu loyihada nomutanosib bo'lardi va buni taxmin emas,
--   o'lchov aytadi:
--
--     - 53 ta fayl QO'LDA yozilgan sof SQL. Alembic ularni Python
--       `op.execute()` ichiga o'rashni talab qiladi — ALLAQACHON
--       ishlab turgan bazaga qo'llangan 4 800 satr DDL ni qayta yozish.
--     - 4 ta fayl psql meta-buyruqlarini ishlatadi
--       (`\set ON_ERROR_STOP on`), `schema_patch_multitenant.sql` esa
--       `\if :{?tenant_id}` — psql O'ZGARUVCHISI. Bularni SQLAlchemy
--       ulanishi orqali yurgizib BO'LMAYDI.
--     - Alembic ning asosiy foydasi — `autogenerate`. Bu loyihada ORM
--       modellari YO'Q (SQL `api/queries.py` da qo'lda yozilgan),
--       ya'ni o'sha foyda mavjud emas.
--     - Alembic chiziqli `down_revision` zanjirini talab qiladi. U
--       zanjir bu yerda MAVJUD EMAS va uni retroaktiv "tiklash" —
--       taxminni fakt qilib ko'rsatish bo'lardi.
--
--   Shuning uchun: minimal jurnal jadvali + `migratsiya.py`
--   yurgizuvchisi. Bu loyihada ALLAQACHON ishlaydigan naqsh —
--   `etl_run` (`etl_ishonch.py`) aynan shunday qurilgan: holat
--   BAZAGA yoziladi, shuning uchun jarayon o'ldirilsa ham SAQLANADI.
--
-- QAYTA QO'LLAMASLIK QOIDASI IZOHDA EMAS, INDEKSDA
-- ------------------------------------------------
--   Bu loyihada takrorlangan nuqson: qoida faqat izoh bilan
--   himoyalanadi va keyin buziladi (1 487 ta soxta `approved` — aynan
--   shu). Shuning uchun "muvaffaqiyatli migratsiya IKKI MARTA
--   yozilmaydi" qoidasi QISMAN UNIKAL INDEKS bilan qulflangan:
--   ilova kodi nima qilishidan qat'i nazar, ikkinchi `ok` qator
--   JISMONAN yozilmaydi.
--
-- Idempotent: bir necha marta yurgizsa bo'ladi.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1) Jurnal jadvali
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migration (
    id             BIGSERIAL PRIMARY KEY,

    -- BARQAROR ID. Fayl nomidan ALOHIDA saqlanadi: fayl qayta
    -- nomlansa tarix uzilmasin. Manifestda muzlatilgan.
    migratsiya_id  TEXT        NOT NULL,
    fayl           TEXT        NOT NULL,

    -- Manifestdagi o'rin. Tarix o'qilganda "qanday tartibda
    -- qo'llangan" degan savolga javob beradi.
    tartib         INT         NOT NULL,

    -- Normallashtirilgan mazmunning SHA-256 i. Fayl o'zgarsa
    -- yurgizuvchi TO'XTAYDI — jimgina farq qolmaydi.
    checksum       TEXT        NOT NULL,

    holat          TEXT        NOT NULL,

    -- Fayl O'Z `BEGIN`/`COMMIT` ini olib yuradimi. Bu UZILGAN
    -- migratsiyani hal qilishda HAL QILUVCHI: tranzaksion fayl
    -- o'ldirilsa TO'LIQ qaytariladi (yarim qo'llanish yo'q),
    -- tranzaksion bo'lmagani esa YARIM qolishi mumkin va uni odam
    -- ko'rishi shart. O'lchandi (2026-08-31): 53 patchdan 26 tasi
    -- o'z tranzaksiyasini olib yuradi.
    tranzaksion    BOOLEAN,

    boshlandi_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    tugadi_at      TIMESTAMPTZ,
    davomiylik_ms  INT,
    chiqish_kod    INT,

    -- Yiqilganda psql ning haqiqiy chiqishi. DALILSIZ "xato"
    -- yozilmaydi — pastdagi CHECK buni talab qiladi.
    xato           TEXT,

    yurgizuvchi    TEXT,
    izoh           TEXT
);

-- ---------------------------------------------------------------------
-- 2) Holat lug'ati va butunlik qoidalari
-- ---------------------------------------------------------------------
--   boshlandi  — yurgizish BOSHLANDI, natija hali yo'q. Jarayon
--                o'ldirilsa qator SHU HOLATDA qoladi va keyingi
--                yurish uni ko'rib TO'XTAYDI. "Uzilgan" holat
--                ko'rinmas bo'lib qolmaydi.
--   ok         — psql 0 bilan tugadi.
--   xato       — psql nolga teng bo'lmagan kod qaytardi.
--   bootstrap  — FAYL YURGIZILMADI. Mavjud bazada obyektlari BOR
--                ekani tekshirilib, "allaqachon qo'llangan" deb
--                yozildi. Bu `ok` DAN FARQLI atalgan, chunki ular
--                bir xil emas: birinchisi o'lchangan, ikkinchisi
--                bajarilgan.
--   otkazildi  — odam ataylab o'tkazib yubordi (izoh MAJBURIY).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'schema_migration_holat_chk') THEN
        ALTER TABLE schema_migration ADD CONSTRAINT schema_migration_holat_chk
            CHECK (holat IN ('boshlandi', 'ok', 'xato', 'bootstrap', 'otkazildi'));
    END IF;

    -- Tugagan qatorda tugash vaqti BO'LISHI SHART; tugamaganda
    -- BO'LMASLIGI shart. Aks holda "qachon tugadi" savoliga jurnal
    -- yolg'on javob berardi.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'schema_migration_tugadi_chk') THEN
        ALTER TABLE schema_migration ADD CONSTRAINT schema_migration_tugadi_chk
            CHECK ((holat = 'boshlandi' AND tugadi_at IS NULL)
                OR (holat <> 'boshlandi' AND tugadi_at IS NOT NULL));
    END IF;

    -- YORLIQ DALILSIZ QO'YILMAYDI. "xato" deyish uchun psql ning
    -- haqiqiy chiqishi bo'lishi shart.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'schema_migration_xato_dalil_chk') THEN
        ALTER TABLE schema_migration ADD CONSTRAINT schema_migration_xato_dalil_chk
            CHECK (holat <> 'xato' OR (xato IS NOT NULL AND length(btrim(xato)) > 0));
    END IF;

    -- `bootstrap` va `otkazildi` — ODAM qarori yoki o'lchov natijasi.
    -- Ikkalasi ham NIMA tekshirilganini yozishga majbur.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'schema_migration_izoh_chk') THEN
        ALTER TABLE schema_migration ADD CONSTRAINT schema_migration_izoh_chk
            CHECK (holat NOT IN ('bootstrap', 'otkazildi')
                OR (izoh IS NOT NULL AND length(btrim(izoh)) > 0));
    END IF;

    -- SHA-256 — aynan 64 ta hex belgi. Bo'sh yoki qisqartirilgan
    -- checksum "tekshirildi" degan yolg'on taassurot berardi.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'schema_migration_checksum_chk') THEN
        ALTER TABLE schema_migration ADD CONSTRAINT schema_migration_checksum_chk
            CHECK (checksum ~ '^[0-9a-f]{64}$');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'schema_migration_tartib_chk') THEN
        ALTER TABLE schema_migration ADD CONSTRAINT schema_migration_tartib_chk
            CHECK (tartib > 0);
    END IF;
END $$;

-- ---------------------------------------------------------------------
-- 3) QAYTA QO'LLASHNI JISMONAN TO'SUVCHI INDEKS
-- ---------------------------------------------------------------------
-- Bir migratsiya UCHUN faqat BITTA muvaffaqiyatli qator bo'la oladi.
-- `xato` va `boshlandi` qatorlari cheklanmaydi — urinishlar tarixi
-- SAQLANISHI kerak, aks holda "nechinchi urinishda o'tdi" degan
-- savolga javob yo'qolardi.
CREATE UNIQUE INDEX IF NOT EXISTS schema_migration_bir_marta
    ON schema_migration (migratsiya_id)
    WHERE holat IN ('ok', 'bootstrap');

-- Bir vaqtda faqat BITTA `boshlandi` bo'la oladi: ikkita yurgizuvchi
-- parallel ketsa ikkinchisi shu yerda YIQILADI. Maslahat qulfi
-- (`pg_advisory_lock`) birinchi to'siq, bu — ikkinchisi, chunki
-- qulf ulanish uzilsa BO'SHAYDI, indeks esa bo'shamaydi.
CREATE UNIQUE INDEX IF NOT EXISTS schema_migration_bitta_ochiq
    ON schema_migration ((1))
    WHERE holat = 'boshlandi';

CREATE INDEX IF NOT EXISTS schema_migration_vaqt_idx
    ON schema_migration (boshlandi_at DESC);

-- ---------------------------------------------------------------------
-- 4) Ko'rinishlar
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_migratsiya_holat;
CREATE VIEW v_migratsiya_holat AS
SELECT migratsiya_id,
       fayl,
       tartib,
       holat,
       checksum,
       tranzaksion,
       boshlandi_at,
       tugadi_at,
       davomiylik_ms,
       yurgizuvchi,
       izoh
  FROM schema_migration s
 WHERE holat IN ('ok', 'bootstrap')
 ORDER BY tartib;

COMMENT ON VIEW v_migratsiya_holat IS
    'Hozir QO''LLANGAN deb hisoblanadigan migratsiyalar. `bootstrap` '
    'qatorlar YURGIZILMAGAN — obyektlari borligi tekshirilgan.';

-- UZILGAN MIGRATSIYALAR. Bo'sh bo'lishi KERAK. Bo'sh bo'lmasa —
-- jarayon o'ldirilgan va odam aralashuvi shart.
DROP VIEW IF EXISTS v_migratsiya_uzilgan;
CREATE VIEW v_migratsiya_uzilgan AS
SELECT migratsiya_id,
       fayl,
       tranzaksion,
       boshlandi_at,
       now() - boshlandi_at AS qancha_vaqt,
       yurgizuvchi,
       CASE WHEN tranzaksion THEN
                'Fayl o''z tranzaksiyasida edi -> DDL QAYTARILGAN, '
                || 'baza toza. Qatorni ''xato'' ga o''tkazib qayta yurgizing.'
            WHEN tranzaksion IS FALSE THEN
                'Fayl tranzaksiyasiz edi -> YARIM qo''llangan bo''lishi '
                || 'MUMKIN. Baza holatini QO''LDA tekshiring.'
            ELSE 'Tranzaksionligi yozilmagan — qo''lda tekshiring.'
       END AS nima_qilish
  FROM schema_migration
 WHERE holat = 'boshlandi';

COMMENT ON VIEW v_migratsiya_uzilgan IS
    'Yurgizish boshlangan, lekin natija yozilmagan migratsiyalar. '
    'BO''SH BO''LISHI KERAK.';

COMMENT ON TABLE schema_migration IS
    'Qo''llangan sxema patchlari jurnali. `migratsiya.py` yozadi. '
    'Qo''lda tahrirlanmaydi — tarix audit izidir.';

COMMIT;
