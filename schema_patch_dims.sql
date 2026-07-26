-- =============================================================================
-- Sxema yangilanishi (patch) — dim reestrlarning REAL strukturasiga moslash
-- xt_xarid_schema.sql dan KEYIN ishga tushiring:
--   psql "dbname=xtxarid user=a1234 host=localhost" -f schema_patch_dims.sql
-- =============================================================================

-- dim_status: real reestr {name, id, code} beradi (faqat ruscha nom)
-- Avvalgi sxemada name_uz/name_ru bor edi; endi status_id qo'shamiz
ALTER TABLE dim_status ADD COLUMN IF NOT EXISTS status_id INTEGER;

-- dim_area: real reestr {id, name, parent_id, has_children} beradi
-- name_ru allaqachon bor; has_children qo'shamiz
ALTER TABLE dim_area ADD COLUMN IF NOT EXISTS has_children BOOLEAN DEFAULT FALSE;

-- name_ru ustuni dim_area da bormi tekshirib, bo'lmasa qo'shamiz
-- (asl sxemada name_uz/name_ru bor edi — bu xavfsiz takror)
ALTER TABLE dim_area   ADD COLUMN IF NOT EXISTS name_ru TEXT;
ALTER TABLE dim_status ADD COLUMN IF NOT EXISTS name_ru TEXT;

-- Izoh: name_uz ustunlari bo'sh qoladi — o'zbekcha nomlar keyin
-- qo'lda tarjima jadvali orqali yoki alohida manba (SOATO) dan to'ldiriladi.
