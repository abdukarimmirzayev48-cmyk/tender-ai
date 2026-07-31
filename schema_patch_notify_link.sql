-- =============================================================================
-- Sxema patch — TELEGRAMNI ULASH (deep-link) + SMTP ni platformaga ko'chirish
-- Ishga tushirish (idempotent):
--   psql "dbname=xtxarid user=postgres host=localhost" -f schema_patch_notify_link.sql
--
-- OLDIN qo'llanadi: schema_patch_notify.sql, _telegram.sql, _subscribers.sql
--
-- =============================================================================
-- NIMA NOTO'G'RI EDI
-- =============================================================================
-- 1) TELEGRAM. Botga /start bosgan HAR QANDAY suhbat obunachi bo'lardi. Ya'ni
--    botni topgan begona odam ham, bot tasodifan qo'shilgan guruh ham
--    kompaniyaning mos tenderlari ro'yxatini olardi. Bundan tashqari
--    foydalanuvchi chat ID ni qo'lда ro'yxatdan tanlab, saqlashi kerak edi —
--    bu texnik detal, unga ko'rinmasligi kerak.
--
--    ENDI: platforma bir martalik ULASH HAVOLASI beradi —
--          https://t.me/<bot>?start=<token>
--    Foydalanuvchi bosadi, Telegram botni ochadi, "Start" bosiladi va bot
--    xabar bilan birga TOKENni oladi. Faqat SHU token bilan kelgan suhbat
--    ulanadi. Tokensiz /start — hech narsa qilmaydi.
--
-- 2) SMTP. Foydalanuvchidan host/port/login/parol so'ralardi. Bu PLATFORMA
--    OPERATORINING ishi, foydalanuvchiniki emas. Endi u `.env` da
--    (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_TLS),
--    foydalanuvchida esa faqat O'Z EMAILI qoladi.
--    `notify_settings` dagi smtp_* ustunlari ESKIRDI — o'chirilmaydi (ma'lumot
--    yo'qotmaslik uchun), lekin endi o'qilmaydi.
-- =============================================================================


-- --- Bir martalik ulash tokenlari -------------------------------------------
CREATE TABLE IF NOT EXISTS notify_telegram_link (
    -- URL-xavfsiz tasodifiy qator. Telegram `?start=` parametriga 64 belgigacha
    -- [A-Za-z0-9_-] sig'adi — token shu doiraga kiradi.
    token       TEXT PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Muddati o'tgan token ISHLAMAYDI: havola boshqa qo'lga tushsa ham
    -- cheksiz ochiq qolmasin.
    expires_at  TIMESTAMPTZ NOT NULL,
    -- Ishlatilgach: qaysi suhbat ulangani va qachon. NULL = hali ishlatilmagan.
    chat_id     TEXT,
    used_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_notify_tg_link_open
    ON notify_telegram_link(expires_at) WHERE used_at IS NULL;

COMMENT ON TABLE notify_telegram_link IS
    'Telegramni ulash uchun bir martalik tokenlar. Foydalanuvchi '
    'https://t.me/<bot>?start=<token> havolasini bosadi; bot tokenni xabar '
    'matnida oladi va api/notify.py uni obunachiga aylantiradi.';


-- --- Obunachi QAYERDAN kelgani ----------------------------------------------
-- DIQQAT: ustun DEFAULTSIZ qo'shiladi. `DEFAULT 'link'` bilan qo'shilsa
-- PostgreSQL MAVJUD qatorlarni ham 'link' deb to'ldirar edi — ya'ni eski,
-- tasdiqlanmagan obunachilar "tasdiqlangan" bo'lib qolardi. Standart qiymat
-- pastda, mavjud qatorlar tuzatilgandan KEYIN qo'yiladi.
ALTER TABLE notify_telegram_subscriber
    ADD COLUMN IF NOT EXISTS source TEXT;

COMMENT ON COLUMN notify_telegram_subscriber.source IS
    '''link'' = platformadagi ulash havolasi orqali tasdiqlangan; '
    '''legacy'' = eski (tasdiqlanmagan) usulda qo''shilgan.';


-- --- TASDIQLANMAGAN obunachilar o'chiriladi ---------------------------------
-- "Tasdiqlangan" = `notify_telegram_link` da SHU chat uchun ishlatilgan token
-- bor. Qolganlari /start bosgani uchungina qo'shilgan — kim ekani platforma
-- tomonidan tekshirilmagan (begona odam yoki tasodifiy guruh bo'lishi mumkin).
--
-- Qatorlar SAQLANADI (ma'lumot yo'qotmaymiz), lekin XABAR KETMAYDI: egasi
-- interfeysдан "Telegramni ulash" bilan qaytadan ulaydi.
--
-- Shart tokenga tayangani uchun patch QAYTA-QAYTA yurgizilsa ham to'g'ri
-- ishlaydi: haqiqiy ulanmalar 'legacy' ga tushib qolmaydi.
UPDATE notify_telegram_subscriber s
SET source = 'legacy', enabled = FALSE
WHERE NOT EXISTS (
    SELECT 1 FROM notify_telegram_link l
    WHERE l.chat_id = s.chat_id AND l.used_at IS NOT NULL
);

UPDATE notify_telegram_subscriber s
SET source = 'link'
WHERE source IS NULL;

ALTER TABLE notify_telegram_subscriber
    ALTER COLUMN source SET DEFAULT 'link';
ALTER TABLE notify_telegram_subscriber
    ALTER COLUMN source SET NOT NULL;


-- --- Tozalash: muddati o'tgan ishlatilmagan tokenlar ------------------------
-- (Bu qatorni vaqti-vaqti bilan qo'lда yurgizsa bo'ladi; jadval kichik.)
DELETE FROM notify_telegram_link WHERE used_at IS NULL AND expires_at < now();

-- Tekshirish:
--   SELECT chat_id, title, source, enabled FROM notify_telegram_subscriber;
--   SELECT token, expires_at, chat_id, used_at FROM notify_telegram_link;
