-- =====================================================================
-- YO'NALTIRISH: AI <-> INSON KELISHUVI — halol o'lchov
-- =====================================================================
--
-- O'LCHANGAN MUAMMO (2026-08-31, `xtxarid`).
--
--   310 yo'naltirish qatori, 30 tasida inson qarori:
--
--       ai=go      inson=olindi      5
--       ai=review  inson=olindi     11
--       ai=review  inson=rad         8
--       ai=review  inson=kutilsin    6
--
--   Mavjud `v_routing_agreement` shuni ko'rsatardi:
--
--       ai_qaror=go      jami 5    moslik 100.0
--       ai_qaror=review  jami 25   moslik   0.0   <-- YOLG'ON
--
--   UCHTA NUQSON:
--
--   1. `review` NOL FOIZ deb ko'rsatilardi. `review` — "AI QAROR
--      QILMADI" degani, "AI xato qildi" degani EMAS. Formula
--      `(go AND olindi) OR (no_go AND rad)` `review` uchun HECH
--      QACHON rost bo'lolmaydi, ya'ni u tuzilishiga ko'ra 0 beradi.
--      Bu NOMA'LUMNI MUVAFFAQIYATSIZLIKKA aylantirish — loyihada
--      taqiqlangan naqsh. Va u ustun holat: 30 dan 25 tasi.
--
--   2. `kutilsin` KO'RINMAYDI. Ko'rinish faqat `olindi` va `rad` ni
--      sanaydi, lekin `jami` ga 6 ta `kutilsin` ham kiradi. Ya'ni
--      maxrajda hisoblanadi, suratda esa hech qachon paydo
--      bo'lolmaydi.
--
--   3. TARIX QAYTA YOZILADI. `ai_qaror` JORIY qiymatni saqlaydi.
--      Inson qaror bergandan keyin AI fikri o'zgarsa, kelishuv
--      inson KO'RMAGAN qaror bilan hisoblanardi. `ai_qaror_eski`
--      buning uchun bor, lekin ko'rinish uni ISHLATMAYDI.
--
-- BUNDAN TASHQARI — SAQLASH NUQSONI (bu patch tuzatadi):
--
--   `routing.SQL_UPSERT` dagi `ai_qaror_eski` IKKINCHI o'zgarishda
--   birinchisini USTIGA YOZADI:
--
--       1-o'zgarish: inson `go` ni ko'rgan, AI -> review
--                    ai_qaror_eski = 'go'          TO'G'RI
--       2-o'zgarish: AI -> no_go
--                    ai_qaror_eski = 'review'      ASL YO'QOLDI
--
--   Ya'ni inson HAQIQATAN ko'rgan qaror ikkinchi o'zgarishda
--   yo'qolardi. Hozir `ai_ozgardi` = 0 qator, ya'ni nuqson hali
--   tishlamagan — lekin u YASHIRIN va o'z-o'zidan tuzalmaydi.
--
--   TUZATISH: `ai_qaror_eski` FAQAT BIR MARTA yoziladi (u NULL
--   bo'lganda). Kod tomoni `api/routing.py` da.
--
-- BU PATCH NIMA QILADI
--   - `ai_korilgan(...)` — inson KO'RGAN AI qarori (yagona manba);
--   - `v_routing_kelishuv` — 3x3 chalkashlik matritsasi, `review`
--     ALOHIDA, `kutilsin` ALOHIDA;
--   - `v_routing_kelishuv_kesim` — manba / ball / sabab bo'yicha;
--   - qat'iy cheklov: `ai_qaror_eski` bir marta yozilishini
--     ta'minlab bo'lmaydi (u UPSERT mantiqi), lekin uning
--     LUG'ATI cheklangan (mavjud CHECK).
--
-- Idempotent.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1) INSON KO'RGAN AI QARORI — yagona manba
-- ---------------------------------------------------------------------
-- Tarixiy haqiqat: inson qaror berganda AI nima degan edi.
-- `ai_qaror_eski` faqat AI fikri inson qaroridan KEYIN o'zgarganda
-- to'ldiriladi, ya'ni u bor bo'lsa — aynan o'sha inson ko'rgan qiymat.
CREATE OR REPLACE FUNCTION ai_korilgan(joriy TEXT, eski TEXT)
    RETURNS TEXT LANGUAGE sql IMMUTABLE AS $$
    SELECT COALESCE(eski, joriy)
$$;

