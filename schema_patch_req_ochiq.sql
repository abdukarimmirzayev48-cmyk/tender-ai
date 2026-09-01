-- =============================================================================
-- TALAB QAMROVI — OPERATSION o'lcham QO'SHILADI (Q-1)
--
--   psql "dbname=xtxarid user=postgres host=localhost" -f schema_patch_req_ochiq.sql
--
-- O'LCHANGAN MUAMMO (2026-09-01)
-- ------------------------------
-- 18-vazifada `ishlangan_foiz` = 32.2% ekani aniqlangan va u qamrov
-- QARZI deb yozilgan (reyestrda Q-1). Qarz bo'yicha ish qilindi:
-- `reyestr` yo'li navbatdagi 627 ta OCHIQ tender uchun yurgizildi
-- (4 sekund, 1 199 talab, 0 xato, PUL SARFLANMADI).
--
-- NATIJA KUTILGANDEK CHIQMADI va bu MUHIM:
--
--     ishlangan_foiz    32.2  ->  34.5     (atigi +2.3)
--     navbatda          2368  ->  2365
--
-- SABAB O'LCHANDI. Qolgan 2 365 tenderning HAMMASI YOPIQ:
--
--     expired               2094
--     close                  164
--     cancel                  81
--     qolgan holatlar         26
--     ---------------------------
--     OCHIQ                    0
--
-- Ya'ni "65.6% ishlanmagan" OPERATSION bo'shliq EMAS edi — u
-- TARIXIY yozuvlar. Ochiq tenderlar bo'yicha qamrov 100%:
--
--     OCHIQ tender          786
--       talab_bor           786    (100%)
--       navbatda              0
--
-- BU 18-VAZIFA SABOG'INING TAKRORI, bir daraja pastda. O'sha yerda
-- "sifat" va "o'tkazuvchanlik" ajratilgan edi; bu yerda
-- "o'tkazuvchanlik" ning O'ZI ikki xil savolga javob berardi:
--
--     "ishlashga ULGURYAPMIZMI?"      -> OCHIQ tenderlar
--     "TARIXNI qanchasini ishladik?"  -> hamma tender
--
-- Ikkalasi ham ROST. Bittasini ikkinchisi o'rniga ko'rsatish esa
-- yolg'on xulosa beradi: 34.5% ni ko'rgan odam "orqada qolyapmiz"
-- deb o'ylaydi, aslida navbat BO'SH.
--
-- Shuning uchun eski ustunlar O'ZGARMAYDI (ular rost), yoniga
-- OPERATSION ustunlar QO'SHILADI.
-- =============================================================================

BEGIN;

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
       -- boshqa hammasi. Bu TARIXIY o'lcham: maxrajda yopiq
       -- tenderlar ham bor.
       round(100.0 * (count(*) FILTER (WHERE holat = 'talab_bor')
                    + count(*) FILTER (WHERE holat = 'ishlandi_topilmadi'))
             / NULLIF(count(*) - count(*) FILTER (WHERE holat = 'tegishli_emas'), 0),
             1)                                            AS ishlangan_foiz,

       -- ------------------------------------------------------------
       -- OPERATSION O'LCHAM — FAQAT OCHIQ TENDERLAR
       -- ------------------------------------------------------------
       -- "Ishlashga ULGURYAPMIZMI?" degan savolga javob. Yopiq
       -- tenderni ishlashning operatsion qiymati YO'Q: ularga taklif
       -- berib bo'lmaydi.
       count(*) FILTER (WHERE ochiq AND holat = 'talab_bor')
                                                           AS ochiq_talab_bor,
       count(*) FILTER (WHERE ochiq AND holat = 'navbatda')
                                                           AS ochiq_navbatda,
       count(*) FILTER (WHERE ochiq AND holat IN ('talab_bor',
                                                  'ishlandi_topilmadi'))
                                                           AS ochiq_ishlangan,
       round(100.0 * count(*) FILTER (WHERE ochiq
                                        AND holat IN ('talab_bor',
                                                      'ishlandi_topilmadi'))
             / NULLIF(count(*) FILTER (WHERE ochiq
                                         AND holat <> 'tegishli_emas'), 0),
             1)                                            AS ochiq_ishlangan_foiz
  FROM v_requirement_tender_holat
 GROUP BY company_id;

COMMENT ON VIEW v_requirement_qamrov IS
    'Talab qamrovi HALOL maxraj bilan. UCH xil savol, UCH xil foiz — '
    'ularni qo''shish yoki bir-birining o''rniga ko''rsatish yolg''on '
    'xulosa beradi: '
    '`ishlanganda_topildi_foiz` — SIFAT (ishlanganlarning qanchasida '
    'talab topilgan); '
    '`ishlangan_foiz` — TARIXIY o''tkazuvchanlik (maxrajda yopiq '
    'tenderlar ham bor); '
    '`ochiq_ishlangan_foiz` — OPERATSION qamrov (ulguryapmizmi). '
    'Q-1 (2026-09-01): tarixiy 34.5%, operatsion 100%.';

COMMIT;
