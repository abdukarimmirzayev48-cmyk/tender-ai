-- =====================================================================
-- schema_patch_requirement.sql
-- J3 — Hujjatdan TALAB ajratish (`tender_requirement`)
--
-- Bog'liqlik: schema_patch_auth_2.sql  (company_account — FK)
--             schema_patch_multitenant.sql (company_id konvensiyasi)
--             schema_patch_ai_chat.sql (doc_chunk — iqtibos ko'rsatkichi)
-- Idempotent: qayta yurgizish xavfsiz.
--
-- Qo'llash:
--   psql -d xtxarid -f schema_patch_requirement.sql
--
-- Orqaga qaytarish: fayl oxiridagi ROLLBACK bo'limiga qarang.
--
-- Reja: reja_ai_chat.md §16.1 (J3 qarorlari)  ·  REJA.md D bosqichi
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. TALABLAR
--
--    NEGA ALOHIDA JADVAL (qaror 3.1): talablar katalogga JOIN qilinadi
--    va filtrlanadi ("GOST X talab qiladigan tenderlar"). `ai_analysis`
--    JSONB ichida bo'lsa, 2900 tender bo'ylab bunday so'rov samarali
--    ishlamaydi va har talabga alohida `confidence` yozib bo'lmaydi.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tender_requirement (
    id              BIGSERIAL PRIMARY KEY,

    -- KO'P IJARACHILIK: qamrov kompaniyaga bog'liq (qaysi tenderlar
    -- ajratilgani katalogga qarab farq qiladi), shuning uchun talab ham
    -- kompaniyaniki. J1 saboqi: `company_id` DARHOL NOT NULL, DEFAULT
    -- YO'Q — vaqtinchalik DEFAULT bir marta noto'g'ri kompaniyaga
    -- yozilishiga olib kelgan edi.
    company_id      INT NOT NULL REFERENCES company_account(id) ON DELETE CASCADE,
    tender_id       BIGINT NOT NULL REFERENCES tender(id) ON DELETE CASCADE,
    lot_id          BIGINT,

    -- 'api'      — reyestrdan kelgan pozitsiya (tender_good)
    -- 'document' — hujjat matnidan model ajratgan
    source          TEXT NOT NULL CHECK (source IN ('api', 'document')),

    position_no     INT,
    name            TEXT NOT NULL,
    attrs           JSONB NOT NULL DEFAULT '{}'::jsonb,

    qty             NUMERIC,
    unit            TEXT,
    delivery_days   INT,

    -- GOST, sertifikat, litsenziya kabi MAJBURIY shart. Ixtiyoriy
    -- afzallikdan (`nice to have`) ajratish uchun.
    is_mandatory    BOOLEAN NOT NULL DEFAULT FALSE,

    -- 0..1. Qaror 3.5: past ishonch TASHLAB YUBORILMAYDI, `needs_review`
    -- bo'ladi. "Bo'sh natija" va "past ishonch" — boshqa-boshqa holat.
    confidence      NUMERIC(3,2) NOT NULL DEFAULT 1.00
                    CHECK (confidence >= 0 AND confidence <= 1),

    -- SHAFFOFLIK: model nimaga tayanganini foydalanuvchi ko'rsin.
    raw_snippet     TEXT,

    -- IQTIBOS KO'RSATKICHI (qaror 3.2).
    --
    -- NEGA `doc_chunk.id` GA FK EMAS: `etl_embed.py --chunks` bo'laklarni
    -- DELETE + INSERT bilan qayta yozadi (idempotentlik uchun). FK bo'lsa
    -- har qayta bo'laklashda talablar CASCADE bilan O'CHIB KETARDI.
    -- `file_ref` + `char_start` esa bo'lak chegarasidan MUSTAQIL —
    -- §16.32 dagi bir xil saboq: matn o'rni barqaror, bo'lak id si emas.
    file_ref        TEXT,
    char_start      INT,
    char_end        INT,

    model           TEXT,
    extracted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- TAKRORLANISHGA QARSHI. `ON CONFLICT` shu maqsadga tayanadi.
    -- J1 saboqi: PK/UNIQUE o'zgarganda `ON CONFLICT` maqsadi ham
    -- o'zgarishi kerak — beshta joyda jimgina buzilgan edi.
    CONSTRAINT tender_requirement_uq
        UNIQUE (company_id, tender_id, source, position_no, name)
);