COMMENT ON FUNCTION ai_korilgan(TEXT, TEXT) IS
    'Inson qaror berganda AI nima degan edi. Kelishuv SHU qiymat '
    'bilan hisoblanadi — joriy qiymat bilan emas, aks holda AI '
    'fikrini o''zgartirgani tarixiy haqiqatni qayta yozardi.';

-- ---------------------------------------------------------------------
-- 2) KELISHUV — 3x3, halol maxraj bilan
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_routing_kelishuv;
CREATE VIEW v_routing_kelishuv AS
WITH q AS (
    SELECT r.company_id,
           r.id,
           ai_korilgan(r.ai_qaror, r.ai_qaror_eski) AS ai,
           r.inson_qaror                            AS inson,
           r.ai_ozgardi,
           r.qaror_ishonch
      FROM tender_routing r
     -- FAQAT HAQIQIY INSON QARORI. `holat='yopildi'` yetarli emas —
     -- u AI tomonidan ham qo'yilishi mumkin.
     WHERE r.inson_qaror IS NOT NULL
)
SELECT company_id,

       count(*)                                                AS inson_qarori,

       -- AI ANIQ DA'VO QILGAN holatlar (go yoki no_go).
       count(*) FILTER (WHERE ai IN ('go', 'no_go'))            AS ai_davo,
       -- AI QAROR QILMAGAN. Bu MUVAFFAQIYATSIZLIK EMAS va
       -- kelishuv maxrajiga KIRMAYDI.
       count(*) FILTER (WHERE ai = 'review')                    AS ai_qaror_yoq,

       -- --- 3x3 KATAKLAR (inson ko'rgan AI qarori bo'yicha) ---
       count(*) FILTER (WHERE ai = 'go'    AND inson = 'olindi')   AS go_olindi,
       count(*) FILTER (WHERE ai = 'go'    AND inson = 'rad')      AS go_rad,
       count(*) FILTER (WHERE ai = 'go'    AND inson = 'kutilsin') AS go_kutilsin,
       count(*) FILTER (WHERE ai = 'no_go' AND inson = 'olindi')   AS nogo_olindi,
       count(*) FILTER (WHERE ai = 'no_go' AND inson = 'rad')      AS nogo_rad,
       count(*) FILTER (WHERE ai = 'no_go' AND inson = 'kutilsin') AS nogo_kutilsin,
       count(*) FILTER (WHERE ai = 'review' AND inson = 'olindi')   AS review_olindi,
       count(*) FILTER (WHERE ai = 'review' AND inson = 'rad')      AS review_rad,
       count(*) FILTER (WHERE ai = 'review' AND inson = 'kutilsin') AS review_kutilsin,

       -- --- KELISHUV: FAQAT aniq da'vo + aniq inson javobi ---
       count(*) FILTER (WHERE (ai = 'go'    AND inson = 'olindi')
                           OR (ai = 'no_go' AND inson = 'rad'))     AS kelishdi,
       count(*) FILTER (WHERE (ai = 'go'    AND inson = 'rad')
                           OR (ai = 'no_go' AND inson = 'olindi'))  AS bekor_qilindi,
       -- Aniq da'voga inson KUTISH bilan javob berdi — na kelishuv,
       -- na bekor qilish. ALOHIDA sanaladi.
       count(*) FILTER (WHERE ai IN ('go', 'no_go') AND inson = 'kutilsin')
                                                                    AS kutildi,

       -- MAXRAJ ANIQ: kelishdi + bekor_qilindi. `review` va
       -- `kutilsin` bu yerga KIRMAYDI.
       (count(*) FILTER (WHERE (ai = 'go'    AND inson = 'olindi')
                            OR (ai = 'no_go' AND inson = 'rad'))
      + count(*) FILTER (WHERE (ai = 'go'    AND inson = 'rad')
                            OR (ai = 'no_go' AND inson = 'olindi'))) AS kelishuv_maxraj,

       -- NOL MAXRAJDA `NULL` — NOL FOIZ EMAS. "O'lchanmadi" va
       -- "hech qachon kelishmadi" BIR XIL EMAS.
       round(100.0 * count(*) FILTER (WHERE (ai = 'go'    AND inson = 'olindi')
                                         OR (ai = 'no_go' AND inson = 'rad'))
             / NULLIF(count(*) FILTER (WHERE (ai = 'go'    AND inson = 'olindi')
                                           OR (ai = 'no_go' AND inson = 'rad'))
                    + count(*) FILTER (WHERE (ai = 'go'    AND inson = 'rad')
                                           OR (ai = 'no_go' AND inson = 'olindi')), 0),
             1)                                                     AS kelishuv_foiz,
       round(100.0 * count(*) FILTER (WHERE (ai = 'go'    AND inson = 'rad')
                                         OR (ai = 'no_go' AND inson = 'olindi'))
             / NULLIF(count(*) FILTER (WHERE (ai = 'go'    AND inson = 'olindi')
                                           OR (ai = 'no_go' AND inson = 'rad'))
                    + count(*) FILTER (WHERE (ai = 'go'    AND inson = 'rad')
                                           OR (ai = 'no_go' AND inson = 'olindi')), 0),
             1)                                                     AS bekor_foiz,

       -- SIFAT BELGILARI — o'lchov qanchalik ishonchli.
       count(*) FILTER (WHERE ai_ozgardi)                           AS ai_keyin_ozgardi,
       count(*) FILTER (WHERE qaror_ishonch = 'kuzatuvdan_oldin')   AS aktori_nomalum,
       count(*) FILTER (WHERE qaror_ishonch IN ('erp_sessiya', 'aktor_elon'))
                                                                    AS aktori_malum
  FROM q
 GROUP BY company_id;

