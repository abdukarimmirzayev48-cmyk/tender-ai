-- =====================================================================
-- VEKTORLASH QAMROVI — HOLAT, XESH BO'YICHA TAKRORSIZLANTIRISH,
--                      MODEL VERSIYASI
-- =====================================================================
--
-- O'LCHANGAN HOLAT (2026-08-30):
--
--     doc_chunk               157 266
--     vektorlangan             95 874   (hammasi multilingual-e5-small)
--     vektorsiz                61 392
--
-- ==================== IKKI SABAB, IKKALASI HAM O'LCHANGAN ====================
--
-- SABAB 1 — QUVVAT ZAXIRADAN ORQADA (asosiy):
--
--     sana        yaratilgan bo'lak   vektorlangan
--     2026-08-25      118 426             93 116     <- boshlang'ich to'ldirish
--     2026-08-27        2 226                  0
--     2026-08-28       36 560              2 758
--
--   Soatlik RAG vazifasi `--vector-budget 1000` bilan yuradi, ya'ni
--   soatiga eng ko'pi 1 000 bo'lak. 2026-08-28 da 36 560 yangi bo'lak
--   keldi va 2 758 tasi vektorlandi. Ustiga vazifaning o'zi muntazam
--   `0xC000013A` bilan o'ldirilardi (`schema_patch_etl_ishonch.sql`).
--
--   HECH NARSA YO'QOLMAGAN: bo'laklar joyida, matni bor, faqat NAVBAT
--   uzun. Lekin buni AYTADIGAN ko'rsatkich yo'q edi — `embedding IS
--   NULL` "navbatda" ni ham, "yiqildi" ni ham, "yaroqsiz" ni ham
--   bir xil ko'rsatardi.
--
-- SABAB 2 — TAKROR MATN QAYTA HISOBLANARDI:
--
--     vektorsiz jami                     61 392
--     xeshi ALLAQACHON vektorlangan      31 138   (51%)
--     vektorsizlar orasida takrorsiz     28 643
--
--   Ya'ni navbatning YARMI allaqachon hisoblangan matnning nusxasi.
--   `content_hash` ustuni 2026-08 dan beri bor edi va `NOT NULL`,
--   lekin vektorlash undan FOYDALANMASDI. Bir xil matn uchun modelni
--   qayta chaqirish — sof isrof.
--
-- ==================== BU PATCH NIMA QILADI ====================
--
-- 1. HOLAT ustuni. `embedding IS NULL` uch xil narsani anglatardi;
--    endi ular AJRATILGAN va har bo'lak AYNAN BITTA holatda.
--
-- 2. XESH BO'YICHA NUSXALASH. Bir xil matn bir marta hisoblanadi.
--
-- 3. MODEL VERSIYASI kuzatiladi (`embed_model` + `embed_dims` +
--    `embed_content_hash`). Model o'zgarsa qayta vektorlash
--    BOSHQARILADIGAN bo'ladi — avtomatik EMAS.
--
-- 4. `v_embedding_coverage` — qamrov 100% ga yig'iladi.
--
-- MAVJUD VEKTORLAR QAYTA HISOBLANMAYDI. Patch faqat metama'lumot
-- qo'shadi va mavjud 95 874 vektorga TEGMAYDI.
--
-- Idempotent.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. HOLAT VA MODEL METAMA'LUMOTI
-- ---------------------------------------------------------------------
ALTER TABLE doc_chunk
    ADD COLUMN IF NOT EXISTS embed_holat        TEXT,
    -- Vektor AYNAN QAYSI o'lchamda saqlangan. `embed_model` nomini
    -- beradi, lekin model ta'rifi keyin o'zgarsa (yoki nom bir xil
    -- qolib o'lcham o'zgarsa) buni faqat SHU ustun ushlaydi.
    ADD COLUMN IF NOT EXISTS embed_dims         INTEGER,
    ADD COLUMN IF NOT EXISTS embedded_at        TIMESTAMPTZ,
    -- Vektor QAYSI MATN uchun hisoblangan. `content_hash` joriy
    -- matnniki; ikkisi farq qilsa vektor ESKIRGAN.
    ADD COLUMN IF NOT EXISTS embed_content_hash TEXT,
    ADD COLUMN IF NOT EXISTS embed_xato         TEXT,
    ADD COLUMN IF NOT EXISTS embed_xato_at      TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS embed_urinish      INTEGER NOT NULL DEFAULT 0,
    -- Vektor QAYERDAN keldi: model chaqiruvi yoki bir xil xeshdan
    -- NUSXA. Tezlik o'lchovi uchun ikkisi ajratilishi SHART, aks
    -- holda "bo'lak/soniya" nusxalar bilan shishib ketardi.
    ADD COLUMN IF NOT EXISTS embed_manba        TEXT;

