-- =====================================================================
-- schema_patch_routing.sql
-- BROKERGA YO'NALTIRISH — "bu tender kimga tegishli va u nima qildi?"
--
-- Idempotent: qayta yurgizish xavfsiz.
--
-- Qo'llash:
--   psql -d xtxarid -f schema_patch_routing.sql
--
-- NEGA TENDER-AI TOMONDA, ERP DA EMAS
-- ═══════════════════════════════════
-- Chegara SIMMETRIK va u SINOV BILAN QULFLANGAN (_tests/auth_test.py):
--
--     ERP        `public.*` dan O'QIYDI, YOZMAYDI.
--     Tender-AI  `erp.v_tender_status` dan O'QIYDI, YOZMAYDI.
--
-- Yo'naltirishni ERP ga yozish bilan qilish bu shartnomani buzardi va
-- ikkala loyihaning sinovini yiqitardi. Shuning uchun navbat SHU
-- TOMONDA turadi: tender-ai "kimga tavsiya qilaman" deydi, ERP esa
-- o'zi bilganini qiladi. Ikkisi `erp.v_tender_status` orqali
-- solishtiriladi — u yerda `opportunity` paydo bo'lsa, broker ishni
-- ERP da boshlagan bo'ladi.
--
-- QARORNING IKKI MANBASI BOR VA ULAR ARALASHMAYDI
-- ═══════════════════════════════════════════════
-- `ai_qaror`    — mashina tavsiyasi (malaka tekshiruvi / GoNoGo)
-- `inson_qaror` — brokerning O'Z qarori
--
-- Ular ALOHIDA ustun. Bitta "status" ga qo'shib yuborilsa, keyin
-- "model necha foizda haq edi" degan savolga javob bo'lmasdi — aynan
-- `blind_value` bilan bir xil sabab (§16.56).
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. Yo'naltirish yozuvi
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tender_routing (
    id           BIGSERIAL PRIMARY KEY,
    company_id   INT    NOT NULL REFERENCES company_account(id) ON DELETE CASCADE,
    tender_id    BIGINT NOT NULL REFERENCES tender(id) ON DELETE CASCADE,

    -- --- MASHINA TOMONI ---
    -- 'go' | 'review' | 'no_go' — `ai_gonogo.DECISIONS` bilan bir xil
    -- so'zlar, chunki manba o'sha yerdan ham kelishi mumkin.
    ai_qaror     TEXT CHECK (ai_qaror IN ('go', 'review', 'no_go')),
    ai_ball      NUMERIC(4,3) CHECK (ai_ball IS NULL
                                     OR (ai_ball >= 0 AND ai_ball <= 1)),
    -- Qaror QAYSI usuldan keldi: 'malaka' (bepul join) yoki 'gonogo' (LLM).
    -- Aralashtirilmasin: ularning ishonchliligi boshqa-boshqa.
    ai_manba     TEXT CHECK (ai_manba IN ('malaka', 'gonogo')),
    ai_sabab     TEXT,

    -- --- INSON TOMONI ---
    -- Broker o'z qarorini AI dan MUSTAQIL yozadi. NULL = hali ko'rmagan.
    inson_qaror  TEXT CHECK (inson_qaror IN ('olindi', 'rad', 'kutilsin')),
    inson_izoh   TEXT,
    broker_nomi  TEXT,
    qaror_vaqti  TIMESTAMPTZ,

    -- --- OQIM ---
    -- 'yangi'      — navbatga tushdi, hali hech kim ko'rmagan
    -- 'korilmoqda' — broker ochdi
    -- 'yopildi'    — inson qaror berdi
    holat        TEXT NOT NULL DEFAULT 'yangi'
                 CHECK (holat IN ('yangi', 'korilmoqda', 'yopildi')),

    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Bir tender bir kompaniyada BIR MARTA navbatda turadi.
    UNIQUE (company_id, tender_id)
);

COMMENT ON TABLE tender_routing IS
    'Brokerga yo`naltirish navbati. Tender-AI TOMONIDA — `erp.*` ga '
    'yozilmaydi, chegara sinov bilan qulflangan.';

COMMENT ON COLUMN tender_routing.inson_qaror IS
    'Broker QARORI, AI dan MUSTAQIL. Alohida ustun: aks holda "model '
    'necha foizda haq edi" degan savolga javob qolmasdi.';

-- Navbat so'rovi: ochiq tenderlar, muddat bo'yicha.
CREATE INDEX IF NOT EXISTS tender_routing_navbat_idx
    ON tender_routing (company_id, holat, created_at DESC);

