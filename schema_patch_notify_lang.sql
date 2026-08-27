-- =============================================================================
-- Sxema patch — BILDIRISHNOMA TILI (xabar platforma tilida ketsin)
-- Ishga tushirish (idempotent, qayta-qayta yurgizsa bo'ladi):
--   psql "dbname=xtxarid user=postgres host=localhost" -f schema_patch_notify_lang.sql
--
-- OLDIN `schema_patch_notify.sql` qo'llanilgan bo'lishi kerak (notify_settings
-- shu patchда yaratiladi).
--
-- NIMA QO'SHILADI: `notify_settings` ga BITTA ustun — `lang`.
--
-- NEGA BAZADA, BRAUZERDA EMAS.
-- Interfeys tili brauzerda (localStorage) tanlanadi, lekin xabarni SERVER
-- yuboradi: `notify_new.py` ETL dan keyin, soatlik jadval bo'yicha, ilova
-- ochiq bo'lmasa ham. Server brauzerni ko'rmaydi — shuning uchun tanlangan
-- til bazaga yozilishi shart. Frontend uni til almashtirilgan zahoti
-- `PUT /notify/settings` bilan yuboradi.
--
-- NEGA `notify_settings` DA (alohida jadvalda emas): til — xabarning O'ZI
-- bilan bog'liq sozlama, xuddi `min_score` va `base_url` kabi. Ikkala kanal
-- (email va Telegram) uni ULASHADI: bir xil xabar ikki joyда turli tilda
-- kelsa, foydalanuvchi buni nosozlik deb hisoblardi.
--
-- ESKI BAZA BILAN MOSLIK: patch qo'llanmagan bo'lsa ham API ishlayveradi —
-- `api/notify.py` ustun borligini tekshiradi va yo'q bo'lsa xabar standart
-- tilда (o'zbekcha) ketadi. Interfeys esa `lang_ready: false` ni ko'rib
-- "patch kerak" deb ogohlantiradi (jimgina "til o'zgardi" demaydi).
-- =============================================================================

-- 'uz' | 'ru' | 'en' — frontenddagi `LANGS` ro'yxati bilan bir xil.
-- Standart 'uz': platformaning asosiy tili shu, ya'ni til tanlanmaган eski
-- yozuvlar avvalgidek o'zbekcha xabar oladi (xulq-atvor o'zgarmaydi).
ALTER TABLE notify_settings
    ADD COLUMN IF NOT EXISTS lang TEXT NOT NULL DEFAULT 'uz';

-- Bazada faqat qo'llab-quvvatlanadigan kodlar yotsin. Cheklov bo'lmasa
-- qo'lда yozilgan 'uz-UZ'/'RU' kabi qiymat xabarni jimgina o'zbekchaga
-- qaytarib qo'yardi va sabab ko'rinmasdi.
DO $$
BEGIN
    ALTER TABLE notify_settings
        ADD CONSTRAINT notify_settings_lang_chk CHECK (lang IN ('uz', 'ru', 'en'));
EXCEPTION
    WHEN duplicate_object THEN NULL;      -- patch qayta yurgizildi — normal
END $$;

COMMENT ON COLUMN notify_settings.lang IS
    'Bildirishnoma tili: uz | ru | en. Foydalanuvchi interfeysда tanlagan til '
    'shu yerga yoziladi (frontend PUT /notify/settings). Email ham, Telegram '
    'ham shu tilda ketadi — matnlar api/i18n.py lug''atида.';

-- Tekshirish (patch qo'llangach):
--   SELECT id, lang FROM notify_settings;
