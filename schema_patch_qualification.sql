-- =====================================================================
-- schema_patch_qualification.sql
-- MALAKA TEKSHIRUVI (qualification) — kompaniya profili tender talabiga
-- mos keladimi.
--
-- Idempotent: qayta yurgizish xavfsiz.
--
-- Qo'llash:
--   psql -d xtxarid -f schema_patch_qualification.sql
--
-- NEGA `is_sample` — eng muhim ustun
-- ═══════════════════════════════════
-- Malaka tekshiruvining IKKI tomoni bor:
--
--   tender tomoni   — `tender_requirement`, 4 708 qator, TURLANGAN
--                     (sertifikat 1347, moliyaviy 524, tolov 257, ...)
--   kompaniya tomoni — `company_profile`, va u BUTUNLAY BO'SH edi:
--                     certificates=[], experience_years=NULL,
--                     max_contract_value=NULL, employees=NULL,
--                     company_document=0 qator.
--
-- Ya'ni tekshiruvni bugun qursak, u har mezonda `malumot_yoq` qaytaradi
-- VA ISHLAYOTGANDEK KO'RINADI. Profilni sinov qiymatlari bilan
-- to'ldirish shart, lekin shunda YANGI XAVF paydo bo'ladi:
--
--   "kompaniya 340 ta tenderga malakali" degan raqam MENING
--   O'YLAB TOPGAN qiymatlarimni o'lchaydi, haqiqatni emas.
--
-- Bu loyihada allaqachon bir marta shu sabab bilan KATALOG sun'iy
-- to'ldirilmagan edi (reja_ai_chat.md §16.6): uydirma mahsulot
-- moslikni, bildirishnoma chegarasini va hujjat qamrovini buzardi.
--
-- Yechim izoh emas, STRUKTURA: bayroq bazada turadi va malaka natijasi
-- uni O'ZI BILAN OLIB YURADI. Har hisobot "SINOV MA'LUMOTI" deb
-- yorliqlanadi va undan xulosa chiqarilmaydi.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. SINOV MA'LUMOTI bayrog'i
-- ---------------------------------------------------------------------
ALTER TABLE company_profile
    ADD COLUMN IF NOT EXISTS is_sample BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN company_profile.is_sample IS
    'Profil QO`LDA O`YLAB TOPILGAN sinov qiymatlari bilan to`ldirilgan. '
    'Malaka natijasi shu bayroqni olib yuradi — undan statistik xulosa '
    'CHIQARILMAYDI. Haqiqiy profil kiritilganda `false` qilinadi.';

-- Sinov profili KIM va QACHON to'ldirganini bilib turaylik — olti oydan
-- keyin "bu haqiqiymi?" degan savol albatta chiqadi.
ALTER TABLE company_profile
    ADD COLUMN IF NOT EXISTS sample_note TEXT;

COMMENT ON COLUMN company_profile.sample_note IS
    'Sinov qiymatlari qayerdan olingani. `is_sample = true` bo`lsa '
    'to`ldirilishi kutiladi.';

-- QOIDA BAZADA TURSIN: bayroq yoqilgan bo'lsa izoh bo'sh qolmasin.
-- Izoh himoya emas — cheklov himoya (§16.58 saboqi).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'company_profile_sample_note_chk') THEN
        ALTER TABLE company_profile
            ADD CONSTRAINT company_profile_sample_note_chk
            CHECK (NOT is_sample OR sample_note IS NOT NULL);
    END IF;
END $$;

-- ---------------------------------------------------------------------
-- 2. Ko'rinish: profil TO'LIQLIGI
--
--    Malaka tekshiruvi profil bo'sh bo'lsa hech narsa ayta olmaydi.
--    "Necha foiz to'ldirilgan" — tekshiruvdan OLDIN ko'riladigan raqam.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_profile_completeness AS
SELECT p.company_id,
       p.is_sample,
       -- Malaka uchun ZARUR maydonlar. `regions` va narx oralig'i
       -- allaqachon `ai_gonogo._facts()` da ishlatiladi.
       --
       -- COALESCE SHART: `array_length(ARRAY[]::text[], 1)` NULL
       -- qaytaradi (0 emas!), `NULL > 0` ham NULL, `(NULL)::int` ham
       -- NULL — va u BUTUN YIG'INDINI NULL qilardi. Ya'ni bo'sh
       -- massivli profil "0 ta to'ldirilgan" emas, "NOMA'LUM" chiqardi
       -- va tekshiruv `NULL < 7` shartida JIMGINA o'tib ketardi.
       (COALESCE(array_length(p.certificates, 1), 0) > 0)::int
     + (COALESCE(array_length(p.clearances,   1), 0) > 0)::int
     + (p.experience_years    IS NOT NULL)::int
     + (p.max_contract_value  IS NOT NULL)::int
     + (p.employees           IS NOT NULL)::int
     + (p.lead_time_days      IS NOT NULL)::int
     + (p.min_margin_percent  IS NOT NULL)::int
     + (COALESCE(array_length(p.regions, 1), 0) > 0)::int
                                                        AS toldirilgan,
       8                                                AS jami_maydon,
       (SELECT count(*) FROM company_document d
         WHERE d.company_id = p.company_id)             AS hujjatlar
FROM company_profile p;

COMMENT ON VIEW v_profile_completeness IS
    'Malaka tekshiruvi ishlashi uchun profil qanchalik to`ldirilgan. '
    '0 bo`lsa tekshiruv har mezonda `malumot_yoq` qaytaradi.';

-- ---------------------------------------------------------------------
-- 3. TEKSHIRUV
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'company_profile'
                     AND column_name = 'is_sample') THEN
        RAISE EXCEPTION 'is_sample yaratilmadi';
    END IF;
    IF to_regclass('public.v_profile_completeness') IS NULL THEN
        RAISE EXCEPTION 'v_profile_completeness yaratilmadi';
    END IF;
    -- MUSBAT TASDIQ: ko'rinish SON qaytarsin, NULL emas. Bo'sh
    -- massivli profilda u NULL qaytarardi va har qanday `< N`
    -- tekshiruvi jimgina o'tib ketardi.
    IF EXISTS (SELECT 1 FROM v_profile_completeness
                WHERE toldirilgan IS NULL) THEN
        RAISE EXCEPTION 'v_profile_completeness NULL qaytarmoqda '
                        '(bo`sh massiv yig`indini buzdi)';
    END IF;
    RAISE NOTICE 'schema_patch_qualification.sql: tekshiruv o`tdi';
END $$;

COMMIT;

-- =====================================================================
-- ROLLBACK (qo'lda):
--
--   BEGIN;
--   DROP VIEW IF EXISTS v_profile_completeness;
--   ALTER TABLE company_profile DROP CONSTRAINT company_profile_sample_note_chk;
--   ALTER TABLE company_profile DROP COLUMN sample_note;
--   ALTER TABLE company_profile DROP COLUMN is_sample;
--   COMMIT;
--
-- DIQQAT: `is_sample` o'chirilsa sinov qiymatlari HAQIQIY ma'lumotdan
-- ajralmaydi. Avval profilni tozalang.
-- =====================================================================
