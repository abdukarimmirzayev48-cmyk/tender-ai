-- =====================================================================
-- KODLASH QARORI — DALILNI SAQLASH, QAROR LUG'ATINI TO'LDIRISH,
--                  BAHOLASH KO'RINISHLARI
-- =====================================================================
--
-- HOLAT (o'lchangan 2026-08-30):
--     catalog_product        1 797
--     kodlangan                960   (hammasi `manba='taklif'`,
--                                     `tasdiqlagan='kompaniya'`)
--     ataylab kodsiz           837
--     kod_qaror                  0   <-- INSON QARORI YO'Q
--
-- Ya'ni quvur ISHLAYDI, lekin uning aniqligini o'lchaydigan HECH
-- QANDAY inson ma'lumoti yo'q. Birinchi 40 qaror aynan shu bo'shliqni
-- to'ldirish uchun.
--
-- BU PATCH NIMANI TUZATADI
-- ------------------------
-- 1. DALIL SAQLANMASDI. `kod_qaror` da qaror BOR edi, lekin inson
--    NIMA KO'RIB qaror qilgani yo'q edi. ML uchun bu halokatli:
--    yorliq bor, kirish yo'q. Endi `dalil` (JSONB) inson ekranda
--    ko'rgan hamma narsani saqlaydi.
--
-- 2. TAKLIF BILAN KELISHUVNI O'LCHAB BO'LMASDI. Mashina nimani
--    taklif qilgani yozilmasdi, shuning uchun "avtomatik taklif necha
--    foizda to'g'ri" degan savol JAVOBSIZ edi. Endi `taklif_code`
--    qaror paytida yozib olinadi.
--
-- 3. QAROR LUG'ATI TO'LIQ EMAS EDI:
--        kod        kod berildi
--        talabsiz   korpusda talab yo'q
--        otkazildi  hozir emas
--    "DALIL YETARLI EMAS" holati YO'Q edi va u `talabsiz` ga
--    qo'shilib ketardi. Ikkisi BUTUNLAY boshqa gap:
--        talabsiz  = "men ko'rdim, korpusda bunday talab yo'q"
--        dalilsiz  = "men qaror qila olmadim"
--    Ularni aralashtirish `talabsiz` ni ishonchsiz qilardi va
--    u aynan quvur aniqligini o'lchaydigan raqam.
--
-- 4. RAD ETILGAN TAKLIF YO'QOLARDI. Inson "bu taklif noto'g'ri"
--    deganda bu hech qayerda qolmasdi — holbuki MANFIY misol
--    musbatidan kam qimmatli emas.
--
-- 5. BIR ATAMAGA IKKI KOD — fikr o'zgarishimi yoki HAQIQATAN ikki
--    kodmi? `UNIQUE(kalit)` ataylab yo'q, lekin ikkisini AJRATIB
--    bo'lmasdi. Endi `qoshimcha_kod` bayrog'i buni aytadi.
--
-- NIMA QILINMAYDI — ATAYLAB
-- -------------------------
-- Bu patch HECH QANDAY QOIDA CHIQARMAYDI. Birinchi 40 qarorning
-- maqsadi — O'LCHASH va SXEMANI SINASH. Qoida jadvalining shakli
-- (bir atama -> bir kod, yoki bir atama -> ko'p kod) qarorlar
-- paytida ma'lum bo'ladi. Ma'lumot yig'ilmasdan qoida yozish —
-- o'lchanmagan chegaraga qatlam qurish demak.
--
-- Idempotent.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. DALIL VA TAKLIF USTUNLARI
-- ---------------------------------------------------------------------
ALTER TABLE kod_qaror
    -- Inson ekranda KO'RGAN hamma narsa. Manba — MIJOZ (interfeys),
    -- server qayta hisoblab ko'rmaydi. Bu ATAYLAB: bizga "haqiqat"
    -- emas, "inson nimaga qarab qaror qildi" kerak. Server qayta
    -- hisoblasa boshqa natija chiqishi mumkin (korpus o'zgargan) va
    -- o'shanda yorliq boshqa kirishga bog'lanib qolardi.
    ADD COLUMN IF NOT EXISTS dalil            JSONB,
    -- Qaror paytida BIRINCHI o'rinda turgan avtomatik taklif.
    -- NULL = taklif ko'rsatilmagan.
    ADD COLUMN IF NOT EXISTS taklif_code      TEXT REFERENCES dim_good_code(code),
    ADD COLUMN IF NOT EXISTS taklif_skor      NUMERIC,
    -- Inson ANIQ "bu taklif noto'g'ri" degan kodlar. MANFIY misollar.
    ADD COLUMN IF NOT EXISTS rad_takliflar    TEXT[],
    -- Oxirgi ishlatilgan qidiruv so'zi. `qidiruv_soni` "nechta"
    -- deydi, bu "nima" deydi.
    ADD COLUMN IF NOT EXISTS qidiruv_sozi     TEXT,
    -- Bu kod OLDINGISIGA QO'SHIMCHA (atama haqiqatan ko'p kodli),
    -- fikr o'zgarishi EMAS.
    ADD COLUMN IF NOT EXISTS qoshimcha_kod    BOOLEAN NOT NULL DEFAULT false,
    -- Ixtiyoriy izoh — "nega shunday qaror qildim".
    ADD COLUMN IF NOT EXISTS izoh             TEXT;

COMMENT ON COLUMN kod_qaror.dalil IS
    'Inson ekranda KO''RGAN dalil (takliflar, qidiruv natijasi, korpus '
    'raqamlari). Mijozdan keladi va server uni QAYTA HISOBLAMAYDI: ML '
    'uchun "haqiqat" emas, "inson nimaga qarab qaror qildi" kerak.';
COMMENT ON COLUMN kod_qaror.taklif_code IS
    'Qaror paytida birinchi o''rinda turgan AVTOMATIK taklif. '
    'Kelishuv foizi shundan hisoblanadi. NULL = taklif bo''lmagan.';
COMMENT ON COLUMN kod_qaror.rad_takliflar IS
    'Inson ANIQ rad etgan kodlar — MANFIY misollar. Musbat misoldan '
    'kam qimmatli emas: "nima emas" ni bilmasdan chegara chizib bo''lmaydi.';
COMMENT ON COLUMN kod_qaror.qoshimcha_kod IS
    'true = bu kod avvalgisiga QO''SHIMCHA (atama haqiqatan ko''p kodli). '
    'false = mustaqil qaror. Ikkisi ajratilmasa "bir atamaga ikki kod" '
    'fikr o''zgarishi bilan aralashib ketardi.';

-- ---------------------------------------------------------------------
-- 2. QAROR LUG'ATI — "DALIL YETARLI EMAS" QO'SHILADI
-- ---------------------------------------------------------------------
ALTER TABLE kod_qaror DROP CONSTRAINT IF EXISTS kod_qaror_turi;
ALTER TABLE kod_qaror ADD CONSTRAINT kod_qaror_turi
    CHECK (qaror IS NULL OR qaror IN ('kod', 'talabsiz', 'dalilsiz', 'otkazildi'));

COMMENT ON COLUMN kod_qaror.qaror IS
    'kod       — kod berildi (code SHART); '
    'talabsiz  — INSON KO''RDI, korpusda bunday talab yo''q; '
    'dalilsiz  — inson QAROR QILA OLMADI (dalil yetarli emas); '
    'otkazildi — hozir emas, keyinroq. '
    '`talabsiz` va `dalilsiz` ATAYLAB ajratilgan: birinchisi XULOSA, '
    'ikkinchisi XULOSA YO''QLIGI.';

-- ---------------------------------------------------------------------
-- 3. BO'SH / YAROQSIZ KOD QULFI
-- ---------------------------------------------------------------------
DO $$
BEGIN
    -- FK `dim_good_code` ga bog'laydi, lekin BO'SH SATR yoki faqat
    -- probel FK ga yetib bormasdan oldin ham to'silsin — xato
    -- xabari ANIQ bo'lsin ("kod bo'sh" vs "kod topilmadi").
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'kod_qaror_code_bosh_emas') THEN
        ALTER TABLE kod_qaror ADD CONSTRAINT kod_qaror_code_bosh_emas
            CHECK (code IS NULL OR length(btrim(code)) > 0);
    END IF;

    -- `kim` ham bo'sh satr bo'la olmaydi. Mavjud `kod_qaror_odam`
    -- faqat NULL ni to'sadi, `''` esa o'tib ketardi.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'kod_qaror_kim_bosh_emas') THEN
        ALTER TABLE kod_qaror ADD CONSTRAINT kod_qaror_kim_bosh_emas
            CHECK (kim IS NULL OR length(btrim(kim)) > 0);
    END IF;

    -- QO'SHIMCHA KOD faqat `kod` qarorida ma'noga ega.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'kod_qaror_qoshimcha_chk') THEN
        ALTER TABLE kod_qaror ADD CONSTRAINT kod_qaror_qoshimcha_chk
            CHECK (NOT qoshimcha_kod OR qaror = 'kod');
    END IF;

    -- Qidiruv so'zi yozilgan bo'lsa qidiruv SANOG'I ham bo'lsin.
    -- Aks holda "qidirdim" degan da'vo hisoblagichda ko'rinmasdi.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'kod_qaror_qidiruv_izchil') THEN
        ALTER TABLE kod_qaror ADD CONSTRAINT kod_qaror_qidiruv_izchil
            CHECK (qidiruv_sozi IS NULL OR qidiruv_soni > 0);
    END IF;

    -- `taklif_skor` faqat taklif bilan birga.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'kod_qaror_taklif_izchil') THEN
        ALTER TABLE kod_qaror ADD CONSTRAINT kod_qaror_taklif_izchil
            CHECK (taklif_skor IS NULL OR taklif_code IS NOT NULL);
    END IF;

    -- DALIL faqat QAROR bilan birga saqlanadi. Ochiq qatorda dalil
    -- bo'lishi mumkin emas: u qaror paytidagi holatni yozib oladi.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'kod_qaror_dalil_qaror_bilan') THEN
        ALTER TABLE kod_qaror ADD CONSTRAINT kod_qaror_dalil_qaror_bilan
            CHECK (dalil IS NULL OR qaror IS NOT NULL);
    END IF;
