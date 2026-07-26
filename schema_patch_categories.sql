-- =============================================================================
-- Sxema patch — KATEGORIYALAR (B bosqich, REJA_UX.md)
-- Ishga tushirish:
--   psql "dbname=xtxarid user=a1234 host=localhost" -f schema_patch_categories.sql
--   keyin: python3 etl_categorize.py   (daraxtni ekadi + tenderlarni belgilaydi)
--
-- Ikki daraja: dim_category ierarxik (parent NULL = level 1).
-- tender_category — har tender qaysi kategoriya(lar)ga tegishli (yaproq kod).
-- =============================================================================

CREATE TABLE IF NOT EXISTS dim_category_uz (
    code       TEXT PRIMARY KEY,          -- 'qurilish', 'qurilish/yol', 'mashina'
    parent     TEXT REFERENCES dim_category_uz(code),
    name_uz    TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 500
);

CREATE TABLE IF NOT EXISTS tender_category (
    tender_id BIGINT NOT NULL REFERENCES tender(id) ON DELETE CASCADE,
    code      TEXT   NOT NULL REFERENCES dim_category_uz(code),
    PRIMARY KEY (tender_id, code)
);

CREATE INDEX IF NOT EXISTS idx_tender_category_code ON tender_category(code);
