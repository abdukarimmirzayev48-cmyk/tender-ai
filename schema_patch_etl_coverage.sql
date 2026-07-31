-- =============================================================================
-- Sxema patch — ETL QAMROVI (P0-1: "1-2 platformani soatiga bir marta kuzatish")
-- Ishga tushirish (idempotent, xohlagancha qayta yurgizsa bo'ladi):
--   psql "dbname=xtxarid user=a1234 host=localhost" -f schema_patch_etl_coverage.sql
--
-- SABAB
-- -----
-- xt-xarid.uz ikkita ochiq reyestr chop etadi:
--     ref_tender_public     -> type='tender'
--     ref_selection_public  -> type='selection'
-- Ilgari ETL faqat birinchisini yig'ardi. Ikkinchisi qo'shilgach `tender.status`
-- da ikkita YANGI kod paydo bo'ladi:
--     tech_check_docs, agree_objections
-- Ular `ref_status_tender` (va umumiy `ref_status`) reestrida QAYTARILMAYDI,
-- ya'ni etl_dims.py ularni hech qachon yuklay olmaydi. Lug'atda bo'lmasa
-- api/queries.py dagi
--     LEFT JOIN dim_status s ON s.status_code = t.status AND s.domain='tender'
-- NULL beradi va frontend status filtri/nishonida BO'SH NOM chiqadi.
-- Shuning uchun ularni QO'LDA, bir marta kiritamiz.
--
-- ESLATMA: nomlar manbadan olinmagani uchun qo'lda tarjima qilingan. Agar
-- kelajakda API bu kodlarni qaytara boshlasa, etl_dims.py dagi
-- ON CONFLICT ... DO UPDATE name_ru/status_id ni manba qiymati bilan
-- avtomatik almashtiradi — bu yerdagi qatorlar to'siq bo'lmaydi.
-- =============================================================================

INSERT INTO dim_status (status_code, domain, name_uz, name_ru, is_terminal, status_id)
VALUES
    ('tech_check_docs',  'tender',
     'Texnik hujjatlarni tekshirish',
     'Проверка технической документации',
     FALSE, NULL),
    ('agree_objections', 'tender',
     'E''tirozlarni kelishish',
     'Согласование возражений',
     FALSE, NULL)
ON CONFLICT (status_code, domain) DO NOTHING;

-- Tekshiruv (yurgizgandan keyin 2 qator chiqishi kerak):
--   SELECT status_code, name_uz, name_ru FROM dim_status
--    WHERE status_code IN ('tech_check_docs','agree_objections');
