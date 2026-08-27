-- =============================================================================
-- Sxema patch — AUTH TUZATISHI: tender-ai KOMPANIYA hisobi bilan kiriladi
-- Ishga tushirish (idempotent, bir necha marta ishlatsa ham xavfsiz):
--   psql "dbname=xtxarid user=postgres host=localhost" -f schema_patch_auth_2.sql
-- Talab: schema_patch_auth.sql qo'llangan bo'lishi kerak.
--
-- NIMA XATO EDI: `schema_patch_auth.sql` (auth-1) bu yerga HODIM hisoblarini
-- qo'ygan edi (`app_user`, rollar, `broker_id`). Domen modeli boshqacha:
--
--   Tender-AI  — KOMPANIYA hisobi bilan kiriladi. U tender agregatori:
--                kompaniya unga ulanadi, tenderlarni ko'radi va ERP ga
--                uzatadi. Bu yerda "xodim" degan tushuncha YO'Q.
--   Tender ERP — kompaniyaning O'Z ERP tizimi; xodimlar, ularning
--                kartalari va huquqlari — hammasi o'sha yerda
--                (`erp.app_user`, `schema_patch_erp_6.sql`).
--
-- YECHIM: bu yerda KOMPANIYA hisobi qoladi — rolsiz, `broker_id`siz.
-- Xodim hisoblari ERP ga ko'chirildi va bu yerdan olib tashlanadi.
--
-- MA'LUMOT YO'QOLMAYDI: hisoblar avval `erp.app_user` ga ko'chirilgan
-- (`schema_patch_erp_6.sql`), shundan keyin bu patch qo'llanadi. Tartib
-- muhim va u README da yozilgan.
-- =============================================================================

CREATE TABLE IF NOT EXISTS company_account (
    id            SERIAL PRIMARY KEY,
    -- Kirish nomi kichik harflarda (kodda normallashtiriladi).
    username      TEXT NOT NULL UNIQUE,
    -- Kompaniya nomi — kim kirganini ko'rsatish uchun. Yuridik passport
    -- ERP da (`erp.own_company`): u shartnoma uchun, bu esa kirish uchun.
    company_name  TEXT NOT NULL,
    -- pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>
    password_hash TEXT NOT NULL,
    email         TEXT,
    active        BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS company_session (
    id            SERIAL PRIMARY KEY,
    account_id    INT NOT NULL REFERENCES company_account(id) ON DELETE CASCADE,
    -- Tokenning O'ZI emas, sha256 xeshi.
    token_hash    TEXT NOT NULL UNIQUE,
    expires_at    TIMESTAMPTZ NOT NULL,
    user_agent    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS company_session_acc_idx ON company_session (account_id);
CREATE INDEX IF NOT EXISTS company_session_exp_idx ON company_session (expires_at);

-- --- Auth-1 dagi xodim jadvallarini olib tashlash ----------------------------
-- Ular `erp.app_user` ga ko'chirilgan. Bu yerda qolsa IKKI joyda ikki xil
-- parol paydo bo'ladi va qaysi biri haqiqiy ekani noma'lum bo'lib qoladi.
--
-- XAVFSIZLIK SHARTI: faqat ko'chirish AMALGA OSHGAN bo'lsa o'chiriladi.
-- `erp.app_user` da hech narsa bo'lmasa jadvallar joyida qoladi va
-- operator xabar oladi.
DO $$
DECLARE moved INT := 0;
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'erp' AND table_name = 'app_user') THEN
        SELECT count(*) INTO moved FROM erp.app_user;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'public' AND table_name = 'app_user') THEN
        IF moved > 0 THEN
            DROP TABLE IF EXISTS public.app_session;
            DROP TABLE IF EXISTS public.app_user;
            RAISE NOTICE 'public.app_user/app_session olib tashlandi (erp.app_user da % ta hisob bor).', moved;
        ELSE
            RAISE WARNING 'public.app_user QOLDIRILDI: erp.app_user bo''sh. Avval schema_patch_erp_6.sql ni qo''llang.';
        END IF;
    END IF;
END $$;

COMMENT ON TABLE company_account IS
    'KOMPANIYA hisobi (tender-ai ga kirish). Xodimlar bu yerda EMAS — ular ERP da (erp.app_user).';
COMMENT ON COLUMN company_account.company_name IS
    'Ko''rsatish uchun nom. Yuridik rekvizitlar ERP da (erp.own_company).';
