-- =====================================================================
-- schema_patch_requirement_3.sql
-- J3 — TASDIQLASH holati (inson ko'rib chiqishi)
--
-- Bog'liqlik: schema_patch_requirement_2.sql
-- Idempotent: qayta yurgizish xavfsiz.
--
-- Qo'llash:
--   psql -d xtxarid -f schema_patch_requirement_3.sql
--
-- NEGA KERAK
-- ══════════
-- `v_requirement_review` da 129 ta tender turibdi, lekin ularni
-- ko'rib chiqadigan MEXANIZM yo'q edi — ya'ni navbat abadiy 129 da
-- qolardi.
--
-- Muhimrogi: `compliance.check()` ga tekshirilmagan talabni ulash
-- AI ajratish xatosini QAROR QATLAMIGA jimgina o'tkazadi. Misol
-- (t7886728):
--
--     Kafolat muddati (shartnoma 5.5) = ko'rsatilmagan (shablon bo'sh)
--     confidence = 0.40
--
-- Model TO'G'RI ish qildi. Lekin cheklist buni ko'r-ko'rona o'qisa,
-- natija ARVOH BLOCKER bo'ladi: "kafolat sharti bajarilmagan",
-- holbuki shart umuman QO'YILMAGAN. Broker bunday ogohlantirishni
-- bir-ikki marta ko'rgach butun cheklistga ishonishni to'xtatadi.
-- Noto'g'ri blocker — yo'q blockerdan YOMONROQ.
--
-- Shu sababli tasdiqlash holati ustundagi ma'lumotning bir qismi
-- bo'ladi va iste'molchilar shunga qarab filtrlaydi.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. Ko'rib chiqish holati
-- ---------------------------------------------------------------------
ALTER TABLE tender_requirement
    ADD COLUMN IF NOT EXISTS review_status TEXT,
    ADD COLUMN IF NOT EXISTS reviewed_by   INT REFERENCES company_account(id),
    ADD COLUMN IF NOT EXISTS reviewed_at   TIMESTAMPTZ,
    -- Inson tuzatgan qiymat. ASL qiymat `attrs->>'qiymat'` da QOLADI —
    -- "model nima degan edi" savoli J6 uchun kerak.
    ADD COLUMN IF NOT EXISTS corrected_value TEXT,
    ADD COLUMN IF NOT EXISTS review_note   TEXT;

-- Mavjud qatorlar:
--   reyestr — RASMIY yozuv, tasdiqlash talab qilmaydi -> 'approved'
--   naqsh/llm — inson ko'rishi kerak -> 'pending'
UPDATE tender_requirement
   SET review_status = CASE WHEN method = 'reyestr' THEN 'approved'
                            ELSE 'pending' END
 WHERE review_status IS NULL;

ALTER TABLE tender_requirement
    ALTER COLUMN review_status SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'tender_requirement_review_chk') THEN
        ALTER TABLE tender_requirement
            ADD CONSTRAINT tender_requirement_review_chk
            CHECK (review_status IN
                   ('pending', 'approved', 'rejected', 'corrected'));
    END IF;
END $$;

-- Tuzatilgan bo'lsa qiymat BO'LISHI shart — aks holda "tuzatdim,
-- lekin nimaga?" degan holat qoladi.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'tender_requirement_corrected_chk') THEN
        ALTER TABLE tender_requirement
            ADD CONSTRAINT tender_requirement_corrected_chk
            CHECK (review_status <> 'corrected' OR corrected_value IS NOT NULL);
    END IF;
END $$;

COMMENT ON COLUMN tender_requirement.review_status IS
    'pending — inson ko`rishi kerak; approved — tasdiqlangan; '
    'rejected — ARVOH talab (hujjatda yo`q); corrected — qiymati '
    'tuzatilgan. `reyestr` usuli avtomatik approved.';