-- ---------------------------------------------------------------------
-- 2. `updated_at` O'ZI yangilansin
--
--    Qo'lda yozilsa bir joyda unutiladi — bu loyihada "qadam yozilgan,
--    chaqirilmaydi" sinfi allaqachon uch marta uchragan.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION tender_routing_touch() RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tender_routing_touch_trg ON tender_routing;
CREATE TRIGGER tender_routing_touch_trg
    BEFORE UPDATE ON tender_routing
    FOR EACH ROW EXECUTE FUNCTION tender_routing_touch();

-- ---------------------------------------------------------------------
-- 3. NAVBAT ko'rinishi — brokerga nima ko'rsatiladi
--
--    FAQAT OCHIQ tenderlar: muddati o'tganga taklif berib bo'lmaydi,
--    ya'ni ular navbatni bekorga uzaytiradi.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_routing_queue AS
SELECT r.id, r.company_id, r.tender_id,
       t.name AS tender_name, t.close_at, t.totalcost, t.currency,
       r.ai_qaror, r.ai_ball, r.ai_manba, r.ai_sabab,
       r.inson_qaror, r.broker_nomi, r.holat, r.created_at,
       EXTRACT(EPOCH FROM (t.close_at - now())) / 86400.0 AS kun_qoldi,
       -- ERP da ish boshlanganmi. View bo'lmasa NULL — bu XATO EMAS.
       EXISTS (SELECT 1 FROM information_schema.views v
                WHERE v.table_schema = 'erp'
                  AND v.table_name = 'v_tender_status')  AS erp_bor
FROM tender_routing r
JOIN tender t ON t.id = r.tender_id
WHERE t.close_at IS NULL OR t.close_at > now()
ORDER BY t.close_at NULLS LAST;

COMMENT ON VIEW v_routing_queue IS
    'Brokerga ko`rsatiladigan navbat — FAQAT ochiq tenderlar.';

-- ---------------------------------------------------------------------
-- 4. KELISHMOVCHILIK — model necha foizda haq edi
--
--    Faqat inson qaror bergan qatorlar. `v_review_disagreement` bilan
--    bir xil mantiq: mashina va inson ALOHIDA yozilgani uchun
--    solishtirish mumkin.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_routing_agreement AS
SELECT company_id,
       ai_manba,
       ai_qaror,
       count(*)                                              AS jami,
       count(*) FILTER (WHERE inson_qaror = 'olindi')        AS olindi,
       count(*) FILTER (WHERE inson_qaror = 'rad')           AS rad,
       -- MOSLIK: AI 'go' deganda inson 'olindi' desa — to'g'ri.
       round(100.0 * count(*) FILTER (
             WHERE (ai_qaror = 'go'    AND inson_qaror = 'olindi')
                OR (ai_qaror = 'no_go' AND inson_qaror = 'rad'))
             / NULLIF(count(*), 0), 1)                       AS moslik_foiz
FROM tender_routing
WHERE inson_qaror IS NOT NULL AND ai_qaror IS NOT NULL
GROUP BY company_id, ai_manba, ai_qaror;

COMMENT ON VIEW v_routing_agreement IS
    'AI tavsiyasi bilan broker qarori necha foizda mos keldi. '
    'USUL bo`yicha ajratilgan: bepul `malaka` va pullik `gonogo` ning '
    'ishonchliligi bir xil emas.';

-- ---------------------------------------------------------------------
-- 5. TEKSHIRUV
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF to_regclass('public.tender_routing') IS NULL THEN
        RAISE EXCEPTION 'tender_routing yaratilmadi';
    END IF;
    IF to_regclass('public.v_routing_queue') IS NULL THEN
        RAISE EXCEPTION 'v_routing_queue yaratilmadi';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                   WHERE tgname = 'tender_routing_touch_trg') THEN
        RAISE EXCEPTION 'updated_at triggeri yaratilmadi';
    END IF;
    RAISE NOTICE 'schema_patch_routing.sql: tekshiruv o`tdi';
END $$;

COMMIT;

-- =====================================================================
-- ROLLBACK (qo'lda):
--
--   BEGIN;
--   DROP VIEW  IF EXISTS v_routing_agreement;
--   DROP VIEW  IF EXISTS v_routing_queue;
--   DROP TABLE IF EXISTS tender_routing;
--   DROP FUNCTION IF EXISTS tender_routing_touch();
--   COMMIT;
--
-- DIQQAT: `inson_qaror` — brokerning MUSTAQIL qarori, ya'ni eng qimmat
-- ma'lumot. Uni qayta olish uchun brokerlar hamma tenderni QAYTADAN
-- ko'rib chiqishi kerak.
-- =====================================================================
