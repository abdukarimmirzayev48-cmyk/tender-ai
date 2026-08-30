-- =====================================================================
-- KATALOG KODLASH TAHLILI — "kod yo'q" ning SABABI saqlanadi
-- =====================================================================
--
-- O'LCHANGAN MUAMMO (2026-08-31, `xtxarid`):
--
--   1 797 mahsulotdan 960 tasi "kodlangan", 837 tasi kodsiz. Lekin
--   ikkala raqam ham aytilganidan boshqacha ma'no beradi:
--
--   a) 960 taning HAMMASIDA 5 BELGILI keng kod va atigi UCH XIL
--      qiymat: 26.40 (612 ta), 26.30 (299 ta), 26.20 (49 ta).
--      Hammasi 2026-08-28 da ~1s40d ichida `kompaniya` tomonidan
--      OMMAVIY berilgan. Ya'ni bu mahsulot bo'yicha tahlil emas,
--      uchta keng chelak.
--
--      8 BELGILI aniq kod: 0 ta.
--
--   b) 837 ta "kodsiz" — bu YAGONA chelak edi va ichida butunlay
--      boshqa ishlar yashiringan. O'lchandi (`catalog_auto.tahlil()`):
--
--          sozlar_mos_emas   294  (35.1%)
--          nomzodsiz         263  (31.4%)
--          dalil_kam         149  (17.8%)
--          KOD TOPILADI      118  (14.1%)   <- bugun kodlanardi
--          tokensiz           13   (1.6%)
--          noaniq              0   (0.0%)
--
--   ILDIZ SABAB: `catalog_auto.classify_product()` FAQAT bitta
--   mahsulot CRUD idan chaqiriladi (`api/main.py` da 3 joy). Barcha
--   1 797 mahsulot 2026-08-27 da OMMAVIY IMPORT bilan yaratilgan va
--   importer klassifikatsiyani chaqirmaydi. Backfill yo'li YO'Q.
--
--   Ya'ni qamrov nol, chunki algoritm qattiq emas — u HECH QACHON
--   YURGIZILMAGAN.
--
-- CHEGARALAR O'ZGARMAYDI. `MIN_EVIDENCE=2` va `MIN_SHARE=0.75` shu
-- holicha qoladi: `noaniq = 0` o'lchovi ularning qamrovni
-- to'smayotganini ko'rsatadi. Qamrovni chegara pasaytirib oshirish
-- precisionni yeydi va bu ATAYLAB qilinmagan.
--
-- BU JADVAL NIMA UCHUN: tahlil qimmat (837 mahsulot uchun ~6 s va
-- 1 674 ta SQL). Uni har so'rovda qayta hisoblash navbatni sekin
-- qilardi. Natija saqlanadi va NAVBAT undan o'qiladi.
--
-- Idempotent.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1) Tahlil natijasi
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS catalog_kod_tahlil (
    company_id   INT    NOT NULL REFERENCES company_account(id) ON DELETE CASCADE,
    product_id   BIGINT NOT NULL REFERENCES catalog_product(id) ON DELETE CASCADE,

    -- NEGA kod berilmadi (yoki berildi). `catalog_auto.SABABLAR`.
    sabab        TEXT   NOT NULL,

    -- Taklif qilingan kod — FAQAT `sabab='kod'` bo'lganda ma'noli.
    -- Boshqa holatlarda eng kuchli nomzod bo'lishi mumkin, lekin u
    -- QO'LLANMAGAN va shunday deb o'qilishi kerak.
    taklif_code  TEXT,
    ishonch      NUMERIC(4,3),

    -- DALIL RAQAMLARI. `dalil` — shu kodni tasdiqlagan tarixiy lot
    -- soni; `jami` — mos kelgan hamma lot. Ulush = dalil/jami.
    dalil        INT    NOT NULL DEFAULT 0,
    jami         INT    NOT NULL DEFAULT 0,
    nomzod       INT    NOT NULL DEFAULT 0,

    -- Tahlil AYNAN qaysi so'zlar bo'yicha ishlaganini saqlaydi —
    -- busiz "nega bu kod?" savoliga javob yo'q.
    tokenlar     TEXT[],
    -- Eng kuchli 3 nomzod: `noaniq` holatida qaysi oilalar
    -- to'qnashganini odam ko'radi.
    kodlar       JSONB,
    misollar     TEXT[],

    -- BIZNES QIYMATI. Navbat shu bo'yicha tartiblanadi: kam
    -- uchraydigan mahsulotni kodlash arzon, lekin foydasi ham kam.
    ochiq_tender INT    NOT NULL DEFAULT 0,
    tarixiy_lot  INT    NOT NULL DEFAULT 0,

    tahlil_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (company_id, product_id)
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='catalog_kod_tahlil_sabab_chk') THEN
        ALTER TABLE catalog_kod_tahlil ADD CONSTRAINT catalog_kod_tahlil_sabab_chk
            CHECK (sabab IN ('kod', 'tokensiz', 'nomzodsiz',
                             'sozlar_mos_emas', 'dalil_kam', 'noaniq'));
    END IF;

    -- KOD TAKLIF QILINGAN BO'LSA DALIL BO'LISHI SHART. Busiz
    -- "kod bor, lekin nimaga asoslangani noma'lum" qatori paydo
    -- bo'lardi — bu loyihada tuzatilgan xatoning aynan takrori.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='catalog_kod_tahlil_dalil_chk') THEN
        ALTER TABLE catalog_kod_tahlil ADD CONSTRAINT catalog_kod_tahlil_dalil_chk
            CHECK (sabab <> 'kod'
                OR (taklif_code IS NOT NULL AND ishonch IS NOT NULL
                    AND dalil >= 2 AND jami > 0));
    END IF;

    -- Ishonch — ULUSH, ya'ni 0..1.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='catalog_kod_tahlil_ishonch_chk') THEN
        ALTER TABLE catalog_kod_tahlil ADD CONSTRAINT catalog_kod_tahlil_ishonch_chk
            CHECK (ishonch IS NULL OR (ishonch >= 0 AND ishonch <= 1));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS catalog_kod_tahlil_sabab_idx
    ON catalog_kod_tahlil (company_id, sabab);
