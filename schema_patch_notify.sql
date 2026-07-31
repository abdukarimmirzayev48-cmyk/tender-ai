-- =============================================================================
-- Sxema patch — EMAIL BILDIRISHNOMA (REJA.md / TZ P0-10)
-- Ishga tushirish (idempotent, qayta-qayta yurgizsa bo'ladi):
--   psql "dbname=xtxarid user=postgres host=localhost" -f schema_patch_notify.sql
--
-- TZ TALABI: "Moslik chegarasidan yuqori bo'lgan yangi tender haqida
-- email-bildirishnoma (chegara sozlanadi)".
--   [x] soatlik kuzatish tsikli davomida keladi  -> notify_new.py ETL dan keyin
--   [x] tizimdagi kartochkaga havolani o'z ichiga oladi -> base_url + /?tender=ID
--
-- IKKI JADVAL:
--   notify_settings — bitta faol yozuv (singleton). Kim, qachon, qaysi
--                     chegaradan yuqorida xabar oladi + SMTP ulanishi.
--   notify_sent     — YUBORILGANLAR JURNALI. Bir tender haqida IKKI MARTA
--                     xabar ketmasligi shu jadval bilan kafolatlanadi
--                     (PK (tender_id, kind) — ikkinchi INSERT konfliktga
--                     tushadi, jimgina o'tkazib yuboriladi).
--
-- MUHIM — SMTP PAROLI BAZAGA YOZILMAYDI.
-- Parol faqat `.env` dagi `SMTP_PASSWORD` dan o'qiladi (api/notify.py).
-- Sabab: baza dumpi/bekapi ko'p qo'ldan o'tadi, sir esa unда qolmasligi kerak.
-- Parol yo'q bo'lsa tizim ANIQ xato beradi — jimgina "yuborildi" demaydi.
-- =============================================================================

-- --- Sozlamalar (bitta faol yozuv, auth kelganда user_id qo'shiladi) ---------
CREATE TABLE IF NOT EXISTS notify_settings (
    id            INTEGER PRIMARY KEY DEFAULT 1,
    -- Bildirishnoma umuman yoqilganmi. Standart: O'CHIQ — SMTP sozlanmagunча
    -- xabar yuborishga urinmaymiz.
    enabled       BOOLEAN NOT NULL DEFAULT FALSE,
    -- Qabul qiluvchi. BO'SH bo'lsa `company_profile.email` dan olinadi
    -- (api/notify.py: recipient()). Shu sabab NOT NULL emas.
    email         TEXT,
    -- MOSLIK CHEGARASI (TZ: "chegara sozlanadi"). Shundan PAST ballli tender
    -- haqida xabar ketmaydi. 0–100 — katalog/profil ballari bilan bir shkalada.
    min_score     INTEGER NOT NULL DEFAULT 70,
    -- --- SMTP ulanishi (parolsiz!) ---
    smtp_host     TEXT,
    smtp_port     INTEGER NOT NULL DEFAULT 587,
    smtp_user     TEXT,
    -- STARTTLS (587). 465 portда api/notify.py o'zi SMTP_SSL ga o'tadi.
    smtp_use_tls  BOOLEAN NOT NULL DEFAULT TRUE,
    -- Jo'natuvchi manzil. Bo'sh bo'lsa smtp_user ishlatiladi.
    from_email    TEXT,
    -- TENDER KARTOCHKASIGA HAVOLA shu manzildan quriladi (TZ talabi):
    --   base_url + '/?tender=' + tender.id
    base_url      TEXT NOT NULL DEFAULT 'http://localhost:5173',
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT notify_settings_singleton CHECK (id = 1),
    CONSTRAINT notify_settings_score_range CHECK (min_score BETWEEN 0 AND 100),
    CONSTRAINT notify_settings_port_range CHECK (smtp_port BETWEEN 1 AND 65535)
);

-- Standart yozuv (bo'lmasa yaratamiz; bor bo'lsa TEGMAYMIZ)
INSERT INTO notify_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

COMMENT ON TABLE notify_settings IS
    'Email bildirishnoma sozlamalari (bitta faol yozuv). SMTP PAROLI BU YERDA '
    'SAQLANMAYDI — .env dagi SMTP_PASSWORD dan o''qiladi.';
COMMENT ON COLUMN notify_settings.min_score IS
    'Moslik chegarasi 0-100. Katalog: kategoriya mosligi=100, nom mosligi=70; '
    'profil: api/matching.py score_tender(). Ikkisining kattasi olinadi.';
COMMENT ON COLUMN notify_settings.base_url IS
    'Frontend manzili. Xabardagi kartochka havolasi: base_url + /?tender=ID';


-- --- Yuborilganlar jurnali (takroriy xabarning oldini oladi) -----------------
CREATE TABLE IF NOT EXISTS notify_sent (
    tender_id  BIGINT NOT NULL REFERENCES tender(id) ON DELETE CASCADE,
    -- Xabar turi. Hozircha 'new_match' (yangi mos tender). Kelajakda
    -- 'deadline_soon' va boshqalar qo'shilsa, bir tender haqida HAR TUR uchun
    -- bittadan xabar ketadi — shuning uchun kind PK ga kiradi.
    kind       TEXT NOT NULL DEFAULT 'new_match',
    sent_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    email      TEXT,                      -- kimga ketgani (audit)
    score      INTEGER,                   -- qanday ball bilan ketgani (audit)
    PRIMARY KEY (tender_id, kind)
);

CREATE INDEX IF NOT EXISTS idx_notify_sent_at ON notify_sent(sent_at DESC);

COMMENT ON TABLE notify_sent IS
    'Yuborilgan bildirishnomalar. PK (tender_id, kind) — BIR TENDER HAQIDA '
    'IKKI MARTA XABAR KETMAYDI (ON CONFLICT DO NOTHING).';
