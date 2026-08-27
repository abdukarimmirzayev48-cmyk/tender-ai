-- =====================================================================
-- SEMANTIK MOSLASHTIRISH — markazlashtirilgan (centered) vektorlar
-- =====================================================================
--
-- MUAMMO (o'lchangan, taxmin emas):
--   `multilingual-e5-small` vektorlari ANIZOTROP — hammasi bitta tor
--   konusga yig'ilgan. Ochiq korpus (782 tender) uchun o'lchandi:
--
--       korpus markaz vektorining normasi = 0.909   (izotropda ~0)
--
--   Natijada har juftlik ~0.82 kosinus beradi va MA'NOSIZ so'rov
--   ('zzz qwerty asdfgh') ham max 0.826 oladi. "dori" so'rovining eng
--   yaxshi natijasi 0.830 — ya'ni shovqindan 0.004 farq. Xom kosinus
--   bu korpusda RANGLASH SIGNALI EMAS.
--
-- YECHIM: markazlashtirish. Har vektordan korpus o'rtachasi ayiriladi
-- va qayta normallashtiriladi:  c = l2_normalize(v - mu)
--
--   O'LCHANGAN NATIJA (top-1, ochiq tenderlar):
--     "dori vositalari, farmatsevtika, tibbiy preparatlar"
--        xom:        "Лаборатория учун ускуналар"        (noto'g'ri)
--        markazli:   "Ftoruratsil Lot-4 Onkogematologik"  (to'g'ri)
--     "videokuzatuv kamerasi, IP kamera"
--        xom:        "Отбор"                              (noto'g'ri)
--        markazli:   "DH-IPC-HFW2441T-ZS, DS-2CD2443G0E-I" (to'g'ri)
--
--   Ajralish (1-o'rin minus 5-o'rin): 0.007 -> 0.027 va 0.026 -> 0.092.
--
-- NEGA SQL DA: pgvector `avg()`, `-` va `l2_normalize()` ni o'zi
-- biladi. Ya'ni markazlash uchun MODEL CHAQIRILMAYDI — bu sof
-- arifmetika. 782 qatorni qayta markazlash millisekundlar oladi,
-- shuning uchun uni har kuni qayta hisoblash arzon.
--
-- Qo'llash:
--   psql "$XT_DB_DSN" -f schema_patch_semantik.sql
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1) Markaz vektori — VERSIYALANADI
--
-- NEGA VERSIYA: korpus o'sadi, markaz suriladi. Markaz o'zgargach
-- ESKI markaz bilan hisoblangan `embedding_c` NOTO'G'RI bo'lib qoladi
-- va buni HECH NARSA ko'rsatmaydi — qidiruv shunchaki sekin-asta
-- yomonlashadi. Shuning uchun har markazlangan vektor QAYSI markaz
-- bilan hisoblanganini yozib boradi (`centroid_id`), va `v_centroid_stale`
-- eskirganini sanaydi.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS embed_centroid (
    id          BIGSERIAL PRIMARY KEY,
    model       TEXT        NOT NULL,
    scope       TEXT        NOT NULL DEFAULT 'tender_open',
    dims        INT         NOT NULL,
    vec         VECTOR(384) NOT NULL,
    n_source    INT         NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active   BOOLEAN     NOT NULL DEFAULT FALSE,

    -- SOVUQ START HIMOYASI. Kam namunadan olingan "o'rtacha" — o'rtacha
    -- emas, shovqin. 50 tadan kam bo'lsa markaz UMUMAN yozilmaydi va
    -- tizim xom vektorga qaytadi (`semantik.py` shuni tekshiradi).
    CONSTRAINT embed_centroid_min_source CHECK (n_source >= 50)
);

COMMENT ON TABLE embed_centroid IS
    'Korpus markaz vektori (anizotropiyani yo''qotish uchun). '
    'Har versiya alohida qator; faqat bittasi is_active.';

-- Bir model uchun FAQAT BITTA faol markaz — struktura darajasida.
CREATE UNIQUE INDEX IF NOT EXISTS embed_centroid_active_uq
    ON embed_centroid (model, scope) WHERE is_active;

-- ---------------------------------------------------------------------
-- 2) Markazlangan vektor ustuni
-- ---------------------------------------------------------------------
ALTER TABLE tender_embedding
    ADD COLUMN IF NOT EXISTS embedding_c VECTOR(384),
    ADD COLUMN IF NOT EXISTS centroid_id BIGINT REFERENCES embed_centroid(id);

