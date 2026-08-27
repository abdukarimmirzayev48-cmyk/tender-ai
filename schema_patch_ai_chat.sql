-- =====================================================================
-- schema_patch_ai_chat.sql
-- AI-Chat (RAG + tool-calling) va semantik qidiruv uchun sxema
--
-- Bog'liqlik: xt_xarid_schema.sql + qolgan barcha schema_patch_*.sql
--             (ayniqsa schema_patch_auth_2.sql — company_account bu yerda FK).
-- Idempotent: qayta yurgizish xavfsiz (IF NOT EXISTS).
--
-- Qo'llash:
--   psql -d xtxarid -f schema_patch_ai_chat.sql
--
-- Orqaga qaytarish: fayl oxiridagi ROLLBACK bo'limiga qarang.
--
-- Reja: reja_ai_chat.md   ·   Kod: api/ai_chat.py
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 0. Kengaytmalar
-- ---------------------------------------------------------------------
-- pgvector: PostgreSQL 13+. HNSW indeksi uchun pgvector >= 0.5.0
--   Windows: Postgres o'rnatgichidagi "Stack Builder" orqali yoki
--            https://github.com/pgvector/pgvector (nmake bilan).
-- MUHIM: bu kengaytma bo'lmasa PATCH SHU YERDA to'xtaydi va hech narsa
-- yaratilmaydi (BEGIN ichida) — yarim qo'llangan holat bo'lmaydi.
CREATE EXTENSION IF NOT EXISTS vector;

-- Diakritikani olib tashlash (é -> e). DIQQAT: `unaccent` KIRILLNI LOTINGA
-- o'girmaydi. Lotin<->kirill masalasi `api/translit.py` da hal qilingan va
-- quyidagi tsvector triggerlari AYNAN o'sha yig'ish (fold) jadvalini
-- takrorlaydi — ular sinxron bo'lishi SHART.
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---------------------------------------------------------------------
-- 1. Embedding registri — qaysi model, qaysi o'lcham
--
--    NEGA: embedding modelini almashtirsak (voyage-4-nano -> voyage-4),
--    eski vektorlar YAROQSIZ bo'ladi. Ularni jimgina ishlatib yubormaslik
--    uchun har vektorda model yozib qo'yiladi, faol model esa shu yerda.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS embed_model (
    name        TEXT PRIMARY KEY,          -- 'voyage-4-nano', 'voyage-4', 'bge-m3'
    dims        SMALLINT NOT NULL,         -- 1024
    provider    TEXT NOT NULL,             -- 'voyage' | 'local'
    is_active   BOOLEAN NOT NULL DEFAULT FALSE,
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Bir vaqtda faqat BITTA faol model
CREATE UNIQUE INDEX IF NOT EXISTS embed_model_one_active
    ON embed_model ((TRUE)) WHERE is_active;

INSERT INTO embed_model (name, dims, provider, is_active, note)
VALUES ('voyage-4-nano', 1024, 'local', TRUE,
        'Apache 2.0, lokal ishlaydi, API kaliti kerak emas. '
        'voyage-4 ga o''tish: bir xil 1024 o''lcham, faqat provider o''zgaradi.')
ON CONFLICT (name) DO NOTHING;

-- ---------------------------------------------------------------------
-- 2. Alifbo yig'ish (fold) — `api/translit.py` SQL_FOLD ning NUSXASI
--
--    translit.py:  translate(lower(col COLLATE "unicode"), 'эёыйщьъ', 'ееииш')
--    Bu yerda ham AYNAN shu jadval ishlatiladi, chunki qidiruv so'rovi
--    `translit.variants()` dan YIG'ILGAN shaklda keladi. Ikki tomon bir xil
--    alifboda bo'lmasa gibrid qidiruvning leksik yarmi hech narsa topmaydi.
--
--    IMMUTABLE: tsvector triggerida ishlatiladi.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION tai_fold(txt TEXT) RETURNS TEXT AS $$
    SELECT translate(lower(coalesce(txt, '')), 'эёыйщьъ', 'ееииш')
$$ LANGUAGE sql IMMUTABLE;

