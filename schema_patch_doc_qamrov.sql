-- =====================================================================
-- HUJJAT QAYTA ISHLASH QAMROVI — JIM BO'SHLIQNI YO'Q QILISH
-- =====================================================================
--
-- O'LCHANGAN MUAMMO (2026-08-30):
--
--     tender_document                     10 633
--     tender_document_text                 3 422
--     ------------------------------------------
--     hisobga olingan holatlar:
--         ok           2 886
--         unreadable     266
--         unsupported    252
--         too_large       18
--                      -------
--                        3 422   <-- metadata ning ATIGI 32%
--
-- Ya'ni 7 211 hujjat HECH QANDAY holatda ko'rinmasdi.
--
-- ==================== BO'SHLIQNING ANIQ SABABI ====================
--
-- SABAB BITTA VA U ARXITEKTURAVIY: **holat FAQAT quyi oqim jadvalida
-- yashardi**. `tender_document_text` ga qator ajratish URINISHIDAN
-- KEYIN qo'yiladi. Demak "hali urinilmagan" holatining BAZADA
-- KO'RINISHI YO'Q edi — u NULL ham emas, qator ham emas, shunchaki
-- YO'Q.
--
-- Bo'shliq ikki tomonlama chiqdi:
--
--   A) METADATA BOR, HOLAT YO'Q — 7 603 qator (o'lchangan):
--        6 998  tender YOPIQ/muddati o'tgan -> ATAYLAB rejalashtirilmagan
--                (`etl_doc_text.py --only-open`, standart YOQILGAN;
--                 o'lchangan foyda: 9.81 GB -> 2.49 GB)
--          605  tender OCHIQ -> navbatda, hali navbat kelmagan
--
--      Bularning HECH BIRI nosozlik emas. Lekin ular hech qayerda
--      SANALMASDI va shuning uchun "3 422 / 10 633" degan raqam
--      "68% yo'qoldi" bo'lib o'qilardi.
--
--   B) HOLAT BOR, METADATA YO'Q — 392 qator (o'lchangan), hammasi
--      uzex, 391 tasi `ok`:
--
--        `etl_uzex.save()` va `etl_details.save()` hujjatlarni
--        DELETE + INSERT bilan qayta yozadi. Manba faylni ro'yxatdan
--        chiqarsa yoki `file_ref` o'zgarsa metadata qatori
--        YO'QOLADI, `tender_document_text` esa (FK yo'q) QOLADI.
--        Natijada MUVAFFAQIYATLI AJRATILGAN 391 ta matn hech qanday
--        JOIN da ko'rinmaydi.
--
--      Bu HAQIQIY nosozlik va u ikki narsani buzardi: qamrov hisobi
--      va hujjat ro'yxati.
--
-- ==================== BU PATCH NIMA QILADI ====================
--
-- 1. HOLAT METADATA QATORIGA KO'CHADI. Har `tender_document` qatori
--    O'ZIDA holatga ega bo'ladi va u HAR DOIM to'ldirilgan.
--
-- 2. HOLAT DALILDAN chiqariladi, TAXMINDAN emas. Yo'qolgan hujjat
--    AVTOMATIK "yiqildi" deb belgilanmaydi: tender yopiq bo'lsa
--    "rejalashtirilmagan", ochiq bo'lsa "navbatda".
--
-- 3. VAQT BELGILARI va QAYTA URINISH metama'lumoti qo'shiladi.
--
-- 4. `v_document_processing_coverage` — qamrov 100% ga YIG'ILADI va
--    buni ko'rinishning O'ZI tekshiradi.
--
-- MAVJUD AJRATISH XATTI-HARAKATI O'ZGARMAYDI: `etl_doc_text.py`
-- qamrovi, chegaralari va status lug'ati o'sha-o'sha.
--
-- Idempotent.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. HOLAT VA VAQT BELGILARI — metadata qatorida
-- ---------------------------------------------------------------------
ALTER TABLE tender_document
    ADD COLUMN IF NOT EXISTS holat                  TEXT,
    -- `fetched_at` DAN FARQI: u har UPSERT da yangilanadi, bu esa
    -- BIRINCHI ko'rilgan payt (tender.first_seen_at bilan bir xil
    -- mantiq). Aniqlash kechikishini shundan o'lchaymiz.
    ADD COLUMN IF NOT EXISTS discovered_at          TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS download_started_at    TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS downloaded_at          TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS extraction_started_at  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS extraction_finished_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_error_at          TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_error             TEXT,
    -- QAYTA URINISH. `download_failed` o'tkinchi bo'lishi mumkin
    -- (tarmoq), lekin `fetch_targets` allaqachon qator bor deb uni
    -- BOSHQA HECH QACHON olmasdi. Endi urinish sanaladi va
    -- chegaradan oshgach `butunlay_yiqildi` bo'ladi.
    ADD COLUMN IF NOT EXISTS urinish                INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS keyingi_urinish_at     TIMESTAMPTZ,
    -- Manba faylni ro'yxatdan chiqargan payt. Qator O'CHIRILMAYDI —
    -- o'chirilsa matn yetim qolardi (392 qator shundan kelib chiqqan).
    ADD COLUMN IF NOT EXISTS manbadan_yoqoldi_at    TIMESTAMPTZ;

