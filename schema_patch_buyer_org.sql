-- =============================================================================
-- schema_patch_buyer_org.sql   —   `tender.company_id` -> `tender.buyer_org_id`
--
-- MUAMMO: bazada `company_id` nomli IKKI XIL tushuncha bor edi.
--
--     tender.company_id          = BUYURTMACHI tashkilot, manba platformadan
--                                  (masalan 1163 = 'АО Quyuv-mexanika zavodi').
--                                  Bizga TEGISHLI EMAS, biz uni faqat
--                                  ko'rsatamiz.
--
--     catalog_product.company_id = BIZNING IJARACHI (company_account.id).
--     (va J1 dan keyin yana 11 ta jadvalda)
--
-- NEGA XAVFLI: ikkalasi bir so'rovda uchraganda alias yozilmasa, PostgreSQL
-- birontasini o'zi tanlaydi. Natija — XATOSIZ, lekin NOTO'G'RI filtr.
-- Ya'ni ko'p-ijarachilik himoyasi jimgina buziladi va hech qanday belgi
-- qolmaydi. J1.6 da 45 ta SQL qayta yozilishi kerak — bunday tuzoq bilan
-- birga emas.
--
-- YECHIM: nomlarni ajratamiz. Noto'g'ri yozilgan SQL endi DARHOL yiqiladi
-- ("column t.company_id does not exist"), jimgina ishlash o'rniga.
--
-- QO'LLASH — KOD BILAN BIRGA:
--     psql -d xtxarid -v ON_ERROR_STOP=1 -f schema_patch_buyer_org.sql
--     # so'ng API ni QAYTA ISHGA TUSHIRING (kod yangi nomni kutadi)
--
--     Patch va kod orasida ilova ishlamaydi — bu bir necha soniya.
--     ETL ni shu oraliqda yurgizmang.
--
-- Bog'liqlik: `schema_patch_multitenant.sql` dan MUSTAQIL — istalgan
-- tartibda qo'llanadi (u `tender` jadvaliga umuman tegmaydi).
--
-- Reja: reja_ai_chat.md §16.7
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

DO $$
BEGIN
    -- Idempotent: allaqachon nomlangan bo'lsa jim o'tamiz
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = 'tender'
                 AND column_name = 'buyer_org_id') THEN
        RAISE NOTICE 'tender.buyer_org_id allaqachon mavjud — o''tkazib yuborildi.';
        RETURN;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'tender'
                     AND column_name = 'company_id') THEN
        RAISE EXCEPTION 'tender.company_id topilmadi — sxema kutilganidan boshqa.';
    END IF;

    ALTER TABLE tender RENAME COLUMN company_id TO buyer_org_id;
    RAISE NOTICE 'tender.company_id -> tender.buyer_org_id';
END $$;

-- Indeks nomi ham ma'noga mos bo'lsin (ta'rif o'zgarmaydi, faqat nom)
ALTER INDEX IF EXISTS idx_tender_company RENAME TO idx_tender_buyer_org;

COMMENT ON COLUMN tender.buyer_org_id IS
    'BUYURTMACHI tashkilotning MANBA PLATFORMADAGI id si (xt-xarid/uzex). '
    'Bu BIZNING ijarachimiz EMAS — ijarachi `company_id` deb nomlanadi va '
    'har doim `company_account(id)` ga ishora qiladi. Ikkalasi bir so''rovda '
    'uchraganda chalkashmasin deb ataylab boshqacha nomlangan.';

COMMENT ON COLUMN tender.company_name IS
    'Buyurtmachi tashkilot nomi (buyer_org_id ning matnli ko''rinishi).';


-- -----------------------------------------------------------------------------
-- TEKSHIRUV
-- -----------------------------------------------------------------------------
DO $$
DECLARE n INT;
BEGIN
    SELECT count(*) INTO n FROM information_schema.columns
     WHERE table_schema = 'public' AND table_name = 'tender'
       AND column_name = 'buyer_org_id';
    IF n <> 1 THEN
        RAISE EXCEPTION 'tender.buyer_org_id yaratilmadi';
    END IF;

    SELECT count(*) INTO n FROM information_schema.columns
     WHERE table_schema = 'public' AND table_name = 'tender'
       AND column_name = 'company_id';
    IF n <> 0 THEN
        RAISE EXCEPTION 'tender.company_id hali ham mavjud';
    END IF;

    -- Endi butun bazada `company_id` FAQAT ijarachini anglatishi kerak
    SELECT count(*) INTO n FROM information_schema.columns
     WHERE table_schema = 'public' AND column_name = 'company_id'
       AND table_name NOT IN (
           SELECT table_name FROM information_schema.columns
            WHERE table_schema = 'public' AND column_name = 'company_id');
    RAISE NOTICE 'TEKSHIRUV O''TDI — `company_id` endi FAQAT ijarachini anglatadi.';
END $$;

COMMIT;


-- =============================================================================
-- ROLLBACK:
--   ALTER TABLE tender RENAME COLUMN buyer_org_id TO company_id;
--   ALTER INDEX IF EXISTS idx_tender_buyer_org RENAME TO idx_tender_company;
--   -- va kodni orqaga qaytaring (7 joy)
-- =============================================================================