CREATE INDEX IF NOT EXISTS catalog_kod_tahlil_qiymat_idx
    ON catalog_kod_tahlil (company_id, ochiq_tender DESC, tarixiy_lot DESC);

COMMENT ON TABLE catalog_kod_tahlil IS
    'Katalog kodlash tahlili: NEGA kod berilgan yoki berilmagan. '
    'Sabab ANIQ saqlanadi — "kod yo''q" yagona chelak emas.';

-- ---------------------------------------------------------------------
-- 2) QAMROV — halol maxraj bilan
-- ---------------------------------------------------------------------
-- MUHIM: 5 belgili KENG kod va 8 belgili ANIQ kod ALOHIDA sanaladi.
-- Ularni qo'shib "kodlangan" deyish 26.40 chelagidagi 612 mahsulotni
-- aniq kodlangan qilib ko'rsatardi.
DROP VIEW IF EXISTS v_catalog_kod_qamrov;
CREATE VIEW v_catalog_kod_qamrov AS
WITH k AS (
    SELECT p.company_id, p.id AS product_id,
           max(length(v.code)) AS eng_uzun
      FROM catalog_product p
      LEFT JOIN v_catalog_code_active v
             ON v.product_id = p.id AND v.company_id = p.company_id
     GROUP BY 1, 2
)
SELECT k.company_id,
       count(*)                                          AS mahsulot,
       count(*) FILTER (WHERE eng_uzun >= 8)             AS aniq_kod,
       count(*) FILTER (WHERE eng_uzun BETWEEN 1 AND 7)  AS keng_kod,
       count(*) FILTER (WHERE eng_uzun IS NULL)          AS kodsiz,
       round(100.0 * count(*) FILTER (WHERE eng_uzun >= 8)
             / nullif(count(*), 0), 2)                   AS aniq_foiz,
       round(100.0 * count(*) FILTER (WHERE eng_uzun IS NOT NULL)
             / nullif(count(*), 0), 2)                   AS har_qanday_foiz
  FROM k
 GROUP BY k.company_id;