COMMENT ON COLUMN tender_document.holat IS
    'Qayta ishlash holati. HAR DOIM to''ldirilgan — "holat yo''q" '
    'degan holat BO''LMAYDI. Aynan uning yo''qligi 7 603 hujjatni '
    'ko''rinmas qilgan edi.';
COMMENT ON COLUMN tender_document.discovered_at IS
    'BIRINCHI marta ko''rilgan payt. `fetched_at` har UPSERT da '
    'yangilanadi, bu esa o''zgarmaydi.';
COMMENT ON COLUMN tender_document.urinish IS
    'Yuklab olish/ajratish urinishlari soni. Chegaradan oshgach holat '
    '`butunlay_yiqildi` bo''ladi va navbatdan chiqadi.';
COMMENT ON COLUMN tender_document.manbadan_yoqoldi_at IS
    'Manba faylni ro''yxatdan chiqargan payt. Qator O''CHIRILMAYDI: '
    'o''chirilsa `tender_document_text` dagi matn YETIM qolardi '
    '(o''lchangan: 392 qator, 391 tasi muvaffaqiyatli ajratilgan).';

-- ---------------------------------------------------------------------
-- 2. HOLAT LUG'ATI
-- ---------------------------------------------------------------------
-- O'ZARO ISTISNO va TO'LIQ: har hujjat AYNAN BITTA holatda.
--
--   rejalashtirilmagan  qamrovdan tashqarida (tender yopiq/muddati o'tgan)
--   navbatda            qamrovda, hali urinilmagan
--   yuklanmoqda         yuklab olish boshlangan, tugamagan
--   yuklab_olindi       yuklandi, matn hali ajratilmagan
--   matn_ajratilmoqda   ajratish boshlangan, tugamagan
--   ok                  matn ajratildi
--   unreadable          o'qib bo'lmadi (skan/chizma/buzuq)
--   unsupported         format qo'llab-quvvatlanmaydi
--   too_large           chegaradan katta
--   yuklab_olinmadi     yuklab olish yiqildi — QAYTA URINILADI
--   butunlay_yiqildi    urinishlar tugadi — qayta urinilmaydi
--   manbadan_yoqoldi    manba ro'yxatdan chiqargan
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'tender_document_holat_chk') THEN
        ALTER TABLE tender_document ADD CONSTRAINT tender_document_holat_chk
            CHECK (holat IN (
                'rejalashtirilmagan', 'navbatda', 'yuklanmoqda',
                'yuklab_olindi', 'matn_ajratilmoqda', 'ok',
                'unreadable', 'unsupported', 'too_large',
                'yuklab_olinmadi', 'butunlay_yiqildi', 'manbadan_yoqoldi'));
    END IF;

    -- Xato vaqti bor bo'lsa xato MATNI ham bo'lsin — "xato bor, lekin
    -- qanaqa" degan holat qolmasin.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'tender_document_xato_chk') THEN
        ALTER TABLE tender_document ADD CONSTRAINT tender_document_xato_chk
            CHECK (last_error_at IS NULL OR last_error IS NOT NULL);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'tender_document_urinish_chk') THEN
        ALTER TABLE tender_document ADD CONSTRAINT tender_document_urinish_chk
            CHECK (urinish >= 0);
    END IF;

    -- `manbadan_yoqoldi` holati SANANI talab qiladi va aksincha.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'tender_document_yoqoldi_chk') THEN
        ALTER TABLE tender_document ADD CONSTRAINT tender_document_yoqoldi_chk
            CHECK ((holat = 'manbadan_yoqoldi') = (manbadan_yoqoldi_at IS NOT NULL));
    END IF;
END $$;

