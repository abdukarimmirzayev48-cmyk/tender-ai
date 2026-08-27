-- =====================================================================
-- schema_patch_requirement_2.sql
-- J3 — `method`: talab QANDAY ajratilgani
--
-- Bog'liqlik: schema_patch_requirement.sql
-- Idempotent: qayta yurgizish xavfsiz.
--
-- Qo'llash:
--   psql -d xtxarid -f schema_patch_requirement_2.sql
--
-- NEGA KERAK
-- ══════════
-- `source` talab QAYERDAN kelganini aytadi ('api' | 'document'), lekin
-- QANDAY olinganini emas. Endi uch usul bor:
--
--     reyestr  — tender_good pozitsiyasi        (bepul, aniq)
--     naqsh    — hujjatdan REGEX bilan          (bepul, sodda holatlar)
--     llm      — hujjatdan model bilan          (pul, kontekstli holatlar)
--
-- Ular ARALASHIB KETMASLIGI shart: 1549 ta reyestr talabi ustiga naqsh
-- va LLM natijalari qo'shiladi, va ularni SOLISHTIRISH kerak
-- ("naqsh 33 tadan nechtasini bepul oldi?").
--
-- `UNIQUE` GA HAM QO'SHILADI — aks holda naqsh va LLM bir xil talabni
-- yozganda BIRI IKKINCHISINI O'CHIRIB YUBORADI va solishtirish
-- imkoniyati yo'qoladi.
--
-- J1 SABOQI: `UNIQUE` o'zgarsa `ON CONFLICT` maqsadi HAM o'zgarishi
-- shart. O'sha paytda bu beshta joyda jimgina buzilgan edi. Bu yerda
-- `api/requirement.py:SQL_UPSERT` va `_tests/requirement_test.py`
-- BIRGA yangilanadi.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. Ustun
-- ---------------------------------------------------------------------
ALTER TABLE tender_requirement
    ADD COLUMN IF NOT EXISTS method TEXT;

-- Mavjud qatorlar: `source` dan kelib chiqib to'ldiramiz.
-- Hozirgi holat: 'api' -> reyestr, 'document' -> llm (naqsh hali yo'q edi).
UPDATE tender_requirement
   SET method = CASE WHEN source = 'api' THEN 'reyestr' ELSE 'llm' END
 WHERE method IS NULL;

-- Endi NOT NULL qilish xavfsiz (J1 saboqi: bosqichma-bosqich).
ALTER TABLE tender_requirement
    ALTER COLUMN method SET NOT NULL;

-- DEFAULT ATAYLAB YO'Q: har chaqiruvchi usulni ANIQ aytishi kerak.
-- J1 da vaqtinchalik DEFAULT bir marta noto'g'ri qiymat yozib qo'ygan edi.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'tender_requirement_method_chk') THEN
        ALTER TABLE tender_requirement
            ADD CONSTRAINT tender_requirement_method_chk
            CHECK (method IN ('reyestr', 'naqsh', 'llm'));
    END IF;
END $$;

COMMENT ON COLUMN tender_requirement.method IS
    'Talab QANDAY olingan: reyestr (tender_good) | naqsh (regex, bepul) | '
    'llm (model, pul). `source` QAYERDAN, `method` QANDAY.';

-- ---------------------------------------------------------------------
-- 2. UNIQUE — `method` bilan
--
--    Naqsh va LLM bir xil talabni topsa, IKKALASI ham saqlanadi va
--    solishtirilishi mumkin.
-- ---------------------------------------------------------------------
ALTER TABLE tender_requirement
    DROP CONSTRAINT IF EXISTS tender_requirement_uq;

ALTER TABLE tender_requirement
    ADD CONSTRAINT tender_requirement_uq
    UNIQUE (company_id, tender_id, source, method, position_no, name);

-- Usul bo'yicha taqqoslash uchun
CREATE INDEX IF NOT EXISTS tender_requirement_method_idx
    ON tender_requirement (company_id, tender_id, method);

-- ---------------------------------------------------------------------
-- 3. Yurish jurnali — usul bo'yicha alohida
--
--    Naqsh yurishi va LLM yurishi BOSHQA-BOSHQA: birini qayta
--    yurgizish ikkinchisining holatini o'chirmasligi kerak.
-- ---------------------------------------------------------------------
ALTER TABLE tender_requirement_run
    ADD COLUMN IF NOT EXISTS method TEXT;

UPDATE tender_requirement_run
   SET method = CASE WHEN model IS NULL THEN 'reyestr' ELSE 'llm' END
 WHERE method IS NULL;

ALTER TABLE tender_requirement_run
    ALTER COLUMN method SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'tender_requirement_run_method_chk') THEN
        ALTER TABLE tender_requirement_run
            ADD CONSTRAINT tender_requirement_run_method_chk
            CHECK (method IN ('reyestr', 'naqsh', 'llm'));
    END IF;
