-- =====================================================================
-- HUBLIK TUZATMASI (CSLS) — semantik taklifni "hub" kodlardan tozalash
-- =====================================================================
--
-- MUAMMO (o'lchangan):
--   `86.90` ("Услуга по лабораторному анализу | Услуга по стерилизации
--   медицинских изделий") 25 ta sinov mahsulotining 14 tasida BIRINCHI
--   o'ringa chiqdi — bor-yo'g'i 1 ta ochiq tenderi bo'lsa ham.
--
--   Sabab HUBLIK: nomlari umumiy tibbiy-xizmat tilida, shuning uchun
--   vektori har qanday tibbiy so'rovga yaqin turadi.
--
--       86.90 ga kosinus > 0.3 bo'lgan kodlar: 183
--       32.50 ga (aniq kod)                  : 124
--
--   Bu yuqori o'lchamli embedding fazolarining ma'lum kasalligi: ba'zi
--   nuqtalar KO'PCHILIKNING eng yaqin qo'shnisi bo'lib qoladi.
--
-- YECHIM — CSLS (Cross-domain Similarity Local Scaling):
--   Har kod uchun uning O'Z qo'shnilariga o'rtacha yaqinligi (`hub_bias`)
--   hisoblanadi. Ranglashda shu ayiriladi:
--
--       skor(q, d) = cos(q, d) - hub_bias(d)
--
--   "Hammaga yaqin" kod katta `hub_bias` oladi va jazolanadi; tor,
--   aniq kod esa kichik bias bilan yuqoriga chiqadi.
--
-- NEGA SQL DA: model chaqirilmaydi — bu mavjud vektorlar ustidagi
-- arifmetika. 1146 kod uchun bir necha soniya.
--
-- Qo'llash:
--   psql "$XT_DB_DSN" -f schema_patch_goodcode_2.sql
-- =====================================================================

BEGIN;

ALTER TABLE good_code_embedding
    ADD COLUMN IF NOT EXISTS hub_bias   REAL,
    ADD COLUMN IF NOT EXISTS hub_k      INT,
    ADD COLUMN IF NOT EXISTS hub_at     TIMESTAMPTZ;

COMMENT ON COLUMN good_code_embedding.hub_bias IS
    'Kodning O''Z qo''shnilariga o''rtacha kosinusi (CSLS). Ranglashda '
    'ayiriladi — "hammaga yaqin" kod jazolanadi.';

-- ---------------------------------------------------------------------
-- Hisoblash. `k` — nechta qo'shni bo'yicha o'rtacha olinadi.
--
-- k=10: standart CSLS qiymati. Kichik bo'lsa shovqinli, katta bo'lsa
-- bias butun korpus o'rtachasiga aylanib, farqlash kuchini yo'qotadi.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION recompute_hub_bias(p_k INT DEFAULT 10)
RETURNS TABLE(kodlar BIGINT, o_rtacha REAL, eng_katta REAL)
LANGUAGE plpgsql AS $$
BEGIN
    IF p_k < 3 THEN
        RAISE EXCEPTION 'k juda kichik (%): CSLS shovqinga aylanadi', p_k;
    END IF;

    UPDATE good_code_embedding g
       SET hub_bias = s.o_rt,
           hub_k    = p_k,
           hub_at   = now()
      FROM (
        SELECT a.code,
               avg(1 - (a.embedding_c <=> n.embedding_c))::REAL AS o_rt
        FROM good_code_embedding a
        CROSS JOIN LATERAL (
            SELECT b.embedding_c
            FROM good_code_embedding b
            WHERE b.embedding_c IS NOT NULL
              AND b.code <> a.code          -- O'ZINI hisobga olmaymiz (cos=1)
            ORDER BY b.embedding_c <=> a.embedding_c
            LIMIT p_k
        ) n
        WHERE a.embedding_c IS NOT NULL
        GROUP BY a.code
      ) s
     WHERE g.code = s.code;

    RETURN QUERY
      SELECT count(*), avg(hub_bias)::REAL, max(hub_bias)::REAL
        FROM good_code_embedding WHERE hub_bias IS NOT NULL;
END;
$$;

-- ---------------------------------------------------------------------
-- ESKIRGANLIK: markaz qayta hisoblansa `embedding_c` o'zgaradi, ya'ni
-- `hub_bias` ham eskiradi. Buni JIMGINA qoldirmaymiz.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_hub_stale AS
SELECT count(*) FILTER (WHERE embedding_c IS NOT NULL)                  AS vektorli,
       count(*) FILTER (WHERE embedding_c IS NOT NULL
                          AND hub_bias IS NULL)                          AS biassiz,
       count(*) FILTER (WHERE hub_at IS NOT NULL AND hub_at <
                              (SELECT max(computed_at) FROM embed_centroid
                                WHERE is_active))                        AS eskirgan
FROM good_code_embedding;

COMMENT ON VIEW v_hub_stale IS
    'Hublik tuzatmasi hisoblanmagan yoki markazdan ESKI qolgan kodlar. '
    'Ikkalasi ham 0 bo''lishi kerak.';

COMMIT;

SELECT * FROM recompute_hub_bias(10);
SELECT * FROM v_hub_stale;
