-- =====================================================================
-- seed_sample_profile.sql
-- SINOV PROFILI — malaka tekshiruvini ishga tushirish uchun
--
-- Idempotent: qayta yurgizish xavfsiz.
--
-- Qo'llash:
--   psql -d xtxarid -f seed_sample_profile.sql
--
-- ██ BU HAQIQIY MA'LUMOT EMAS ██
--
-- `is_sample = true` qo'yiladi va malaka natijasi shu bayroqni O'ZI
-- BILAN OLIB YURADI. "Kompaniya 340 ta tenderga malakali" degan raqam
-- SHU FAYLDAGI o'ylab topilgan qiymatlarni o'lchaydi, haqiqatni emas.
--
-- Haqiqiy profil kiritilganda: `is_sample = false`, `sample_note = NULL`.
--
-- QIYMATLAR NEGA AYNAN SHUNDAY — o'lchovga qarab tanlangan
-- ═══════════════════════════════════════════════════════
-- Agar profil MAKSIMAL qiymatlar bilan to'ldirilsa, har tender o'tib
-- ketardi va `fail` tarmog'i HECH QACHON sinalmasdi — ya'ni tekshiruv
-- "hammasi joyida" deb turaverardi. Bu loyihada allaqachon uchragan
-- sinf: muvaffaqiyat salbiy shartdan olinishi (§16.58).
--
-- Shuning uchun qiymatlar OCHIQ TENDERLAR TAQSIMOTIGA qarab olindi
-- (653 ta ochiq, summasi ma'lum):
--
--     p25      51 000 000
--     mediana 219 886 577
--     p75   1 074 194 716
--     eng ko'p 189 647 892 000
--
--   `max_contract_value = 1 500 000 000` -> tenderlarning ~75% i
--   quvvat ichida, ~25% i tashqarida. Ikkala tarmoq ham sinaladi.
--
--   `certificates` da LITSENZIYA ATAYLAB YO'Q. Tibbiy uskuna
--   xaridlarida litsenziya tez-tez talab qilinadi, ya'ni `fail`
--   tarmog'i haqiqiy ma'lumotda ishga tushadi.
--
--   `clearances` BO'SH qoldiriladi -> `malumot_yoq` tarmog'i. Kichik
--   korxonalarda xavfsizlik ruxsatnomasi odatda bo'lmaydi, ya'ni bu
--   sun'iy holat emas.
--
--   `regions` ikkita: 33.2137 (709 tender) va 33.711 (214 tender).
--   Qolgan hududlar mos kelmaydi -> hudud tarmog'i ham ikki tomonlama.
-- =====================================================================

BEGIN;

UPDATE company_profile SET
    -- SERTIFIKATLAR — inson o'qiydigan matn, kod emas.
    -- `qualification.py` ikkala tomonni `compliance.DOC_TYPES` lug'ati
    -- va `atama.py` orqali normallashtiradi (uch alifbo muammosi).
    certificates = ARRAY[
        'Davlat ro''yxatidan o''tganlik guvohnomasi',
        'Muvofiqlik sertifikati (ISO 13485)',
        'Kafolat xati',
        'Bank rekvizitlari',
        'Soliq ma''lumotnomasi'
    ],

    -- ATAYLAB BO'SH: `malumot_yoq` tarmog'ini sinash uchun.
    clearances = ARRAY[]::text[],

    experience_years      = 6,
    max_contract_value    = 1500000000,
    max_contract_currency = 'UZS',
    employees             = 18,
    capacity_note         = 'Toshkentda ombor (400 m2); yetkazish o''z '
                            || 'transporti bilan (2 ta furgon).',
    lead_time_days        = 21,
    min_margin_percent    = 12,
    constraints_note      = 'Avans 0% bo''lgan yirik shartnomalar '
                            || 'aylanma mablag'' tanqisligi tug''diradi.',

    regions   = ARRAY['33.2137', '33.711'],
    min_cost  = 20000000,
    max_cost  = 3000000000,
    currency  = 'UZS',

    is_sample   = true,
    sample_note = 'seed_sample_profile.sql (2026-08-26). Qiymatlar '
                  || 'ochiq tenderlar taqsimotiga qarab tanlangan, '
                  || 'ya''ni malaka tekshiruvining o''tadi/o''tmaydi/'
                  || 'ma''lumot yo''q tarmoqlari uchalasi ham ishga '
                  || 'tushadi. HAQIQIY MA''LUMOT EMAS.',
    updated_at  = now()
WHERE company_id = (SELECT id FROM company_account
                    WHERE active ORDER BY id DESC LIMIT 1);

-- ---------------------------------------------------------------------
-- TEKSHIRUV — musbat tasdiq, "xato chiqmadi" yetarli emas
-- ---------------------------------------------------------------------
DO $$
DECLARE
    n_toldirilgan INT;
    n_sample      INT;
BEGIN
    SELECT toldirilgan INTO n_toldirilgan
      FROM v_profile_completeness WHERE is_sample LIMIT 1;
    SELECT count(*) INTO n_sample
      FROM company_profile WHERE is_sample;

    IF n_sample = 0 THEN
        RAISE EXCEPTION 'Hech bir profil yangilanmadi (faol hisob bormi?)';
    END IF;
    -- NULL NI ALOHIDA TUTAMIZ. `NULL < 7` -> NULL, ya'ni IF ISHGA
    -- TUSHMAYDI va tekshiruv "o'tdi" deb ko'rinadi. Birinchi yurishda
    -- AYNAN SHUNDAY bo'ldi: jurnalda "<NULL> ta to'ldirildi" yozildi
    -- va skript muvaffaqiyat deb tugadi.
    IF n_toldirilgan IS NULL THEN
        RAISE EXCEPTION 'To`ldirilgan maydon soni O`LCHANMADI '
                        '(v_profile_completeness NULL qaytardi)';
    END IF;
    IF n_toldirilgan < 7 THEN
        RAISE EXCEPTION 'Profil to`liq to`ldirilmadi: 8 dan %', n_toldirilgan;
    END IF;
    RAISE NOTICE 'seed_sample_profile.sql: % maydondan % ta to`ldirildi '
                 '(clearances ATAYLAB bo`sh)', 8, n_toldirilgan;
END $$;

COMMIT;

-- =====================================================================
-- QAYTARISH (haqiqiy profil kiritilganda):
--
--   UPDATE company_profile
--      SET is_sample = false, sample_note = NULL
--    WHERE company_id = <id>;
--
-- Sinov qiymatlarini TOZALASH:
--
--   UPDATE company_profile SET
--       certificates = ARRAY[]::text[], clearances = ARRAY[]::text[],
--       experience_years = NULL, max_contract_value = NULL,
--       employees = NULL, capacity_note = NULL, lead_time_days = NULL,
--       min_margin_percent = NULL, constraints_note = NULL,
--       is_sample = false, sample_note = NULL
--    WHERE is_sample;
-- =====================================================================