-- Kompaniya bo'yicha qamrov — eng ko'p ishlatiladigan filtr.
CREATE INDEX IF NOT EXISTS tender_requirement_company_idx
    ON tender_requirement (company_id, tender_id);

-- "Qaysi tenderlar GOST talab qiladi" — JSONB bo'yicha qidiruv.
CREATE INDEX IF NOT EXISTS tender_requirement_attrs_idx
    ON tender_requirement USING gin (attrs);

-- Ko'rib chiqish navbati: past ishonchli talablar birinchi.
CREATE INDEX IF NOT EXISTS tender_requirement_review_idx
    ON tender_requirement (company_id, confidence)
    WHERE confidence < 0.60;

-- Majburiy talablar bo'yicha filtr (cheklist va Go/No-Go uchun).
CREATE INDEX IF NOT EXISTS tender_requirement_mandatory_idx
    ON tender_requirement (company_id, tender_id)
    WHERE is_mandatory;

COMMENT ON TABLE tender_requirement IS
    'J3: tender talablari — API pozitsiyalari va hujjatdan ajratilgani. '
    'Iqtibos file_ref+char_start bilan (doc_chunk ga FK ATAYLAB YO`Q).';
COMMENT ON COLUMN tender_requirement.confidence IS
    '0..1. <0.60 -> tender_requirement_run.status=needs_review; '
    'TASHLAB YUBORILMAYDI (qaror 3.5).';