COMMENT ON FUNCTION tai_fold(TEXT) IS
    'Kirill yig''ish jadvali — api/translit.py SQL_FOLD bilan AYNAN bir xil '
    'bo''lishi SHART. O''zgartirilsa ikkala joyda birga o''zgartiriladi va '
    'search_tsv ustunlari qayta hisoblanadi.';

-- ---------------------------------------------------------------------
-- 3. Hujjat bo'laklari (chunk) — RAG ning "R" qismi
--
--    char_start/char_end MAJBURIY: "qora quti bo'lmasin" tamoyili —
--    chat javobidagi har iqtibos hujjat matnining aniq joyiga bog'lanadi.
--    Ofset `tender_document_text.text` ichida o'lchanadi.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS doc_chunk (
    id           BIGSERIAL PRIMARY KEY,
    tender_id    BIGINT NOT NULL REFERENCES tender(id) ON DELETE CASCADE,
    file_ref     TEXT,                     -- tender_document.file_ref; NULL = tender matni
    chunk_no     INTEGER NOT NULL,
    text         TEXT NOT NULL,
    char_start   INTEGER NOT NULL,
    char_end     INTEGER NOT NULL,
    token_count  INTEGER,
    lang         CHAR(2),                  -- 'uz' | 'ru' | 'en' (taxminiy)
    embedding    vector(1024),             -- NULL = hali hisoblanmagan
    embed_model  TEXT REFERENCES embed_model(name),
    content_hash TEXT NOT NULL,            -- bo'lak matnining SHA-256
    search_tsv   tsvector,                 -- gibrid qidiruvning leksik tomoni
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tender_id, file_ref, chunk_no)
);

CREATE INDEX IF NOT EXISTS doc_chunk_tender_idx  ON doc_chunk (tender_id);
CREATE INDEX IF NOT EXISTS doc_chunk_pending_idx ON doc_chunk (id) WHERE embedding IS NULL;
CREATE INDEX IF NOT EXISTS doc_chunk_tsv_idx     ON doc_chunk USING gin (search_tsv);

CREATE OR REPLACE FUNCTION doc_chunk_tsv_trg() RETURNS trigger AS $$
BEGIN
    NEW.search_tsv := to_tsvector('simple', tai_fold(unaccent(COALESCE(NEW.text, ''))));
    RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS doc_chunk_tsv ON doc_chunk;
CREATE TRIGGER doc_chunk_tsv BEFORE INSERT OR UPDATE OF text ON doc_chunk
    FOR EACH ROW EXECUTE FUNCTION doc_chunk_tsv_trg();

-- HNSW: qidiruv tez, qurish sekin. ~2600 hujjat uchun ayni muddao.
-- TAVSIYA: birinchi to'liq vektorlashdan KEYIN indeksni DROP/CREATE qiling —
-- bo'sh jadvalga qurib, keyin 130k qator qo'shishdan 3-5 barobar tezroq.
CREATE INDEX IF NOT EXISTS doc_chunk_vec_idx
    ON doc_chunk USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ---------------------------------------------------------------------
