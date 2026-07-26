-- =============================================================================
-- Sxema patch — ANIQLIK QUVURI (H bosqich, REJA.md NFT)
-- Ishga tushirish:
--   psql "dbname=xtxarid user=a1234 host=localhost" -f schema_patch_freshness.sql
--
-- MAQSAD: "tender e'lon qilingandan qancha keyin biz topdik?" ni O'LCHASH.
--   - first_seen_at: biz tenderni BIRINCHI qachon ko'rdik (fetched_at emas —
--     u har qayta-yurishда yangilanadi; bu esa faqat INSERT'да o'rnatiladi va
--     UPSERT'да saqlanib qoladi).
--   - etl_run: har ETL yurishi jurnali (sog'lik + yangi topilganlar soni).
-- =============================================================================

-- 1) first_seen_at — biz birinchi ko'rgan vaqt
ALTER TABLE tender ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- Mavjud yozuvlar uchun backfill: eng yaqin taxmin = fetched_at (biz yuklagan vaqt).
-- (Faqat default-now() qo'yilgan, ya'ni hali backfill qilinmagan qatorlar.)
UPDATE tender SET first_seen_at = fetched_at
WHERE fetched_at IS NOT NULL AND first_seen_at > fetched_at;

-- Aniqlash-kechikishi bo'yicha tez saralash uchun
CREATE INDEX IF NOT EXISTS idx_tender_first_seen ON tender(first_seen_at);

-- MUHIM: ETL UPSERT'lari first_seen_at ni SET qilmaydi (ustun ro'yxatida yo'q),
-- shuning uchun qayta-yurishда u O'ZGARMAYDI — kod o'zgartirish shart emas.

-- 2) etl_run — har yurish jurnali (sog'lik + metrika)
CREATE TABLE IF NOT EXISTS etl_run (
    id              SERIAL PRIMARY KEY,
    source_platform TEXT NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'running',  -- running | ok | error
    found           INTEGER,      -- yurishdan keyin platformadagi jami tender
    new             INTEGER,      -- shu yurishда birinchi marta ko'rilganlar
    error           TEXT
);
CREATE INDEX IF NOT EXISTS idx_etl_run_platform ON etl_run(source_platform, started_at DESC);
