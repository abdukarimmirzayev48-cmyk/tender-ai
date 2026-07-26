-- =============================================================================
-- Sxema patch — SAQLANGAN QIDIRUVLAR (A bosqich, REJA_UX.md)
-- Ishga tushirish:
--   psql "dbname=xtxarid user=a1234 host=localhost" -f schema_patch_saved_search.sql
--
-- G'OYA: hozir bitta `company_profile` bor. Uni bir nechta NOMLANGAN
-- saqlangan qidiruvga aylantiramiz. Har qidiruv o'z filtri + xabarnoma
-- sozlamasi bilan. Mavjud profil yo'qolmaydi — u birinchi saqlangan
-- qidiruvga ko'chiriladi.
-- =============================================================================

CREATE TABLE IF NOT EXISTS saved_search (
    id           SERIAL PRIMARY KEY,
    company_id   BIGINT,                    -- auth kelganда (hozir NULL = yagona foydalanuvchi)
    name         TEXT NOT NULL,
    keywords     TEXT[]  NOT NULL DEFAULT '{}',
    categories   TEXT[]  NOT NULL DEFAULT '{}',   -- B bosqich (kategoriya) uchun tayyor
    regions      TEXT[]  NOT NULL DEFAULT '{}',
    currency     TEXT,
    min_cost     NUMERIC(18,2),
    max_cost     NUMERIC(18,2),
    notify       BOOLEAN NOT NULL DEFAULT TRUE,   -- C bosqich (xabarnoma) uchun
    last_seen_at TIMESTAMPTZ,               -- C: shu vaqtdan keyingi mos = "yangi"
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_saved_search_company ON saved_search(company_id);

-- Mavjud profilni birinchi saqlangan qidiruvga ko'chiramiz (agar bo'lsa va
-- hali ko'chirilmagan bo'lsa) — ma'lumot yo'qolmaydi.
INSERT INTO saved_search (name, keywords, regions, currency, min_cost, max_cost)
SELECT COALESCE(NULLIF(name, ''), 'Mening qidiruvim'),
       keywords, regions, currency, min_cost, max_cost
FROM company_profile
WHERE EXISTS (SELECT 1 FROM company_profile)
  AND NOT EXISTS (SELECT 1 FROM saved_search)   -- faqat bir marta
ORDER BY updated_at DESC
LIMIT 1;
