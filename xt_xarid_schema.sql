-- =============================================================================
-- xt-xarid.uz  |  ref_tender_public  →  Normalizatsiyalangan PostgreSQL sxemasi
-- Manba: JSON-RPC 2.0 endpoint  POST https://api.xt-xarid.uz/rpc
--        { "method": "ref", "params": { "ref": "ref_tender_public", "op": "read" } }
--
-- Dizayn tamoyillari:
--   1. Denormalizatsiyalangan RPC javobini 3 darajaga ajratamiz: tender → lot → good
--   2. Xom javobni har doim raw_json (JSONB) da saqlaymiz — kelajakda sxema
--      o'zgarsa yoki yangi maydon chiqsa, ma'lumot yo'qolmaydi (ETL "landing" qatlami)
--   3. Barcha sana maydonlari NULLABLE — chunki ular tenderning status'iga bog'liq
--   4. currency har yozuvda saqlanadi (USD ham, UZS ham uchraydi)
--   5. area ierarxik string sifatida ham, leaf-kod sifatida ham saqlanadi
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 0. YORDAMCHI REESTRLAR (dimension jadvallari)
--    Bular ref_area, ref_status_* reestrlaridan bir marta yuklab olinadi va
--    kamdan-kam o'zgaradi. Fakt jadvallar bularга FK bilan bog'lanadi.
-- ---------------------------------------------------------------------------

-- Hudud ierarxiyasi (ref_area) — respublika → viloyat → tuman
CREATE TABLE dim_area (
    area_id       TEXT PRIMARY KEY,          -- masalan '2140' (leaf) yoki '33' (root)
    parent_id     TEXT REFERENCES dim_area(area_id),
    name_uz       TEXT,
    name_ru       TEXT,
    level         SMALLINT,                  -- 0=respublika, 1=viloyat, 2=tuman
    full_path     TEXT                       -- '33.2137.2138.2140'
);

-- Status lug'ati (ref_status_tender, ref_status_reduction, ref_status_ad, ...)
-- Har xil tur (tender/auksion/dokon) uchun statuslar bir jadvalda, 'domain' bilan ajratiladi
CREATE TABLE dim_status (
    status_code   TEXT NOT NULL,             -- 'open', 'docs_objections', 'not_realized', ...
    domain        TEXT NOT NULL,             -- 'tender' | 'reduction' | 'ad' | 'selection'
    name_uz       TEXT,
    name_ru       TEXT,
    is_terminal   BOOLEAN DEFAULT FALSE,      -- tugallangan/bekor qilinganmi (dashboard filtri uchun)
    PRIMARY KEY (status_code, domain)
);

