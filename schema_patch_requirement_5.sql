-- =====================================================================
-- schema_patch_requirement_5.sql
-- J3 — KO'RIB CHIQISH VAQTINI o'lchash
--
-- Bog'liqlik: schema_patch_requirement_4.sql
-- Idempotent: qayta yurgizish xavfsiz.
--
-- Qo'llash:
--   psql -d xtxarid -f schema_patch_requirement_5.sql
--
-- NEGA KERAK
-- ══════════
-- "Har talabni inson tasdiqlaydi" modeli ISHLAYDIMI degan savolning
-- javobi bitta noma'lum raqamga bog'liq: BIR TENDERNI ko'rib chiqish
-- VAQTI.
--
--     ~2 daqiqa  ->  611 tender = ~20 soat  -> to'liq ko'rib chiqish real
--     ~5 daqiqa  ->  ~50 soat   -> faqat c<0.85 qo'lda, qolgani avto
--     ~10 daqiqa ->  ~100 soat  -> namuna asosida tekshirish kerak
--
-- Bu raqamni TAXMIN QILIB BO'LMAYDI: manbaga sakrash, o'qish va qaror
-- vaqti hujjatga qarab juda farq qiladi. O'LCHASH kerak.
--
-- NEGA ALOHIDA JADVAL: `reviewed_at` faqat OXIRGI bosishni biladi.
-- Tenderni ochib, hujjatni o'qib, keyin birinchi tugmani bosgunicha
-- o'tgan vaqt — ko'rib chiqishning ENG KATTA qismi — u yerda yo'q.
-- Ochilish vaqtini alohida yozmasak, o'lchov haqiqiydan PAST chiqadi.
-- =====================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS requirement_review_open (
    company_id  INT NOT NULL REFERENCES company_account(id) ON DELETE CASCADE,
    tender_id   BIGINT NOT NULL REFERENCES tender(id) ON DELETE CASCADE,

    -- Tender ko'rib chiqish uchun BIRINCHI marta ochilgan vaqt.
    -- Qayta ochilsa YANGILANMAYDI (`ON CONFLICT DO NOTHING`) — aks
    -- holda sahifani yangilash o'lchovni nolga qaytarardi.
    opened_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Oxirgi kutayotgan talab ko'rib chiqilgan vaqt.
    finished_at TIMESTAMPTZ,

    -- Nechta talab ko'rib chiqilgan (vaqtni talabga bo'lish uchun).
    n_reviewed  INT NOT NULL DEFAULT 0,

    PRIMARY KEY (company_id, tender_id)
);

COMMENT ON TABLE requirement_review_open IS
    'J3: ko`rib chiqish VAQTINI o`lchash. opened_at — tender birinchi '
    'ochilgan payt (o`qish vaqti ham hisobga olinsin), finished_at — '
    'oxirgi talab belgilangan payt.';

-- Hisobot so'rovi shu indeksdan foydalanadi.
CREATE INDEX IF NOT EXISTS requirement_review_open_done_idx
    ON requirement_review_open (company_id, finished_at)
    WHERE finished_at IS NOT NULL;

-- ---------------------------------------------------------------------
-- HISOBOT ko'rinishi — pilot natijasi shu yerdan o'qiladi
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_review_speed AS
SELECT o.company_id,
       o.tender_id,
       t.name                              AS tender_name,
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

COMMENT ON VIEW v_review_speed IS
    'J3 pilot: bir tenderni ko`rib chiqish vaqti. 611 tender uchun '
    'umumiy yukni shu raqamdan hisoblanadi.';

-- ---------------------------------------------------------------------
-- TEKSHIRUV
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF to_regclass('public.requirement_review_open') IS NULL THEN
        RAISE EXCEPTION 'requirement_review_open yaratilmadi';
    END IF;
    IF to_regclass('public.v_review_speed') IS NULL THEN
        RAISE EXCEPTION 'v_review_speed yaratilmadi';
    END IF;
    RAISE NOTICE 'schema_patch_requirement_5.sql: tekshiruv o`tdi';
END $$;

COMMIT;

-- =====================================================================
-- ROLLBACK (qo'lda):
--
--   BEGIN;
--   DROP VIEW  IF EXISTS v_review_speed;
--   DROP TABLE IF EXISTS requirement_review_open;
--   COMMIT;
--
-- Yo'qoladigan narsa: vaqt o'lchovlari. Talablar va yorliqlar
-- TEGILMAYDI.
-- =====================================================================
