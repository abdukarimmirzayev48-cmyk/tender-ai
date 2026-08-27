-- =====================================================================
-- KOD-ASOSLI MOSLASHTIRISH — rasmiy tasniflagich (good_code) bo'yicha
-- =====================================================================
--
-- NEGA (o'lchangan, taxmin emas):
--
--   Matn bo'yicha moslashtirish TILGA BOG'LIQ va shu sababli yiqiladi.
--   Korpus rus va o'zbek-kirillda, foydalanuvchi o'zbek-lotinda yozadi.
--   O'lchandi (tasniflagich lug'ati ustidan semantik qidiruv):
--
--       "dori"                              -> Сосуд Дьюара, Чай зеленый   XATO
--       "дори" (transliteratsiya)           -> Урна                        XATO
--       "лекарственные средства препараты"  -> 21.40, 86.23                TO'G'RI
--
--   Ya'ni kerak bo'lgani boshqa ALIFBO emas, boshqa LUG'AT. Transliteratsiya
--   (api/translit.py) bu bo'shliqni yopmaydi.
--
--   Ayni paytda `tender_good.good_code` QAMROVI 100%:
--       ochiq pozitsiyalar: 1880 ta, good_code bor: 1880 ta
--       kodli ochiq tender: 782 / 782
--
--   Kod TILGA BOG'LIQ EMAS. Natija (ochiq tenderlar):
--       substring "dori"          ->  6 tender
--       gibrid semantik           ->  6 tender
--       good_code LIKE '21%'      -> 63 tender, 124 pozitsiya
--
-- ARXITEKTURA:
--   Katalog mahsuloti --(BIR MARTA: taklif + INSON tasdig'i)--> kod prefikslari
--   Tender pozitsiyasi --(good_code)--------------------------> ANIQ moslik
--
--   Semantika har qidiruvda emas, mahsulot qo'shilganda BIR MARTA ishlaydi.
--
-- MUHIM CHEKLOV — BU O'LCHOVNI OZ ORACLE BILAN TEKSHIRIB BO'LMAYDI.
--   `etl_categorize.py` kategoriyani AYNAN good_code dan chiqaradi
--   (good_code -> NACE bo'limi -> kategoriya). Ya'ni kod-asosli moslikni
--   kategoriya bo'yicha o'lchash 100% beradi va HECH NARSANI isbotlamaydi
--   (asbob o'zini o'lchaydi). Yagona haqiqiy tekshiruv — INSON tasdig'i.
--   Shuning uchun `tasdiqlandi` ustuni bor va u NULL bo'lsa mahsulot
--   moslashtirishda ISHLATILMAYDI.
--
-- Qo'llash:
--   psql "$XT_DB_DSN" -f schema_patch_goodcode.sql
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 0) Ko'p-ijarachilik uchun kompozit kalit
--
-- NEGA: `catalog_product_code` ikkala ustunni ham (product_id, company_id)
-- saqlaydi va ular BIR-BIRIGA MOS bo'lishi SHART. Buni izoh emas, FK
-- ta'minlaydi — aks holda A kompaniyaning mahsulotiga B kompaniya nomidan
-- kod bog'lash mumkin bo'lardi.
-- ---------------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS catalog_product_id_company_uq
    ON catalog_product (id, company_id);

-- ---------------------------------------------------------------------
-- 1) Tasniflagich lug'ati — KORPUSDAN quriladi
--
-- Daraja: kod prefiksining uzunligi.
--     2  -> '21'          NACE bo'limi          (91 ta)
--     5  -> '21.31'       guruh                 (324 ta)
--     8  -> '21.31.10'    sinf                  (823 ta)
-- Moslashtirish 5 yoki 8 darajada bo'ladi; 2 juda keng.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_good_code (
    code          TEXT PRIMARY KEY,
    level         INT  NOT NULL,
    parent        TEXT REFERENCES dim_good_code(code),
    name_ru       TEXT,                       -- korpusdagi eng ko'p uchragan nom
    names         TEXT[] NOT NULL DEFAULT '{}',  -- variantlar (taklif matni)
    n_position    INT  NOT NULL DEFAULT 0,    -- korpusda nechta pozitsiya
    n_tender_open INT  NOT NULL DEFAULT 0,    -- hozir nechta OCHIQ tender
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT dim_good_code_level_ok CHECK (level IN (2, 5, 8)),
    CONSTRAINT dim_good_code_len_ok   CHECK (length(code) = level)
);

COMMENT ON TABLE dim_good_code IS
    'Rasmiy tovar tasniflagichi, korpusdan (tender_good.good_code) quriladi. '
    'Tilga bog''liq EMAS — moslashtirishning tayanchi.';

CREATE INDEX IF NOT EXISTS dim_good_code_level_idx  ON dim_good_code (level);
CREATE INDEX IF NOT EXISTS dim_good_code_parent_idx ON dim_good_code (parent);