COMMENT ON COLUMN tender_requirement.corrected_value IS
    'Inson tuzatgan qiymat. ASL qiymat attrs->>''qiymat'' da qoladi — '
    'model nima deganini J6 uchun bilish kerak.';

-- Navbat so'rovi shu indeksdan foydalanadi.
CREATE INDEX IF NOT EXISTS tender_requirement_pending_idx
    ON tender_requirement (company_id, tender_id)
    WHERE review_status = 'pending';

-- ---------------------------------------------------------------------
-- 2. NAVBAT ko'rinishi — KO'RIB CHIQILGANI CHIQIB KETADI
--
--    Eski `v_requirement_review` yurish holatiga (`needs_review`)
--    qarardi va u HECH QACHON o'zgarmasdi — ya'ni navbat abadiy
--    bir xil qolardi. Endi TALAB darajasidagi holatga qaraydi.
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_requirement_review;
CREATE VIEW v_requirement_review AS
SELECT r.company_id,
       r.tender_id,
       t.name                       AS tender_name,
       t.close_at,
       count(*)                     AS kutayotgan,
       count(*) FILTER (WHERE r.method = 'llm')   AS modeldan,
       count(*) FILTER (WHERE r.method = 'naqsh') AS naqshdan,
       min(r.confidence)            AS eng_past_ishonch,
       count(*) FILTER (WHERE r.confidence < 0.60) AS past_ishonchli,
       max(r.extracted_at)          AS ajratilgan
FROM tender_requirement r
JOIN tender t ON t.id = r.tender_id
WHERE r.review_status = 'pending'
GROUP BY r.company_id, r.tender_id, t.name, t.close_at
-- Muddati YAQIN tenderlar birinchi: ular bo'yicha qaror tezroq kerak.
ORDER BY t.close_at NULLS LAST, min(r.confidence);

COMMENT ON VIEW v_requirement_review IS
    'J3 navbati: KUTAYOTGAN talabi bor tenderlar. Hammasi ko`rib '
    'chiqilgach tender bu yerdan CHIQIB KETADI.';

-- ---------------------------------------------------------------------
-- 3. TEKSHIRUV — COMMIT dan OLDIN
-- ---------------------------------------------------------------------
DO $$
DECLARE
    n INT;
BEGIN
    SELECT count(*) INTO n FROM tender_requirement WHERE review_status IS NULL;
    IF n > 0 THEN
        RAISE EXCEPTION '% ta qatorda review_status NULL', n;
    END IF;

    -- Reyestr talablari tasdiqlash navbatiga TUSHMASLIGI kerak
    SELECT count(*) INTO n FROM tender_requirement
     WHERE method = 'reyestr' AND review_status = 'pending';
    IF n > 0 THEN
        RAISE EXCEPTION 'reyestr talablari navbatga tushdi: % ta', n;
    END IF;

    RAISE NOTICE 'schema_patch_requirement_3.sql: tekshiruv o`tdi';
END $$;

COMMIT;

-- =====================================================================
-- ROLLBACK (qo'lda):
--
--   BEGIN;
--   DROP VIEW IF EXISTS v_requirement_review;
--   CREATE VIEW v_requirement_review AS
--     SELECT r.company_id, r.tender_id, t.name AS tender_name, t.close_at,
--            r.method, r.status, r.n_requirements, r.min_confidence,
--            r.error, r.extracted_at
--     FROM tender_requirement_run r JOIN tender t ON t.id = r.tender_id
--     WHERE r.status IN ('needs_review','failed');
--   ALTER TABLE tender_requirement
--     DROP COLUMN review_status, DROP COLUMN reviewed_by,
--     DROP COLUMN reviewed_at, DROP COLUMN corrected_value,
--     DROP COLUMN review_note;
--   COMMIT;
--
-- DIQQAT: inson qilgan BARCHA tasdiqlash va tuzatishlar yo'qoladi.
-- Ular J6 uchun "oltin" yozuvlar — avval zaxira oling.
-- =====================================================================
