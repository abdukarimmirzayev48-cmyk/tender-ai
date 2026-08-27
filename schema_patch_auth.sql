-- =============================================================================
-- Sxema patch — AUTH: foydalanuvchilar, sessiyalar va rollar
-- Ishga tushirish (idempotent, bir necha marta ishlatsa ham xavfsiz):
--   psql "dbname=xtxarid user=postgres host=localhost" -f schema_patch_auth.sql
--
-- MUAMMO: tizimda login yo'q. "Kim qildi?" degan savolga javob — dropdown'dan
-- tanlangan ism (`created_by` matn ustuni). 1-4 bosqichda bu arzon edi; ERP
-- 5B da pul (hisob-faktura) va moddiy qiymat (ombor) bilan ishlay boshlaydi
-- va o'sha yerda "istalgan odam istalgan ism bilan yozadi" holati qabul
-- qilib bo'lmaydigan bo'ladi.
--
-- YECHIM: BITTA kimlik manbai. Foydalanuvchilar va sessiyalar shu yerda
-- (tender-ai), ERP esa tokenni HTTP orqali tekshiradi — xuddi cheklist va
-- xabar yuborishdagi kabi (`erp_arxitektura_2.md` 3-bo'lim). Parol xeshi
-- ikkinchi loyihaga ko'chmaydi.
--
-- QARORLAR:
--   1. PAROL XESHI — PBKDF2-HMAC-SHA256, stdlib (`hashlib`). Yangi
--      bog'liqlik (bcrypt/passlib) qo'shilmaydi; format ustunda saqlanadi,
--      shuning uchun keyin kuchliroq algoritmga o'tish migratsiyasiz mumkin.
--   2. TOKEN BAZADA XESH KO'RINISHIDA. Baza dumpi qo'lga tushsa ham
--      sessiyalarni tiklab bo'lmaydi (parol xeshi bilan bir xil mantiq).
--   3. FOYDALANUVCHI O'CHIRILMAYDI — `active=false`. Uning nomi tarixda
--      (`created_by`, `changed_by`) qolgan va yo'qolmasligi kerak.
-- =============================================================================

CREATE TABLE IF NOT EXISTS app_user (
    id            SERIAL PRIMARY KEY,
    -- Kirish nomi: kichik harflarda saqlanadi (kodda normallashtiriladi),
    -- shuning uchun "Admin" va "admin" bitta odam.
    username      TEXT NOT NULL UNIQUE,
    full_name     TEXT NOT NULL,
    -- Format: pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>
    password_hash TEXT NOT NULL,
    -- Rollar ro'yxati kodda ham (api/auth.py ROLES), bazada ham; sinov
    -- ikkalasini solishtiradi. Kengaytirilganda:
    --   ALTER TABLE app_user DROP CONSTRAINT IF EXISTS app_user_role_check;
    --   ALTER TABLE app_user ADD CONSTRAINT app_user_role_check CHECK (...);
    role          TEXT NOT NULL DEFAULT 'broker'
                  CHECK (role IN ('admin', 'manager', 'broker')),
    -- ERP brokeri bilan bog'lash: kim kirgan bo'lsa, uning kartalari
    -- "mening ishlarim"da chiqadi. FK YO'Q — `erp.broker` boshqa sxemada va
    -- ERP mustaqil ko'chirilishi mumkin (erp_arxitektura_2.md).
    broker_id     INT,
    email         TEXT,
    active        BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS app_user_active_idx ON app_user (active);

CREATE TABLE IF NOT EXISTS app_session (
    id            SERIAL PRIMARY KEY,
    user_id       INT NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    -- Tokenning O'ZI emas, sha256 xeshi. Xom token faqat brauzerda.
    token_hash    TEXT NOT NULL UNIQUE,
    expires_at    TIMESTAMPTZ NOT NULL,
    -- Qaysi ilova bergani: 'erp' | 'tender-ai'. Chiqish va tekshiruv uchun
    -- emas, ma'lumot uchun: sessiyalar ro'yxati o'qiladigan bo'lsin.
    issued_for    TEXT,
    user_agent    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS app_session_user_idx ON app_session (user_id);
-- Muddati o'tganlarni tozalash uchun (login paytida yuriladi).
CREATE INDEX IF NOT EXISTS app_session_exp_idx  ON app_session (expires_at);

COMMENT ON TABLE app_user IS
    'Foydalanuvchilar. O''CHIRILMAYDI: active=false — ism tarixda qoladi.';
COMMENT ON COLUMN app_user.password_hash IS
    'pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex> — algoritm ustunda, migratsiyasiz almashtiriladi.';
COMMENT ON COLUMN app_user.broker_id IS
    'erp.broker.id — FK YO''Q: ERP boshqa sxemada va mustaqil ko''chirilishi mumkin.';
COMMENT ON TABLE app_session IS
    'Faol sessiyalar. Token BAZADA XESH ko''rinishida: dump qo''lga tushsa ham tiklab bo''lmaydi.';
