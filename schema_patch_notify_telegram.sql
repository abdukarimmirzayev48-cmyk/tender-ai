-- =============================================================================
-- Sxema patch — TELEGRAM BILDIRISHNOMA (P0-10 kanalining ikkinchisi)
-- Ishga tushirish (idempotent, qayta-qayta yurgizsa bo'ladi):
--   psql "dbname=xtxarid user=postgres host=localhost" -f schema_patch_notify_telegram.sql
--
-- OLDIN `schema_patch_notify.sql` qo'llanilgan bo'lishi kerak (notify_settings
-- va notify_sent jadvallari shu patchда yaratiladi).
--
-- NIMA QO'SHILADI: `notify_settings` ga IKKITA ustun. YANGI JADVAL YO'Q —
-- Telegram email bilan bir xil sozlamalarni (moslik chegarasi `min_score`,
-- kartochka havolasi uchun `base_url`) ULASHADI. Chegarani ikki joyda saqlash
-- ularning bir-biridan uzoqlashishiga olib kelardi.
--
-- MUHIM — BOT TOKENI BAZAGA YOZILMAYDI.
-- Token faqat `.env` dagi `TELEGRAM_BOT_TOKEN` dan o'qiladi (api/telegram.py),
-- xuddi SMTP_PASSWORD kabi. Token bilan botni TO'LIQ boshqarish mumkin, baza
-- dumpi esa ko'p qo'ldan o'tadi. Token yo'q bo'lsa tizim ANIQ xato beradi.
-- =============================================================================

-- Telegram kanali yoqilganmi. Email (`enabled`) dan MUSTAQIL: foydalanuvchi
-- faqat Telegram, faqat email yoki ikkalasini ham yoqishi mumkin.
ALTER TABLE notify_settings
    ADD COLUMN IF NOT EXISTS telegram_enabled BOOLEAN NOT NULL DEFAULT FALSE;

-- Qabul qiluvchi suhbat. TEXT (INTEGER emas) — sabab: guruh/kanal ID lari
-- manfiy va uzun (-1001234567890), kanal uchun '@username' ham beriladi.
ALTER TABLE notify_settings
    ADD COLUMN IF NOT EXISTS telegram_chat_id TEXT;

COMMENT ON COLUMN notify_settings.telegram_enabled IS
    'Telegram kanali yoqilganmi. Email (enabled) dan mustaqil.';
COMMENT ON COLUMN notify_settings.telegram_chat_id IS
    'Telegram chat ID (guruh uchun manfiy son, kanal uchun @username ham '
    'bo''ladi). Foydalanuvchi botga /start yozgach api/telegram.py '
    'discover_chats() uni topib beradi. BOT TOKENI bu yerda emas — .env da.';


-- --- Yuborilganlar jurnali: Telegram uchun ALOHIDA `kind` ---------------------
-- `notify_sent` PK (tender_id, kind). Email 'new_match', Telegram
-- 'new_match_tg' yozadi — ya'ni HAR KANAL O'Z JURNALINI yuritadi.
--
-- NEGA shunday: agar ikkala kanal bitta 'new_match' qatoriga tayansa,
-- keyinroq Telegram yoqilganда email allaqachon "yuborilgan" deb belgilagan
-- tenderlar Telegramга hech qachon tushmasdi — foydalanuvchi esa buni
-- xatolik deb hisoblardi. Jadval o'zgartirilmaydi, faqat yangi `kind` qiymati.
COMMENT ON COLUMN notify_sent.kind IS
    'Xabar turi/kanali: ''new_match'' = email, ''new_match_tg'' = Telegram. '
    'PK (tender_id, kind) — bir tender haqida HAR KANALDA bir marta xabar ketadi.';

-- Tekshirish (patch qo'llangach qaysi ustunlar borligini ko'rsatadi):
--   SELECT column_name, data_type FROM information_schema.columns
--   WHERE table_name = 'notify_settings' ORDER BY ordinal_position;
