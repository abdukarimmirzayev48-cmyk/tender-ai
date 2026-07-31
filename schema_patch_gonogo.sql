-- =============================================================================
-- Sxema patch — GO / NO-GO uchun KOMPANIYA SALOHIYATI
-- Ishga tushirish:
--   psql "dbname=xtxarid user=postgres host=localhost" -f schema_patch_gonogo.sql
--
-- MUAMMO: `company_profile` hozirgacha faqat QIDIRUV sozlamalarini saqlagan
-- (kalit so'z, hudud, byudjet). Go/No-Go qarori esa kompaniyaning O'ZI haqida
-- ma'lumot talab qiladi. O'lchov: 11 mezondan 5 tasi (sertifikat, moliya,
-- tajriba, resurs, xavfsizlik ruxsati) uchun bazada MANBA YO'Q edi.
--
-- YECHIM: shu 5 mezonni yopadigan MINIMAL maydonlar. Hammasi NULL bo'lishi
-- mumkin — to'ldirilmagani "yomon" degani emas, "ma'lumot yo'q" degani.
-- AI shunda o'sha mezonni `malumot_yoq` deb belgilaydi va umumiy qarorni
-- "Review" ga tushiradi, xulosani O'YLAB TOPMAYDI.
--
-- Hozircha bitta faol profil (auth yo'q) — schema_patch_profile.sql bilan bir xil.
-- =============================================================================

ALTER TABLE company_profile
    -- Faoliyat tavsifi: "Biz tibbiy uskunalar yetkazib beramiz va montaj qilamiz"
    ADD COLUMN IF NOT EXISTS about              TEXT,
    -- Sertifikat/litsenziyalar: {'ISO 9001','Dori vositalari litsenziyasi'}
    ADD COLUMN IF NOT EXISTS certificates       TEXT[] NOT NULL DEFAULT '{}',
    -- Xavfsizlik ruxsatnomalari: {'Davlat siri bilan ishlash ruxsati'}
    ADD COLUMN IF NOT EXISTS clearances         TEXT[] NOT NULL DEFAULT '{}',
    -- Tajriba (yil). Shu sohada necha yil ishlagan.
    ADD COLUMN IF NOT EXISTS experience_years   INTEGER,
    -- Moliyaviy salohiyat: bir vaqtda bajara oladigan ENG KATTA shartnoma summasi.
    -- `max_cost` (qidiruv filtri) dan FARQLI — bu real qobiliyat chegarasi.
    ADD COLUMN IF NOT EXISTS max_contract_value NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS max_contract_currency CHAR(3),
    -- Resurs yetarliligi
    ADD COLUMN IF NOT EXISTS employees          INTEGER,
    ADD COLUMN IF NOT EXISTS capacity_note      TEXT,
    -- Deadline mezoni (kompaniya tomoni): odatiy yetkazish/bajarish muddati.
    -- Tenderning `delivery_period` i bilan taqqoslanadi.
    ADD COLUMN IF NOT EXISTS lead_time_days     INTEGER,
    -- Foyda/xarajat mezoni: shundan past marjada qatnashmaymiz.
    ADD COLUMN IF NOT EXISTS min_margin_percent NUMERIC(5,2),
    -- Majburiy talablar mezoni (kompaniya tomoni): o'z cheklovlarimiz.
    -- Masalan "avans talab qilamiz", "kafolat 12 oydan oshmaydi".
    ADD COLUMN IF NOT EXISTS constraints_note   TEXT,
    -- Akkaunt ma'lumotlari (yon paneldagi foydalanuvchi bloki shulardan o'qiydi).
    -- Auth qo'shilгanда bular alohida `app_user` jadvaliga ko'chadi; hozircha
    -- bitta profil bor, shuning uchun shu yerda turadi.
    ADD COLUMN IF NOT EXISTS contact_name       TEXT,
    ADD COLUMN IF NOT EXISTS email              TEXT,
    ADD COLUMN IF NOT EXISTS phone              TEXT,
    ADD COLUMN IF NOT EXISTS position           TEXT;

-- ESLATMA: `regions`, `min_cost`, `max_cost` ustunlari schema_patch_profile.sql
-- da allaqachon bor va frontendда HECH QAYERDA o'qilmayotgan edi (qidiruv
-- profili saqlangan qidiruvlardan keladi). Endi ular kompaniya profiliga
-- tegishli: `regions` -> geografik cheklov mezoni, `min_cost`/`max_cost` ->
-- tender qiymati mezoni.

COMMENT ON COLUMN company_profile.max_contract_value IS
    'Moliyaviy salohiyat: bajara oladigan eng katta shartnoma. min_cost/max_cost '
    'qidiruv filtri, bu esa Go/No-Go uchun real chegara.';
