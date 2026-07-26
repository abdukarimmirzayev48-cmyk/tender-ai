-- =============================================================================
-- Sxema patch — kompaniya profili (aqlli moslashtirish uchun)
-- xt_xarid_schema.sql + patchlardan KEYIN:
--   psql "dbname=xtxarid user=a1234 host=localhost" -f schema_patch_profile.sql
--
-- MAQSAD: kompaniya nima sotishini/qidirayotganini saqlaymiz. `POST /match`
-- shu profilga qarab ochiq tenderlarni ballab tartiblaydi. Hozircha deterministik
-- (qoidaga asoslangan) skorlash; kelajakda Claude bilan almashtiriladi.
--
-- Hozircha bitta faol profil (ko'p-ijarachiliksiz). Kelajakda auth qo'shilганда
-- user_id/company_id ustuni bilan kengaytiriladi.
-- =============================================================================

CREATE TABLE IF NOT EXISTS company_profile (
    id            SERIAL PRIMARY KEY,
    name          TEXT,                       -- ixtiyoriy yorliq: 'Mening kompaniyam'
    keywords      TEXT[] NOT NULL DEFAULT '{}', -- ['mebel','stol','kompyuter']
    regions       TEXT[] NOT NULL DEFAULT '{}', -- dim_area.area_id lar (viloyat kodlari)
    currency      CHAR(3),                    -- afzal valyuta: 'UZS' | 'USD' | NULL(farqsiz)
    min_cost      NUMERIC(18,2),              -- byudjet quyi chegarasi (NULL = cheksiz)
    max_cost      NUMERIC(18,2),              -- byudjet yuqori chegarasi (NULL = cheksiz)
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