-- Lug'at vektorlari ALOHIDA jadvalda — `tender_embedding` bilan bir naqsh.
-- Sabab: model o'zgarsa (384 -> 768) lug'atning O'ZI o'zgarmaydi.
CREATE TABLE IF NOT EXISTS good_code_embedding (
    code         TEXT PRIMARY KEY REFERENCES dim_good_code(code) ON DELETE CASCADE,
    embedding    VECTOR(384),
    embedding_c  VECTOR(384),
    centroid_id  BIGINT REFERENCES embed_centroid(id),
    embed_model  TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT good_code_embedding_c_needs_centroid
        CHECK (embedding_c IS NULL OR centroid_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS good_code_embedding_vec_idx
    ON good_code_embedding USING hnsw (embedding_c vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ---------------------------------------------------------------------
-- 2) Katalog mahsuloti -> kod bog'lanishi
--
-- `tasdiqlandi` NULL = TAKLIF, tasdiqlanmagan. Moslashtirish uni
-- KO'RMAYDI (pastdagi `v_catalog_code_active`).
--
-- NEGA SHUNCHALIK QAT'IY: bu loyihada allaqachon 1514 ta talab
-- `review_status='approved'` bo'lib turibdi va ularni HECH KIM
-- ko'rmagan — kodning o'zi tasdiqlagan. O'sha xato bu yerda
-- TAKRORLANMASLIGI uchun tasdiq ODAMSIZ yozila olmaydi (CHECK).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS catalog_product_code (
    product_id  BIGINT NOT NULL,
    company_id  INT    NOT NULL,
    code        TEXT   NOT NULL REFERENCES dim_good_code(code),
    manba       TEXT   NOT NULL DEFAULT 'taklif',   -- 'taklif' | 'qol'
    skor        NUMERIC(4,3),                       -- taklif kuchi (faqat ma'lumot)
    tasdiqlagan TEXT,                               -- KIM (company_account.username)
    tasdiqlandi TIMESTAMPTZ,                        -- QACHON; NULL = tasdiqlanmagan
    rad_etildi  TIMESTAMPTZ,                        -- inson RAD etgan taklif
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (product_id, code),

    -- Ko'p-ijarachilik: mahsulot va bog'lanish BIR kompaniyaniki.
    FOREIGN KEY (product_id, company_id)
        REFERENCES catalog_product (id, company_id) ON DELETE CASCADE,

    CONSTRAINT catalog_product_code_manba_ok
        CHECK (manba IN ('taklif', 'qol')),

    -- TASDIQ ODAMSIZ YOZILMAYDI.
    CONSTRAINT catalog_product_code_tasdiq_odam
        CHECK (tasdiqlandi IS NULL OR tasdiqlagan IS NOT NULL),

    -- Bir vaqtda ham tasdiqlangan, ham rad etilgan bo'la olmaydi.
    CONSTRAINT catalog_product_code_bir_qaror
        CHECK (NOT (tasdiqlandi IS NOT NULL AND rad_etildi IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS catalog_product_code_company_idx
    ON catalog_product_code (company_id);
CREATE INDEX IF NOT EXISTS catalog_product_code_code_idx
    ON catalog_product_code (code);
-- Tasdiqlanganlar bo'yicha moslashtirish tez bo'lsin.
CREATE INDEX IF NOT EXISTS catalog_product_code_faol_idx
    ON catalog_product_code (company_id, code) WHERE tasdiqlandi IS NOT NULL;

-- ---------------------------------------------------------------------
-- 3) YAGONA MANBA: moslashtirish FAQAT shu ko'rinishni o'qiydi
--
-- Nega ko'rinish: "tasdiqlanmaganini ishlatmang" qoidasi har SQL da
-- qayta yozilsa, kimdir uni bir joyda unutadi va JIMGINA tasdiqlanmagan
-- taklif bo'yicha moslik chiqa boshlaydi. Ko'rinish buni struktura
-- darajasida yopadi.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_catalog_code_active AS
SELECT pc.company_id, pc.product_id, pc.code, pc.tasdiqlagan, pc.tasdiqlandi,
       p.name AS product_name, d.name_ru AS code_name, d.level
FROM catalog_product_code pc
JOIN catalog_product p ON p.id = pc.product_id
JOIN dim_good_code   d ON d.code = pc.code
WHERE pc.tasdiqlandi IS NOT NULL;

COMMENT ON VIEW v_catalog_code_active IS
    'TASDIQLANGAN mahsulot<->kod bog''lanishlari. Moslashtirish FAQAT shuni '
    'o''qiydi — tasdiqlanmagan taklif hech qachon moslikka aylanmaydi.';

-- ---------------------------------------------------------------------
-- 4) Lug'atni korpusdan qayta qurish
--
-- Idempotent. `n_tender_open` har chaqiruvда qayta hisoblanadi, chunki
-- tenderlar yopiladi.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION rebuild_good_code_dict() RETURNS TABLE(daraja INT, soni BIGINT)
LANGUAGE plpgsql AS $$
BEGIN
    -- Har daraja uchun prefikslarni yig'amiz.
    INSERT INTO dim_good_code (code, level, parent, name_ru, names, n_position, n_tender_open)
    SELECT x.code, x.level,
           CASE x.level WHEN 5 THEN substring(x.code from 1 for 2)
                        WHEN 8 THEN substring(x.code from 1 for 5)
                        ELSE NULL END,
           x.names[1], x.names, x.n_pos, x.n_open
    FROM (
        -- NOMLAR CHASTOTA BO'YICHA tartiblanadi, alifbo bo'yicha EMAS.
        -- Sabab: `names[1]` inson tasdiqlaydigan ekranda kodning YORLIG'I
        -- bo'lib ko'rinadi. Alifbo tartibida 21.20 uchun "Aciclovir"
        -- chiqardi — bu butun farmatsevtika guruhini bitta dori nomi
        -- bilan atash demak. Chastota bo'yicha esa guruhning haqiqiy
        -- vakili chiqadi.
        SELECT s.code, s.level,
               (array_agg(s.name ORDER BY s.n DESC, s.name))[1:8] AS names,
               sum(s.n)::INT                                      AS n_pos,
               COALESCE(o.n_open, 0)                              AS n_open
        FROM (
            SELECT substring(g.good_code from 1 for lv.level) AS code,
                   lv.level,
                   g.name,
                   count(*)::INT AS n
            FROM tender_good g
            CROSS JOIN (VALUES (2), (5), (8)) AS lv(level)
            WHERE g.good_code IS NOT NULL
              AND length(g.good_code) >= lv.level
              AND g.name IS NOT NULL
            GROUP BY 1, 2, 3
        ) s
        -- OCHIQ tender soni ALOHIDA hisoblanadi. Korrelatsiyalangan ostki
        -- so'rov bu yerda ishlamaydi: `g.good_code` GROUP BY da yo'q
        -- (faqat uning prefiksi bor).
        LEFT JOIN (
            SELECT substring(g2.good_code from 1 for lv2.level) AS code,
                   lv2.level,
                   count(DISTINCT t2.id)::INT AS n_open
            FROM tender_good g2
            JOIN tender t2 ON t2.id = g2.tender_id
            CROSS JOIN (VALUES (2), (5), (8)) AS lv2(level)
            WHERE t2.status = 'open'
              AND g2.good_code IS NOT NULL
              AND length(g2.good_code) >= lv2.level
            GROUP BY 1, 2
        ) o ON o.code = s.code AND o.level = s.level
        GROUP BY s.code, s.level, o.n_open
    ) x
    -- Parent AVVAL kelishi shart (FK): darajaga qarab tartiblaymiz.
    ORDER BY x.level
    ON CONFLICT (code) DO UPDATE SET
        name_ru       = EXCLUDED.name_ru,
        names         = EXCLUDED.names,
        n_position    = EXCLUDED.n_position,
        n_tender_open = EXCLUDED.n_tender_open,
        parent        = EXCLUDED.parent,
        updated_at    = now();

    RETURN QUERY SELECT d.level, count(*) FROM dim_good_code d GROUP BY d.level ORDER BY d.level;
END;
$$;

-- ---------------------------------------------------------------------
-- 5) Kuzatuv ko'rinishlari
-- ---------------------------------------------------------------------

-- Tasdiq kutayotgan takliflar — INSON NAVBATI.
CREATE OR REPLACE VIEW v_code_review AS
SELECT pc.company_id, pc.product_id, p.name AS product_name,
       pc.code, d.name_ru AS code_name, d.n_tender_open, pc.skor, pc.created_at
FROM catalog_product_code pc
JOIN catalog_product p ON p.id = pc.product_id
JOIN dim_good_code   d ON d.code = pc.code
WHERE pc.tasdiqlandi IS NULL AND pc.rad_etildi IS NULL
ORDER BY pc.company_id, p.name, pc.skor DESC NULLS LAST;

-- Kodsiz mahsulotlar — bular moslashtirishda KO'RINMAYDI.
-- Bu 2-sinfga qarshi: "moslik topilmadi" != "hammasi joyida".
CREATE OR REPLACE VIEW v_catalog_kodsiz AS
SELECT p.company_id, p.id AS product_id, p.name,
       (SELECT count(*) FROM catalog_product_code pc
         WHERE pc.product_id = p.id AND pc.tasdiqlandi IS NULL
           AND pc.rad_etildi IS NULL) AS kutayotgan_taklif
FROM catalog_product p
WHERE NOT EXISTS (SELECT 1 FROM catalog_product_code pc
                   WHERE pc.product_id = p.id AND pc.tasdiqlandi IS NOT NULL);

COMMENT ON VIEW v_catalog_kodsiz IS
    'Tasdiqlangan kodi YO''Q mahsulotlar. Ular moslashtirishda qatnashmaydi — '
    'interfeys buni ANIQ ko''rsatishi shart, jimgina 0 natija emas.';

COMMIT;

-- Lug'atni darhol quramiz.
SELECT * FROM rebuild_good_code_dict();
