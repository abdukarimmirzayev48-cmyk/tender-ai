-- =============================================================================
-- Sxema patch — AI TAHLIL QATLAMI (5a bosqich)
-- Ishga tushirish:
--   psql "dbname=xtxarid user=a1234 host=localhost" -f schema_patch_ai.sql
--
-- MAQSAD: Claude'ning har tender uchun bergan tahlilini saqlash.
--
-- ENG MUHIM QAROR — KESHLASH:
--   Tender ma'lumoti bir marta yig'ilgach O'ZGARMAYDI. Shuning uchun AI
--   natijasini shu yerda saqlaymiz va `content_hash` bilan taqqoslaymiz:
--     - hash bir xil  -> AI QAYTA CHAQIRILMAYDI (xarajat 0)
--     - hash o'zgargan -> demak manba ma'lumoti yangilangan, qayta tahlil
--   Foydalanuvchi bitta tenderni 100 marta ochsa ham API'ga bitta so'rov
--   ketadi. Bu prompt-caching'dan ham muhimroq tejamkorlik.
--
--   `kind` — tahlil turi ('summary_v1'). Prompt/sxema o'zgarsa versiyani
--   oshiramiz ('summary_v2') va eski natijalar saqlanib qoladi.
-- =============================================================================

CREATE TABLE IF NOT EXISTS ai_analysis (
    tender_id      BIGINT NOT NULL REFERENCES tender(id) ON DELETE CASCADE,
    kind           TEXT   NOT NULL,          -- 'summary_v1'
    content_hash   TEXT   NOT NULL,          -- kirish ma'lumotining SHA-256 i

    result         JSONB  NOT NULL,          -- Claude qaytargan strukturali javob

    -- Audit / xarajat kuzatuvi
    model          TEXT,
    input_tokens   INTEGER,
    output_tokens  INTEGER,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (tender_id, kind)
);

CREATE INDEX IF NOT EXISTS idx_ai_kind ON ai_analysis(kind);

-- Kategoriya teglari bo'yicha qidiruv (5b — semantik moslashtirish uchun)
CREATE INDEX IF NOT EXISTS idx_ai_tags
    ON ai_analysis USING GIN ((result -> 'category_tags'));
