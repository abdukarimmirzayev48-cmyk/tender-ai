-- =============================================================================
-- Sxema patch — TELEGRAM OBUNACHILARI
-- Ishga tushirish (idempotent):
--   psql "dbname=xtxarid user=postgres host=localhost" -f schema_patch_notify_subscribers.sql
--
-- OLDIN `schema_patch_notify_telegram.sql` qo'llanilgan bo'lishi kerak.
--
-- NIMA O'ZGARADI — MODEL O'ZGARADI:
--   ILGARI: sozlamalarda BITTA `telegram_chat_id` turardi, uni foydalanuvchi
--           ro'yxatdan qo'lda tanlab, saqlashi kerak edi. Botga /start bosgan
--           boshqa hech kim xabar olmasdi.
--   ENDI:   botga /start bosgan (yoki bot qo'shilgan guruhда yozilgan) HAR BIR
--           suhbat shu jadvalga OBUNACHI bo'lib tushadi va xabar oladi.
--
-- OBUNA QANDAY QAYD ETILADI: `api/notify.py` `sync_subscribers()` Telegram
-- `getUpdates` javobini o'qib shu jadvalga yozadi. U ikki joyda chaqiriladi —
-- bildirishnoma tsiklida (`notify_new.py`, soatiga bir marta) va interfeysdagi
-- "Chatlarni aniqlash" tugmasida. Ya'ni foydalanuvchi hech narsa bosmasa ham
-- /start bosgan odam keyingi tsiklda obunachi bo'ladi.
--
-- DIQQAT — RUXSAT NAZORATI YO'Q. Tizimda autentifikatsiya yo'q, shuning uchun
-- botni topgan ISTALGAN odam /start bosib obunachi bo'lishi mumkin. `enabled`
-- ustuni aynan shu uchun: egasi interfeysdan keraksiz obunachini bir bosishda
-- o'chiradi. Botni yopiqroq qilish kerak bo'lsa — @BotFather da uni guruhga
-- qo'shishni cheklang yoki bu jadvalga qo'lda kirish nazoratini qo'shing.
-- =============================================================================

CREATE TABLE IF NOT EXISTS notify_telegram_subscriber (
    -- Telegram chat ID. TEXT (INTEGER emas): guruh/kanal ID lari manfiy va
    -- uzun (-1001234567890), kanal uchun '@username' ham bo'ladi.
    chat_id       TEXT PRIMARY KEY,
    -- Ko'rsatish uchun: shaxs ismi yoki guruh nomi (Telegram bergani).
    title         TEXT,
    -- private | group | supergroup | channel
    chat_type     TEXT,
    username      TEXT,
    -- Xabar shu obunachiga ketadimi. Standart YOQILGAN — "start bosgan xabar
    -- oladi" qoidasi shu. Egasi keraksizini o'chirib qo'yadi.
    enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notify_tg_sub_enabled
    ON notify_telegram_subscriber(enabled) WHERE enabled;

COMMENT ON TABLE notify_telegram_subscriber IS
    'Telegram bildirishnoma obunachilari. Botga /start bosgan har bir suhbat '
    'shu yerga tushadi (api/notify.py sync_subscribers). BOT TOKENI bu yerda '
    'emas — .env dagi TELEGRAM_BOT_TOKEN.';
COMMENT ON COLUMN notify_telegram_subscriber.enabled IS
    'Xabar ketadimi. Standart TRUE — tizimda auth yo''q, shuning uchun egasi '
    'keraksiz obunachini interfeysdan o''chirib qo''yishi mumkin.';


-- --- Mavjud sozlamadagi chat obunachiga ko'chiriladi ------------------------
-- Patchdan keyin foydalanuvchi hech narsa qilmasdan avvalgidek xabar olsin.
INSERT INTO notify_telegram_subscriber (chat_id, title, chat_type)
SELECT telegram_chat_id, 'Sozlamalardan ko''chirilgan', NULL
FROM notify_settings
WHERE id = 1 AND telegram_chat_id IS NOT NULL AND telegram_chat_id <> ''
ON CONFLICT (chat_id) DO NOTHING;


-- --- Yuborilganlar jurnali: `kind` endi CHAT bo'yicha ajratiladi ------------
-- `notify_sent` PK — (tender_id, kind). Bir nechta obunachi bo'lgani uchun
-- kanal nomi yetmaydi: har obunachi O'Z jurnaliga ega bo'lishi kerak, aks
-- holda birinchi obunachiga yuborilgan tender qolganlariga hech qachon
-- ketmasdi. Shuning uchun kind = 'new_match_tg:<chat_id>'.
--
-- Eski 'new_match_tg' qatorlari ko'chirilgan chatga biriktiriladi — aks holda
-- unga allaqachon yuborilgan tenderlar QAYTA ketardi.
-- (Yangi ko'rinishdagi qatorlar hali mavjud emas, shuning uchun PK ziddiyati
--  bo'lishi mumkin emas.)
UPDATE notify_sent
SET kind = 'new_match_tg:' || (SELECT telegram_chat_id FROM notify_settings WHERE id = 1)
WHERE kind = 'new_match_tg'
  AND EXISTS (SELECT 1 FROM notify_settings
              WHERE id = 1 AND telegram_chat_id IS NOT NULL AND telegram_chat_id <> '');

-- Chat biriktirib bo'lmagan eski qatorlar (sozlamada chat yo'q edi) — ular
-- endi hech qaysi obunachiga tegishli emas, tozalanadi.
DELETE FROM notify_sent WHERE kind = 'new_match_tg';

COMMENT ON COLUMN notify_sent.kind IS
    'Xabar turi/kanali: ''new_match'' = email, ''new_match_tg:<chat_id>'' = '
    'Telegram obunachisi. PK (tender_id, kind) — bir tender haqida HAR '
    'OBUNACHIGA bir marta xabar ketadi.';

-- Tekshirish:
--   SELECT chat_id, title, chat_type, enabled FROM notify_telegram_subscriber;