-- ---------------------------------------------------------------------
-- 2. AJRATISH YURISHI — nima bo'lganini YOZIB QO'YAMIZ
--
--    NEGA KERAK: faqat `tender_requirement` ga tayansak, "talab
--    topilmadi" va "hali ajratilmagan" holatlari BIR XIL ko'rinadi
--    (ikkalasida ham qator yo'q). Natijada:
--      - har yurishda o'sha tender qayta-qayta modelga yuboriladi (PUL);
--      - xato sababi hech qayerda qolmaydi.
--
--    Aynan shu naqsh `tender_document_text` da ishlagan: har hujjat
--    uchun `status` + `error` yozilgani nosozlikni ko'rinadigan qildi.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tender_requirement_run (
    company_id      INT NOT NULL REFERENCES company_account(id) ON DELETE CASCADE,
    tender_id       BIGINT NOT NULL REFERENCES tender(id) ON DELETE CASCADE,

    -- ok            — ajratildi (talab bo'lmasligi ham mumkin)
    -- needs_review  — ajratildi, lekin ishonch past (qaror 3.5)
    -- no_text       — hujjat matni yo'q (skan / OCR kerak)
    -- failed        — model yoki parse xatosi
    -- skipped       — qamrovga tushmadi (yopilgan tender va h.k.)
    status          TEXT NOT NULL CHECK (status IN
                        ('ok', 'needs_review', 'no_text', 'failed', 'skipped')),

    n_requirements  INT NOT NULL DEFAULT 0,
    min_confidence  NUMERIC(3,2),

    -- Manba matnining hashi. O'zgarmagan bo'lsa QAYTA AJRATILMAYDI —
    -- Opus 5 chaqiruvi qimmat (qaror 3.4).
    content_hash    TEXT,

    model           TEXT,
    input_tokens    INT,
    output_tokens   INT,
    cost_usd        NUMERIC(10,4),
    error           TEXT,
    extracted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (company_id, tender_id)
);

CREATE INDEX IF NOT EXISTS tender_requirement_run_status_idx
    ON tender_requirement_run (status, extracted_at DESC);

COMMENT ON TABLE tender_requirement_run IS
    'J3: har (kompaniya, tender) uchun ajratish natijasi. "Topilmadi" va '
    '"hali ajratilmagan" ni AJRATADI — aks holda qayta-qayta pul sarflanadi.';

-- ---------------------------------------------------------------------
-- 3. KO'RINISH: ko'rib chiqish navbati
--
--    Interfeys uchun: past ishonchli yoki xato bo'lgan tenderlar.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_requirement_review AS
SELECT r.company_id,
       r.tender_id,
       t.name           AS tender_name,
       t.close_at,
       r.status,
       r.n_requirements,
       r.min_confidence,
       r.error,
       r.extracted_at
FROM tender_requirement_run r
JOIN tender t ON t.id = r.tender_id
WHERE r.status IN ('needs_review', 'failed')
ORDER BY t.close_at NULLS LAST, r.min_confidence NULLS FIRST;

COMMENT ON VIEW v_requirement_review IS
    'J3: inson ko`rib chiqishi kerak bo`lgan tenderlar (past ishonch yoki xato).';

-- ---------------------------------------------------------------------
-- 4. TEKSHIRUV — patch haqiqatan qo'llandimi
--
--    COMMIT dan OLDIN. J1 saboqi: "qo'llandi" degan taxminga tayanmaymiz,
--    tekshiramiz. Xato bo'lsa BUTUN patch qaytadi.
-- ---------------------------------------------------------------------
DO $$
DECLARE
    n_col INT;
BEGIN
    IF to_regclass('public.tender_requirement') IS NULL THEN
        RAISE EXCEPTION 'tender_requirement yaratilmadi';
    END IF;
    IF to_regclass('public.tender_requirement_run') IS NULL THEN
        RAISE EXCEPTION 'tender_requirement_run yaratilmadi';
    END IF;

    -- `company_id` NOT NULL bo'lishi SHART (J1 qoidasi)
    SELECT count(*) INTO n_col
    FROM information_schema.columns
    WHERE table_name = 'tender_requirement'
      AND column_name = 'company_id'
      AND is_nullable = 'NO';
    IF n_col <> 1 THEN
        RAISE EXCEPTION 'tender_requirement.company_id NOT NULL emas';
    END IF;

    -- `doc_chunk` ga FK BO'LMASLIGI shart (qayta bo'laklash talablarni
    -- o'chirib yuborardi)
    SELECT count(*) INTO n_col
    FROM information_schema.table_constraints tc
    JOIN information_schema.constraint_column_usage ccu
      ON ccu.constraint_name = tc.constraint_name
    WHERE tc.table_name = 'tender_requirement'
      AND tc.constraint_type = 'FOREIGN KEY'
      AND ccu.table_name = 'doc_chunk';
    IF n_col <> 0 THEN
        RAISE EXCEPTION 'tender_requirement doc_chunk ga FK bilan bog`langan '
                        '— qayta bo`laklashda talablar o`chib ketadi';
    END IF;

    RAISE NOTICE 'schema_patch_requirement.sql: tekshiruv o`tdi';
END $$;

COMMIT;

-- =====================================================================
-- ROLLBACK (qo'lda):
--
--   BEGIN;
--   DROP VIEW  IF EXISTS v_requirement_review;
--   DROP TABLE IF EXISTS tender_requirement_run;
--   DROP TABLE IF EXISTS tender_requirement;
--   COMMIT;
--
-- DIQQAT: `tender_requirement` da ajratilgan talablar YO'QOLADI va
-- qayta ajratish PUL sarflaydi (Opus 5). Avval zaxira oling:
--   pg_dump -d xtxarid -t tender_requirement -t tender_requirement_run \
--           -f requirement_backup.sql
-- =====================================================================