COMMENT ON COLUMN doc_chunk.embed_holat IS
    'Vektorlash holati. `embedding IS NULL` uch xil narsani anglatardi '
    '(navbatda / yiqildi / yaroqsiz) — endi ular ajratilgan.';
COMMENT ON COLUMN doc_chunk.embed_content_hash IS
    'Vektor QAYSI matn uchun hisoblangan. `content_hash` bilan farq '
    'qilsa vektor ESKIRGAN va qayta hisoblanishi kerak.';
COMMENT ON COLUMN doc_chunk.embed_manba IS
    'model — model chaqirilgan; xesh — bir xil matnli bo''lakdan '
    'NUSXA olingan. Tezlik o''lchovi faqat `model` bo''yicha '
    'hisoblanadi, aks holda nusxalar uni shishirardi.';

-- ---------------------------------------------------------------------
-- 2. HOLAT LUG'ATI
-- ---------------------------------------------------------------------
--   navbatda        vektorlanishi kerak, hali navbat kelmagan
--   ok              vektorlangan
--   eskirgan        matn o'zgargan yoki model boshqa — qayta kerak
--   yiqildi         model xato berdi, QAYTA URINILADI
--   butunlay_yiqildi urinishlar tugadi
--   yaroqsiz        matn bo'sh/juda qisqa — vektorlash MA'NOSIZ
--   otkazildi       ATAYLAB o'tkazib yuborilgan
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'doc_chunk_embed_holat_chk') THEN
        ALTER TABLE doc_chunk ADD CONSTRAINT doc_chunk_embed_holat_chk
            CHECK (embed_holat IN ('navbatda', 'ok', 'eskirgan', 'yiqildi',
                                   'butunlay_yiqildi', 'yaroqsiz', 'otkazildi'));
    END IF;

    -- `ok` VEKTORNI TALAB QILADI. Aks holda "vektorlandi" degan
    -- yolg'on holat paydo bo'lardi — aynan shu loyihada takrorlangan
    -- "yorliq bor, dalil yo'q" sinfi.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'doc_chunk_ok_vektor_chk') THEN
        ALTER TABLE doc_chunk ADD CONSTRAINT doc_chunk_ok_vektor_chk
            CHECK (embed_holat <> 'ok' OR (embedding IS NOT NULL
                                           AND embed_model IS NOT NULL
                                           AND embedded_at IS NOT NULL
                                           AND embed_content_hash IS NOT NULL));
    END IF;

    -- Vektor bor bo'lsa holat `ok` yoki `eskirgan` bo'lishi shart.
    -- "Vektor bor, lekin navbatda" — o'qib bo'lmaydigan holat.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'doc_chunk_vektor_holat_chk') THEN
        -- `embed_holat IS NULL` ham QABUL qilinadi: u "aniq
        -- belgilanmagan" degani va holat DALILDAN chiqariladi
        -- (`embed_holat_aniqla`). Mass backfill qilinmagani uchun
        -- mavjud 95 874 qator aynan shu holatda.
        ALTER TABLE doc_chunk ADD CONSTRAINT doc_chunk_vektor_holat_chk
            CHECK (embedding IS NULL OR embed_holat IS NULL
                   OR embed_holat IN ('ok', 'eskirgan'));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'doc_chunk_xato_chk') THEN
        ALTER TABLE doc_chunk ADD CONSTRAINT doc_chunk_xato_chk
            CHECK (embed_xato_at IS NULL OR embed_xato IS NOT NULL);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'doc_chunk_urinish_chk') THEN
        ALTER TABLE doc_chunk ADD CONSTRAINT doc_chunk_urinish_chk
            CHECK (embed_urinish >= 0);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'doc_chunk_manba_chk') THEN
        ALTER TABLE doc_chunk ADD CONSTRAINT doc_chunk_manba_chk
            CHECK (embed_manba IS NULL OR embed_manba IN ('model', 'xesh'));
    END IF;
END $$;

