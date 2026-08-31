-- =====================================================================
-- TALAB QAYTA ISHLASH QAMROVI — tushuntiriladigan qilib
-- =====================================================================
--
-- O'LCHANGAN MUAMMO (2026-08-31, `xtxarid`).
--
--   Sodda metrika `talabi bor / hamma tender` = 1161 / 3605 = 32.2
--   foiz. Bu raqam "tizim ishning uchdan birini bajardi" degan
--   taassurot beradi va SABABINI aytmaydi.
--
--   O'LCHANDI — sabab maxrajda EMAS:
--
--       talab TOPILDI                 1161   32.2 foiz
--       ishlandi, TOPILMADI              1    0.0 foiz
--       matn yo'q (hujjat yopiq)        79    2.2 foiz
--       YAROQLI, lekin NAVBATDA       2364   65.6 foiz
--                                     ----
--                                     3605   (yarashadi)
--
--   Ya'ni 65.6 foiz tender YAROQLI va shunchaki HECH QACHON
--   ISHLANMAGAN. Maxrajni tuzatish bu raqamni o'zgartirmaydi:
--   LOTSIZ tender 0 ta, ya'ni HAR tender `reyestr` yo'li uchun
--   yaroqli.
--
-- IKKI YO'L, IKKI MAXRAJ. Talab ikki mustaqil usul bilan olinadi
-- va ularning yaroqlilik sharti BOSHQA:
--
--   `reyestr` — `tender_good` pozitsiyalaridan. Yaroqli: lot bor.
--               O'lchandi: 530 urinish, 530 tasida topildi.
--   `naqsh`   — hujjat MATNIDAN regex bilan. Yaroqli: hujjat bor.
--               O'lchandi: 1239 urinish, 988 topildi, 249 matnsiz.
--
--   Ularni bitta maxrajga qo'shish qaysi yo'l ishlamayotganini
--   YASHIRARDI.
--
-- "HUJJAT YOPIQ" YAKUNIY HOLAT EMAS. 79 ta `no_text` tenderning
-- HAMMASIDA lot bor, ya'ni `reyestr` yo'li HALI OCHIQ. Ularni
-- "qayta ishlab bo'lmaydi" deb ko'rsatish yolg'on bo'lardi:
-- yopilgani BITTA yo'l, tender emas.
--
-- "TOPILMADI" va "ISHLANMAGAN" BIR XIL EMAS. Birinchisi — natija
-- (qidirdik, yo'q ekan), ikkinchisi — natija YO'QLIGI. Ularni
-- qo'shish "talab yo'q" degan yolg'on xulosaga olib borardi.
--
-- Idempotent.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1) USUL bo'yicha qamrov — HAR USULNING O'Z MAXRAJI
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_requirement_qamrov_usul;
CREATE VIEW v_requirement_qamrov_usul AS
WITH
-- `reyestr` uchun yaroqli: lot bor.
reyestr_yaroqli AS (
    SELECT DISTINCT g.tender_id FROM tender_good g
),
-- `naqsh` uchun yaroqli: hujjat metama'lumoti bor. (Matn bor-yo'qligi
-- NATIJA, yaroqlilik sharti emas — matnsizlik `matn_yoq` bo'lib
-- chiqadi va bu O'LCHOV.)
naqsh_yaroqli AS (
    SELECT DISTINCT d.tender_id FROM tender_document d
),
yurish AS (
    SELECT company_id, tender_id, method,
           bool_or(status IN ('ok', 'needs_review')) AS tugadi,
           bool_or(status = 'no_text')               AS matnsiz,
           bool_or(status NOT IN ('ok', 'needs_review', 'no_text'))
                                                     AS xato,
           sum(COALESCE(n_requirements, 0))          AS talab
      FROM tender_requirement_run
     GROUP BY company_id, tender_id, method
)
SELECT c.id AS company_id, u.usul,
       (SELECT count(*) FROM (
            SELECT tender_id FROM reyestr_yaroqli WHERE u.usul = 'reyestr'
            UNION ALL
            SELECT tender_id FROM naqsh_yaroqli   WHERE u.usul = 'naqsh') z)
                                                          AS yaroqli,
       count(y.tender_id)                                 AS urinildi,
       count(y.tender_id) FILTER (WHERE y.talab > 0)      AS topildi,
       count(y.tender_id) FILTER (WHERE y.tugadi AND y.talab = 0)
                                                          AS topilmadi,
       count(y.tender_id) FILTER (WHERE y.matnsiz AND y.talab = 0)
                                                          AS matn_yoq,
       count(y.tender_id) FILTER (WHERE y.xato)           AS xato
  FROM company_account c
 CROSS JOIN (VALUES ('reyestr'), ('naqsh')) AS u(usul)
  LEFT JOIN yurish y ON y.company_id = c.id AND y.method = u.usul
 GROUP BY c.id, u.usul;

