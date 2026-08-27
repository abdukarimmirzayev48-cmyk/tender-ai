-- =============================================================================
-- Sxema patch — MUDDATI TUGAGAN tenderlar uchun alohida status
--   psql "dbname=xtxarid user=a1234 host=localhost" -f schema_patch_expired.sql
--
-- MUAMMO: `tender.status` — manba bergan OXIRGI qiymat. Tender yopilgach u
-- manbaning ochiq reyestridan shunchaki CHIQIB KETADI: biz uni boshqa hech
-- qachon ko'rmaymiz, ya'ni bizdagi 'open' abadiy qotib qoladi. 2026-08-12 holati:
-- 915 ta yozuv 'open' turgan, muddati esa allaqachon o'tgan (778 uzex + 137
-- xt-xarid, eng eskisi 2 haftalik).
--
-- Shu paytgacha buni HAR SO'ROVDA yamoq bilan yashirardik:
--     AND (close_at IS NULL OR close_at > now())
-- Bu yamoq queries.py da 7 joyda takrorlangan va u YETMAYDI: foydalanuvchi
-- "Barcha statuslar"ni tanlasa yoki tenderni to'g'ridan-to'g'ri ochsa, muddati
-- o'tgan yozuv baribir "Открыт" deb ko'rinadi. Ya'ni ro'yxatdan CHIQMAYDI.
--
-- YECHIM: yurishdan keyin (run_etl.py -> expire_stale_tenders) muddati o'tgan
-- 'open' yozuvlar 'expired' ga o'tkaziladi. Status endi ROSTNI aytadi va
-- barcha ko'rinishlar — ro'yxat, statistika, AI moslik, bildirishnoma — hech
-- qanday qo'shimcha shartsiz to'g'ri ishlaydi.
--
-- NEGA 'close' EMAS: 'close' — manbaning "tender yopildi" degan xabari. Biz
-- buni BILMAYMIZ, biz faqat muddat o'tganini ko'ramiz (tender uzaytirilgan
-- bo'lishi ham mumkin). Alohida kod ikkalasini chalkashtirmaydi va manba
-- yozuvni qayta ochiq deb bersa, keyingi ETL uni 'open' ga qaytaradi.
--
-- is_terminal = TRUE: dashboard buni "harakat qilib bo'lmaydi" deb belgilaydi.
-- status_id = NULL: bu manbaning kodi emas, BIZ qo'shgan kod.
-- =============================================================================

INSERT INTO dim_status (status_code, domain, name_ru, name_uz, is_terminal, status_id)
VALUES ('expired', 'tender', 'Срок истёк', 'Muddati tugagan', TRUE, NULL)
ON CONFLICT (status_code, domain) DO UPDATE
    SET name_ru = EXCLUDED.name_ru,
        name_uz = EXCLUDED.name_uz,
        is_terminal = EXCLUDED.is_terminal;

-- Yurish oxiridagi supurish shu ikki ustunni birga so'raydi.
CREATE INDEX IF NOT EXISTS idx_tender_status_close_at ON tender(status, close_at);
