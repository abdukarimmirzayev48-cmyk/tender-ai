-- =====================================================================
-- schema_patch_requirement_4.sql
-- J3 — talab QAYSI HUJJAT TURIGA tegishli (compliance moslashtiruvi)
--
-- Bog'liqlik: schema_patch_requirement_3.sql
-- Idempotent: qayta yurgizish xavfsiz.
--
-- Qo'llash:
--   psql -d xtxarid -f schema_patch_requirement_4.sql
--
-- NEGA AYNAN TASDIQLASH BILAN BIRGA
-- ═════════════════════════════════
-- `compliance` moslashtiruvi ("ISO 14001 talab etiladi" ->
-- `company_document.doc_type = 'iso_14001'`) NOANIQ vazifa, ya'ni
-- o'z evalini talab qiladi. O'sha evalning haqiqiy manbai — INSON
-- YORLIQLAGAN to'plam.
--
-- Agar tasdiqlash navbatini oddiy yurgizsak, keyin compliance uchun
-- O'SHA TALABLARNI QAYTADAN ko'rib chiqish kerak bo'lardi — inson
-- vaqti IKKI MARTA sarflanadi.
--
-- Shuning uchun tasdiqlash oynasida bitta maydon: hujjat turi.
-- Bir pass — ikki natija: J6 oltin to'plami va moslashtiruv ground
-- truth i.
--
-- QIYMATLAR: `api/compliance.DOC_TYPES` dagi `code` lar, yoki
--   'yoq'    — bu talab hech qaysi hujjat turiga tegishli emas
--              (masalan "kafolat muddati 12 oy");
--   'boshqa' — hujjat kerak, lekin lug'atda mos turi yo'q.
--
-- 'yoq' va 'boshqa' NULL DAN FARQ QILADI: NULL = "hali so'ralmagan",
-- 'yoq' = "inson qaradi va tegishli emas dedi". Bu farq §16.44 dagi
-- "topilmadi va ajratilmagan" bilan bir xil sinf.
-- =====================================================================

BEGIN;

ALTER TABLE tender_requirement
    ADD COLUMN IF NOT EXISTS doc_type TEXT;

COMMENT ON COLUMN tender_requirement.doc_type IS
    'Talab QAYSI hujjat turini so`raydi (compliance.DOC_TYPES code), '
    'yoki ''yoq'' (tegishli emas) / ''boshqa'' (lug`atda yo`q). '
    'NULL = hali so`ralmagan — ''yoq'' dan FARQ QILADI.';

-- Moslashtiruv statistikasi uchun: "qaysi turlar qanchalik tez-tez".
CREATE INDEX IF NOT EXISTS tender_requirement_doctype_idx
    ON tender_requirement (company_id, doc_type)
    WHERE doc_type IS NOT NULL;

-- ---------------------------------------------------------------------
-- YORLIQLANGAN TO'PLAM ko'rinishi — moslashtiruv uchun ground truth
--
-- Faqat INSON KO'RGAN qatorlar: `pending` da yorliq ishonchsiz.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_requirement_labeled AS
SELECT r.company_id,
       r.tender_id,
       r.id            AS requirement_id,
       r.name,
       r.attrs->>'qiymat'                       AS qiymat,
       COALESCE(r.corrected_value, r.attrs->>'qiymat') AS amaldagi_qiymat,
       r.attrs->>'tur' AS tur,
       r.method,
       r.confidence,
       r.is_mandatory,
       r.doc_type,
       r.review_status,
       r.reviewed_at
FROM tender_requirement r
WHERE r.review_status IN ('approved', 'corrected', 'rejected')
  AND r.doc_type IS NOT NULL;

COMMENT ON VIEW v_requirement_labeled IS
    'J3: inson yorliqlagan to`plam. compliance moslashtiruvining '
    'ground truth i va J6 uchun oltin yozuvlar.';

-- ---------------------------------------------------------------------
-- TEKSHIRUV
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'tender_requirement'
                     AND column_name = 'doc_type') THEN
        RAISE EXCEPTION 'doc_type ustuni yaratilmadi';
    END IF;
    IF to_regclass('public.v_requirement_labeled') IS NULL THEN
        RAISE EXCEPTION 'v_requirement_labeled yaratilmadi';
    END IF;
    RAISE NOTICE 'schema_patch_requirement_4.sql: tekshiruv o`tdi';
END $$;

COMMIT;

-- =====================================================================
-- ROLLBACK (qo'lda):
--
--   BEGIN;
--   DROP VIEW IF EXISTS v_requirement_labeled;
--   ALTER TABLE tender_requirement DROP COLUMN doc_type;
--   COMMIT;
--
-- DIQQAT: inson qo'ygan BARCHA yorliqlar yo'qoladi. Ular
-- moslashtiruv evalining yagona manbai — avval zaxira oling.
-- =====================================================================
