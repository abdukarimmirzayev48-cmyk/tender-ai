-- =============================================================================
-- HUJJAT HOLATI DALILGA BOG'LANADI (M-1)
--
--   psql "dbname=xtxarid user=postgres host=localhost" -f schema_patch_hujjat_dalil.sql
--
-- O'LCHANGAN NUQSON (2026-09-01)
-- ------------------------------
-- 30 ta hujjat `holat='ok'` deb belgilangan, lekin
-- `tender_document_text` da ularning matn qatori UMUMAN YO'Q.
-- `ok` "matn muvaffaqiyatli ajratildi" degani, ya'ni bu DALILSIZ
-- YORLIQ — loyihaning takrorlanuvchi nuqson sinfi.
--
-- SABAB ISBOTLANDI, TAXMIN EMAS. `_tests/doctext_test.py:test_cache`
-- HAQIQIY hujjat qatorini oladi, uning matnini `"sinov"` (5 belgi)
-- bilan ALMASHTIRADI, so'ng matn qatorini O'CHIRADI — lekin
-- `tender_document.holat` `ok` bo'lib QOLADI. O'lchov:
--
--     sinovdan OLDIN  29
--     sinovdan KEYIN  30      (har yurishda +1)
--
-- Ikki zarar bor edi:
--   1. HAQIQIY ajratilgan matn YO'QOLARDI (ustiga "sinov" yozilardi);
--   2. Hujjat `ok` bo'lgani uchun ETL uni QAYTA OLMASDI
--      (`fetch_targets()` `ok` larni o'tkazib yuboradi) — ya'ni matn
--      butunlay yo'qolardi va buni hech narsa ko'rsatmasdi.
--
-- Sinov tuzatildi (soxta qator bilan ishlaydi). Bu patch qolgan
-- ikkisini qiladi: MAVJUD zararni tiklaydi va QAYTA sodir bo'lishini
-- BAZA DARAJASIDA to'xtatadi.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. TIKLASH — dalilsiz `ok` yorlig'i OLIB TASHLANADI
-- ---------------------------------------------------------------------
-- Yorliq olib tashlanadi, YANGISI TAXMIN QILINMAYDI: qaysi holatga
-- o'tishi `schema_patch_doc_qamrov.sql` §3b dagi AYNI qamrov qoidasi
-- bilan hal qilinadi (ochiq va muddati o'tmagan -> navbatda, aks
-- holda rejalashtirilmagan). Ikki joyda ikki qoida bo'lsa hisob va
-- ish bir-biriga mos kelmasdi.
--
-- Vaqt belgilari ham TOZALANADI: "ajratish tugadi" degani ham
-- dalilsiz edi.
UPDATE tender_document d
   SET holat = CASE
        WHEN EXISTS (SELECT 1 FROM tender t2
                      WHERE t2.id = d.tender_id
                        AND t2.status = 'open'
                        AND (t2.close_at IS NULL OR t2.close_at > now()))
            THEN 'navbatda'
        ELSE 'rejalashtirilmagan'
       END,
       extraction_started_at  = NULL,
       extraction_finished_at = NULL
 WHERE d.holat = 'ok'
   AND NOT EXISTS (SELECT 1 FROM tender_document_text t
                    WHERE t.tender_id = d.tender_id
                      AND t.file_ref  = d.file_ref);

-- ---------------------------------------------------------------------
-- 2. QO'ROVUL — `ok` uchun DALIL SHART
-- ---------------------------------------------------------------------
-- NEGA TRIGGER, CHECK EMAS: shart IKKINCHI jadvalga qaraydi va
-- `CHECK` da boshqa jadvalni o'qib bo'lmaydi.
--
-- NEGA UMUMAN BAZADA: qoida shu paytgacha faqat KODDA edi
-- (`etl_doc_text.save()` ikkalasini bitta tranzaksiyada yozadi) va
-- uni CHETLAB O'TISH oson bo'lib chiqdi — buni sinovning o'zi
-- isbotladi. "Qoida faqat izoh bilan himoyalangan" — bu loyihada
-- takrorlangan nuqson sinfi.
CREATE OR REPLACE FUNCTION hujjat_ok_dalil_talab() RETURNS trigger AS $$
BEGIN
    IF NEW.holat = 'ok' AND NOT EXISTS (
        SELECT 1 FROM tender_document_text t
         WHERE t.tender_id = NEW.tender_id
           AND t.file_ref  = NEW.file_ref) THEN
        RAISE EXCEPTION
            'tender_document.holat = ''ok'' uchun tender_document_text '
            'da qator SHART (tender_id=%, file_ref=%). '
            '`ok` "matn ajratildi" degani — dalilsiz qo''yilmaydi.',
            NEW.tender_id, NEW.file_ref
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- `save()` da tartib: AVVAL matn qatori INSERT, KEYIN metadata
-- UPDATE — ya'ni trigger ishlaganda dalil allaqachon joyida.
DROP TRIGGER IF EXISTS hujjat_ok_dalil_trg ON tender_document;
CREATE TRIGGER hujjat_ok_dalil_trg
    BEFORE INSERT OR UPDATE OF holat ON tender_document
    FOR EACH ROW EXECUTE FUNCTION hujjat_ok_dalil_talab();

COMMENT ON FUNCTION hujjat_ok_dalil_talab() IS
    'M-1: `holat=''ok''` uchun matn qatori SHART. 30 ta hujjat '
    'dalilsiz `ok` bo''lib qolgan edi (sabab: doctext_test).';

-- ---------------------------------------------------------------------
-- 3. O'LCHOV — nomuvofiqlik KO'RINSIN
-- ---------------------------------------------------------------------
-- Uch yo'nalish ALOHIDA sanaladi: ular BOSHQA sabablardan kelib
-- chiqadi va boshqa javob talab qiladi.
CREATE OR REPLACE VIEW v_hujjat_dalil_nomuvofiq AS
SELECT
    -- Endi qo'rovul buni TO'XTATADI; nol bo'lib qolishi kerak.
    (SELECT count(*) FROM tender_document d
      WHERE d.holat = 'ok'
        AND NOT EXISTS (SELECT 1 FROM tender_document_text t
                         WHERE t.tender_id = d.tender_id
                           AND t.file_ref  = d.file_ref))       AS ok_dalilsiz,
    -- Matn bor, lekin statusi `ok` emas: `ok` yorlig'i noto'g'ri.
    (SELECT count(*) FROM tender_document d
       JOIN tender_document_text t
         ON t.tender_id = d.tender_id AND t.file_ref = d.file_ref
      WHERE d.holat = 'ok' AND t.status <> 'ok')                AS ok_status_qarama_qarshi,
    -- YETIM matn: metadata qatori yo'q. TARIXIY — `b3e819f` gacha
    -- ETL `DELETE FROM tender_document` qilardi. O'chirib
    -- bo'lmaydi: matn MUVAFFAQIYATLI ajratilgan va uni yo'qotish
    -- ma'lumot yo'qotish bo'lardi.
    (SELECT count(*) FROM tender_document_text t
      WHERE NOT EXISTS (SELECT 1 FROM tender_document d
                         WHERE d.tender_id = t.tender_id
                           AND d.file_ref  = t.file_ref))       AS yetim_matn;

COMMENT ON VIEW v_hujjat_dalil_nomuvofiq IS
    'M-1 o''lchovi. `ok_dalilsiz` va `ok_status_qarama_qarshi` NOL '
    'bo''lishi SHART (qo''rovul ushlaydi). `yetim_matn` tarixiy va '
    'o''chirilmaydi — matn muvaffaqiyatli ajratilgan.';

COMMIT;
