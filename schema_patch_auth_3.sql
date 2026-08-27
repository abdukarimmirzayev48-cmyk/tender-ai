-- =============================================================================
-- Sxema patch — AUTH-4: kompaniya sessiyasiga CSRF tokeni
-- Ishga tushirish (idempotent, bir necha marta ishlatsa ham xavfsiz):
--   psql "dbname=xtxarid user=postgres host=localhost" -f schema_patch_auth_3.sql
-- Talab: schema_patch_auth_2.sql qo'llangan bo'lishi kerak.
--
-- ERP tomonidagi `schema_patch_erp_9.sql` bilan BIR XIL o'zgarish va bir
-- xil sabab: sessiya tokeni endi `HttpOnly` cookie'da (localStorage da
-- emas), shuning uchun CSRF himoyasi kerak bo'ldi.
--
-- Batafsil izoh: `tender erp/docs/erp_auth.md` 9-bo'lim.
-- =============================================================================

ALTER TABLE company_session
    ADD COLUMN IF NOT EXISTS csrf_token TEXT;

COMMENT ON COLUMN company_session.csrf_token IS
    'CSRF tokeni. Sessiya tokenidan FARQLI: bu qiymat sahifaga ochiq '
    '(HttpOnly bo''lmagan cookie) va faqat "so''rovni bizning sahifamiz '
    'yubordimi" degan savolga javob beradi. Kirish huquqini bermaydi.';

-- Eski sessiyalarda CSRF yo'q — hamma qaytadan kiradi (tokenlar qisqa
-- umrli). Ularni qoldirsak "kirgan, lekin hech narsa yozolmaydigan"
-- holatda osilib turardi.
DELETE FROM company_session WHERE csrf_token IS NULL;
