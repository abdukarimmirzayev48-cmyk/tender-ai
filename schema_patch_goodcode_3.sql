-- =====================================================================
-- TUZATISH: markaz yangilanganda LUG'AT vektorlari ham qayta markazlansin
-- =====================================================================
--
-- TOPILGAN NOSOZLIK (bazada o'lchangan, taxmin emas):
--
--     embed_centroid:                    id=3 faol
--     tender_embedding.centroid_id:      3      (to'g'ri)
--     good_code_embedding.centroid_id:   1      (IKKI VERSIYA ORQADA)
--     v_hub_stale.eskirgan:              0      (KO'RMAYAPTI)
--
-- Sabab: `recompute_centroid()` faqat `tender_embedding` ni yangilardi —
-- `good_code_embedding` u yozilganda hali mavjud emas edi. Natijada
-- so'rov vektori YANGI markaz bilan, lug'at vektorlari ESKI markaz
-- bilan hisoblanardi, ya'ni ikkalasi BOSHQA fazoda. Qidiruv xato
-- bermaydi — shunchaki sekin-asta yomonlashadi.
--
-- `v_hub_stale` buni ko'rmadi, chunki u `hub_at < markaz.computed_at`
-- ni tekshirardi. Hublik markazdan KEYIN hisoblangani uchun bu shart
-- doim yolg'on chiqardi. Ya'ni asbob tekshirayotgan narsaning xatosini
-- takrorlagan.
--
-- IKKI TUZATISH:
--   1) `recompute_centroid()` lug'atni HAM qayta markazlaydi;
--   2) eskirganlik `centroid_id <> faol` bo'yicha o'lchanadi — vaqt
--      bo'yicha emas. Vaqt taqqoslash tartibga bog'liq, id esa emas.
--
-- Qo'llash (schema_patch_goodcode_2.sql DAN KEYIN):
--   psql "$XT_DB_DSN" -f schema_patch_goodcode_3.sql
-- =====================================================================

BEGIN;

CREATE OR REPLACE FUNCTION recompute_centroid(
    p_model TEXT DEFAULT NULL,
    p_scope TEXT DEFAULT 'tender_open'
) RETURNS BIGINT
LANGUAGE plpgsql AS $$
DECLARE
    v_model TEXT;
    v_vec   VECTOR(384);
    v_n     INT;
    v_id    BIGINT;
BEGIN
    v_model := COALESCE(p_model,
                        (SELECT name FROM embed_model WHERE is_active LIMIT 1));
    IF v_model IS NULL THEN
        RAISE EXCEPTION 'Faol embedding modeli yo''q (embed_model.is_active)';
    END IF;

    IF p_scope = 'tender_open' THEN
        SELECT avg(e.embedding)::VECTOR(384), count(*)
          INTO v_vec, v_n
          FROM tender_embedding e
          JOIN tender t ON t.id = e.tender_id
         WHERE e.embed_model = v_model
           AND e.embedding IS NOT NULL
           AND t.status = 'open';
    ELSE
        SELECT avg(e.embedding)::VECTOR(384), count(*)
          INTO v_vec, v_n
          FROM tender_embedding e
         WHERE e.embed_model = v_model
           AND e.embedding IS NOT NULL;
    END IF;

    IF v_n IS NULL OR v_n < 50 THEN
        RAISE NOTICE 'Markaz hisoblanmadi: namuna % ta (kamida 50 kerak)',
                     COALESCE(v_n, 0);
        RETURN NULL;
    END IF;

    UPDATE embed_centroid SET is_active = FALSE
     WHERE model = v_model AND scope = p_scope AND is_active;

    INSERT INTO embed_centroid (model, scope, dims, vec, n_source, is_active)
    VALUES (v_model, p_scope, 384, v_vec, v_n, TRUE)
    RETURNING id INTO v_id;

    UPDATE tender_embedding
       SET embedding_c = l2_normalize(embedding - v_vec),
           centroid_id = v_id
     WHERE embed_model = v_model
       AND embedding IS NOT NULL;

    -- LUG'AT HAM SHU MARKAZ BILAN. So'rov va lug'at bir fazoda
    -- bo'lishi SHART — aks holda kosinus ma'nosini yo'qotadi.
    -- Jadval hali yaratilmagan bo'lishi mumkin (patch tartibi), shuning
    -- uchun mavjudligi tekshiriladi.
    IF to_regclass('good_code_embedding') IS NOT NULL THEN
        UPDATE good_code_embedding
           SET embedding_c = l2_normalize(embedding - v_vec),
               centroid_id = v_id,
               -- Hublik ENDI ESKI: u markazlangan vektorlardan
               -- hisoblanadi. NULL qo'yamiz, ya'ni `v_hub_stale`
               -- darhol ko'rsatadi va quvur qayta hisoblaydi.
               hub_bias    = NULL,
               hub_at      = NULL
         WHERE embed_model = v_model
           AND embedding IS NOT NULL;
    END IF;

    RETURN v_id;
END;
$$;

-- ---------------------------------------------------------------------
-- ESKIRGANLIK — VAQT bo'yicha emas, ID bo'yicha.
--
-- Vaqt taqqoslash chaqiruv TARTIBIGA bog'liq edi va shu sababli
-- nosozlikni ko'rmadi. `centroid_id` esa tartibdan mustaqil.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_hub_stale AS
WITH faol AS (
    SELECT c.id
    FROM embed_centroid c
    JOIN embed_model m ON m.name = c.model AND m.is_active
    WHERE c.is_active
    ORDER BY c.computed_at DESC
    LIMIT 1
)
SELECT count(*) FILTER (WHERE g.embedding_c IS NOT NULL)          AS vektorli,
       count(*) FILTER (WHERE g.embedding_c IS NOT NULL
                          AND g.hub_bias IS NULL)                  AS biassiz,
       count(*) FILTER (WHERE g.embedding IS NOT NULL
                          AND g.centroid_id IS DISTINCT FROM
                              (SELECT id FROM faol))               AS eskirgan
FROM good_code_embedding g;

COMMENT ON VIEW v_hub_stale IS
    'Lug''at vektorlarining holati. `eskirgan` — FAOL markazdan boshqa '
    'markaz bilan hisoblanganlar (id bo''yicha, vaqt bo''yicha EMAS).';

COMMIT;

-- Darhol tuzatamiz: markazni qayta hisoblab, lug'atni ham markazlaymiz.
SELECT recompute_centroid() AS markaz;
SELECT * FROM v_hub_stale;