COMMENT ON VIEW v_requirement_qamrov_usul IS
    'Talab qamrovi HAR USUL uchun O''Z maxraji bilan. `reyestr` '
    'yaroqli: lot bor. `naqsh` yaroqli: hujjat bor. Ularni bitta '
    'maxrajga qo''shish qaysi yo''l ishlamayotganini yashirardi.';

-- ---------------------------------------------------------------------
-- 2) TENDER holati — o'zaro istisno, JAMIGA yarashadi
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION requirement_holat(
        talab_bor BOOLEAN, tugadi BOOLEAN, matnsiz BOOLEAN, xato BOOLEAN,
        lot_bor BOOLEAN, hujjat_bor BOOLEAN, reyestr_urinildi BOOLEAN)
    RETURNS TEXT LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        -- 1. NATIJA BOR.
        WHEN talab_bor THEN 'talab_bor'
        -- 2. XATO — dalil bor va u yashirilmaydi.
        WHEN xato THEN 'ajratish_xato'
        -- 3. IKKALA YO'L HAM YOPIQ va natija yo'q.
        WHEN tugadi AND NOT (lot_bor AND NOT reyestr_urinildi)
             THEN 'ishlandi_topilmadi'
        -- 4. HUJJAT YO'LI YOPIQ, lekin REYESTR yo'li OCHIQ.
        --    Bu YAKUNIY holat EMAS.
        WHEN matnsiz AND lot_bor AND NOT reyestr_urinildi
             THEN 'hujjat_yopiq_reyestr_navbatda'
        -- 5. Hujjat yo'li yopiq va boshqa yo'l ham yo'q.
        WHEN matnsiz THEN 'hujjat_yopiq'
        -- 6. YAROQLI, lekin urinilmagan.
        WHEN lot_bor OR hujjat_bor THEN 'navbatda'
        -- 7. Hech qanday yo'l yo'q.
        ELSE 'tegishli_emas'
    END
$$;

COMMENT ON FUNCTION requirement_holat(BOOLEAN, BOOLEAN, BOOLEAN, BOOLEAN,
                                      BOOLEAN, BOOLEAN, BOOLEAN) IS
    'Tenderning talab qamrovidagi holati. "Topilmadi" (natija) va '
    '"navbatda" (natija YO''QLIGI) ATAYLAB ajratilgan.';

DROP VIEW IF EXISTS v_requirement_tender_holat;
CREATE VIEW v_requirement_tender_holat AS
SELECT c.id AS company_id,
       tn.id AS tender_id,
       tn.status AS tender_status,
       (tn.status = 'open' AND (tn.close_at IS NULL OR tn.close_at > now()))
           AS ochiq,
       requirement_holat(
           EXISTS (SELECT 1 FROM tender_requirement r
                    WHERE r.tender_id = tn.id AND r.company_id = c.id),
           EXISTS (SELECT 1 FROM tender_requirement_run rr
                    WHERE rr.tender_id = tn.id AND rr.company_id = c.id
                      AND rr.status IN ('ok', 'needs_review')),
           EXISTS (SELECT 1 FROM tender_requirement_run rr
                    WHERE rr.tender_id = tn.id AND rr.company_id = c.id
                      AND rr.status = 'no_text'),
           EXISTS (SELECT 1 FROM tender_requirement_run rr
                    WHERE rr.tender_id = tn.id AND rr.company_id = c.id
                      AND rr.status NOT IN ('ok', 'needs_review', 'no_text')),
           EXISTS (SELECT 1 FROM tender_good g WHERE g.tender_id = tn.id),
           EXISTS (SELECT 1 FROM tender_document d WHERE d.tender_id = tn.id),
           EXISTS (SELECT 1 FROM tender_requirement_run rr
                    WHERE rr.tender_id = tn.id AND rr.company_id = c.id
                      AND rr.method = 'reyestr')
       ) AS holat
  FROM tender tn
 CROSS JOIN company_account c
 WHERE c.active;

