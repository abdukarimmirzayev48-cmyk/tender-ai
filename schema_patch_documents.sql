-- =============================================================================
-- Sxema patch — TENDER TAFSILOTI va HUJJATLARI
-- Ishga tushirish:
--   psql "dbname=xtxarid user=a1234 host=localhost" -f schema_patch_documents.sql
--
-- MANBA (aniqlangan, autentifikatsiyasiz):
--   POST https://api.xt-xarid.uz/urpc   method="get_proc"  params={"proc_id":"<id>"}
--   Sarlavhalar: X-DBRPC-Language, x-idempotency-key, x-url-on
--   Javob: result.fields — 129 maydonli obyekt.
--
-- MUHIM: fayllar QATTIQ maydon nomida emas, TARQOQ joylashgan:
--   anno_file (asos-hujjatlar), proform_file (shartnoma namunasi),
--   proc_custom2/4/6 (buyurtmachining qo'shimcha ma'lumot maydonlari) ...
--   Shuning uchun ETL nom bo'yicha emas, STRUKTURA bo'yicha skanerlaydi:
--   {id: <uuid>, meta: {size, content_type, ...}} ko'rinishidagi har obyekt = fayl.
--
-- Yuklab olish: https://api.xt-xarid.uz/file/<file_id>  (GET, autentifikatsiyasiz)
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. TENDER TAFSILOTI — get_proc javobining "landing" qatlami
--    Falsafamizga sodiq qolamiz: xom javob to'liq saqlanadi (raw_json), ustiga
--    eng kerakli maydonlar ajratib olinadi. Sxema o'zgarsa ma'lumot yo'qolmaydi.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tender_detail (
    tender_id        BIGINT PRIMARY KEY REFERENCES tender(id) ON DELETE CASCADE,

    -- Ajratib olingan foydali maydonlar (dashboard/AI uchun)
    anno             TEXT,        -- tender izohi/tavsifi
    method_marks     TEXT,        -- 'Метод оценки - "По балльной системе"'
    company_details  TEXT,        -- buyurtmachining bank rekvizitlari
    director         TEXT,        -- mas'ul/rahbar
    close_time       TEXT,        -- '14:00 (Asia/Tashkent)'
    proc_lang        TEXT,        -- tender tili ('узбекский')
    offer_period     TEXT,        -- takliflar berish muddati

    doc_count        INTEGER NOT NULL DEFAULT 0,  -- topilgan fayllar soni (tez filtr uchun)

    raw_json         JSONB NOT NULL,              -- get_proc to'liq javobi
    fetched_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_detail_doccount ON tender_detail(doc_count);


-- ---------------------------------------------------------------------------
-- 2. HUJJATLAR — tenderga biriktirilgan fayllar
--    Bu mahsulotning eng qimmatli qismi: kompaniya texnik topshiriqni
--    o'qimasdan ariza bera olmaydi.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tender_document (
    tender_id       BIGINT NOT NULL REFERENCES tender(id) ON DELETE CASCADE,
    file_id         UUID   NOT NULL,             -- yuklab olish shu ID orqali

    name            TEXT,                        -- 'ТЗ Листогибочный пресс.pdf'
    size_bytes      BIGINT,                      -- 4945768
    content_type    TEXT,                        -- 'application/pdf'
    file_type       TEXT,                        -- 'pdf'

    -- Fayl qaysi maydondan kelgani — UI'da guruhlash uchun
    -- ('anno_file' | 'proform_file' | 'proc_custom2' | ...)
    field_key       TEXT,
    field_path      TEXT,                        -- to'liq yo'l (debug): 'fields.proc_custom2.value[0]'

    source_platform TEXT NOT NULL DEFAULT 'xt-xarid',
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Bitta fayl bir tenderda bir marta (turli maydonda takrorlansa ham)
    PRIMARY KEY (tender_id, file_id)
);

CREATE INDEX IF NOT EXISTS idx_doc_tender ON tender_document(tender_id);
CREATE INDEX IF NOT EXISTS idx_doc_type   ON tender_document(file_type);
