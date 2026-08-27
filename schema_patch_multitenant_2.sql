-- =============================================================================
-- schema_patch_multitenant_2.sql   —   J1 ning YAKUNI: himoya to'rini olib tashlash
--
-- QACHON QO'LLANADI: J1.7 (barcha endpointlar `company_id` uzatishi) TUGAGACH.
-- ERTA QO'LLASH XAVFLI: kod hali `company_id` uzatmayotgan bo'lsa, har
-- `INSERT` `NOT NULL violation` bilan yiqiladi va ilova ishlamay qoladi.
--
-- NEGA KERAK — bu shunchaki tozalash emas:
--
--   `schema_patch_multitenant.sql` har jadvalga
--   `company_id DEFAULT <birinchi kompaniya>` qo'ydi. J1.6–J1.7 davomida bu
--   HIMOYA TO'RI edi: kod biror joyda `company_id` uzatishni unutsa, qator
--   yo'qolmasdi.
--
--   J1.7 tugagach o'sha DEFAULT XATONI YASHIRUVCHIGA aylanadi: unutilgan
--   `INSERT` JIMGINA birinchi kompaniyaga yozadi. Ikkinchi kompaniya
--   ma'lumoti birinchisiniki bo'lib qoladi va buni HECH KIM SEZMAYDI —
--   xato yo'q, jurnal yo'q, faqat noto'g'ri egalik.
--
--   DEFAULT olib tashlangach esa o'sha unutilgan `INSERT` baland ovozda
--   `null value in column "company_id" violates not-null constraint` beradi.
--   Bu loyihaning "jimgina o'tkazib yuborilmaydi" tamoyili — SQL qatlamida.
--
-- QO'LLASH:
--     psql -d xtxarid -v ON_ERROR_STOP=1 -f schema_patch_multitenant_2.sql
--
-- Reja: reja_ai_chat.md §10 (J1) · schema_patch_multitenant.sql §8
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

-- -----------------------------------------------------------------------------
-- 0. TAYYORLIK TEKSHIRUVI
--    DEFAULT ni olib tashlashdan oldin: kod haqiqatan tayyormi?
--    To'liq javobni faqat sinovlar beradi, lekin bitta belgi bor —
--    bazada BIR NECHTA kompaniya ma'lumoti bo'lishi kerak. Agar hamma
--    qator hali ham bitta kompaniyaga tegishli bo'lsa, ehtimol J1.7
--    tugamagan yoki sinovdan o'tmagan.
-- -----------------------------------------------------------------------------
DO $$
DECLARE
    hisoblar INT;
    egalar   INT;
BEGIN
    SELECT count(*) INTO hisoblar FROM company_account WHERE active;
    SELECT count(DISTINCT company_id) INTO egalar FROM catalog_product;

    IF hisoblar > 1 AND egalar = 1 THEN
        RAISE WARNING 'DIQQAT: % ta faol hisob bor, lekin catalog_product '
                      'butunlay BITTA kompaniyaga tegishli. J1.7 tugaganmi va '
                      '_tests/multitenant_test.py o''tdimi? Davom etilmoqda.',
                      hisoblar;
    END IF;
END $$;


-- -----------------------------------------------------------------------------
-- 1. DEFAULT LARNI OLIB TASHLASH
--    NOT NULL va FK O'Z O'RNIDA QOLADI — faqat "avtomatik to'ldirish"
--    yo'qoladi.
-- -----------------------------------------------------------------------------
DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'catalog_product', 'catalog_import_batch', 'saved_search',
        'company_profile', 'company_document', 'tender_pricing',
        'notify_sent', 'notify_telegram_subscriber', 'notify_telegram_link',
        'pricing_settings', 'notify_settings', 'catalog_state']
    LOOP
        EXECUTE format('ALTER TABLE public.%I ALTER COLUMN company_id DROP DEFAULT', t);
        RAISE NOTICE '  % : DEFAULT olib tashlandi', t;
    END LOOP;
END $$;


-- -----------------------------------------------------------------------------
-- 2. TEKSHIRUV — hech bir jadvalda DEFAULT qolmadimi
-- -----------------------------------------------------------------------------
DO $$
DECLARE
    qoldi TEXT;
BEGIN
    SELECT string_agg(table_name, ', ') INTO qoldi
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND column_name = 'company_id'
      AND column_default IS NOT NULL;

    IF qoldi IS NOT NULL THEN
        RAISE EXCEPTION 'Bu jadvallarda company_id DEFAULT qoldi: %', qoldi;
    END IF;

    RAISE NOTICE 'TEKSHIRUV O''TDI — endi unutilgan INSERT jimgina o''tmaydi.';
END $$;

COMMIT;


-- =============================================================================
-- ROLLBACK (himoya to'rini qaytarish kerak bo'lsa):
--
--   DO $$
--   DECLARE t TEXT; cid INT;
--   BEGIN
--       SELECT MIN(id) INTO cid FROM company_account;
--       FOREACH t IN ARRAY ARRAY['catalog_product', 'catalog_import_batch',
--           'saved_search', 'company_profile', 'company_document',
--           'tender_pricing', 'notify_sent', 'notify_telegram_subscriber',
--           'notify_telegram_link', 'pricing_settings', 'notify_settings',
--           'catalog_state']
--       LOOP
--           EXECUTE format('ALTER TABLE public.%I ALTER COLUMN company_id SET DEFAULT %s', t, cid);
--       END LOOP;
--   END $$;
-- =============================================================================