COMMENT ON VIEW v_catalog_kod_qamrov IS
    'Kodlash qamrovi. ANIQ (8+) va KENG (5) kod ALOHIDA — ularni '
    'qo''shish keng chelakni aniq kodlangan qilib ko''rsatardi.';

-- ---------------------------------------------------------------------
-- 3) KO'RIB CHIQISH NAVBATI — biznes qiymati bo'yicha
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_catalog_kod_navbat;
CREATE VIEW v_catalog_kod_navbat AS
SELECT t.company_id,
       t.product_id,
       p.name                AS mahsulot,
       p.category_code,
       t.sabab,
       t.taklif_code,
       t.ishonch,
       t.dalil,
       t.jami,
       t.tokenlar,
       t.kodlar,
       t.misollar,
       t.ochiq_tender,
       t.tarixiy_lot,
       -- USTUVORLIK. Ochiq tender KUCHLIROQ signal: u bugungi
       -- imkoniyat. Tarixiy lot — barqarorlik belgisi.
       (t.ochiq_tender * 10 + t.tarixiy_lot) AS ustuvorlik,
       -- QAYSI ISH KERAK. Sabab har xil ishni talab qiladi va uni
       -- navbatda ko'rsatish odamning vaqtini tejaydi.
       CASE t.sabab
           WHEN 'kod'             THEN 'avtomatik kod tayyor — tasdiqlash'
           WHEN 'noaniq'          THEN 'bir nechta kod oilasi teng — odam tanlaydi'
           WHEN 'dalil_kam'       THEN 'dalil kam (korpus o''ssa hal bo''lishi mumkin)'
           WHEN 'sozlar_mos_emas' THEN 'nom korpusdagi atama bilan mos emas'
           WHEN 'nomzodsiz'       THEN 'korpusda umuman uchramaydi'
           WHEN 'tokensiz'        THEN 'nomdan ma''noli so''z chiqmadi (model/SKU)'
       END AS nima_kerak
  FROM catalog_kod_tahlil t
  JOIN catalog_product p ON p.id = t.product_id AND p.company_id = t.company_id
 WHERE NOT EXISTS (SELECT 1 FROM v_catalog_code_active v
                    WHERE v.product_id = t.product_id
                      AND v.company_id = t.company_id
                      AND length(v.code) >= 8);

COMMENT ON VIEW v_catalog_kod_navbat IS
    'Aniq kodi YO''Q mahsulotlar, biznes qiymati bo''yicha. '
    '`nima_kerak` — sabab har xil ishni talab qiladi.';

-- ---------------------------------------------------------------------
-- 4) SABAB TAQSIMOTI — o'lchov
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_catalog_kod_sabab;
CREATE VIEW v_catalog_kod_sabab AS
SELECT company_id, sabab,
       count(*)                                   AS soni,
       sum(ochiq_tender)                          AS ochiq_tender_jami,
       round(avg(ishonch), 3)                     AS ortacha_ishonch,
       round(100.0 * count(*) / sum(count(*)) OVER (PARTITION BY company_id), 1)
                                                  AS ulush_foiz
  FROM catalog_kod_tahlil
 GROUP BY company_id, sabab;

COMMENT ON VIEW v_catalog_kod_sabab IS
    'Kodsizlik sabablari taqsimoti. "Kod yo''q" yagona chelak emas — '
    'har sabab boshqa ishni talab qiladi.';

COMMIT;
