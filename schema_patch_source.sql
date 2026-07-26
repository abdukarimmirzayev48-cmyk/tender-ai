-- =============================================================================
-- Sxema patch — ko'p-platformali kelajak uchun `source_platform` ustuni
-- xt_xarid_schema.sql va schema_patch_dims.sql dan KEYIN ishga tushiring:
--   psql "dbname=xtxarid user=a1234 host=localhost" -f schema_patch_source.sql
--
-- MAQSAD: bitta baza/backend/dashboard turli manbalarni (xt-xarid.uz,
--         xarid.uzex.uz, e-auksion.uz ...) birlashtiradi. Har yozuv qaysi
--         platformadan kelganini bilishi kerak.
--
-- PK STRATEGIYASI (ongli qaror):
--   Hozircha PK `tender.id` (BIGINT) o'zgarmaydi — unga tender_lot/tender_good
--   FK bilan bog'langan. Kompozit PK (source_platform, id) faqat 2-platforma
--   real qo'shilib, ID'lar to'qnashuvi ehtimoli paydo bo'lganda kerak bo'ladi.
--   O'shanda alohida migratsiya patch'i yoziladi. Hozir buni qilish — ortiqcha
--   xavf (barcha FK'larni qayta qurish) real ehtiyojsiz.
-- =============================================================================

ALTER TABLE tender
    ADD COLUMN IF NOT EXISTS source_platform TEXT NOT NULL DEFAULT 'xt-xarid';

-- Platforma bo'yicha filtr/agregatsiya uchun indeks
CREATE INDEX IF NOT EXISTS idx_tender_source ON tender(source_platform);

-- Deadline bo'yicha saralash dashboardning asosiy tartibi — indeks qo'shamiz
-- (ochiq tenderlarni close_at yaqinlashishi bo'yicha tez saralash uchun)
CREATE INDEX IF NOT EXISTS idx_tender_close_at ON tender(close_at);
