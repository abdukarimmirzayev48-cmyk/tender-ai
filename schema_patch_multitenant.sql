-- =============================================================================
-- schema_patch_multitenant.sql   —   J1: ko'p-ijarachilik (A bosqichning qolgani)
--
-- MAQSAD: kompaniya ma'lumoti bo'lgan HAR jadvalga `company_id` qo'shish va
-- ikki kompaniya bir-birining ma'lumotini ko'ra/ustidan yoza olmasligini
-- SXEMA DARAJASIDA ta'minlash.
--
-- NEGA SHOSHILINCH (o'lchangan, taxmin emas):
--   * `tender_pricing` PK = (tender_id)  -> ikkinchi kompaniya smeta saqlasa
--     birinchisining TANNARXI ustidan yoziladi. Bu tirik ma'lumot yo'qotish.
--   * `notify_sent`    PK = (tender_id, kind) -> A ga xabar ketgan tender
--     haqida B HECH QACHON xabar olmaydi.
--   * `ai_analysis`    PK = (tender_id, kind) -> `match_v2`/`gonogo_v2`
--     kompaniya katalogiga asoslanadi, lekin qator kompaniyasiz saqlanadi.
--   * Bazada ALLAQACHON 2 ta `company_account` bor — bu kelajak muammosi emas.
--
-- QO'LLASH:
--     pg_dump -Fc -d xtxarid -f xtxarid_before_multitenant.dump   -- ZAXIRA
--     psql -d xtxarid -v ON_ERROR_STOP=1 -f schema_patch_multitenant.sql
--
-- ORTGA QAYTARISH: PostgreSQL da DDL TRANZAKSION. Butun patch bitta
-- `BEGIN ... COMMIT` ichida va COMMIT dan OLDIN tekshiruvlar (§7) turadi.
-- Biror tekshiruv yiqilsa — tranzaksiya to'liq qaytadi, baza tegilmagan
-- holatda qoladi. `pg_dump` ikkinchi qatlam, birinchisi emas.
--
-- KEYINGI PATCH: `schema_patch_multitenant_2.sql` — `DEFAULT` larni olib
-- tashlaydi. U J1.7 (endpointlar `company_id` uzatishi) TUGAGANDAN KEYIN
-- qo'llanadi. Sabab §8 da.
--
-- Reja: reja_ai_chat.md §10 (J1) · LOYIHA.md §5
-- =============================================================================

\set ON_ERROR_STOP on

-- -----------------------------------------------------------------------------
-- IJARACHI HISOBI — mavjud ma'lumot KIMGA biriktiriladi
--
-- Aniq ko'rsatish (TAVSIYA ETILADI):
--     psql -v tenant_id=2 -d xtxarid -f schema_patch_multitenant.sql
--
-- Ko'rsatilmasa: YAGONA FAOL hisob tanlanadi. Bir nechta faol hisob bo'lsa
-- yoki bittasi ham bo'lmasa — patch TO'XTAYDI va ro'yxatni chiqaradi.
--
-- NEGA `MIN(id)` EMAS (bu haqiqiy xato bo'lgan): bazada eng kichik id
-- O'CHIRILGAN SINOV hisobiga tegishli bo'lishi mumkin. Shunda butun
-- kompaniya ma'lumoti `active=false` hisobga biriktirilardi va buni
-- hech kim sezmasdi — FK to'g'ri, NOT NULL to'g'ri, faqat EGASI noto'g'ri.
-- -----------------------------------------------------------------------------
\if :{?tenant_id}
\else
  \set tenant_id ''
\endif

BEGIN;

SELECT set_config('tai.tenant_id', :'tenant_id', true);

DO $$
DECLARE
    want INT := NULLIF(current_setting('tai.tenant_id', true), '')::INT;
    cid  INT;
    faol INT;
    royxat TEXT;
BEGIN
    IF want IS NOT NULL THEN
        SELECT id INTO cid FROM company_account WHERE id = want;
        IF cid IS NULL THEN
            RAISE EXCEPTION 'tenant_id=% : bunday company_account YO''Q', want;
        END IF;
        IF NOT (SELECT active FROM company_account WHERE id = cid) THEN
            RAISE WARNING 'tenant_id=% hisobi FAOL EMAS (active=false). '
                          'Ataylab shundaymi?', cid;
        END IF;
    ELSE
        SELECT count(*) INTO faol FROM company_account WHERE active;
        IF faol = 0 THEN
            RAISE EXCEPTION 'FAOL company_account YO''Q. Hisob yarating yoki '
                            'aniq ko''rsating: psql -v tenant_id=<id> ...';
        ELSIF faol > 1 THEN
            SELECT string_agg(format('%s(%s)', id, username), ', ' ORDER BY id)
              INTO royxat FROM company_account WHERE active;
            RAISE EXCEPTION 'Bir nechta FAOL hisob: %. Qaysi biriga biriktirishni '
                            'ANIQ ko''rsating: psql -v tenant_id=<id> ...', royxat;
        END IF;
        SELECT id INTO cid FROM company_account WHERE active;
    END IF;

    PERFORM set_config('tai.tenant_id', cid::TEXT, true);
    RAISE NOTICE 'IJARACHI: id=% (%) — mavjud ma''lumot shunga biriktiriladi.',
                 cid, (SELECT username FROM company_account WHERE id = cid);
END $$;

-- -----------------------------------------------------------------------------
-- 1. YORDAMCHI: ustunni "tez" qo'shish
--
--    DIQQAT — TUZATISH: `DEFAULT (SELECT MIN(id) FROM company_account)`
--    PostgreSQL da ISHLAMAYDI. Hujjatda aniq yozilgan: DEFAULT ifodasi
--    QUYIDAGILARNI o'z ichiga OLA OLMAYDI — kichik so'rov (subquery),
--    joriy jadvalning boshqa ustuniga havola, boshqa jadvalga havola.
--    Xato: "cannot use subquery in DEFAULT expression".
--
--    Yechim: qiymatni DO blokida HISOBLAB, `format()` bilan KONSTANTA
--    sifatida qo'yamiz. Natija bir xil — PG 11+ da `ADD COLUMN ... NOT NULL
--    DEFAULT <konstanta>` jadvalni QAYTA YOZMAYDI, ya'ni tez.
-- -----------------------------------------------------------------------------
-- DIQQAT: parametr nomi `notnull` BO'LMASLIGI kerak — PostgreSQL da
-- `NOTNULL` kalit so'z (`x NOTNULL` = `x IS NOT NULL`) va plpgsql uni
-- o'zgaruvchi deb qabul qilmaydi: "ошибка синтаксиса в конце".
CREATE OR REPLACE FUNCTION tai_add_company_id(
    tbl TEXT, majburiy BOOLEAN DEFAULT TRUE) RETURNS VOID AS $$
DECLARE
    cid INT;
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = tbl
                 AND column_name = 'company_id') THEN
        RAISE NOTICE '  % : company_id allaqachon bor — o''tkazib yuborildi', tbl;
        RETURN;
    END IF;

    cid := current_setting('tai.tenant_id')::INT;   -- yuqorida ANIQLANGAN

    IF majburiy THEN
        EXECUTE format(
            'ALTER TABLE public.%I ADD COLUMN company_id INT NOT NULL DEFAULT %s',
            tbl, cid);
    ELSE
        EXECUTE format(
            'ALTER TABLE public.%I ADD COLUMN company_id INT', tbl);
    END IF;

    -- FK NOT VALID bilan: mavjud qatorlarni tekshirmaydi, jadvalni bloklamaydi
    EXECUTE format(
        'ALTER TABLE public.%I ADD CONSTRAINT %I '
        'FOREIGN KEY (company_id) REFERENCES company_account(id) '
        'ON DELETE CASCADE NOT VALID', tbl, tbl || '_company_fk');

    -- Tasdiqlash: ACCESS EXCLUSIVE emas, SHARE UPDATE EXCLUSIVE qulf
    EXECUTE format('ALTER TABLE public.%I VALIDATE CONSTRAINT %I',
                   tbl, tbl || '_company_fk');

    EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON public.%I (company_id)',
                   'idx_' || tbl || '_company', tbl);

    RAISE NOTICE '  % : company_id qo''shildi (DEFAULT %)', tbl, cid;
END $$ LANGUAGE plpgsql;


-- -----------------------------------------------------------------------------
-- 2. `company_id` ALLAQACHON BOR (nullable) — to'ldirish va NOT NULL qilish
-- -----------------------------------------------------------------------------
DO $$
DECLARE
    cid INT;
    t   TEXT;
BEGIN
    cid := current_setting('tai.tenant_id')::INT;   -- yuqorida ANIQLANGAN
    FOREACH t IN ARRAY ARRAY['catalog_product', 'catalog_import_batch', 'saved_search']
    LOOP
        EXECUTE format('UPDATE public.%I SET company_id = %s WHERE company_id IS NULL',
                       t, cid);
        EXECUTE format('ALTER TABLE public.%I ALTER COLUMN company_id SET NOT NULL', t);
        EXECUTE format('ALTER TABLE public.%I ALTER COLUMN company_id SET DEFAULT %s',
                       t, cid);
        -- Bu jadvallarda ustun BIGINT edi; FK uchun turni moslashtiramiz.
        -- SHART MAJBURIY: patch ikkinchi marta yurgizilsa, §6 dagi
        -- `v_catalog_all_companies` ko'rinishi shu ustunga tayangan bo'ladi va
        -- PostgreSQL "изменить тип столбца, задействованного в представлении,
        -- нельзя" deb yiqiladi. Tur allaqachon INT bo'lsa — tegmaymiz.
        IF (SELECT data_type FROM information_schema.columns
             WHERE table_schema = 'public' AND table_name = t
               AND column_name = 'company_id') <> 'integer' THEN
            EXECUTE format('ALTER TABLE public.%I ALTER COLUMN company_id TYPE INT', t);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_constraint
                       WHERE conname = t || '_company_fk') THEN
            EXECUTE format(
                'ALTER TABLE public.%I ADD CONSTRAINT %I '
                'FOREIGN KEY (company_id) REFERENCES company_account(id) '
                'ON DELETE CASCADE NOT VALID', t, t || '_company_fk');
            EXECUTE format('ALTER TABLE public.%I VALIDATE CONSTRAINT %I',
                           t, t || '_company_fk');
        END IF;
        RAISE NOTICE '  % : to''ldirildi va NOT NULL qilindi', t;
    END LOOP;
END $$;


-- -----------------------------------------------------------------------------
-- 3. `company_id` UMUMAN YO'Q — qo'shamiz
-- -----------------------------------------------------------------------------
SELECT tai_add_company_id('company_profile');
SELECT tai_add_company_id('company_document');
SELECT tai_add_company_id('tender_pricing');
SELECT tai_add_company_id('notify_sent');
SELECT tai_add_company_id('notify_telegram_subscriber');
SELECT tai_add_company_id('notify_telegram_link');


-- -----------------------------------------------------------------------------
-- 4. SINGLETONLARNI SINDIRISH  (id = 1 -> har kompaniyaga bitta qator)
--
--    `id` PK bo'lib qoladi (kod unga tayanadi), lekin:
--      * CHECK (id = 1) olib tashlanadi
--      * `id` ketma-ketlik (sequence) oladi — yangi qator o'zi id oladi
--      * (company_id) UNIQUE — har kompaniyada AYNAN BITTA yozuv
-- -----------------------------------------------------------------------------
DO $$
DECLARE
    t    TEXT;
    seq  TEXT;
    chk  TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['pricing_settings', 'notify_settings', 'catalog_state']
    LOOP
        chk := t || '_singleton';
        EXECUTE format('ALTER TABLE public.%I DROP CONSTRAINT IF EXISTS %I', t, chk);

        seq := t || '_id_seq';
        EXECUTE format('CREATE SEQUENCE IF NOT EXISTS public.%I OWNED BY public.%I.id',
                       seq, t);
        EXECUTE format('SELECT setval(%L, GREATEST(COALESCE((SELECT MAX(id) FROM public.%I), 1), 1))',
                       'public.' || seq, t);
        EXECUTE format('ALTER TABLE public.%I ALTER COLUMN id SET DEFAULT nextval(%L)',
                       t, 'public.' || seq);

        PERFORM tai_add_company_id(t);

        EXECUTE format('CREATE UNIQUE INDEX IF NOT EXISTS %I ON public.%I (company_id)',
                       'uq_' || t || '_company', t);
        RAISE NOTICE '  % : singleton sindirildi', t;
    END LOOP;
END $$;


-- -----------------------------------------------------------------------------
-- 5. BIRLAMCHI KALITLARNI KENGAYTIRISH
-- -----------------------------------------------------------------------------

-- 5.1 tender_pricing: (tender_id) -> (tender_id, company_id)
--     ENG MUHIM QADAM: shu paytgacha ikkinchi kompaniya smetasi birinchisining
--     TANNARXI ustidan yozardi.
ALTER TABLE tender_pricing DROP CONSTRAINT IF EXISTS tender_pricing_pkey;
ALTER TABLE tender_pricing ADD PRIMARY KEY (tender_id, company_id);

-- 5.2 notify_sent: (tender_id, kind) -> (tender_id, kind, company_id)
--     Shu paytgacha A ga xabar ketgan tender haqida B xabar OLMAY qolardi.
ALTER TABLE notify_sent DROP CONSTRAINT IF EXISTS notify_sent_pkey;
ALTER TABLE notify_sent ADD PRIMARY KEY (tender_id, kind, company_id);

-- 5.3 notify_telegram_subscriber: (chat_id) -> (company_id, chat_id)
--     Bitta Telegram suhbat ikki kompaniyaga obuna bo'lishi mumkin.
ALTER TABLE notify_telegram_subscriber DROP CONSTRAINT IF EXISTS notify_telegram_subscriber_pkey;
ALTER TABLE notify_telegram_subscriber ADD PRIMARY KEY (company_id, chat_id);

-- 5.4 ai_analysis — ARALASH holat, alohida qarash kerak.
--
--     `summary_v1`  — tenderning O'ZI haqida (nima sotib olinadi, qanday
--                     kategoriya). Kompaniyaga bog'liq EMAS -> UMUMIY qoladi,
--                     company_id IS NULL. Ikki kompaniya bir keshdan foydalanadi
--                     va bu TO'G'RI: takroriy to'lov bo'lmaydi.
--
--     `match_v2`    — `build_input(tender, products, profile, docs)`, ya'ni
--     `gonogo_v2`     KOMPANIYA katalogi va profiliga asoslanadi. `result`
--                     ichida `matched_items[]` — kompaniyaning MAHSULOT
--                     NOMLARI. Bu kompaniya siri va u kompaniyasiz qatorda
--                     turishi mumkin emas.
--
--     NULL li ustun PK da bo'la olmaydi -> ikkita QISMAN UNIQUE indeks.
ALTER TABLE ai_analysis ADD COLUMN IF NOT EXISTS company_id INT
    REFERENCES company_account(id) ON DELETE CASCADE;

DO $$
DECLARE cid INT;
BEGIN
    cid := current_setting('tai.tenant_id')::INT;   -- yuqorida ANIQLANGAN
    -- Mavjud kompaniyaga oid tahlillar birinchi hisobga biriktiriladi
    EXECUTE format(
        'UPDATE ai_analysis SET company_id = %s '
        'WHERE kind <> ''summary_v1'' AND company_id IS NULL', cid);
    -- Umumiy tahlil ataylab NULL
    UPDATE ai_analysis SET company_id = NULL WHERE kind = 'summary_v1';
END $$;

ALTER TABLE ai_analysis DROP CONSTRAINT IF EXISTS ai_analysis_pkey;

CREATE UNIQUE INDEX IF NOT EXISTS ai_analysis_shared
    ON ai_analysis (tender_id, kind) WHERE company_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ai_analysis_private
    ON ai_analysis (tender_id, kind, company_id) WHERE company_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ai_analysis_company ON ai_analysis (company_id);

COMMENT ON COLUMN ai_analysis.company_id IS
    'NULL = UMUMIY tahlil (summary_v1) — tenderning o''zi haqida, hamma '
    'kompaniya bir keshdan foydalanadi. NOT NULL = kompaniya tahlili '
    '(match_v2, gonogo_v2) — katalog va profilga asoslangan, siri.';


-- -----------------------------------------------------------------------------
-- 6. QAMROV KO'RINISHI — hujjat ETL si uchun
--    `etl_doc_text.py --catalog` barcha kompaniyalar kataloglarining
--    BIRLASHMASINI oladi. Ko'rinish shuni aniq qilib qo'yadi.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_catalog_all_companies AS
SELECT id, company_id, name, category_code, keywords, unit
FROM catalog_product;

COMMENT ON VIEW v_catalog_all_companies IS
    'Hujjat qamrovi uchun: BARCHA kompaniyalar katalogi birlashmasi. '
    'ETL kompaniya nomidan emas, platforma nomidan ishlaydi — filtr '
    'qo''ysak B kompaniyasining tenderlari o''qilmay qolardi.';


-- -----------------------------------------------------------------------------
-- 7. COMMIT DAN OLDINGI TEKSHIRUVLAR
--    Biror shart bajarilmasa — butun tranzaksiya qaytadi.
-- -----------------------------------------------------------------------------
DO $$
DECLARE
    n   INT;
    t   TEXT;
BEGIN
    -- 7.1 Yetim qator qolmadimi (NOT NULL bo'lishi kerak bo'lganlarda)
    FOREACH t IN ARRAY ARRAY[
        'catalog_product', 'catalog_import_batch', 'saved_search',
        'company_profile', 'company_document', 'tender_pricing',
        'notify_sent', 'notify_telegram_subscriber', 'notify_telegram_link',
        'pricing_settings', 'notify_settings', 'catalog_state']
    LOOP
        EXECUTE format('SELECT count(*) FROM public.%I WHERE company_id IS NULL', t)
            INTO n;
        IF n > 0 THEN
            RAISE EXCEPTION '% : % ta yetim qator (company_id IS NULL)', t, n;
        END IF;
    END LOOP;

    -- 7.2 ai_analysis — faqat summary_v1 NULL bo'lishi mumkin
    SELECT count(*) INTO n FROM ai_analysis
     WHERE company_id IS NULL AND kind <> 'summary_v1';
    IF n > 0 THEN
        RAISE EXCEPTION 'ai_analysis: % ta kompaniya tahlili company_id siz', n;
    END IF;

    -- 7.3 PK lar haqiqatan kengaydimi
    SELECT count(*) INTO n FROM pg_index i
      JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
     WHERE i.indrelid = 'tender_pricing'::regclass AND i.indisprimary
       AND a.attname = 'company_id';
    IF n <> 1 THEN
        RAISE EXCEPTION 'tender_pricing PK company_id ni o''z ichiga olmadi';
    END IF;

    SELECT count(*) INTO n FROM pg_index i
      JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
     WHERE i.indrelid = 'notify_sent'::regclass AND i.indisprimary
       AND a.attname = 'company_id';
    IF n <> 1 THEN
        RAISE EXCEPTION 'notify_sent PK company_id ni o''z ichiga olmadi';
    END IF;

    -- 7.4 FK lar tasdiqlanganmi (NOT VALID qolib ketmasin)
    SELECT count(*) INTO n FROM pg_constraint
     WHERE conname LIKE '%_company_fk' AND NOT convalidated;
    IF n > 0 THEN
        RAISE EXCEPTION '% ta FK tasdiqlanmagan (NOT VALID) qoldi', n;
    END IF;

    RAISE NOTICE 'TEKSHIRUVLAR O''TDI — commit qilinmoqda.';
END $$;

DROP FUNCTION IF EXISTS tai_add_company_id(TEXT, BOOLEAN);

COMMIT;


-- =============================================================================
-- 8. KEYINGI QADAM — `DEFAULT` LARNI OLIB TASHLASH (bu yerda EMAS)
--
-- Hozir har jadvalda `company_id DEFAULT <birinchi kompaniya>` turibdi.
-- Bu J1.6–J1.7 davomida ATAYLAB qoldirilgan HIMOYA TO'RI: kod biror joyda
-- `company_id` uzatishni unutsa, qator YO'QOLMAYDI.
--
-- Ammo J1.7 tugagach u XATONI YASHIRUVCHIGA aylanadi: unutilgan `INSERT`
-- jimgina birinchi kompaniyaga yozadi va buni hech kim sezmaydi.
-- `DROP DEFAULT` dan keyin esa u baland ovozda `NOT NULL violation` beradi.
-- Bu loyihaning "jimgina o'tkazib yuborilmaydi" tamoyiliga mos.
--
--     -> schema_patch_multitenant_2.sql   (J1.7 TUGAGANDAN KEYIN)
-- =============================================================================

-- =============================================================================
-- ROLLBACK (COMMIT dan KEYIN kerak bo'lsa — qo'lda):
--
--   ALTER TABLE tender_pricing DROP CONSTRAINT tender_pricing_pkey;
--   ALTER TABLE tender_pricing ADD PRIMARY KEY (tender_id);
--   ALTER TABLE notify_sent DROP CONSTRAINT notify_sent_pkey;
--   ALTER TABLE notify_sent ADD PRIMARY KEY (tender_id, kind);
--   ALTER TABLE notify_telegram_subscriber DROP CONSTRAINT notify_telegram_subscriber_pkey;
--   ALTER TABLE notify_telegram_subscriber ADD PRIMARY KEY (chat_id);
--   DROP INDEX ai_analysis_shared, ai_analysis_private;
--   ALTER TABLE ai_analysis ADD PRIMARY KEY (tender_id, kind);
--   -- keyin har jadvaldan: ALTER TABLE <t> DROP COLUMN company_id;
--
--   DIQQAT: `tender_pricing` da PK ni qaytarish TAKROR qatorlar bo'lsa
--   YIQILADI — o'sha paytgacha ikki kompaniya smeta saqlagan bo'lishi mumkin.
--   Shuning uchun zaxira (`pg_dump`) baribir kerak.
-- =============================================================================
