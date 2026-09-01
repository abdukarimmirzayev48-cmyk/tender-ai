-- =============================================================================
-- INSON HALQASI — QATLAM BO'YICHA O'LCHOV (B-3)
--
--   psql "dbname=xtxarid user=postgres host=localhost" -f schema_patch_inson_halqasi.sql
--
-- O'LCHANGAN HOLAT (2026-09-01)
-- -----------------------------
-- Reyestrda B-3 "inson halqasi hali bo'sh" deb yozilgan edi va u
-- BITTA raqamga (`tender_routing` dagi 30 qaror) tayangan. Qatlam
-- bo'yicha o'lchanganda manzara BOSHQA chiqdi:
--
--     qatlam            qaror    navbat    ulush
--     kod tasdig'i      1 048      379      73%
--     yo'naltirish         31      279      10%
--     talab ko'rigi         0    8 445       0%
--
-- Ya'ni halqa BO'SH EMAS — u NOTEKIS. Kod tasdig'i ishlayapti,
-- yo'naltirish boshlangan, talab ko'rigi esa BIR MARTA HAM
-- ishlatilmagan.
--
-- "Halqa bo'sh" degan bitta raqam bu farqni YASHIRARDI va noto'g'ri
-- xulosaga olib borardi: kod tasdig'i qatlamini ham "ishlamayapti"
-- deb hisoblash.
--
-- BU KO'RINISH NIMANI QILMAYDI
-- ----------------------------
-- U halqani TO'LDIRMAYDI — buni faqat ODAM qiladi. U faqat
-- BO'SHLIQNI KO'RINADIGAN qiladi, ya'ni "0" ni "ko'rib chiqildi va
-- muammo yo'q" deb o'qib bo'lmaydi.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. QATLAM BO'YICHA INSON QAMROVI
-- ---------------------------------------------------------------------
-- HAR QATLAM ALOHIDA. Ularni qo'shish ma'nosiz: bitta kod tasdig'i
-- va bitta tender qarori bir xil vaznda emas.
DROP VIEW IF EXISTS v_inson_halqasi;
CREATE VIEW v_inson_halqasi AS
SELECT 'talab_korigi'::TEXT                                    AS qatlam,
       company_id,
       count(*)                                                AS jami,
       count(*) FILTER (WHERE review_status IN ('approved', 'rejected',
                                                'corrected'))  AS inson_qarori,
       count(*) FILTER (WHERE review_status = 'pending_review') AS navbatda,
       round(100.0 * count(*) FILTER (WHERE review_status IN
                 ('approved', 'rejected', 'corrected'))
             / NULLIF(count(*), 0), 1)                         AS foiz
  FROM tender_requirement
 GROUP BY company_id
UNION ALL
SELECT 'yonaltirish', company_id,
       count(*),
       count(*) FILTER (WHERE inson_qaror IS NOT NULL),
       count(*) FILTER (WHERE inson_qaror IS NULL),
       round(100.0 * count(*) FILTER (WHERE inson_qaror IS NOT NULL)
             / NULLIF(count(*), 0), 1)
  FROM tender_routing
 GROUP BY company_id
UNION ALL
SELECT 'kod_tasdigi', company_id,
       count(*),
       count(*) FILTER (WHERE tasdiqlandi IS NOT NULL
                           OR rad_etildi IS NOT NULL),
       count(*) FILTER (WHERE tasdiqlandi IS NULL AND rad_etildi IS NULL),
       round(100.0 * count(*) FILTER (WHERE tasdiqlandi IS NOT NULL
                                         OR rad_etildi IS NOT NULL)
             / NULLIF(count(*), 0), 1)
  FROM catalog_product_code
 GROUP BY company_id;

COMMENT ON VIEW v_inson_halqasi IS
    'B-3: inson qarori QATLAM BO''YICHA. Halqa bo''sh emas, NOTEKIS '
    '(2026-09-01: kod 73%, yo''naltirish 10%, talab 0%). Bitta raqam '
    'bu farqni yashirardi. Ko''rinish halqani TO''LDIRMAYDI — u faqat '
    'bo''shliqni KO''RINADIGAN qiladi.';

-- ---------------------------------------------------------------------
-- 2. PILOT TO'PLAMINING YANGILIGI
-- ---------------------------------------------------------------------
-- O'LCHANGAN MUAMMO: pilot 2026-08-26 da yaratilgan, 30 tender.
-- 2026-09-01 ga kelib ularning 22 tasining MUDDATI O'TGAN — ya'ni
-- to'plam ESKIRGAN va uni ko'rib chiqishning operatsion qiymati
-- YO'Q.
--
-- `pilot_yarat()` ATAYLAB idempotent ("to'plam bir marta muzlaydi"
-- — namuna buzilmasin uchun) va unda QAYTA QURISH yo'li YO'Q.
-- Ya'ni eskirgan to'plam yangisini BLOKLAYDI.
--
-- Bu ko'rinish shu holatni ko'rsatadi. QAROR — mahsulot qarori:
-- eskirgan namunani tashlab yangisini qurish namunaviy
-- xolislikni buzadi, saqlab qolish esa halqani bloklab turadi.
CREATE OR REPLACE VIEW v_pilot_holat AS
SELECT p.company_id,
       count(*)                                                AS jami,
       min(p.added_at)                                         AS yaratilgan,
       count(*) FILTER (WHERE t.status = 'open'
                          AND (t.close_at IS NULL
                               OR t.close_at > now()))         AS hali_ochiq,
       count(*) FILTER (WHERE t.status <> 'open'
                           OR t.close_at <= now())             AS eskirgan,
       -- Pilot tenderlarida NECHTA talab inson qarorini kutyapti.
       (SELECT count(*) FROM review_pilot p2
          JOIN tender_requirement r ON r.tender_id = p2.tender_id
                                   AND r.company_id = p2.company_id
         WHERE p2.company_id = p.company_id
           AND r.review_status = 'pending_review')             AS kutayotgan_talab,
       -- Nechta talab bo'yicha qaror BERILGAN.
       (SELECT count(*) FROM review_pilot p3
          JOIN tender_requirement r ON r.tender_id = p3.tender_id
                                   AND r.company_id = p3.company_id
         WHERE p3.company_id = p.company_id
           AND r.review_status IN ('approved', 'rejected', 'corrected'))
                                                               AS qaror_berilgan
  FROM review_pilot p
  JOIN tender t ON t.id = p.tender_id
 GROUP BY p.company_id;

COMMENT ON VIEW v_pilot_holat IS
    'B-3: pilot to''plami YANGIMI. 2026-09-01 da 30 tadan 22 tasining '
    'muddati o''tgan va `qaror_berilgan` = 0. `pilot_yarat()` '
    'idempotent va qayta qurish yo''li YO''Q — eskirgan to''plam '
    'yangisini BLOKLAYDI.';

COMMIT;
