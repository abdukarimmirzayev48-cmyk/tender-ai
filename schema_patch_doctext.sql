-- =============================================================================
-- Sxema patch — HUJJAT MATNI (P0-2)
-- Ishga tushirish:
--   psql "dbname=xtxarid user=postgres host=localhost" -f schema_patch_doctext.sql
--
-- MUAMMO: `tender_document` da FAQAT metama'lumot bor (nom, hajm, tur, file_id).
-- Fayllar bizda saqlanmaydi — API ularni manbadan proksi/redirekt qiladi.
-- Shu sababli tenderning ASOSIY mazmuni (texnik topshiriq, talablar) hech
-- qayerda MATN ko'rinishida mavjud emas: qidirib ham, tahlil qilib ham
-- bo'lmaydi.
--
-- YECHIM: `etl_doc_text.py` faylni manbadan yuklab oladi, DETERMINISTIK
-- parserlar (pypdf / python-docx / openpyxl / stdlib) bilan matnini ajratadi
-- va shu jadvalga yozadi. Faylning O'ZI saqlanmaydi — faqat matni.
--
-- MUHIM: `status` — mahsulot mantig'ining yuragi. TZ talabi:
--   "o'qib bo'lmaydigan fayllar 'qo'lda tekshirish talab etiladi' deb
--    belgilanadi" — ya'ni 'ok' dan boshqa har qanday status UI'da shu
--   ogohlantirishni chiqaradi. Matn YO'Q bo'lsa ham yozuv QOLADI, aks holda
--   "hali ishlanmagan" va "o'qib bo'lmadi" farqlanmay qoladi.
-- =============================================================================

CREATE TABLE IF NOT EXISTS tender_document_text (
    tender_id    BIGINT NOT NULL,
    -- `tender_document.file_ref` bilan bir xil kalit:
    --   xt-xarid -> file_id (uuid), uzex -> file_path ('/files/2026/...')
    file_ref     TEXT   NOT NULL,

    -- Ajratib olingan matn. NULL — matn chiqmadi (status'ga qara).
    text         TEXT,

    -- ok             — matn muvaffaqiyatli ajratildi
    -- unreadable     — fayl olindi, lekin matn chiqmadi (skan/rasm/buzilgan)
    -- unsupported    — format qo'llab-quvvatlanmaydi (rar, zip, doc, ...)
    -- download_failed— manbadan yuklab olib bo'lmadi
    -- too_large      — hajm chegarasidan katta
    status       TEXT   NOT NULL,

    char_count   INTEGER,        -- ajratilgan matn uzunligi (belgi)
    page_count   INTEGER,        -- PDF sahifa / DOCX paragraf / XLSX varaq soni
    error        TEXT,           -- xato matni (qisqartirilgan, debug uchun)
    extractor    TEXT,           -- 'pypdf' | 'python-docx' | 'openpyxl' | 'plain'
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Bitta fayl bitta tenderda bir marta
    PRIMARY KEY (tender_id, file_ref)

    -- FOREIGN KEY ATAYLAB QO'YILMAGAN.
    -- SABAB: `etl_details.py` har yurishda tenderning hujjatlarini
    -- DELETE qilib qaytadan INSERT qiladi. ON DELETE CASCADE bo'lganda
    -- shu paytda soatlab yig'ilgan matn JIMGINA o'chib ketardi va keyingi
    -- yurishda hamma fayl qaytadan yuklab olinardi. `file_ref` esa barqaror
    -- (xt-xarid: fayl uuid, uzex: fayl yo'li) — qayta INSERT dan keyin ham
    -- matn o'sha faylga to'g'ri ulanadi.
    -- Yetim yozuvlarni vaqti-vaqti bilan tozalash uchun:
    --   DELETE FROM tender_document_text t WHERE NOT EXISTS (
    --       SELECT 1 FROM tender_document d
    --       WHERE d.tender_id = t.tender_id AND d.file_ref = t.file_ref);
);

-- Tender kartochkasi uchun asosiy kirish nuqtasi
CREATE INDEX IF NOT EXISTS idx_doctext_tender ON tender_document_text(tender_id);
-- "Nechta hujjat qo'lda tekshirish talab qiladi" — statistika/monitoring
CREATE INDEX IF NOT EXISTS idx_doctext_status ON tender_document_text(status);
-- ETL "yangi ishlanganini oxirida ko'rsat" uchun
CREATE INDEX IF NOT EXISTS idx_doctext_time   ON tender_document_text(extracted_at DESC);

-- To'liq matnli qidiruv (keyingi bosqich uchun tayyor turadi).
-- 1 MB dan katta matnlarda to_tsvector xato beradi, shuning uchun kesamiz.
CREATE INDEX IF NOT EXISTS idx_doctext_fts ON tender_document_text
    USING gin (to_tsvector('simple', left(coalesce(text, ''), 1000000)));
