-- =============================================================================
-- Sxema patch — HUJJATLAR TO'LIQLIGI CHEKLISTI (REJA.md P0-8)
-- Ishga tushirish (idempotent, bir necha marta ishlatsa ham xavfsiz):
--   psql "dbname=xtxarid user=postgres host=localhost" -f schema_patch_compliance.sql
--
-- MUAMMO: broker tenderga ariza berishdan oldin "qaysi hujjatlar kerak va
-- ular bizda bormi?" degan savolga javob bera olmaydi — kompaniya hujjatlari
-- bazasi umuman yo'q edi. Biznes-jarayonда (oddiy xarid, 10-11 bosqich)
-- buyurtmachi namunaviy ravishda quyidagilarni so'raydi: davlat ro'yxatidan
-- o'tganlik guvohnomasi, ishonchnoma, litsenziya, muvofiqlik sertifikati,
-- kafolat xati, bank rekvizitlari. Hujjat YO'Q yoki MUDDATI TUGAGAN bo'lsa
-- tizim brokerga xabar berishi kerak.
--
-- YECHIM: bitta jadval — `company_document`. Amal qilish muddati (`valid_until`)
-- eng muhim maydon: "bor" bilan "yaroqli" bir narsa emas.
--
-- MUHIM: `company_profile` ga TEGILMAYDI (u qidiruv + Go/No-Go salohiyati
-- uchun, boshqa modul egasi). Hujjatlar ALOHIDA jadvalda — ular ro'yxat
-- (1:N), profil esa bitta qator (1:1).
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 1. KOMPANIYA HUJJATLARI BAZASI
--    Hozircha bitta kompaniya (auth yo'q) — company_profile bilan bir xil
--    yondashuv. Auth qo'shilganda `company_id` ustuni qo'shiladi.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS company_document (
    id           SERIAL PRIMARY KEY,

    -- Kanonik hujjat turi kodi — api/compliance.py dagi DOC_TYPES ro'yxatidan
    -- ('reg_certificate', 'license', 'conformity_certificate', ...).
    -- ATAYIN FK/ENUM emas: turlar ro'yxati kod bilan birga versiyalanadi
    -- (pastdagi izohga qarang), yangi tur qo'shilganda migratsiya kerak emas.
    -- Notanish kod kelsa cheklist uni "boshqa hujjat" sifatida ko'rsatadi.
    doc_type     TEXT NOT NULL,

    name         TEXT NOT NULL,   -- 'Davlat ro'yxatidan o'tganlik guvohnomasi'
    number       TEXT,            -- hujjat raqami/seriyasi
    issued_at    DATE,            -- berilgan sana
    -- AMAL QILISH MUDDATI — cheklistning yuragi. NULL = muddatsiz
    -- (masalan ro'yxatdan o'tganlik guvohnomasi). NULL ni "muddati tugagan"
    -- deb hisoblash MUMKIN EMAS.
    valid_until  DATE,

    file_name    TEXT,            -- 'guvohnoma.pdf' (ko'rsatish uchun)
    -- Faylning o'zi. MVP da yuklash yo'q — bu tashqi havola yoki yo'l.
    -- Yuklash qo'shilganda shu ustun ichki fayl ID siga aylanadi.
    file_ref     TEXT,

    note         TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Cheklist har band uchun "shu turdagi hujjat bormi?" deb qidiradi —
-- doc_type bo'yicha indeks shuning uchun.
CREATE INDEX IF NOT EXISTS idx_company_document_type  ON company_document(doc_type);
-- "Muddati tugayotganlar" ro'yxati (kelgusi ogohlantirishlar uchun).
CREATE INDEX IF NOT EXISTS idx_company_document_valid ON company_document(valid_until);

COMMENT ON TABLE company_document IS
    'Kompaniyaning o''z hujjatlari bazasi. Tender cheklisti shunga qarab '
    '"bazada bor / yo''q" va "muddati tugagan" holatini aniqlaydi.';
COMMENT ON COLUMN company_document.doc_type IS
    'Kanonik tur kodi — api/compliance.py DOC_TYPES. NULL valid_until = muddatsiz.';


-- ---------------------------------------------------------------------------
-- 2. ANIQLASH QOIDALARI — NEGA JADVAL EMAS, KODDA
--
-- Qoidalar `api/compliance.py` dagi DOC_TYPES ichida (patterns/exclude).
-- Sabab:
--   a) Qoida "kalit so'z -> tur" emas: u BIR NECHA o'zakning bir-biriga
--      YAQINLIGINI talab qiladi ("сертификат" + "соответстви" 80 belgi
--      ichida) va ISTISNO o'zaklarga ega ("лицензия ... программного
--      обеспечения" — bu sotib olinayotgan dastur litsenziyasi, talab emas).
--      O'lchov ko'rsatdi: yalang'och kalit so'z bilan 58 ta tenderда
--      "muvofiqlik sertifikati" topildi va DEYARLI HAMMASI SOXTA edi
--      ("в соответствии с Заключением..."). Bunga jadvalда mini-DSL kerak.
--   b) Qoidalar api/translit.py bilan bevosita bog'langan (variants()) —
--      alifbo mantig'i o'zgarsa qoida ham o'zgaradi. Ular bir joyda,
--      bir commitда, bir testда tursin (_tests/compliance_test.py).
--   c) Qoida foydalanuvchi ma'lumoti emas — mahsulot mantig'i. Jadvalда
--      saqlansa har o'rnatishда urug'lantirish (seed) va migratsiya kerak.
-- Foydalanuvchi tahrirlaydigan qoidalar kerak bo'lganda shu yerga
-- `doc_requirement_rule` jadvali qo'shiladi va kod undagi qatorlarni
-- DOC_TYPES ustiga QO'SHIMCHA sifatida o'qiydi (o'rniga emas).
-- ---------------------------------------------------------------------------
