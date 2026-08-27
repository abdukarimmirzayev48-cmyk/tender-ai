-- =====================================================================
-- schema_patch_requirement_6.sql
-- J3 — YOPIQ (ko'r-ko'rona) ko'rib chiqish va PILOT to'plami
--
-- Bog'liqlik: schema_patch_requirement_5.sql
-- Idempotent: qayta yurgizish xavfsiz.
--
-- Qo'llash:
--   psql -d xtxarid -f schema_patch_requirement_6.sql
--
-- ANCHORING — pilotning eng jiddiy xavfi
-- ══════════════════════════════════════
-- Interfeys talabni MODEL JAVOBI BILAN BIRGA ko'rsatadi:
-- `kafolat = 12 oy, c=0.96, yashil`. Inson buni ko'rib, keyin manbaga
-- sakraydi. Ya'ni u TEKSHIRMAYDI — TASDIQLAYDI.
--
-- Amalda: yashil qatorda ko'z hujjatdan "12 oy" ni izlaydi va topadi.
-- Agar hujjatda "12 oy (ehtiyot qismlar)" va "24 oy (asosiy uzellar)"
-- bo'lsa — birinchisini topib tasdiqlab ketadi. MODEL XATOSI GROUND
-- TRUTH GA AYLANADI.
--
-- Yumshatish: birinchi 10 tenderda ishonch va qiymat YASHIRILADI.
-- Inson avval hujjatdan O'ZI o'qib yozadi (`blind_value`), keyingina
-- model javobi ochiladi va solishtiriladi.
--
-- Bu ikki narsa beradi:
--   1. haqiqiy ground truth;
--   2. MODELNING KELISHMOVCHILIK DARAJASI — "necha foizda model xato
--      qilgan" degan raqam. Oddiy oqimda bu raqam CHIQMAYDI, chunki
--      inson modelni tasdiqlashga moyil.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. Insonning MUSTAQIL javobi
-- ---------------------------------------------------------------------
ALTER TABLE tender_requirement
    ADD COLUMN IF NOT EXISTS blind_value TEXT;

COMMENT ON COLUMN tender_requirement.blind_value IS
    'YOPIQ rejimda inson model javobini KO`RMASDAN yozgan qiymat. '
    'Kelishmovchilik darajasi shundan hisoblanadi. NULL = yopiq '
    'rejimda ko`rilmagan.';

-- ---------------------------------------------------------------------
-- 2. PILOT to'plami — NAMUNA TANLASH qiyshiq bo'lmasin
--
--    Navbat MUDDAT bo'yicha saralangan. Ish jarayoni uchun to'g'ri,
--    NAMUNA uchun YOMON: tez yopiladigan tenderlar ma'lum turdagi
--    bo'lishi mumkin (shoshilinch xaridlar, kichik summalar, bir xil
--    buyurtmachilar). Shunda "6 talab har tenderga" degan o'rtacha
--    ham qiyshiq chiqadi.
--
--    Aralashtiramiz: muddati yaqin + tasodifiy + katta summali.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS review_pilot (
    company_id  INT NOT NULL REFERENCES company_account(id) ON DELETE CASCADE,
    tender_id   BIGINT NOT NULL REFERENCES tender(id) ON DELETE CASCADE,

    -- Qanday tanlangani — natijani guruhlab tahlil qilish uchun.
    guruh       TEXT NOT NULL CHECK (guruh IN ('muddat', 'tasodif', 'summa')),

    -- 'blind'    — model javobi YASHIRIN (birinchi 10 ta)
    -- 'anchored' — oddiy oqim (qolgani; TEZLIK shundan o'lchanadi,
    --              chunki u HAQIQIY ish sharoitini aks ettiradi)
    rejim       TEXT NOT NULL CHECK (rejim IN ('blind', 'anchored')),

    tartib      INT NOT NULL,          -- ko'rib chiqish tartibi
    added_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (company_id, tender_id)
);

COMMENT ON TABLE review_pilot IS
    'J3 pilot: 30 ta tender. Birinchi 10 tasi YOPIQ rejimda '
    '(anchoring ga qarshi), qolgani oddiy oqimda (tezlik o`lchovi).';

-- TARTIB NOYOB bo'lishi SHART. Bir marta buzilgan: `pilot_yarat`
-- ertasi kuni qayta chaqirilganda navbat o'zgargani uchun BOSHQA
-- tanlov qildi, `ON CONFLICT (company_id, tender_id) DO NOTHING`
-- esa faqat tenderni tutdi — tartib raqamlari esa TAKRORLANDI
-- (30 -> 50 qator, 10 ta tartib uch martadan). Natijada yopiq
-- rejim ulushi 10 dan 16 ga suzib ketdi.
--
-- Endi to'plam bir marta muzlaydi (`pilot_yarat` mavjud pilotni
-- qaytaradi), va bu cheklov o'sha qoidani MA'LUMOTLAR BAZASIDA
-- ushlab turadi — kod xatosi jimgina o'tib ketmasin.
CREATE UNIQUE INDEX IF NOT EXISTS review_pilot_tartib_idx
    ON review_pilot (company_id, tartib);

