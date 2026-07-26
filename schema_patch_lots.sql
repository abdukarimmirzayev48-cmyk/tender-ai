-- =============================================================================
-- Sxema patch — LOT NOMLARI va BOY POZITSIYA ma'lumoti
-- Ishga tushirish:
--   psql "dbname=xtxarid user=a1234 host=localhost" -f schema_patch_lots.sql
--
-- NEGA KERAK:
--   Ko'p lotli tenderning nomi foydasiz bo'ladi ("Многолотовая процедура"),
--   lekin LOT nomlari aniq: "Оборудование лазерной резки металлов 6,12,30 кВт".
--   Tadbirkor uchun qaror birligi — TENDER emas, LOT.
--
-- MANBA (/urpc, autentifikatsiyasiz):
--   get_lots  {"proc_id":"<id>"}                   -> lot title, total_sum_lot, item_count
--   get_items {"proc_id":<id>,"lot_id":<n>,...}    -> pozitsiya tafsiloti
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. LOT NOMI — get_lots dan
-- ---------------------------------------------------------------------------
ALTER TABLE tender_lot ADD COLUMN IF NOT EXISTS title TEXT;


-- ---------------------------------------------------------------------------
-- 2. POZITSIYA (item) — get_items dan.
--    tender_good (meta.good_maps dan) qoladi — u narx/miqdor uchun.
--    Bu jadval esa YETKAZIB BERISH SHARTLARI va TEXNIK talablarni saqlaydi —
--    yetkazuvchi uchun "bajara olamanmi?" degan savolga javob beradi.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tender_item (
    tender_id        BIGINT  NOT NULL REFERENCES tender(id) ON DELETE CASCADE,
    lot_id           INTEGER NOT NULL,
    item_id          TEXT    NOT NULL,        -- get_items.item_id

    product_code     TEXT,                    -- '28.99.30.000_00069'
    name             TEXT,                    -- 'Listlarni bukish mashinasi'
    unit             TEXT,                    -- 'dona'
    amount_text      TEXT,                    -- '2.00 dona' (xom, formatlangan)
    price_text       TEXT,                    -- ' 138 815.00 Доллар США'
    totalcost_text   TEXT,

    -- YETKAZIB BERISH / KAFOLAT SHARTLARI (eng qimmatli qism)
    delivery_period  INTEGER,                 -- kun (item_delivery_period)
    guarantee        INTEGER,                 -- kun
    prod_year        INTEGER,                 -- talab qilingan ishlab chiqarish yili
    country_of_origin TEXT,
    delivery_address TEXT,
    spec             TEXT,                    -- 'Texnik topshiriqga asosan'

    properties       JSONB,                   -- [{prop_name, val_name}] texnik xarakteristikalar
    raw_json         JSONB NOT NULL,

    fetched_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tender_id, lot_id, item_id)
);

CREATE INDEX IF NOT EXISTS idx_item_tender   ON tender_item(tender_id);
CREATE INDEX IF NOT EXISTS idx_item_delivery ON tender_item(delivery_period);