COMMENT ON VIEW v_routing_kelishuv IS
    'AI <-> inson kelishuvi. `review` (AI qaror qilmadi) va '
    '`kutilsin` (inson kutdi) kelishuv maxrajiga KIRMAYDI — ularni '
    'qo''shish "AI xato qildi" degan yolg''on berardi. Maxraj nol '
    'bo''lsa foiz NULL, nol EMAS.';

-- ---------------------------------------------------------------------
-- 3) KESIMLAR — manba, ball, sabab
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_routing_kelishuv_kesim;
CREATE VIEW v_routing_kelishuv_kesim AS
WITH q AS (
    SELECT r.company_id,
           ai_korilgan(r.ai_qaror, r.ai_qaror_eski) AS ai,
           r.inson_qaror                            AS inson,
           r.ai_manba,
           CASE
               WHEN r.ai_ball IS NULL      THEN 'ball yo''q'
               WHEN r.ai_ball >= 0.80      THEN '0.80-1.00'
               WHEN r.ai_ball >= 0.60      THEN '0.60-0.79'
               WHEN r.ai_ball >= 0.40      THEN '0.40-0.59'
               ELSE                             '0.00-0.39'
           END AS ball_bandi,
           -- Malaka sababi — birinchi qatori (to'liq matn juda uzun).
           NULLIF(split_part(COALESCE(r.ai_sabab, ''), E'\n', 1), '') AS sabab
      FROM tender_routing r
     WHERE r.inson_qaror IS NOT NULL
)
SELECT company_id, 'manba'::TEXT AS kesim, ai_manba AS qiymat,
       count(*) AS inson_qarori,
       count(*) FILTER (WHERE ai = 'review') AS ai_qaror_yoq,
       count(*) FILTER (WHERE (ai='go' AND inson='olindi') OR (ai='no_go' AND inson='rad')) AS kelishdi,
       count(*) FILTER (WHERE (ai='go' AND inson='rad') OR (ai='no_go' AND inson='olindi')) AS bekor_qilindi
  FROM q GROUP BY company_id, ai_manba
UNION ALL
SELECT company_id, 'ball', ball_bandi,
       count(*),
       count(*) FILTER (WHERE ai = 'review'),
       count(*) FILTER (WHERE (ai='go' AND inson='olindi') OR (ai='no_go' AND inson='rad')),
       count(*) FILTER (WHERE (ai='go' AND inson='rad') OR (ai='no_go' AND inson='olindi'))
  FROM q GROUP BY company_id, ball_bandi
UNION ALL
SELECT company_id, 'sabab', left(sabab, 60),
       count(*),
       count(*) FILTER (WHERE ai = 'review'),
       count(*) FILTER (WHERE (ai='go' AND inson='olindi') OR (ai='no_go' AND inson='rad')),
       count(*) FILTER (WHERE (ai='go' AND inson='rad') OR (ai='no_go' AND inson='olindi'))
  FROM q WHERE sabab IS NOT NULL GROUP BY company_id, left(sabab, 60);

COMMENT ON VIEW v_routing_kelishuv_kesim IS
    'Kelishuv kesimlari: manba / ball bandi / malaka sababi. '
    'Foiz BERILMAYDI — kesimlarda son kichik va foiz yolg''on '
    'aniqlik berardi. Xom sonlar chaqiruvchida bo''linadi.';

COMMIT;