-- ---------------------------------------------------------------------
-- 3. MAVJUD QATORLARNI TO'LDIRISH — MASS UPDATE QILINMAYDI
-- ---------------------------------------------------------------------
-- O'LCHANGAN TO'SIQ: `doc_chunk` da HNSW vektor indeksi bor
-- (`doc_chunk_vec_idx`). PostgreSQL MVCC da UPDATE yangi qator
-- versiyasini yaratadi va u HAMMA indeksga, shu jumladan 384
-- o'lchamli HNSW ga, qayta yoziladi. 95 874 qatorli UPDATE 7
-- daqiqadan oshib ketdi va tugamadi (o'lchangan 2026-08-30).
--
-- SHUNING UCHUN HOLAT DERIVATSIYA QILINADI, YOZILMAYDI.
-- `embed_holat` NULL = "aniq belgilanmagan" va u DALILDAN chiqadi:
--     vektor bor      -> ok
--     matn juda qisqa -> yaroqsiz
--     qolgani         -> navbatda
--
-- ETL yangi ishda ustunni ANIQ to'ldiradi (yiqilish, yaroqsizlik,
-- ataylab o'tkazish). Ya'ni: mavjud 157k qator uchun bepul
-- derivatsiya, yangi ish uchun aniq yozuv. Ikkalasi ham bitta
-- ko'rinishdan o'qiladi va farqi KO'RINADI (`aniq_belgilangan`).
--
-- Xohlansa keyin `etl_embed.py --holat-toldir` bilan bo'lak-bo'lak
-- to'ldirsa bo'ladi — lekin bu QAMROV uchun SHART EMAS.

--: Holatni DALILDAN chiqaradigan yagona manba. Ko'rinishlar ham,
--: ETL ham shu funksiyani ishlatadi — ikki joyda ikki qoida bo'lsa
--: biri jimgina eskirardi.
CREATE OR REPLACE FUNCTION embed_holat_aniqla(
    p_holat TEXT, p_embedding_bor BOOLEAN, p_text TEXT)
RETURNS TEXT LANGUAGE sql IMMUTABLE AS $fn$
    SELECT COALESCE(
        p_holat,
        CASE
            WHEN p_embedding_bor                          THEN 'ok'
            WHEN p_text IS NULL
                 OR length(btrim(p_text)) < 80            THEN 'yaroqsiz'
            ELSE 'navbatda'
        END)
$fn$;

COMMENT ON FUNCTION embed_holat_aniqla(TEXT, BOOLEAN, TEXT) IS
    'Bo`lakning AMALDAGI vektorlash holati. `embed_holat` aniq '
    'belgilangan bo`lsa o`sha, aks holda DALILDAN chiqariladi. '
    'Mass UPDATE qilinmaydi: HNSW indeksi tufayli 95 874 qatorli '
    'UPDATE 7 daqiqada ham tugamadi (o`lchangan).';

-- ---------------------------------------------------------------------
-- 4. INDEKSLAR
-- ---------------------------------------------------------------------
-- Eski qisman indeks `embedding IS NULL` bo'yicha edi; endi navbat
-- HOLAT bo'yicha tanlanadi.
CREATE INDEX IF NOT EXISTS doc_chunk_navbat_idx
    ON doc_chunk (id)
    WHERE embed_holat IN ('navbatda', 'eskirgan', 'yiqildi');

-- XESH BO'YICHA NUSXALASH uchun. Bu indekssiz nusxalash so'rovi
-- 157k qatorli jadvalda ketma-ket skanerlaydi.
CREATE INDEX IF NOT EXISTS doc_chunk_hash_idx
    ON doc_chunk (content_hash);

-- Vektorlangan xeshlarni tez topish uchun (nusxa manbai).
CREATE INDEX IF NOT EXISTS doc_chunk_hash_ok_idx
    ON doc_chunk (content_hash, embed_model)
    WHERE embed_holat = 'ok';

-- ---------------------------------------------------------------------
-- 5. QAMROV KO'RINISHLARI
-- ---------------------------------------------------------------------
-- Har bo'lakning AMALDAGI holati. `embed_holat` aniq belgilangan
-- bo'lsa o'sha, aks holda DALILDAN chiqariladi.
CREATE OR REPLACE VIEW v_embedding_state AS
SELECT
    c.id, c.tender_id, c.file_ref, c.chunk_no, c.content_hash,
    embed_holat_aniqla(c.embed_holat, c.embedding IS NOT NULL, c.text) AS holat,
    (c.embed_holat IS NOT NULL)          AS aniq_belgilangan,
    c.embed_model, c.embed_dims, c.embedded_at, c.embed_content_hash,
    c.embed_manba, c.embed_urinish, c.embed_xato, c.embed_xato_at,
    length(c.text)                       AS matn_uzunlik,
    c.created_at
FROM doc_chunk c;

COMMENT ON VIEW v_embedding_state IS
    'Har bo`lakning AMALDAGI vektorlash holati. `aniq_belgilangan` '
    'false = holat DALILDAN chiqarilgan (mass backfill qilinmagan: '
    'HNSW indeksi tufayli 95 874 qatorli UPDATE 7 daqiqada tugamadi).';

CREATE OR REPLACE VIEW v_embedding_coverage AS
SELECT
    (SELECT name FROM embed_model WHERE is_active LIMIT 1)  AS faol_model,
    (SELECT dims FROM embed_model WHERE is_active LIMIT 1)  AS faol_olcham,
    count(*)                                                AS jami,

    -- --- YAKUNIY ---
    count(*) FILTER (WHERE holat = 'ok')                    AS vektorlangan,
    count(*) FILTER (WHERE holat = 'yaroqsiz')              AS yaroqsiz,
    count(*) FILTER (WHERE holat = 'otkazildi')             AS otkazildi,
    count(*) FILTER (WHERE holat = 'butunlay_yiqildi')      AS butunlay_yiqildi,

    -- --- NAVBATDA ---
    count(*) FILTER (WHERE holat = 'navbatda')              AS navbatda,
    count(*) FILTER (WHERE holat = 'eskirgan')              AS eskirgan,
    count(*) FILTER (WHERE holat = 'yiqildi')               AS yiqildi,

    -- --- NAZORAT: yig'indi jamiga tengmi ---
    count(*) - (
        count(*) FILTER (WHERE holat = 'ok')
      + count(*) FILTER (WHERE holat = 'yaroqsiz')
      + count(*) FILTER (WHERE holat = 'otkazildi')
      + count(*) FILTER (WHERE holat = 'butunlay_yiqildi')
      + count(*) FILTER (WHERE holat = 'navbatda')
      + count(*) FILTER (WHERE holat = 'eskirgan')
      + count(*) FILTER (WHERE holat = 'yiqildi')
    )                                                       AS hisobga_olinmagan,

    -- --- MODEL MOSLIGI ---
    -- Faol modeldan BOSHQA model bilan hisoblangan vektorlar.
    -- AVTOMATIK qayta hisoblanmaydi — bu BOSHQARILADIGAN qaror
    -- (`etl_embed.py --model-ozgardi`).
    count(*) FILTER (WHERE embed_model IS NOT NULL
                       AND embed_model <> (SELECT name FROM embed_model
                                            WHERE is_active LIMIT 1))
                                                            AS model_mos_emas,
    count(*) FILTER (WHERE embed_content_hash IS NOT NULL
                       AND embed_content_hash <> content_hash)
                                                            AS matn_ozgargan,
    count(*) FILTER (WHERE aniq_belgilangan)                AS aniq_belgilangan,

    -- --- QAMROV ---
    -- MAXRAJ = YAROQLI bo'laklar. `yaroqsiz` va `otkazildi` maxrajga
    -- KIRMAYDI: ularni vektorlash ma'nosiz va foizni pasaytirish
    -- "ishlamayapti" degan yolg'on beradi.
    count(*) FILTER (WHERE holat NOT IN ('yaroqsiz', 'otkazildi'))
                                                            AS yaroqli,
    round(100.0 * count(*) FILTER (WHERE holat = 'ok')
          / NULLIF(count(*) FILTER (WHERE holat
                                    NOT IN ('yaroqsiz', 'otkazildi')), 0), 2)
                                                            AS qamrov_foiz,

    -- --- MANBA KESIMI (tezlik o'lchovi uchun) ---
    count(*) FILTER (WHERE embed_manba = 'model')           AS modeldan,
    count(*) FILTER (WHERE embed_manba = 'xesh')            AS xeshdan
FROM v_embedding_state;

COMMENT ON VIEW v_embedding_coverage IS
    'Vektorlash qamrovi. `hisobga_olinmagan` HAR DOIM 0 bo`lishi '
    'shart. `qamrov_foiz` maxraji YAROQLI bo`laklar — `yaroqsiz` va '
    '`otkazildi` kirmaydi, aks holda foiz "ishlamayapti" degan '
    'yolg`on berardi.';

-- NUSXA IMKONIYATI — ALOHIDA ko'rinish.
--
-- NEGA ALOHIDA: bu so'rov 157k qator ustida korrelyatsiyalangan
-- EXISTS qiladi va sekin. Uni asosiy qamrov ko'rinishiga qo'shish
-- har chaqiruvni sekinlashtirardi, holbuki bu raqam FAQAT
-- rejalashtirish uchun kerak.
CREATE OR REPLACE VIEW v_embedding_dedup AS
SELECT
    count(*)                                    AS navbat,
    count(DISTINCT a.content_hash)              AS takrorsiz_navbat,
    count(*) FILTER (WHERE EXISTS (
        SELECT 1 FROM doc_chunk b
         WHERE b.content_hash = a.content_hash
           AND b.embedding IS NOT NULL))        AS xeshdan_nusxalanadi
FROM doc_chunk a
WHERE a.embedding IS NULL
  AND embed_holat_aniqla(a.embed_holat, false, a.text) IN
      ('navbatda', 'eskirgan', 'yiqildi');

COMMENT ON VIEW v_embedding_dedup IS
    'Navbatning qancha qismi ALLAQACHON hisoblangan matnning '
    'nusxasi. O`lchangan 2026-08-30: 61 392 dan 31 138 tasi (51%) — '
    'ular uchun modelni qayta chaqirish sof isrof.';

-- Sabab kesimi — nega vektorlanmagan.
CREATE OR REPLACE VIEW v_embedding_pending_reason AS
SELECT
    holat,
    CASE
        WHEN holat = 'yaroqsiz'         THEN 'matn juda qisqa (< 80 belgi)'
        WHEN holat IN ('yiqildi', 'butunlay_yiqildi')
                                        THEN COALESCE(left(embed_xato, 60), 'xato')
        WHEN holat = 'eskirgan'         THEN 'matn yoki model ozgargan'
        WHEN holat = 'otkazildi'        THEN 'ataylab otkazib yuborilgan'
        ELSE 'navbatda — quvvat zaxiradan orqada'
    END                                          AS sabab,
    count(*)                                     AS soni,
    min(created_at)                              AS eng_eski,
    max(created_at)                              AS eng_yangi
FROM v_embedding_state
WHERE holat <> 'ok'
GROUP BY 1, 2
ORDER BY 3 DESC;

COMMENT ON VIEW v_embedding_pending_reason IS
    'Har vektorlanmagan bo`lak NEGA vektorlanmagani. Nusxalash '
    'imkoniyati alohida ko`rinishda (`v_embedding_dedup`) — u sekin.';

-- ---------------------------------------------------------------------
-- 6. MUSBAT TASDIQ
-- ---------------------------------------------------------------------
DO $$
DECLARE
    v RECORD;
BEGIN
    SELECT * INTO v FROM v_embedding_coverage;
    IF v.hisobga_olinmagan <> 0 THEN
        RAISE EXCEPTION 'Qamrov yig''ilmadi: % ta hisobga olinmagan',
                        v.hisobga_olinmagan;
    END IF;
    -- `embed_holat IS NULL` NORMAL holat: u "aniq belgilanmagan"
    -- degani va holat DALILDAN chiqariladi. Tekshirilishi kerak
    -- bo'lgan narsa — DERIVATSIYA hech qachon NULL qaytarmasligi.
    IF EXISTS (SELECT 1 FROM v_embedding_state WHERE holat IS NULL) THEN
        RAISE EXCEPTION 'Derivatsiya NULL qaytardi — holatsiz bo''lak bor';
    END IF;
    IF EXISTS (SELECT 1 FROM v_embedding_state WHERE holat NOT IN
               ('navbatda','ok','eskirgan','yiqildi','butunlay_yiqildi',
                'yaroqsiz','otkazildi')) THEN
        RAISE EXCEPTION 'Lug''atdan tashqari holat topildi';
    END IF;
    RAISE NOTICE 'TASDIQ: jami=%, vektorlangan=%, navbatda=%, qamrov=%%%',
                 v.jami, v.vektorlangan, v.navbatda, v.qamrov_foiz;
END $$;

COMMIT;