-- QOIDA STRUKTURADA, IZOHDA EMAS: markazlangan vektor bor bo'lsa,
-- uni QAYSI markaz yasaganini ham bilishimiz SHART. Aks holda
-- eskirganini aniqlab bo'lmaydi.
ALTER TABLE tender_embedding
    DROP CONSTRAINT IF EXISTS tender_embedding_c_needs_centroid;
ALTER TABLE tender_embedding
    ADD CONSTRAINT tender_embedding_c_needs_centroid
    CHECK (embedding_c IS NULL OR centroid_id IS NOT NULL);

CREATE INDEX IF NOT EXISTS tender_embedding_c_vec_idx
    ON tender_embedding USING hnsw (embedding_c vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ---------------------------------------------------------------------
-- 3) Qayta hisoblash — MODEL CHAQIRMAYDI, sof arifmetika
--
-- Qaytaradi: yangi markaz id si, yoki NULL (namuna yetarli emas).
-- NULL qaytsa CHAQIRUVCHI buni xato deb bilishi shart — jimgina
-- "muvaffaqiyat" emas.
-- ---------------------------------------------------------------------
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
    -- Model berilmasa FAOL modelni olamiz.
    v_model := COALESCE(p_model,
                        (SELECT name FROM embed_model WHERE is_active LIMIT 1));
    IF v_model IS NULL THEN
        RAISE EXCEPTION 'Faol embedding modeli yo''q (embed_model.is_active)';
    END IF;

    -- Markaz QIDIRILADIGAN populatsiya ustidan olinadi. 'tender_open' —
    -- ochiq tenderlar, chunki "Sizga mos" aynan shular ichidan tanlaydi.
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

    -- SOVUQ START: kam namuna -> markaz yozilmaydi, NULL qaytadi.
    IF v_n IS NULL OR v_n < 50 THEN
        RAISE NOTICE 'Markaz hisoblanmadi: namuna % ta (kamida 50 kerak)', COALESCE(v_n, 0);
        RETURN NULL;
    END IF;

    UPDATE embed_centroid SET is_active = FALSE
     WHERE model = v_model AND scope = p_scope AND is_active;

    INSERT INTO embed_centroid (model, scope, dims, vec, n_source, is_active)
    VALUES (v_model, p_scope, 384, v_vec, v_n, TRUE)
    RETURNING id INTO v_id;

    -- Barcha vektorlarni yangi markaz bilan qayta hisoblaymiz.
    -- MODEL CHAQIRILMAYDI: bu shunchaki ayirish + normallashtirish.
    UPDATE tender_embedding
       SET embedding_c = l2_normalize(embedding - v_vec),
           centroid_id = v_id
     WHERE embed_model = v_model
       AND embedding IS NOT NULL;

    RETURN v_id;
END;
$$;

-- ---------------------------------------------------------------------
-- 4) ESKIRGANLIKNI KO'RSATADIGAN ko'rinish
--
-- Bu 2-sinfga qarshi: "xato chiqmadi" != "markaz to'g'ri". Qidiruv
-- eskirgan markaz bilan ham JIMGINA ishlayveradi, faqat yomonroq.
-- Shuning uchun eskirgan sonini ALOHIDA sanaymiz va sinov shuni
-- tekshiradi.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_centroid_stale AS
SELECT em.name                                        AS model,
       (SELECT c.id FROM embed_centroid c
         WHERE c.model = em.name AND c.is_active
         ORDER BY c.computed_at DESC LIMIT 1)          AS faol_markaz,
       count(*) FILTER (WHERE e.embedding IS NOT NULL) AS vektor_jami,
       count(*) FILTER (WHERE e.embedding IS NOT NULL
                          AND e.embedding_c IS NULL)   AS markazlanmagan,
       count(*) FILTER (WHERE e.embedding_c IS NOT NULL
                          AND e.centroid_id IS DISTINCT FROM
                              (SELECT c.id FROM embed_centroid c
                                WHERE c.model = em.name AND c.is_active
                                ORDER BY c.computed_at DESC LIMIT 1))
                                                       AS eskirgan
FROM embed_model em
LEFT JOIN tender_embedding e ON e.embed_model = em.name
WHERE em.is_active
GROUP BY em.name;

COMMENT ON VIEW v_centroid_stale IS
    'Markazlanmagan va ESKIRGAN markaz bilan hisoblangan vektorlar soni. '
    'Ikkalasi ham 0 bo''lishi kerak; aks holda semantik qidiruv jimgina yomonlashadi.';

COMMIT;

-- Birinchi hisoblash (qo'llashning bir qismi).
SELECT recompute_centroid() AS yangi_markaz_id;
SELECT * FROM v_centroid_stale;