-- ---------------------------------------------------------------------
-- 3. MAVJUD QATORLARNI DALIL BO'YICHA TO'LDIRISH
-- ---------------------------------------------------------------------
-- TAXMIN QILINMAYDI. Har holat KUZATILGAN dalildan chiqadi:
--   matn qatori bor      -> uning statusi
--   matn qatori yo'q + tender qamrovda      -> navbatda
--   matn qatori yo'q + tender qamrovdan tashqarida -> rejalashtirilmagan
--
-- HECH BIR QATOR "yiqildi" DEB BELGILANMAYDI: yiqilish uchun dalil
-- kerak, dalil esa yo'q.

-- 3a. Matn qatori BOR -> statusni ko'chiramiz.
UPDATE tender_document d
   SET holat = CASE t.status
                   WHEN 'ok'              THEN 'ok'
                   WHEN 'unreadable'      THEN 'unreadable'
                   WHEN 'unsupported'     THEN 'unsupported'
                   WHEN 'too_large'       THEN 'too_large'
                   WHEN 'download_failed' THEN 'yuklab_olinmadi'
                   ELSE 'unreadable'      -- notanish status: eng ehtiyotkor
               END,
       extraction_finished_at = COALESCE(d.extraction_finished_at, t.extracted_at),
       last_error    = COALESCE(d.last_error, t.error),
       last_error_at = CASE WHEN t.error IS NOT NULL
                            THEN COALESCE(d.last_error_at, t.extracted_at) END
  FROM tender_document_text t
 WHERE t.tender_id = d.tender_id AND t.file_ref = d.file_ref
   AND d.holat IS NULL;

-- 3b. Matn qatori YO'Q -> QAMROV qoidasiga qarab.
--
--     Qamrov qoidasi `etl_doc_text.fetch_targets()` dagi `--only-open`
--     bilan AYNAN bir xil bo'lishi SHART. Ikki joyda ikki qoida bo'lsa
--     hisob va ish bir-biriga mos kelmasdi.
UPDATE tender_document d
   SET holat = CASE
        WHEN EXISTS (SELECT 1 FROM tender t2
                      WHERE t2.id = d.tender_id
                        AND t2.status = 'open'
                        AND (t2.close_at IS NULL OR t2.close_at > now()))
            THEN 'navbatda'
        ELSE 'rejalashtirilmagan'
       END
 WHERE d.holat IS NULL;

-- 3c. `discovered_at` — mavjud `fetched_at` dan tiklanadi. Bu TAXMIN
--     emas: `fetched_at` biz qatorni ko'rgan paytni bildiradi va
--     birinchi ko'rish uchun eng yaqin dalil shu.
UPDATE tender_document
   SET discovered_at = fetched_at
 WHERE discovered_at IS NULL;

ALTER TABLE tender_document ALTER COLUMN holat SET NOT NULL;
ALTER TABLE tender_document ALTER COLUMN holat SET DEFAULT 'navbatda';
ALTER TABLE tender_document ALTER COLUMN discovered_at SET DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_tender_document_holat
    ON tender_document (holat);
-- Navbat so'rovi shu indeksdan foydalanadi.
CREATE INDEX IF NOT EXISTS idx_tender_document_navbat
    ON tender_document (tender_id)
    WHERE holat IN ('navbatda', 'yuklab_olinmadi');

-- ---------------------------------------------------------------------
-- 4. QAMROV KO'RINISHI — 100% GA YIG'ILADI
-- ---------------------------------------------------------------------
-- IKKI TOMONLAMA. `FULL OUTER JOIN` ATAYLAB: bo'shliq IKKI yo'nalishda
-- chiqqan edi va faqat bir tomondan qaralsa ikkinchisi yana JIM
-- qolardi. `metadata_yoqolgan` — matni bor, lekin metadata qatori
-- yo'q hujjatlar (392 ta, o'lchangan).
CREATE OR REPLACE VIEW v_document_state AS
SELECT
    COALESCE(d.tender_id, t.tender_id)      AS tender_id,
    COALESCE(d.file_ref, t.file_ref)        AS file_ref,
    d.source_platform,
    d.file_type,
    d.size_bytes,
    CASE
        -- Metadata YO'Q, matn BOR: DELETE+INSERT qoldirgan yetim.
        WHEN d.tender_id IS NULL THEN 'metadata_yoqolgan'
        ELSE d.holat
    END                                     AS holat,
    d.urinish,
    d.discovered_at,
    d.download_started_at,
    d.downloaded_at,
    d.extraction_started_at,
    COALESCE(d.extraction_finished_at, t.extracted_at) AS extraction_finished_at,
    d.last_error_at,
    COALESCE(d.last_error, t.error)         AS last_error,
    t.status                                AS matn_status,
    t.char_count,
    (t.tender_id IS NOT NULL)               AS matn_qatori_bor
