-- =====================================================================
-- KOD QARORI — O'LCHOV JADVALI (qoida jadvali EMAS)
-- =====================================================================
--
-- MAQSAD: 40 ta haqiqiy qarorni qabul qilish va UCH RAQAMNI avtomatik
-- yozib olish:
--
--     1. VAQT           `ochilgan_at` -> `qaror_at`
--     2. MANBA          qaror taklifdan keldimi, qidiruvdanmi, qo'lda kiritildimi
--     3. QIDIRUV SONI   necha marta qidirildi
--
-- Uchinchisi eng muhimi: `talabsiz` tugmasi bosilganda undan OLDIN
-- qidiruv qilinganmi. Qidiruvsiz "talabsiz" — bu avtomatik o'lchovga
-- ishonish, va u XATO bo'lishi o'lchangan: `turniket` va `shlagbaum`
-- avtomatik o'lchovda "talabsiz" edi, qidiruv esa ularga aniq kod
-- topdi (26.30 Турникет, 27.90 Шлагбаум).
--
-- BU QOIDA JADVALI EMAS. Qoida jadvalining SHAKLI shu jadvaldagi
-- ma'lumotdan aniqlanadi, taxmindan emas.
--
-- ATAYLAB `UNIQUE (kalit)` YO'Q
-- ─────────────────────────────
-- Aynan o'sha cheklov o'lchamoqchi bo'lgan holatni to'sib qo'yardi:
-- broker bir atamaga IKKI kod bermoqchi bo'lishi mumkin
-- ("Кабель" -> 27.32 kuchlanish kabeli VA 26.20 tarmoq kabeli).
-- 40 qarordan keyin bu necha marta uchragani SANALADI va qoida
-- jadvali shunga qarab quriladi.
--
-- Qo'llash:
--   psql "$XT_DB_DSN" -f schema_patch_kod_qaror.sql
-- =====================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS kod_qaror (
    id           BIGSERIAL PRIMARY KEY,
    company_id   INT  NOT NULL REFERENCES company_account(id) ON DELETE CASCADE,

    kalit        TEXT NOT NULL,       -- `atama.normal()` — taqqoslash kaliti
    atama        TEXT NOT NULL,       -- ASL matn, ko'rsatish uchun

    -- 'kod' -> `code` to'ldirilgan;  'talabsiz' / 'otkazildi' -> NULL
    qaror        TEXT,
    code         TEXT REFERENCES dim_good_code(code),

    -- QAROR QAYERDAN KELDI. "Qidiruv yordam berdimi" raqami shundan.
    manba        TEXT,                -- 'taklif' | 'qidiruv' | 'qolda'

    qidiruv_soni INT  NOT NULL DEFAULT 0,
    ochilgan_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    qaror_at     TIMESTAMPTZ,
    kim          TEXT,

    -- Qaror bo'lsa KIM va QACHON majburiy — `catalog_product_code`
    -- dagi bilan bir xil qoida: tasdiq odamsiz yozilmaydi.
    CONSTRAINT kod_qaror_odam
        CHECK (qaror IS NULL OR (kim IS NOT NULL AND qaror_at IS NOT NULL)),

    CONSTRAINT kod_qaror_turi
        CHECK (qaror IS NULL OR qaror IN ('kod', 'talabsiz', 'otkazildi')),

    -- 'kod' qarorida kod BO'LISHI, boshqasida BO'LMASLIGI shart.
    -- Aks holda "talabsiz" deb belgilangan qatorda kod qolib ketardi.
    CONSTRAINT kod_qaror_kod_mos
        CHECK ((qaror = 'kod') = (code IS NOT NULL)),

    CONSTRAINT kod_qaror_manba
        CHECK (manba IS NULL OR manba IN ('taklif', 'qidiruv', 'qolda'))
);

COMMENT ON TABLE kod_qaror IS
    'Kodlash qarorlari va ular haqidagi O''LCHOV (vaqt, manba, qidiruv '
    'soni). Qoida jadvali EMAS — uning shakli shu ma''lumotdan chiqadi. '
    'UNIQUE(kalit) ATAYLAB yo''q: bir atamaga ikki kod berilishi '
    'o''lchanadigan holat.';

CREATE INDEX IF NOT EXISTS kod_qaror_company_idx ON kod_qaror (company_id);
CREATE INDEX IF NOT EXISTS kod_qaror_kalit_idx   ON kod_qaror (company_id, kalit);
--: Bir atama uchun bir vaqtda FAQAT BITTA ochiq (qarorsiz) qator.
--: Aks holda har ochilishda yangi qator paydo bo'lib, `qidiruv_soni`
--: bo'linib ketardi.
CREATE UNIQUE INDEX IF NOT EXISTS kod_qaror_ochiq_uq
    ON kod_qaror (company_id, kalit) WHERE qaror IS NULL;

-- ---------------------------------------------------------------------
-- O'LCHOV KO'RINISHI — 40 qarordan keyin javob beradigan uch savol
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_kod_qaror_olchov AS
SELECT company_id,
       count(*) FILTER (WHERE qaror IS NOT NULL)              AS qaror_soni,
       count(*) FILTER (WHERE qaror = 'kod')                  AS kod_berildi,
       count(*) FILTER (WHERE qaror = 'talabsiz')             AS talabsiz,
       count(*) FILTER (WHERE qaror = 'otkazildi')            AS otkazildi,
       -- 1. VAQT
       round(avg(extract(epoch FROM (qaror_at - ochilgan_at)))
             FILTER (WHERE qaror IS NOT NULL))                AS ortacha_sek,
       -- 2. MANBA — "qidiruv yordam berdimi"
       count(*) FILTER (WHERE manba = 'taklif')               AS taklifdan,
       count(*) FILTER (WHERE manba = 'qidiruv')              AS qidiruvdan,
       count(*) FILTER (WHERE manba = 'qolda')                AS qoldan,
       -- 3. QIDIRUVSIZ "talabsiz" — avtomatik o'lchovga ISHONILGAN holat.
       --    `turniket` misoli shu toifada xato bo'lgan bo'lardi.
       count(*) FILTER (WHERE qaror = 'talabsiz' AND qidiruv_soni = 0)
                                                              AS talabsiz_qidiruvsiz,
       count(*) FILTER (WHERE qaror = 'talabsiz' AND qidiruv_soni > 0)
                                                              AS talabsiz_qidiruvli,
       -- Bir atamaga BIR NECHTA kod berilganmi — qoida jadvali
       -- `UNIQUE(atama)` bo'la oladimi degan savolning javobi.
       (SELECT count(*) FROM (
           SELECT kalit FROM kod_qaror k2
            WHERE k2.company_id = k.company_id AND k2.qaror = 'kod'
            GROUP BY kalit HAVING count(*) > 1) x)             AS kop_kodli_atama
FROM kod_qaror k
GROUP BY company_id;

COMMENT ON VIEW v_kod_qaror_olchov IS
    'Uch savolning javobi: qancha vaqt ketdi, qidiruv yordam berdimi, '
    'qidiruvsiz "talabsiz" nechta. Va: bir atamaga ikki kod nechta marta.';

COMMIT;
