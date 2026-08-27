-- =====================================================================
-- schema_patch_routing_2.sql
-- `ai_ozgardi` — INSON QARORI ESKIRGANINI aytadigan bayroq
--
-- Bog'liqlik: schema_patch_routing.sql
-- Idempotent: qayta yurgizish xavfsiz.
--
-- Qo'llash:
--   psql -d xtxarid -f schema_patch_routing_2.sql
--
-- NEGA BU PATCH BOR — IZOH MAVJUD BO'LMAGAN HIMOYANI VA'DA QILGAN
-- ══════════════════════════════════════════════════════════════
-- `api/routing.py` ning modul izohida shunday yozilgan edi:
--
--     "Talab o'zgarganda `ai_qaror` yangilanadi, inson qarori esa
--      turaveradi va `ai_ozgardi` bayrog'i qo'yiladi — broker o'zi
--      qayta ko'radi."
--
-- Bunday ustun YO'Q EDI. `grep ai_ozgardi` bitta natija berdi — o'sha
-- izohning O'ZI. Ya'ni izoh himoyani TASVIRLARDI, lekin himoya
-- yo'q edi.
--
-- Bu §16.58 dagi saboqning teskari shakli. U yerda izoh xatoni
-- tasvirlab turgan va kod uning ustiga qo'yilgan edi. Bu yerda izoh
-- YECHIMNI tasvirlaydi va yechim yozilmagan. Ikkalasida ham izohga
-- ishonilgan.
--
-- HAQIQIY XAVF: broker "olindi" deb qaror beradi. Ertasiga hujjat
-- qayta ajratiladi, yangi sertifikat talabi topiladi, `ai_qaror`
-- `go` dan `no_go` ga o'tadi — va broker BUNDAN XABAR TOPMAYDI.
-- Uning qarori eskirgan tahlilga asoslangan bo'lib qolaveradi.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. Bayroq
-- ---------------------------------------------------------------------
ALTER TABLE tender_routing
    ADD COLUMN IF NOT EXISTS ai_ozgardi BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN tender_routing.ai_ozgardi IS
    'Inson qaror bergandan KEYIN `ai_qaror` o`zgardi. Broker qarorini '
    'qayta ko`rishi kerak. Yangi qaror berilganda tozalanadi.';

-- Eski qaror QANDAY edi — broker "nima o'zgardi" degan savolga javob
-- olsin. Busiz bayroq "nimadir o'zgardi" deb qo'rqitardi, xolos.
ALTER TABLE tender_routing
    ADD COLUMN IF NOT EXISTS ai_qaror_eski TEXT;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'tender_routing_ai_qaror_eski_chk') THEN
        ALTER TABLE tender_routing
            ADD CONSTRAINT tender_routing_ai_qaror_eski_chk
            CHECK (ai_qaror_eski IS NULL
                   OR ai_qaror_eski IN ('go', 'review', 'no_go'));
    END IF;
END $$;

-- QOIDA BAZADA: bayroq yoqilgan bo'lsa eski qaror ham yozilgan
-- bo'lsin. Izoh emas, CHEKLOV.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'tender_routing_ozgardi_chk') THEN
        ALTER TABLE tender_routing
            ADD CONSTRAINT tender_routing_ozgardi_chk
            CHECK (NOT ai_ozgardi OR ai_qaror_eski IS NOT NULL);
    END IF;
END $$;

-- ---------------------------------------------------------------------
-- 2. Navbat ko'rinishiga qo'shamiz
--
--    ESKIRGAN QAROR NAVBATGA QAYTADI. Aks holda `holat = 'yopildi'`
--    bo'lgani uchun broker uni boshqa ko'rmasdi va bayroq foydasiz
--    bo'lardi.
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_routing_queue;
CREATE VIEW v_routing_queue AS
SELECT r.id, r.company_id, r.tender_id,
       t.name AS tender_name, t.close_at, t.totalcost, t.currency,
       r.ai_qaror, r.ai_ball, r.ai_manba, r.ai_sabab,
       r.ai_ozgardi, r.ai_qaror_eski,
       r.inson_qaror, r.broker_nomi, r.holat, r.created_at,
       EXTRACT(EPOCH FROM (t.close_at - now())) / 86400.0 AS kun_qoldi,
       EXISTS (SELECT 1 FROM information_schema.views v
                WHERE v.table_schema = 'erp'
                  AND v.table_name = 'v_tender_status')  AS erp_bor
FROM tender_routing r
JOIN tender t ON t.id = r.tender_id
WHERE (t.close_at IS NULL OR t.close_at > now())
ORDER BY t.close_at NULLS LAST;

COMMENT ON VIEW v_routing_queue IS
    'Brokerga ko`rsatiladigan navbat — FAQAT ochiq tenderlar. '
    '`ai_ozgardi` yoqilgan yopiq yozuv ham ko`rinadi: qaror eskirgan.';

-- ---------------------------------------------------------------------
-- 3. TEKSHIRUV
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'tender_routing'
                     AND column_name = 'ai_ozgardi') THEN
        RAISE EXCEPTION 'ai_ozgardi yaratilmadi';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'tender_routing_ozgardi_chk') THEN
        RAISE EXCEPTION 'ozgardi cheklovi yaratilmadi';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'v_routing_queue'
                     AND column_name = 'ai_ozgardi') THEN
        RAISE EXCEPTION 'v_routing_queue da ai_ozgardi yo`q';
    END IF;
    RAISE NOTICE 'schema_patch_routing_2.sql: tekshiruv o`tdi';
END $$;

COMMIT;

-- =====================================================================
-- ROLLBACK (qo'lda):
--
--   BEGIN;
--   ALTER TABLE tender_routing DROP CONSTRAINT tender_routing_ozgardi_chk;
--   ALTER TABLE tender_routing DROP CONSTRAINT tender_routing_ai_qaror_eski_chk;
--   ALTER TABLE tender_routing DROP COLUMN ai_qaror_eski;
--   ALTER TABLE tender_routing DROP COLUMN ai_ozgardi;
--   -- v_routing_queue ni schema_patch_routing.sql dan tiklang
--   COMMIT;
-- =====================================================================
