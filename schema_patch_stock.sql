-- =============================================================================
-- Sxema patch — OMBOR QOLDIG'I va KATALOG IMPORTI (TZ P0-4 / P0-6)
-- Ishga tushirish:
--   psql "dbname=xtxarid user=postgres host=localhost" -f schema_patch_stock.sql
--
-- MUAMMO: `catalog_product` da mahsulotning OMBORDAGI MIQDORI yo'q edi —
-- faqat nomi, kategoriyasi va SOTUV narxi (`price`) saqlanardi. Shu sababli:
--   * P0-4 "Excel/Google Sheets dan katalog VA OMBOR QOLDIQLARINI import qilish"
--     bajarib bo'lmas edi (qoldiqni yozadigan ustun yo'q);
--   * P0-6 "mos kelgan pozitsiyalar bo'yicha qoldiqlarni tekshirish" mumkin emas
--     edi (nimaga solishtirishni bilmaymiz).
--
-- YECHIM: yangi jadval yaratmasdan, `catalog_product` ga 5 ta ustun. Bitta
-- mahsulot = bitta qoldiq (ko'p omborli hisob MVP doirasidan tashqarida; kerak
-- bo'lsa keyinchalik `catalog_stock(product_id, warehouse_id, qty)` qo'shiladi
-- va bu ustunlar "umumiy qoldiq" ko'rinishi bo'lib qoladi).
--
-- NARX ustunlari FARQI (chalkashmasligi uchun):
--   `price`      — SOTUV narxi. Foydalanuvchi qo'lda kiritadi, taklif tuzishda
--                  ishlatiladi. MAVJUD ustun, ma'nosi O'ZGARMAYDI.
--   `cost_price` — TANNARX (xarid/ishlab chiqarish narxi). YANGI. Marja hisobi
--                  uchun: marja = price - cost_price. Import shablonidagi
--                  "tannarx" ustuni AYNAN shu yerga tushadi, `price` ga EMAS.
-- =============================================================================

-- --- 1. Import partiyalari (import izi) ------------------------------------
-- Har bir yuklash bitta yozuv. Qaysi mahsulot qaysi fayldan kelganini bilish,
-- xato yuklashni orqaga qaytarish va "oxirgi import qachon bo'lgan" savoliga
-- javob berish uchun. Dry-run yozuv YARATMAYDI (bazaga umuman tegmaydi).
CREATE TABLE IF NOT EXISTS catalog_import_batch (
    id           UUID PRIMARY KEY,
    company_id   BIGINT,                  -- auth kelganda (hozir NULL = yagona)
    filename     TEXT,
    source       TEXT,                    -- 'xlsx' | 'csv'
    rows_total   INTEGER NOT NULL DEFAULT 0,
    rows_ok      INTEGER NOT NULL DEFAULT 0,
    rows_error   INTEGER NOT NULL DEFAULT 0,
    inserted     INTEGER NOT NULL DEFAULT 0,
    updated      INTEGER NOT NULL DEFAULT 0,
    errors       JSONB NOT NULL DEFAULT '[]'::jsonb,  -- qator bo'yicha xatolar
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_import_batch_created
    ON catalog_import_batch(created_at DESC);

-- --- 2. Qoldiq maydonlari ---------------------------------------------------
ALTER TABLE catalog_product
    -- Ombordagi mavjud miqdor. NULL = "qoldiq kiritilmagan" (0 dan FARQLI:
    -- 0 = "yo'q", NULL = "bilmaymiz"). P0-6 shu farqni "yetishmaydi" va
    -- "noma'lum" holatlariga ajratadi.
    ADD COLUMN IF NOT EXISTS stock_qty         NUMERIC(18,3),
    -- Qoldiq o'lchov birligi. `unit` (sotuv birligi) dan ATAYIN alohida:
    -- omborda "kg" da hisoblanib, tenderda "dona" so'ralishi mumkin — bunda
    -- solishtirish ishonchsiz va P0-6 uni "noma'lum" deb belgilaydi.
    ADD COLUMN IF NOT EXISTS stock_unit        TEXT,
    -- Qoldiq ENG OXIRGI marta qachon yangilangani. TZ talabi:
    -- "Ombor qoldiqlari yuklanmagan/eskirgan (N kundan ortiq) — interfeysda
    -- ogohlantirish, solishtiruv 'dastlabki' deb belgilanadi".
    -- NULL = hech qachon yuklanmagan.
    ADD COLUMN IF NOT EXISTS stock_updated_at  TIMESTAMPTZ,
    -- TANNARX (yuqoridagi izohga qarang — `price` sotuv narxi, bu xarid narxi).
    ADD COLUMN IF NOT EXISTS cost_price        NUMERIC(18,2),
    -- Import izi: mahsulot oxirgi marta qaysi partiyada yangilangan.
    -- Qo'lda kiritilgan mahsulotlarda NULL.
    ADD COLUMN IF NOT EXISTS import_batch_id   UUID REFERENCES catalog_import_batch(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_catalog_import_batch
    ON catalog_product(import_batch_id);

-- Nom bo'yicha upsert (import "bor bo'lsa yangila, yo'q bo'lsa qo'sh" qiladi)
-- katta-kichik harf farqsiz ishlaydi — shu qidiruvni tez qilamiz.
CREATE INDEX IF NOT EXISTS idx_catalog_name_lower
    ON catalog_product(lower(name));

-- --- 3. Izohlar (baza o'zini o'zi hujjatlaydi) ------------------------------
COMMENT ON COLUMN catalog_product.stock_qty IS
    'Ombordagi qoldiq. NULL = kiritilmagan (0 = mavjud emas). P0-6 shu farqni '
    '"noma''lum" va "yetishmaydi" ga ajratadi.';
COMMENT ON COLUMN catalog_product.stock_unit IS
    'Qoldiq o''lchov birligi. `unit` (sotuv birligi) dan alohida — mos kelmasa '
    'qoldiq solishtiruvi "noma''lum" bo''ladi.';
COMMENT ON COLUMN catalog_product.stock_updated_at IS
    'Qoldiq oxirgi yangilangan vaqt. Eskirganlik ogohlantirishi shundan '
    'hisoblanadi (STOCK_STALE_DAYS, default 14 kun).';
COMMENT ON COLUMN catalog_product.cost_price IS
    'TANNARX (xarid/ishlab chiqarish narxi). `price` esa SOTUV narxi — '
    'import shablonidagi "tannarx" ustuni shu yerga tushadi.';
COMMENT ON COLUMN catalog_product.import_batch_id IS
    'Oxirgi import partiyasi (catalog_import_batch.id). Qo''lda kiritilganda NULL.';