END $$;

-- ---------------------------------------------------------------------
-- 4. AUDIT IZI — mahsulot kodi QAYSI qarordan keldi
-- ---------------------------------------------------------------------
-- Ilgari `catalog_product_code` da faqat `tasdiqlagan` (ism) bor edi.
-- "Bu kod qayerdan keldi" degan savolga javob YO'Q edi va 960 ta
-- mavjud qator aynan shu holatda: `tasdiqlagan='kompaniya'`, ya'ni
-- na foydalanuvchi, na skript — shunchaki matn.
--
-- Endi yangi qarorlar `kod_qaror` ga BOG'LANADI. Eski 960 qatorda
-- `qaror_id` NULL qoladi va bu HALOL: ular ko'rib chiqish halqasidan
-- o'tmagan (ular `_tests/ai_eval/kod_biriktir.py` skripti tur
-- darajasidagi inson qaroridan kengaytirgan to'plam).
ALTER TABLE catalog_product_code
    ADD COLUMN IF NOT EXISTS qaror_id BIGINT REFERENCES kod_qaror(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_cpc_qaror ON catalog_product_code (qaror_id)
    WHERE qaror_id IS NOT NULL;

COMMENT ON COLUMN catalog_product_code.qaror_id IS
    'Bu biriktirma QAYSI inson qaroridan kelgani (`kod_qaror.id`). '
    'NULL = ko''rib chiqish halqasidan o''tmagan (2026-08-28 dagi '
    '960 ta to''plam shunday: tur darajasidagi qaror skript bilan '
    'kengaytirilgan). ML ground truth uchun FAQAT `qaror_id IS NOT '
    'NULL` qatorlar ishlatilsin.';

-- ---------------------------------------------------------------------
-- 5. O'LCHOV KO'RINISHI — kengaytirildi
-- ---------------------------------------------------------------------
-- FAQAT HAQIQIY INSON HARAKATI SANALADI: `qaror IS NOT NULL`
-- (ya'ni tugma bosilgan). Ochilgan-u qaror qilinmagan qator
-- hisoblagichga TUSHMAYDI — aynan shu render/qaror chalkashligi
-- 2026-08-30 da "40 qaror" degan soxta raqam bergan edi.
-- `CREATE OR REPLACE` ISHLAMAYDI: ustunlar ro'yxati o'zgaradi va
-- PostgreSQL mavjud ko'rinishning ustun tartibini o'zgartirishga
-- ruxsat bermaydi. `CASCADE` ATAYLAB ishlatilmaydi — bog'liq obyekt
-- bo'lsa DROP yiqilsin va biz uni KO'RAYLIK.
DROP VIEW IF EXISTS v_kod_pilot;
DROP VIEW IF EXISTS v_kod_qaror_olchov;
CREATE VIEW v_kod_qaror_olchov AS
SELECT
    k.company_id,

    -- ---- HAJM ----
    count(*) FILTER (WHERE k.qaror IS NOT NULL)                  AS qaror_soni,
    count(DISTINCT k.kalit) FILTER (WHERE k.qaror IS NOT NULL)   AS atama_soni,
    count(*) FILTER (WHERE k.qaror IS NULL)                      AS ochiq_qator,

    -- ---- QAROR TURLARI ----
    count(*) FILTER (WHERE k.qaror = 'kod')                      AS kod_berildi,
    count(*) FILTER (WHERE k.qaror = 'talabsiz')                 AS talabsiz,
    count(*) FILTER (WHERE k.qaror = 'dalilsiz')                 AS dalilsiz,
    count(*) FILTER (WHERE k.qaror = 'otkazildi')                AS otkazildi,

    -- ---- TAKLIF BILAN KELISHUV ----
    -- Uch holat ATAYLAB alohida: "qabul qildim", "boshqasini
    -- tanladim" va "umuman kod bermadim" — uchtasi uch xil signal.
    count(*) FILTER (WHERE k.qaror IS NOT NULL
                       AND k.taklif_code IS NOT NULL)            AS taklifli_qaror,
    count(*) FILTER (WHERE k.qaror = 'kod'
                       AND k.taklif_code IS NOT NULL
                       AND k.code = k.taklif_code)               AS taklif_qabul,
    count(*) FILTER (WHERE k.qaror = 'kod'
                       AND k.taklif_code IS NOT NULL
                       AND k.code <> k.taklif_code)              AS taklif_ozgartirildi,
    count(*) FILTER (WHERE k.qaror IN ('talabsiz', 'dalilsiz')
                       AND k.taklif_code IS NOT NULL)            AS taklif_rad,
    round(100.0 * count(*) FILTER (WHERE k.qaror = 'kod'
                                     AND k.taklif_code IS NOT NULL
                                     AND k.code = k.taklif_code)
          / NULLIF(count(*) FILTER (WHERE k.qaror IS NOT NULL
                                      AND k.taklif_code IS NOT NULL), 0), 1)
                                                                 AS taklif_kelishuv_foiz,
    -- ANIQ rad etilgan takliflar (manfiy misollar).
    coalesce(sum(coalesce(array_length(k.rad_takliflar, 1), 0)), 0)
                                                                 AS rad_taklif_soni,

    -- ---- VAQT ----
    -- O'LCHANMAGAN QATOR O'RTACHAGA QO'SHILMAYDI. `ochilgan_at`
    -- NULL = "o'lchanmadi", nol EMAS.
    round(avg(EXTRACT(epoch FROM k.qaror_at - k.ochilgan_at))
          FILTER (WHERE k.qaror IS NOT NULL AND k.ochilgan_at IS NOT NULL))
                                                                 AS ortacha_sek,
    round(percentile_cont(0.5) WITHIN GROUP (
              ORDER BY EXTRACT(epoch FROM k.qaror_at - k.ochilgan_at))
          FILTER (WHERE k.qaror IS NOT NULL AND k.ochilgan_at IS NOT NULL))
                                                                 AS median_sek,
    count(*) FILTER (WHERE k.qaror IS NOT NULL
                       AND k.ochilgan_at IS NOT NULL)            AS olchangan,
    count(*) FILTER (WHERE k.qaror IS NOT NULL
                       AND k.ochilgan_at IS NULL)                AS olchovsiz,

    -- ---- MANBA ----
    count(*) FILTER (WHERE k.manba = 'taklif')                   AS taklifdan,
    count(*) FILTER (WHERE k.manba = 'qidiruv')                  AS qidiruvdan,
    count(*) FILTER (WHERE k.manba = 'qolda')                    AS qoldan,

    -- ---- QIDIRUV ----
    count(*) FILTER (WHERE k.qaror IS NOT NULL
                       AND k.qidiruv_soni > 0)                   AS qidiruvli_qaror,
    round(100.0 * count(*) FILTER (WHERE k.qaror IS NOT NULL AND k.qidiruv_soni > 0)
          / NULLIF(count(*) FILTER (WHERE k.qaror IS NOT NULL), 0), 1)
                                                                 AS qidiruv_foiz,
    -- QIDIRUVSIZ "talabsiz" — avtomatik o'lchovga ISHONISH demak.
    -- Bu raqam past bo'lishi kerak; yuqori bo'lsa `talabsiz`
    -- statistikasiga tayanib bo'lmaydi.
    count(*) FILTER (WHERE k.qaror = 'talabsiz' AND k.qidiruv_soni = 0)
                                                                 AS talabsiz_qidiruvsiz,
    count(*) FILTER (WHERE k.qaror = 'talabsiz' AND k.qidiruv_soni > 0)
                                                                 AS talabsiz_qidiruvli,

    -- ---- KO'P KODLI ATAMA ----
    -- ANIQ belgilangani (inson "bu qo'shimcha" dedi) va shunchaki
    -- ikki qator bo'lgani AJRATILADI.
    count(*) FILTER (WHERE k.qoshimcha_kod)                      AS qoshimcha_kod_soni,
    (SELECT count(*) FROM (
        SELECT k2.kalit FROM kod_qaror k2
         WHERE k2.company_id = k.company_id AND k2.qaror = 'kod'
         GROUP BY k2.kalit HAVING count(*) > 1) x)               AS kop_kodli_atama,

    -- ---- DALIL QAMROVI ----
    -- Dalilsiz qaror ML uchun YAROQSIZ: yorliq bor, kirish yo'q.
    count(*) FILTER (WHERE k.qaror IS NOT NULL AND k.dalil IS NOT NULL)
                                                                 AS dalilli_qaror,
    round(100.0 * count(*) FILTER (WHERE k.qaror IS NOT NULL AND k.dalil IS NOT NULL)
          / NULLIF(count(*) FILTER (WHERE k.qaror IS NOT NULL), 0), 1)
                                                                 AS dalil_qamrov_foiz
FROM kod_qaror k
GROUP BY k.company_id;

COMMENT ON VIEW v_kod_qaror_olchov IS
    'Kodlash qarorlarining o`lchovi. FAQAT `qaror IS NOT NULL` '
    'sanaladi — ochilgan-u qaror qilinmagan qator hisoblagichga '
    'tushmaydi. `olchovsiz` o`rtachaga QO`SHILMAYDI.';

-- ---------------------------------------------------------------------
-- 6. QAROR TAFSILOTI — baholash uchun eksport
-- ---------------------------------------------------------------------
-- Har qaror bitta qatorda, dalili bilan. ML to'plamini shundan
-- yig'iladi va u ATAYLAB "xom": hech qanday qoida qo'llanmaydi.
CREATE OR REPLACE VIEW v_kod_qaror_tafsil AS
SELECT
    k.id, k.company_id, k.kalit, k.atama,
    k.qaror, k.code,
    d.name_ru                                   AS kod_nomi,
    k.taklif_code,
    dt.name_ru                                  AS taklif_nomi,
    k.taklif_skor,
    CASE
        WHEN k.taklif_code IS NULL                 THEN 'taklif_yoq'
        WHEN k.qaror <> 'kod'                      THEN 'kod_berilmadi'
        WHEN k.code = k.taklif_code                THEN 'qabul'
        ELSE 'ozgartirildi'
    END                                         AS taklif_holati,
    k.rad_takliflar,
    k.qoshimcha_kod,
    k.manba, k.qidiruv_soni, k.qidiruv_sozi,
    k.kim, k.ochilgan_at, k.qaror_at,
    CASE WHEN k.ochilgan_at IS NOT NULL AND k.qaror_at IS NOT NULL
         THEN round(EXTRACT(epoch FROM k.qaror_at - k.ochilgan_at))
    END                                         AS sek,
    k.izoh,
    k.dalil,
    (k.dalil IS NOT NULL)                       AS dalil_bor
FROM kod_qaror k
LEFT JOIN dim_good_code d  ON d.code  = k.code
LEFT JOIN dim_good_code dt ON dt.code = k.taklif_code
WHERE k.qaror IS NOT NULL;

COMMENT ON VIEW v_kod_qaror_tafsil IS
    'Har inson qarori bitta qatorda, dalili bilan — ML to`plamining '
    'xom manbai. `sek` NULL = vaqt o`lchanmadi (nol EMAS).';

-- ---------------------------------------------------------------------
-- 7. PILOT HOLATI — "40 qarorga qancha qoldi"
-- ---------------------------------------------------------------------
-- Maqsad EKRANDA ko'rinsin: nechta qaror bor, nechtasi kerak.
-- Bu raqam qo'lda hisoblanmasin — qo'lda hisoblangan raqam
-- xotiradan tiklanib TAXMINGA aylanadi.
CREATE VIEW v_kod_pilot AS
SELECT
    c.id                                        AS company_id,
    40                                          AS maqsad,
    coalesce(o.qaror_soni, 0)                   AS qaror_soni,
    coalesce(o.atama_soni, 0)                   AS atama_soni,
    greatest(0, 40 - coalesce(o.atama_soni, 0)) AS qolgan,
    coalesce(o.olchangan, 0)                    AS olchangan,
    coalesce(o.dalilli_qaror, 0)                AS dalilli,
    o.ortacha_sek,
    o.median_sek,
    o.taklif_kelishuv_foiz,
    o.qidiruv_foiz,
    -- Navbatda qancha atama qolgani `kodlash.navbat()` dan keladi;
    -- bu yerda faqat kodsiz MAHSULOT soni (arzon sanoq).
    (SELECT count(*) FROM v_catalog_kodsiz z WHERE z.company_id = c.id)
                                                AS kodsiz_mahsulot
FROM company_account c
LEFT JOIN v_kod_qaror_olchov o ON o.company_id = c.id;

COMMENT ON VIEW v_kod_pilot IS
    'Pilot holati: 40 ta ATAMA qaroriga qancha qolgani. Maqsad '
    'ATAMA soni bo`yicha (`atama_soni`), qator soni bo`yicha EMAS — '
    'bir atamaga ikki kod berish maqsadni soxta yaqinlashtirardi.';

-- ---------------------------------------------------------------------
-- 8. MUSBAT TASDIQ
-- ---------------------------------------------------------------------
DO $$
DECLARE
    n_soxta INT;
BEGIN
    -- Qaror bor, lekin kim yoki vaqt yo'q -> imkonsiz bo'lishi kerak.
    SELECT count(*) INTO n_soxta FROM kod_qaror
     WHERE qaror IS NOT NULL AND (kim IS NULL OR btrim(kim) = ''
                                  OR qaror_at IS NULL);
    IF n_soxta > 0 THEN
        RAISE EXCEPTION 'Odamsiz qaror qatori: %', n_soxta;
    END IF;
    RAISE NOTICE 'TASDIQ: odamsiz qaror = 0; qaror lug''ati 4 qiymatli; dalil ustuni tayyor.';
END $$;

COMMIT;