-- 4. Tender darajasidagi vektor — "niyat bo'yicha" ro'yxat qidiruvi
--
--    NEGA ALOHIDA: doc_chunk hujjat ICHIDAN javob topadi;
--    bu esa "menga mos tender bormi?" savoliga 863 tenderdan tanlaydi.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tender_embedding (
    tender_id    BIGINT PRIMARY KEY REFERENCES tender(id) ON DELETE CASCADE,
    embedding    vector(1024) NOT NULL,
    embed_model  TEXT NOT NULL REFERENCES embed_model(name),
    content_hash TEXT NOT NULL,            -- ai.build_input() natijasining hashi
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS tender_embedding_vec_idx
    ON tender_embedding USING hnsw (embedding vector_cosine_ops);

-- Tenderning leksik indeksi (gibrid qidiruvning ikkinchi tomoni)
ALTER TABLE tender ADD COLUMN IF NOT EXISTS search_tsv tsvector;
CREATE INDEX IF NOT EXISTS tender_tsv_idx ON tender USING gin (search_tsv);

CREATE OR REPLACE FUNCTION tender_tsv_trg() RETURNS trigger AS $$
BEGIN
    NEW.search_tsv := to_tsvector('simple', tai_fold(unaccent(
        COALESCE(NEW.name, '') || ' ' || COALESCE(NEW.company_name, ''))));
    RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tender_tsv ON tender;
CREATE TRIGGER tender_tsv BEFORE INSERT OR UPDATE OF name, company_name ON tender
    FOR EACH ROW EXECUTE FUNCTION tender_tsv_trg();

-- Mavjud qatorlarni to'ldirish (bir marta; ~863 qator — tez).
UPDATE tender SET search_tsv = to_tsvector('simple', tai_fold(unaccent(
        COALESCE(name, '') || ' ' || COALESCE(company_name, ''))))
WHERE search_tsv IS NULL;

-- ---------------------------------------------------------------------
-- 5. Chat sessiyalari
--
--    company_id NOT NULL — bu loyihadagi BIRINCHI jadval bo'lib, ko'p-
--    ijarachilikni MAJBURIY qiladi. Sabab: chat tool'lari bazaga
--    to'g'ridan-to'g'ri kiradi, "hozircha bitta kompaniya" rejimi bu yerda
--    xavfli. Shuning uchun reja J1 (company_id filtri) ni bloklovchi deb
--    belgilaydi — reja_ai_chat.md §10.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_session (
    id          UUID PRIMARY KEY,
    company_id  INTEGER NOT NULL REFERENCES company_account(id) ON DELETE CASCADE,
    tender_id   BIGINT REFERENCES tender(id) ON DELETE SET NULL,  -- NULL = global chat
    title       TEXT,                      -- birinchi savoldan avtomatik
    lang        CHAR(2) NOT NULL DEFAULT 'uz',
    archived    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chat_session_company_idx
    ON chat_session (company_id, updated_at DESC) WHERE NOT archived;
CREATE INDEX IF NOT EXISTS chat_session_tender_idx ON chat_session (tender_id);

-- ---------------------------------------------------------------------
-- 6. Chat xabarlari
--
--    content — Anthropic Messages API bloklari MASSIVI, o'zgartirilmasdan:
--      [{"type":"text","text":"..."},
--       {"type":"tool_use","id":"toolu_..","name":"search_tenders","input":{}}]
--    NEGA XOM: keyingi navbatda API ga aynan shu ko'rinishda qaytariladi.
--
--    DIQQAT: `tool_use` bloki saqlangan bo'lsa, unga MOS `tool_result` ham
--    bo'lishi shart — aks holda keyingi so'rov 400 beradi. Shuning uchun
--    ai_chat.py faqat YAKUNIY (matnli) javobni saqlaydi.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_message (
    id            BIGSERIAL PRIMARY KEY,
    session_id    UUID NOT NULL REFERENCES chat_session(id) ON DELETE CASCADE,
    seq           INTEGER NOT NULL,        -- sessiya ichida tartib
    role          TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content       JSONB NOT NULL,
    citations     JSONB,                   -- [{tender_id, file_ref, char_start, char_end, snippet}]
    model         TEXT,
    input_tokens  INTEGER,
    output_tokens INTEGER,
    cache_read_tokens  INTEGER,
    cache_write_tokens INTEGER,
    latency_ms    INTEGER,
    stop_reason   TEXT,
    error         TEXT,                    -- muvaffaqiyatsiz javob ham SAQLANADI
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, seq)
);

CREATE INDEX IF NOT EXISTS chat_message_session_idx ON chat_message (session_id, seq);

COMMENT ON COLUMN chat_message.error IS
    'Xato matni. "Jimgina o''tkazib yuborilmaydi" tamoyili: muvaffaqiyatsiz '
    'javob ham jurnalda qoladi. Bunday qatorlar TARIXGA QO''SHILMAYDI.';

-- ---------------------------------------------------------------------
-- 7. Tool chaqiruvlari jurnali — audit va nosozlik qidirish
--
--    NEGA ALOHIDA JADVAL: chat javobi noto'g'ri bo'lsa, "model yolg'on
--    aytdimi yoki tool noto'g'ri ma'lumot qaytardimi?" degan savolga
--    faqat shu jadval javob beradi (reja_ai_chat.md §4.3).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_tool_call (
    id          BIGSERIAL PRIMARY KEY,
    session_id  UUID NOT NULL REFERENCES chat_session(id) ON DELETE CASCADE,
    message_id  BIGINT REFERENCES chat_message(id) ON DELETE CASCADE,
    tool_name   TEXT NOT NULL,
    args        JSONB NOT NULL,
    result_rows INTEGER,                   -- nechta qator qaytdi
    ok          BOOLEAN NOT NULL,
    error       TEXT,
    duration_ms INTEGER,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chat_tool_call_session_idx ON chat_tool_call (session_id);
CREATE INDEX IF NOT EXISTS chat_tool_call_name_idx    ON chat_tool_call (tool_name, created_at DESC);

-- ---------------------------------------------------------------------
-- 8. AI xarajat hisobi
--
--    NEGA KERAK: ai_analysis content_hash bilan keshlanadi — chat esa
--    HAR SAVOLDA pul sarflaydi. Cheklovsiz chat = cheklovsiz hisob.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_usage (
    company_id     INTEGER NOT NULL REFERENCES company_account(id) ON DELETE CASCADE,
    period         DATE NOT NULL,          -- oyning 1-kuni
    kind           TEXT NOT NULL,          -- 'chat' | 'summary_v1' | 'match_v2' | 'gonogo_v2' | 'embed'
    model          TEXT NOT NULL,
    calls          INTEGER NOT NULL DEFAULT 0,
    input_tokens   BIGINT NOT NULL DEFAULT 0,
    output_tokens  BIGINT NOT NULL DEFAULT 0,
    cache_read_tokens  BIGINT NOT NULL DEFAULT 0,
    cache_write_tokens BIGINT NOT NULL DEFAULT 0,
    cost_usd       NUMERIC(12,4) NOT NULL DEFAULT 0,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, period, kind, model)
);

CREATE TABLE IF NOT EXISTS ai_quota (
    company_id       INTEGER PRIMARY KEY REFERENCES company_account(id) ON DELETE CASCADE,
    monthly_usd      NUMERIC(10,2) NOT NULL DEFAULT 50.00,
    daily_messages   INTEGER NOT NULL DEFAULT 100,
    enabled          BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Joriy oydagi sarf (endpoint va kvota tekshiruvi shu ko'rinishdan o'qiydi)
CREATE OR REPLACE VIEW v_ai_spend_current AS
SELECT u.company_id,
       SUM(u.cost_usd)                          AS spent_usd,
       COALESCE(q.monthly_usd, 50.00)           AS limit_usd,
       COALESCE(q.enabled, TRUE)                AS enabled
FROM ai_usage u
LEFT JOIN ai_quota q ON q.company_id = u.company_id
WHERE u.period = date_trunc('month', CURRENT_DATE)::date
GROUP BY u.company_id, q.monthly_usd, q.enabled;

COMMIT;

-- =====================================================================
-- KEYINGI PATCH (bu yerda EMAS):
--   tender_requirement — AI ajratgan talablar (REJA.md D bosqichi)
--   tender_decision    — ish jarayoni holati (REJA.md I bosqichi)
--   tender_award       — g'olib ma'lumoti (analitika uchun)
-- =====================================================================

-- =====================================================================
-- ROLLBACK (kerak bo'lsa, qo'lda):
--
--   DROP VIEW  IF EXISTS v_ai_spend_current;
--   DROP TABLE IF EXISTS ai_quota, ai_usage, chat_tool_call,
--                        chat_message, chat_session,
--                        tender_embedding, doc_chunk, embed_model CASCADE;
--   DROP TRIGGER  IF EXISTS tender_tsv ON tender;
--   DROP FUNCTION IF EXISTS tender_tsv_trg, doc_chunk_tsv_trg, tai_fold;
--   ALTER TABLE tender DROP COLUMN IF EXISTS search_tsv;
--   -- vector kengaytmasi boshqa joyda ishlatilmasa:
--   -- DROP EXTENSION IF EXISTS vector;
-- =====================================================================