FROM tender_document d
FULL OUTER JOIN tender_document_text t
     ON t.tender_id = d.tender_id AND t.file_ref = d.file_ref;

COMMENT ON VIEW v_document_state IS
    'Har hujjatning YAGONA holati. `FULL OUTER JOIN` — bo`shliq ikki '
    'yo`nalishda chiqqan: metadata bor/holat yo`q (7 603) va holat '
    'bor/metadata yo`q (392).';

CREATE OR REPLACE VIEW v_document_processing_coverage AS
WITH s AS (SELECT * FROM v_document_state)
SELECT
    (SELECT count(*) FROM tender_document)                AS metadata_qatori,
    (SELECT count(*) FROM tender_document_text)           AS matn_qatori,
    count(*)                                              AS jami,

    -- --- REJALASHTIRILMAGAN (nosozlik EMAS) ---
    count(*) FILTER (WHERE holat = 'rejalashtirilmagan')  AS rejalashtirilmagan,

    -- --- NAVBATDA ---
    count(*) FILTER (WHERE holat = 'navbatda')            AS navbatda,
    count(*) FILTER (WHERE holat = 'yuklanmoqda')         AS yuklanmoqda,
    count(*) FILTER (WHERE holat = 'yuklab_olindi')       AS yuklab_olindi,
    count(*) FILTER (WHERE holat = 'matn_ajratilmoqda')   AS matn_ajratilmoqda,

    -- --- YAKUNIY (muvaffaqiyat) ---
    count(*) FILTER (WHERE holat = 'ok')                  AS ok,

    -- --- YAKUNIY (o'qilmadi, lekin NOSOZLIK EMAS) ---
    count(*) FILTER (WHERE holat = 'unreadable')          AS unreadable,
    count(*) FILTER (WHERE holat = 'unsupported')         AS unsupported,
    count(*) FILTER (WHERE holat = 'too_large')           AS too_large,

    -- --- NOSOZLIK ---
    count(*) FILTER (WHERE holat = 'yuklab_olinmadi')     AS yuklab_olinmadi,
    count(*) FILTER (WHERE holat = 'butunlay_yiqildi')    AS butunlay_yiqildi,

    -- --- BOSHQA QONUNIY HOLAT ---
    count(*) FILTER (WHERE holat = 'manbadan_yoqoldi')    AS manbadan_yoqoldi,
    count(*) FILTER (WHERE holat = 'metadata_yoqolgan')   AS metadata_yoqolgan,

    -- --- NAZORAT: YIG'INDI JAMIGA TENGMI ---
    -- Bu ustun ATAYLAB ko'rinishning O'ZIDA. Qamrov da'vosi
    -- hujjatda emas, SO'ROVDA tekshirilsin.
    count(*) - (
        count(*) FILTER (WHERE holat = 'rejalashtirilmagan')
      + count(*) FILTER (WHERE holat = 'navbatda')
      + count(*) FILTER (WHERE holat = 'yuklanmoqda')
      + count(*) FILTER (WHERE holat = 'yuklab_olindi')
      + count(*) FILTER (WHERE holat = 'matn_ajratilmoqda')
      + count(*) FILTER (WHERE holat = 'ok')
      + count(*) FILTER (WHERE holat = 'unreadable')
      + count(*) FILTER (WHERE holat = 'unsupported')
      + count(*) FILTER (WHERE holat = 'too_large')
      + count(*) FILTER (WHERE holat = 'yuklab_olinmadi')
      + count(*) FILTER (WHERE holat = 'butunlay_yiqildi')
      + count(*) FILTER (WHERE holat = 'manbadan_yoqoldi')
      + count(*) FILTER (WHERE holat = 'metadata_yoqolgan')
    )                                                     AS hisobga_olinmagan,

    -- --- FOIZLAR (qamrovdagi hujjatlar bo'yicha) ---
    -- MAXRAJ ATAYLAB `rejalashtirilmagan` SIZ: "ajratildi %" ni
    -- butun populyatsiyaga bo'lish 27% beradi va u ishlamayapti
    -- degan yolg'on taassurot qoldiradi. Aslida ular qamrovda EMAS.
    count(*) FILTER (WHERE holat <> 'rejalashtirilmagan')  AS qamrovda,
    round(100.0 * count(*) FILTER (WHERE holat = 'ok')
          / NULLIF(count(*) FILTER (WHERE holat <> 'rejalashtirilmagan'), 0), 1)
                                                          AS ok_foiz_qamrovda,
    round(100.0 * count(*) FILTER (WHERE holat IN
              ('ok', 'unreadable', 'unsupported', 'too_large'))
          / NULLIF(count(*) FILTER (WHERE holat <> 'rejalashtirilmagan'), 0), 1)
                                                          AS yakunlangan_foiz
FROM s;

COMMENT ON VIEW v_document_processing_coverage IS
    'Hujjat qayta ishlash qamrovi. `hisobga_olinmagan` HAR DOIM 0 '
    'bo`lishi SHART — noldan farqli qiymat jim bo`shliq qaytganini '
    'bildiradi. Foizlar `rejalashtirilmagan` SIZ hisoblanadi: ular '
    'qamrovda emas va maxrajga qo`shilsa "ishlamayapti" degan yolg`on '
    'taassurot berardi.';

-- Platforma bo'yicha kesim — qaysi manba bo'shliq beryapti.
CREATE OR REPLACE VIEW v_document_coverage_platform AS
SELECT
    COALESCE(source_platform, '(metadata yo''q)')        AS source_platform,
    count(*)                                             AS jami,
    count(*) FILTER (WHERE holat = 'rejalashtirilmagan') AS rejalashtirilmagan,
    count(*) FILTER (WHERE holat = 'navbatda')           AS navbatda,
    count(*) FILTER (WHERE holat = 'ok')                 AS ok,
    count(*) FILTER (WHERE holat = 'unreadable')         AS unreadable,
    count(*) FILTER (WHERE holat = 'unsupported')        AS unsupported,
    count(*) FILTER (WHERE holat = 'too_large')          AS too_large,
    count(*) FILTER (WHERE holat IN ('yuklab_olinmadi', 'butunlay_yiqildi'))
                                                         AS yiqilgan,
    count(*) FILTER (WHERE holat = 'manbadan_yoqoldi')   AS manbadan_yoqoldi,
    count(*) FILTER (WHERE holat = 'metadata_yoqolgan')  AS metadata_yoqolgan
FROM v_document_state
GROUP BY 1;

-- YETIM MATNLAR — alohida ko'rinish. Ular YO'QOTILMAYDI: matn bor va
-- u qimmatli (391 tasi muvaffaqiyatli ajratilgan). Sabab tuzatilgach
-- bu ro'yxat O'SMAYDI.
CREATE OR REPLACE VIEW v_document_text_yetim AS
SELECT t.tender_id, t.file_ref, t.status, t.char_count, t.extracted_at,
       (SELECT count(*) FROM tender_document d2 WHERE d2.tender_id = t.tender_id)
                                                    AS tenderda_hujjat,
       EXISTS (SELECT 1 FROM tender tn WHERE tn.id = t.tender_id) AS tender_bor
FROM tender_document_text t
WHERE NOT EXISTS (SELECT 1 FROM tender_document d
                   WHERE d.tender_id = t.tender_id AND d.file_ref = t.file_ref);

COMMENT ON VIEW v_document_text_yetim IS
    'Matni bor, lekin metadata qatori YO`Q hujjatlar. Sabab: '
    '`etl_uzex.save()` va `etl_details.save()` DELETE+INSERT qilardi '
    'va manba faylni ro`yxatdan chiqarsa metadata yo`qolardi '
    '(FK yo`q). O`lchangan: 392 qator, 391 tasi `ok`.';

-- ---------------------------------------------------------------------
-- 5. MUSBAT TASDIQ — qamrov 100% ga yig'ilyaptimi
-- ---------------------------------------------------------------------
DO $$
DECLARE
    n_holatsiz INT;
    n_qoldiq   INT;
    n_jami     INT;
    n_yetim    INT;
BEGIN
    SELECT count(*) INTO n_holatsiz FROM tender_document WHERE holat IS NULL;
    IF n_holatsiz > 0 THEN
        RAISE EXCEPTION 'Holatsiz hujjat qoldi: %', n_holatsiz;
    END IF;

    SELECT hisobga_olinmagan, jami INTO n_qoldiq, n_jami
      FROM v_document_processing_coverage;
    IF n_qoldiq <> 0 THEN
        RAISE EXCEPTION 'Qamrov yig''ilmadi: % ta hisobga olinmagan', n_qoldiq;
    END IF;

    SELECT count(*) INTO n_yetim FROM v_document_text_yetim;
    RAISE NOTICE 'TASDIQ: % hujjat, hisobga olinmagan = 0, yetim matn = %',
                 n_jami, n_yetim;
END $$;

COMMIT;
