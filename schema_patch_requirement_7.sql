-- =====================================================================
-- schema_patch_requirement_7.sql
-- `v_review_disagreement` INSON TEGMAGAN qatorlarni sanardi
--
-- Bog'liqlik: schema_patch_requirement_6.sql
-- Idempotent: qayta yurgizish xavfsiz.
--
-- Qo'llash:
--   psql -d xtxarid -f schema_patch_requirement_7.sql
--
-- TOPILGAN XATO
-- ═════════════
-- Ko'rinish shunday edi:
--
--     WHERE p.rejim = 'blind'
--       AND r.review_status <> 'pending'
--
-- `<> 'pending'` — NOTO'G'RI SHART. Reyestr pozitsiyalari
-- AVTO-TASDIQLANADI (`review_status = 'approved'`, `confidence = 1.00`,
-- `reviewed_by IS NULL`) va shu shartga tushib qoladi.
--
-- Natijada ko'rinish shuni ko'rsatdi:
--
--     ishonch_darajasi = 'yuqori (>=0.85)'
--     jami = 12, tasdiqlangan = 12, kelishmovchilik_foiz = 0.0
--
-- ya'ni "model yuqori ishonch darajasida HECH QACHON xato qilmaydi".
--
-- Holbuki `reviewed_by IS NOT NULL` bo'lgan qator BITTA HAM YO'Q —
-- hech kim hech narsani ko'rmagan. O'n ikkita reyestr pozitsiyasi
-- INSON ROZILIGI deb hisoblangan.
--
-- Bu pilotning BOSH KO'RSATKICHI. Agar tuzatilmasa, pilot yurganda
-- ham raqam soxta chiqardi va "0%" ishonchli ko'ringani uchun hech
-- kim shubhalanmasdi.
--
-- TO'G'RI SHART: `reviewed_by IS NOT NULL` — INSON HAQIQATAN
-- harakat qilgan.
-- =====================================================================

BEGIN;

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
       round(100.0 * count(*) FILTER (
             WHERE r.review_status IN ('rejected', 'corrected'))
             / NULLIF(count(*), 0), 1)                   AS kelishmovchilik_foiz
FROM tender_requirement r
JOIN review_pilot p ON p.tender_id = r.tender_id AND p.company_id = r.company_id
WHERE p.rejim = 'blind'            -- FAQAT yopiq rejim ishonchli
  -- INSON HAQIQATAN HARAKAT QILGAN BO'LSIN.
  --
  -- Ilgari `r.review_status <> 'pending'` edi va u REYESTR
  -- pozitsiyalarini ham tortardi: ular avto-tasdiqlanadi
  -- (`approved`, `confidence = 1.00`, `reviewed_by IS NULL`).
  -- 12 ta shunday qator "inson roziligi" deb hisoblanib,
  -- "yuqori ishonchda 0% kelishmovchilik" degan SOXTA raqam bergan.
  AND r.reviewed_by IS NOT NULL
GROUP BY r.company_id, 2
ORDER BY 2 DESC;

COMMENT ON VIEW v_review_disagreement IS
    'J3: model necha foizda xato qilgan, ISHONCH DARAJASI bo`yicha. '
    'FAQAT yopiq rejim va FAQAT inson HAQIQATAN ko`rgan qatorlar '
    '(`reviewed_by IS NOT NULL`) — avto-tasdiqlangan reyestr '
    'pozitsiyalari kelishuv EMAS.';

-- ---------------------------------------------------------------------
-- TEKSHIRUV — musbat tasdiq
-- ---------------------------------------------------------------------
DO $$
DECLARE
    n_soxta INT;
BEGIN
    -- Inson tegmagan qator ko'rinishga TUSHMASLIGI kerak.
    SELECT count(*) INTO n_soxta
      FROM tender_requirement r
      JOIN review_pilot p ON p.tender_id = r.tender_id
                         AND p.company_id = r.company_id
     WHERE p.rejim = 'blind' AND r.reviewed_by IS NULL
       AND r.review_status <> 'pending';
    RAISE NOTICE 'avto-tasdiqlangan (endi SANALMAYDI): % qator', n_soxta;

    IF EXISTS (SELECT 1 FROM v_review_disagreement v
               JOIN tender_requirement r ON r.company_id = v.company_id
               WHERE r.reviewed_by IS NULL
                 AND v.jami > 0
                 AND NOT EXISTS (SELECT 1 FROM tender_requirement x
                                 WHERE x.company_id = v.company_id
                                   AND x.reviewed_by IS NOT NULL)) THEN
        RAISE EXCEPTION 'ko`rinish hali ham inson tegmagan qatorni sanaydi';
    END IF;
    RAISE NOTICE 'schema_patch_requirement_7.sql: tekshiruv o`tdi';
END $$;

COMMIT;

-- =====================================================================
-- ROLLBACK: schema_patch_requirement_6.sql dagi ta'rifni qayta qo'llang.
--
-- DIQQAT: eski ta'rif SOXTA raqam beradi (avto-tasdiqlangan reyestr
-- pozitsiyalarini inson roziligi deb sanaydi).
-- =====================================================================
