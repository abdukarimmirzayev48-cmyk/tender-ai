-- =============================================================================
-- Sxema patch — MAHSULOT/XIZMAT KATALOGI (REJA.md P0-4/5 + xabarnoma)
-- Ishga tushirish:
--   psql "dbname=xtxarid user=a1234 host=localhost" -f schema_patch_catalog.sql
--
-- G'OYA: mijoz o'zi sotadigan mahsulot/xizmatlarni kiritadi (nomi, KATEGORIYASI,
-- narxi). Tizim shu kategoriya/nom bo'yicha tenderlarni avtomatik topadi va
-- yangi mos tender chiqsa belgilaydi (ilova-ichi xabarnoma).
--
-- KATEGORIYA = KO'PRIK: tenderlar allaqachon kategoriyalangan (tender_category),
-- mahsulot ham kategoriyaga bog'lanadi -> moslashtirish deterministik.
-- =============================================================================

CREATE TABLE IF NOT EXISTS catalog_product (
    id            SERIAL PRIMARY KEY,
    company_id    BIGINT,                     -- auth kelganда (hozir NULL = yagona)
    name          TEXT NOT NULL,
    category_code TEXT REFERENCES dim_category_uz(code),   -- NULL = faqat nom bo'yicha
    keywords      TEXT[] NOT NULL DEFAULT '{}',            -- qo'shimcha moslik so'zlari
    unit          TEXT,
    price         NUMERIC(18,2),
    currency      CHAR(3),
    notify        BOOLEAN NOT NULL DEFAULT TRUE,           -- yangi mos tenderда xabar
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_catalog_company ON catalog_product(company_id);
CREATE INDEX IF NOT EXISTS idx_catalog_category ON catalog_product(category_code);

-- Yangi-mos kuzatuvi: foydalanuvchi katalog moslarini oxirgi ko'rgan vaqti.
-- Undan keyin e'lon qilingan mos tenderlar "YANGI" hisoblanadi (badge).
CREATE TABLE IF NOT EXISTS catalog_state (
    id           INTEGER PRIMARY KEY DEFAULT 1,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT catalog_state_singleton CHECK (id = 1)
);
INSERT INTO catalog_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING;