-- Tovar kategoriyalari (meta.good_maps[].category dan yig'iladi)
CREATE TABLE dim_category (
    category_uid  UUID PRIMARY KEY,          -- 'af7d5ed7-7f5f-454f-997b-2dd8d12355d5'
    code          TEXT,                      -- '28.41.24.190' (milliy klassifikator kodi)
    title_ru      TEXT,
    title_uz      TEXT
);


-- ---------------------------------------------------------------------------
-- 1. TENDER (asosiy fakt jadvali) — bitta RPC yozuvining skalyar qismi
-- ---------------------------------------------------------------------------
CREATE TABLE tender (
    id                          BIGINT PRIMARY KEY,        -- 8062765
    type                        TEXT,                      -- 'tender' | 'reduction' | 'shop'
    name                        TEXT,                      -- 'Многолотовая процедура'
    status                      TEXT,                      -- FK → dim_status(status_code, 'tender')

    -- Moliyaviy
    totalcost                   NUMERIC(18,2),             -- 991000
    currency                    CHAR(3),                   -- 'USD' | 'UZS' — HARDCODE QILMANG
    lang                        TEXT,                      -- 'uz-UZ@cyrillic'

    -- Struktura (ko'p lotli tender ko'rsatkichlari)
    is_new_multilot             BOOLEAN,
    lot_count                   INTEGER,
    good_count                  INTEGER,
    part_count                  INTEGER,
    participants_of_joint_purchase INTEGER DEFAULT 0,
    green                       BOOLEAN DEFAULT FALSE,      -- "yashil xarid"mi

    -- Hudud
    area_path                   TEXT,                      -- '33.2137.2138.2140' (xom string)
    area_leaf_id                TEXT REFERENCES dim_area(area_id),  -- '2140' — indekslash uchun

    -- Buyurtmachi (company)
    buyer_org_id                BIGINT,                    -- 1163 (BUYURTMACHI
                                                           --  tashkiloti, manba
                                                           --  platformadan. Bizning
                                                           --  ijarachimiz EMAS!)
    company_name                TEXT,                      -- 'АО "Quyuv-mexanika zavodi"'

    -- Shartnoma (ko'pincha null, tugatilgach to'ladi)
    contract_num                TEXT,
    contract_number             TEXT,
    contract_id                 BIGINT,

    -- Sanalar (BARCHASI NULLABLE — status'ga bog'liq)
    created_at                  TIMESTAMPTZ,
    inserted_at                 TIMESTAMPTZ,
    publicated_at               TIMESTAMPTZ,
    starting_date               TIMESTAMPTZ,
    agree_at                    TIMESTAMPTZ,
    close_at                    TIMESTAMPTZ,
    ends_at                     TIMESTAMPTZ,
    close_docs_objections_at    TIMESTAMPTZ,

    -- Qolgan vaqt (sekundlarda; snapshot momentiga nisbatan — vaqt o'tsa eskiradi)
    docs_objections_remain_time INTEGER,
    remain_time                 INTEGER,

    -- ETL / audit
    raw_json                    JSONB NOT NULL,            -- to'liq xom javob (govno shu yerda qoladi)
    fetched_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),  -- biz qachon yig'ib oldik
    source_ref                  TEXT DEFAULT 'ref_tender_public'
);

-- Indekslar — dashboard filtrlari va agregatsiyalari uchun eng muhimlari
CREATE INDEX idx_tender_status      ON tender(status);
CREATE INDEX idx_tender_area_leaf   ON tender(area_leaf_id);
CREATE INDEX idx_tender_buyer_org   ON tender(buyer_org_id);
CREATE INDEX idx_tender_created     ON tender(created_at);
CREATE INDEX idx_tender_currency    ON tender(currency);
CREATE INDEX idx_tender_type        ON tender(type);


-- ---------------------------------------------------------------------------
-- 2. LOT  — meta.lots[] dan
-- ---------------------------------------------------------------------------
CREATE TABLE tender_lot (
    tender_id       BIGINT NOT NULL REFERENCES tender(id) ON DELETE CASCADE,
    lot_id          INTEGER NOT NULL,          -- lot raqami tender ichida (1, 2, ...)
    item_count      INTEGER,
    total_sum_lot   NUMERIC(18,2),
    PRIMARY KEY (tender_id, lot_id)
);


-- ---------------------------------------------------------------------------
-- 3. GOOD (tovar)  — meta.good_maps[] dan  (asosiy tovar manbai)
-- ---------------------------------------------------------------------------
CREATE TABLE tender_good (
    tender_id       BIGINT NOT NULL REFERENCES tender(id) ON DELETE CASCADE,
    lot_id          INTEGER NOT NULL,          -- qaysi lotga tegishli
    good_code       TEXT NOT NULL,             -- '28.99.30.000_00069' (klassifikator + variant)
    name            TEXT,                      -- 'Listlarni bukish mashinasi'
    unit            TEXT,                      -- 'dona', 'компл.'
    amount          NUMERIC(18,3),             -- 2
    price           NUMERIC(18,2),             -- 138815
    totalcost_item  NUMERIC(18,2),             -- 277630
    category_uid    UUID REFERENCES dim_category(category_uid),  -- ko'pincha null
    PRIMARY KEY (tender_id, lot_id, good_code),
    FOREIGN KEY (tender_id, lot_id) REFERENCES tender_lot(tender_id, lot_id) ON DELETE CASCADE
);

CREATE INDEX idx_good_code      ON tender_good(good_code);
CREATE INDEX idx_good_category  ON tender_good(category_uid);


-- =============================================================================
-- FOYDALI VIEW'lar (dashboard uchun tez agregatsiyalar)
-- =============================================================================

-- Hudud + status bo'yicha tenderlar soni va umumiy summasi (valyuta bo'yicha ajratilgan)
CREATE VIEW v_tender_by_area_status AS
SELECT
    a.name_uz            AS region,
    t.status,
    t.currency,
    COUNT(*)             AS tender_count,
    SUM(t.totalcost)     AS total_value
FROM tender t
LEFT JOIN dim_area a ON a.area_id = t.area_leaf_id
GROUP BY a.name_uz, t.status, t.currency;

-- Kategoriya bo'yicha eng ko'p xarid qilinadigan tovarlar
CREATE VIEW v_top_categories AS
SELECT
    c.title_ru,
    c.code,
    COUNT(*)                  AS line_items,
    SUM(g.totalcost_item)     AS total_spend
FROM tender_good g
JOIN dim_category c ON c.category_uid = g.category_uid
GROUP BY c.title_ru, c.code
ORDER BY total_spend DESC NULLS LAST;