-- ---------------------------------------------------------------------
-- 3. Vaqt o'lchoviga REJIM yorlig'i
--
--    Hozirgi mediana ANCHORING BILAN ishlash vaqtini o'lchaydi. Yopiq
--    ko'rib chiqish sezilarli SEKINROQ. Yorliqsiz saqlansa, olti
--    oydan keyin taqqoslab bo'lmaydi.
-- ---------------------------------------------------------------------
ALTER TABLE requirement_review_open
    ADD COLUMN IF NOT EXISTS rejim TEXT;

UPDATE requirement_review_open SET rejim = 'anchored' WHERE rejim IS NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'requirement_review_open_rejim_chk') THEN
        ALTER TABLE requirement_review_open
            ADD CONSTRAINT requirement_review_open_rejim_chk
            CHECK (rejim IN ('blind', 'anchored'));
    END IF;
END $$;

COMMENT ON COLUMN requirement_review_open.rejim IS
    'O`lchov QAYSI SHAROITDA olingani. `blind` sezilarli sekinroq — '
    'yorliqsiz taqqoslash xato bo`lardi.';

DROP VIEW IF EXISTS v_review_speed;
CREATE VIEW v_review_speed AS
SELECT o.company_id,
       o.tender_id,
       t.name                              AS tender_name,
       o.rejim,
       o.opened_at,
       o.finished_at,
       o.n_reviewed,
       EXTRACT(EPOCH FROM (o.finished_at - o.opened_at))      AS sekund,
       CASE WHEN o.n_reviewed > 0
            THEN EXTRACT(EPOCH FROM (o.finished_at - o.opened_at))
                 / o.n_reviewed END                            AS sekund_talabga
FROM requirement_review_open o
JOIN tender t ON t.id = o.tender_id
WHERE o.finished_at IS NOT NULL
ORDER BY o.finished_at DESC;

-- ---------------------------------------------------------------------
-- 4. KELISHMOVCHILIK — eng qimmatli raqam
--
--    `c >= 0.85` da kelishmovchilik PAST bo'lsa, avto-tasdiqlash
--    asosli. YUQORI bo'lsa — `ishonchli()` chegarasi noto'g'ri va
--    `compliance` uni ishlatolmaydi.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_review_disagreement AS
SELECT r.company_id,
       CASE WHEN r.confidence >= 0.85 THEN 'yuqori (>=0.85)'
            WHEN r.confidence >= 0.60 THEN 'orta (0.60-0.85)'
            ELSE 'past (<0.60)' END                     AS ishonch_darajasi,
       count(*)                                          AS jami,
       count(*) FILTER (WHERE r.review_status = 'rejected')       AS rad_etilgan,
       count(*) FILTER (WHERE r.review_status = 'corrected')      AS tuzatilgan,
       count(*) FILTER (WHERE r.review_status = 'approved')       AS tasdiqlangan,
       -- KELISHMOVCHILIK = rad etilgan + tuzatilgan.
       -- Ikkalasi ham "model javobi noto'g'ri edi" degani.
       round(100.0 * count(*) FILTER (
             WHERE r.review_status IN ('rejected', 'corrected'))
             / NULLIF(count(*), 0), 1)                   AS kelishmovchilik_foiz
FROM tender_requirement r
JOIN review_pilot p ON p.tender_id = r.tender_id AND p.company_id = r.company_id
WHERE p.rejim = 'blind'            -- FAQAT yopiq rejim ishonchli
  AND r.review_status <> 'pending'
GROUP BY r.company_id, 2
ORDER BY 2 DESC;

COMMENT ON VIEW v_review_disagreement IS
    'J3: model necha foizda xato qilgan, ISHONCH DARAJASI bo`yicha. '
    'FAQAT yopiq rejim — oddiy oqimda inson modelni tasdiqlashga moyil.';

-- ---------------------------------------------------------------------
-- 5. TEKSHIRUV
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF to_regclass('public.review_pilot') IS NULL THEN
        RAISE EXCEPTION 'review_pilot yaratilmadi';
    END IF;
    IF to_regclass('public.v_review_disagreement') IS NULL THEN
        RAISE EXCEPTION 'v_review_disagreement yaratilmadi';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'requirement_review_open'
                     AND column_name = 'rejim') THEN
        RAISE EXCEPTION 'rejim ustuni yaratilmadi';
    END IF;
    RAISE NOTICE 'schema_patch_requirement_6.sql: tekshiruv o`tdi';
END $$;

COMMIT;

-- =====================================================================
-- ROLLBACK (qo'lda):
--
--   BEGIN;
--   DROP VIEW  IF EXISTS v_review_disagreement;
--   DROP TABLE IF EXISTS review_pilot;
--   ALTER TABLE requirement_review_open DROP COLUMN rejim;
--   ALTER TABLE tender_requirement DROP COLUMN blind_value;
--   COMMIT;
--
-- DIQQAT: `blind_value` — insonning MUSTAQIL javobi, ya'ni eng qimmat
-- ma'lumot. Uni qayta olish uchun pilotni BOSHIDAN yurgizish kerak.
-- =====================================================================