END $$;

-- PK ni `method` bilan qayta quramiz.
ALTER TABLE tender_requirement_run
    DROP CONSTRAINT IF EXISTS tender_requirement_run_pkey;
ALTER TABLE tender_requirement_run
    ADD PRIMARY KEY (company_id, tender_id, method);

-- ---------------------------------------------------------------------
-- 4. Ko'rinish — usul ustuni bilan
-- ---------------------------------------------------------------------
-- DROP + CREATE, `CREATE OR REPLACE` EMAS: u ustun TARTIBINI
-- o'zgartira olmaydi ('изменить имя столбца ... нельзя').
-- Quruq yurish shu xatoni tutdi.
DROP VIEW IF EXISTS v_requirement_review;
CREATE VIEW v_requirement_review AS
SELECT r.company_id,
       r.tender_id,
       t.name           AS tender_name,
       t.close_at,
       r.method,
       r.status,
       r.n_requirements,
       r.min_confidence,
       r.error,
       r.extracted_at
FROM tender_requirement_run r
JOIN tender t ON t.id = r.tender_id
WHERE r.status IN ('needs_review', 'failed')
ORDER BY t.close_at NULLS LAST, r.min_confidence NULLS FIRST;

-- ---------------------------------------------------------------------
-- 5. TEKSHIRUV — COMMIT dan OLDIN
-- ---------------------------------------------------------------------
DO $$
DECLARE
    n INT;
    ustunlar TEXT;
BEGIN
    SELECT count(*) INTO n FROM tender_requirement WHERE method IS NULL;
    IF n > 0 THEN
        RAISE EXCEPTION '% ta qatorda method NULL qoldi', n;
    END IF;

    SELECT string_agg(a.attname, ',' ORDER BY k.ord) INTO ustunlar
    FROM pg_constraint c
    JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
    WHERE c.conname = 'tender_requirement_uq';
    IF ustunlar <> 'company_id,tender_id,source,method,position_no,name' THEN
        RAISE EXCEPTION 'UNIQUE ustunlari kutilgandek emas: %', ustunlar;
    END IF;

    RAISE NOTICE 'schema_patch_requirement_2.sql: tekshiruv o`tdi (UNIQUE: %)',
                 ustunlar;
END $$;

COMMIT;

-- =====================================================================
-- ROLLBACK (qo'lda):
--
--   BEGIN;
--   ALTER TABLE tender_requirement DROP CONSTRAINT tender_requirement_uq;
--   ALTER TABLE tender_requirement ADD CONSTRAINT tender_requirement_uq
--       UNIQUE (company_id, tender_id, source, position_no, name);
--   ALTER TABLE tender_requirement DROP COLUMN method;
--   ALTER TABLE tender_requirement_run DROP CONSTRAINT
--       tender_requirement_run_pkey;
--   ALTER TABLE tender_requirement_run ADD PRIMARY KEY (company_id, tender_id);
--   ALTER TABLE tender_requirement_run DROP COLUMN method;
--   COMMIT;
--
-- DIQQAT: `method` o'chirilsa naqsh va LLM natijalari bir-birini
-- o'chirib yuboradi (UNIQUE toraygani uchun) — avval dublikatlarni
-- tozalash kerak bo'ladi.
-- =====================================================================