COMMENT ON VIEW v_requirement_tender_holat IS
    'Har tenderning talab qamrovidagi holati (faol ijarachilar '
    'bo''yicha).';

-- ---------------------------------------------------------------------
-- 3) QAMROV — HALOL maxraj bilan
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_requirement_qamrov;
CREATE VIEW v_requirement_qamrov AS
SELECT company_id,
       count(*)                                            AS tender,
       count(*) FILTER (WHERE ochiq)                       AS ochiq_tender,

       count(*) FILTER (WHERE holat = 'talab_bor')         AS talab_bor,
       count(*) FILTER (WHERE holat = 'ishlandi_topilmadi') AS ishlandi_topilmadi,
       count(*) FILTER (WHERE holat = 'hujjat_yopiq_reyestr_navbatda')
                                                           AS hujjat_yopiq_navbatda,
       count(*) FILTER (WHERE holat = 'hujjat_yopiq')      AS hujjat_yopiq,
       count(*) FILTER (WHERE holat = 'navbatda')          AS navbatda,
       count(*) FILTER (WHERE holat = 'ajratish_xato')     AS ajratish_xato,
       count(*) FILTER (WHERE holat = 'tegishli_emas')     AS tegishli_emas,

       -- NAZORAT USTUNI: holatlar jamiga TENG bo'lishi SHART.
       -- Nol bo'lmasa — tasnifdan tashqarida qolgan tender bor.
       count(*) - (
           count(*) FILTER (WHERE holat = 'talab_bor')
         + count(*) FILTER (WHERE holat = 'ishlandi_topilmadi')
         + count(*) FILTER (WHERE holat = 'hujjat_yopiq_reyestr_navbatda')
         + count(*) FILTER (WHERE holat = 'hujjat_yopiq')
         + count(*) FILTER (WHERE holat = 'navbatda')
         + count(*) FILTER (WHERE holat = 'ajratish_xato')
         + count(*) FILTER (WHERE holat = 'tegishli_emas'))
                                                           AS hisobga_olinmagan,

       -- QAYTA ISHLANGAN = natija CHIQQAN (topildi yoki topilmadi).
       -- Navbatdagilar MAXRAJGA KIRMAYDI: ular hali savol berilmagan
       -- tenderlar va ularni "talabsiz" deb sanash yolg'on bo'lardi.
       (count(*) FILTER (WHERE holat = 'talab_bor')
      + count(*) FILTER (WHERE holat = 'ishlandi_topilmadi'))  AS ishlangan,
       round(100.0 * count(*) FILTER (WHERE holat = 'talab_bor')
             / NULLIF(count(*) FILTER (WHERE holat = 'talab_bor')
                    + count(*) FILTER (WHERE holat = 'ishlandi_topilmadi'), 0),
             1)                                            AS ishlanganda_topildi_foiz,
       -- QAMROV = ishlangan / YAROQLI. Yaroqli = tegishli_emas dan
       -- boshqa hammasi.
       round(100.0 * (count(*) FILTER (WHERE holat = 'talab_bor')
                    + count(*) FILTER (WHERE holat = 'ishlandi_topilmadi'))
             / NULLIF(count(*) - count(*) FILTER (WHERE holat = 'tegishli_emas'), 0),
             1)                                            AS ishlangan_foiz
  FROM v_requirement_tender_holat
 GROUP BY company_id;

COMMENT ON VIEW v_requirement_qamrov IS
    'Talab qamrovi HALOL maxraj bilan. `ishlanganda_topildi_foiz` — '
    'ishlangan tenderlarning qanchasida talab topilgan. '
    '`ishlangan_foiz` — yaroqlilarning qanchasi umuman ishlangan. '
    'Ikkalasi BOSHQA savol va ularni qo''shish "talab yo''q" degan '
    'yolg''on xulosaga olib borardi.';

COMMIT;
