-- =============================================================================
-- schema_patch_embed_384.sql   —   vektor o'lchamini 1024 -> 384 ga o'tkazish
--
-- NEGA: `schema_patch_ai_chat.sql` `voyage-4-nano` (1024 o'lcham) ni ko'zda
-- tutgan edi. O'LCHOV ko'rsatdiki, u O'RTA DARAJADAGI SERVERDA yaroqsiz:
--
--     voyage-4-nano   344M · 1024 o'lcham ·  8.9 s/bo'lak  -> ~50 SOAT
--     e5-small        118M ·  384 o'lcham ·  0.17 s/bo'lak -> ~56 daqiqa
--
-- Ikkalasi ham 4 CPU ipi, GPU'siz, bir xil matnda (~460 token).
-- 53 barobar farq — "nano" nomi aldamchi: u Qwen3 asosidagi LLM-embedder.
--
-- `intfloat/multilingual-e5-small` — 100+ til (rus va o'zbek ham),
-- MIT litsenziya, 118M parametr. Korpus aralash alifboda bo'lgani uchun
-- ko'p tillilik majburiy.
--
-- XAVFSIZ: barcha `embedding` qiymatlari hozir NULL (vektorlash hali
-- boshlanmagan), shuning uchun tur o'zgarishi MA'LUMOT YO'QOTMAYDI.
-- Patch buni COMMIT dan oldin TEKSHIRADI.
--
-- QO'LLASH:
--     psql -d xtxarid -v ON_ERROR_STOP=1 -f schema_patch_embed_384.sql
--
-- Reja: reja_ai_chat.md §16.18
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

-- -----------------------------------------------------------------------------
-- 0. XAVFSIZLIK TEKSHIRUVI — vektor bor bo'lsa TO'XTAYMIZ
--
--    Tur o'zgarishi mavjud vektorlarni YAROQSIZ qiladi (boshqa model,
--    boshqa fazo). Ular bo'lsa — avval ataylab o'chirish kerak, patch
--    buni O'ZI qilmaydi.
-- -----------------------------------------------------------------------------
DO $$
DECLARE n INT;
BEGIN
    SELECT count(*) INTO n FROM doc_chunk WHERE embedding IS NOT NULL;
    IF n > 0 THEN
        RAISE EXCEPTION 'doc_chunk da % ta VEKTOR bor. Ular 1024 o''lchamda '
                        'va 384 ga to''g''ri kelmaydi. Ataylab o''chiring: '
                        'UPDATE doc_chunk SET embedding=NULL, embed_model=NULL;', n;
    END IF;
    SELECT count(*) INTO n FROM tender_embedding;
    IF n > 0 THEN
        RAISE EXCEPTION 'tender_embedding da % ta qator bor. Tozalang: '
                        'TRUNCATE tender_embedding;', n;
    END IF;
END $$;


-- -----------------------------------------------------------------------------
-- 1. HNSW indekslarini VAQTINCHA olib tashlaymiz
--    Ustun turi o'zgarganda indeks yaroqsiz bo'ladi.
-- -----------------------------------------------------------------------------
DROP INDEX IF EXISTS doc_chunk_vec_idx;
DROP INDEX IF EXISTS tender_embedding_vec_idx;


-- -----------------------------------------------------------------------------
-- 2. Ustun turi
-- -----------------------------------------------------------------------------
ALTER TABLE doc_chunk        ALTER COLUMN embedding TYPE vector(384);
ALTER TABLE tender_embedding ALTER COLUMN embedding TYPE vector(384);


-- -----------------------------------------------------------------------------
-- 3. Indekslarni qaytaramiz
--
--    m=16, ef_construction=64 — pgvector standarti. O'RTA SERVER uchun
--    yetarli: 20k vektorda indeks ~30 MB va qurish bir necha soniya.
--    Kattaroq `m` sifatni biroz oshiradi, lekin xotirani ham oshiradi.
-- -----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS doc_chunk_vec_idx
    ON doc_chunk USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS tender_embedding_vec_idx
    ON tender_embedding USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);


-- -----------------------------------------------------------------------------
-- 4. Faol modelni almashtiramiz
--
--    `embed_model` aynan shu holat uchun yaratilgan: qaysi vektor qaysi
--    model bilan yasalganini yozadi va eski vektorlar jimgina
--    ishlatilmasligini ta'minlaydi.
-- -----------------------------------------------------------------------------
UPDATE embed_model SET is_active = FALSE WHERE is_active;

INSERT INTO embed_model (name, dims, provider, is_active, note)
VALUES ('multilingual-e5-small', 384, 'local', TRUE,
        'intfloat/multilingual-e5-small · MIT · 118M parametr · 100+ til. '
        'O''rta serverda 4 CPU ipida ~0.17 s/bo''lak (o''lchangan). '
        'PREFIKS MAJBURIY: "query: " va "passage: ".')
ON CONFLICT (name) DO UPDATE
    SET dims = EXCLUDED.dims, provider = EXCLUDED.provider,
        is_active = TRUE, note = EXCLUDED.note;

COMMENT ON COLUMN doc_chunk.embedding IS
    '384 o''lchamli vektor (multilingual-e5-small). Model almashtirilsa '
    'BU USTUN TURI ham o''zgarishi kerak — `embed_model.dims` bilan mos '
    'bo''lishi SHART, aks holda `etl_embed.py` yozishdan oldin to''xtaydi.';


-- -----------------------------------------------------------------------------
-- 5. TEKSHIRUV
-- -----------------------------------------------------------------------------
DO $$
DECLARE
    d1 INT; d2 INT; m TEXT; md INT;
BEGIN
    SELECT atttypmod INTO d1 FROM pg_attribute
     WHERE attrelid = 'doc_chunk'::regclass AND attname = 'embedding';
    SELECT atttypmod INTO d2 FROM pg_attribute
     WHERE attrelid = 'tender_embedding'::regclass AND attname = 'embedding';
    -- pgvector `atttypmod` da o'lchamni TO'G'RIDAN-TO'G'RI saqlaydi
    IF d1 <> 384 OR d2 <> 384 THEN
        RAISE EXCEPTION 'o''lcham noto''g''ri: doc_chunk=%, tender_embedding=%', d1, d2;
    END IF;

    SELECT name, dims INTO m, md FROM embed_model WHERE is_active;
    IF md <> 384 THEN
        RAISE EXCEPTION 'faol model % o''lchami % — 384 kutilgandi', m, md;
    END IF;

    RAISE NOTICE 'TEKSHIRUV O''TDI — faol model: % (% o''lcham).', m, md;
END $$;

COMMIT;


-- =============================================================================
-- ROLLBACK (1024 ga qaytarish):
--   UPDATE doc_chunk SET embedding = NULL, embed_model = NULL;
--   TRUNCATE tender_embedding;
--   DROP INDEX doc_chunk_vec_idx, tender_embedding_vec_idx;
--   ALTER TABLE doc_chunk        ALTER COLUMN embedding TYPE vector(1024);
--   ALTER TABLE tender_embedding ALTER COLUMN embedding TYPE vector(1024);
--   -- indekslarni qayta yarating va embed_model da voyage-4-nano ni yoqing
-- =============================================================================
