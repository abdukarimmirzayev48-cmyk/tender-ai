-- =============================================================================
-- Sxema patch — KO'P PLATFORMALI qo'llab-quvvatlash (2-manba: etender.uzex.uz)
-- Ishga tushirish:
--   psql "dbname=xtxarid user=a1234 host=localhost" -f schema_patch_multiplatform.sql
--
-- MUAMMO: ikkala platforma ham butun son ID ishlatadi va ular KESISHADI.
--   xt-xarid: 108 ... 8 062 765   (bizda 400k-600k oralig'ida 13 ta yozuv bor)
--   uzex:     496 165 ... 503 308
--   Ya'ni to'qnashuv vaqt masalasi.
--
-- YECHIM: deterministik ID ofseti.
--   tender.source_id = platformaning o'z ID'si (manba havolasi uchun kerak)
--   tender.id        = global ID = source_id + PLATFORM_OFFSET
--                      xt-xarid -> 0 (ID'lar o'zgarmaydi!)
--                      uzex     -> 20 000 000 000
--
-- NEGA kompozit PK (source_platform, id) EMAS:
--   U 5 ta bola jadval FK'sini qayta qurishni, barcha so'rov va ETL'larni
--   o'zgartirishni talab qilardi. Ofset yondashuvida bolalar tegilmaydi,
--   mavjud ma'lumot o'zgarmaydi va ON CONFLICT (id) idempotent UPSERT
--   ishlashda davom etadi (sekvens bo'lganda har yozuvdan oldin qidiruv
--   kerak bo'lar edi — ETL ancha murakkablashardi).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. TENDER — manbadagi asl ID
-- ---------------------------------------------------------------------------
ALTER TABLE tender ADD COLUMN IF NOT EXISTS source_id BIGINT;

-- Mavjud yozuvlar xt-xarid'dan (ofset 0) — asl ID = global ID
UPDATE tender SET source_id = id WHERE source_id IS NULL;

ALTER TABLE tender ALTER COLUMN source_id SET NOT NULL;

-- Bir platformada bir manba-ID faqat bir marta
CREATE UNIQUE INDEX IF NOT EXISTS uq_tender_source
    ON tender(source_platform, source_id);


-- ---------------------------------------------------------------------------
-- 2. HUJJATLAR — UzEx fayllari UUID emas, YO'L (path) bilan identifikatsiyalanadi
--    xt-xarid: file_id (uuid) -> https://api.xt-xarid.uz/file/<uuid>       (GET)
--    uzex:     file_path      -> POST /api/common/DownloadFile?path=<path> (POST!)
--    Shuning uchun umumiy matnli kalit (file_ref) kiritamiz.
-- ---------------------------------------------------------------------------
ALTER TABLE tender_document ADD COLUMN IF NOT EXISTS file_path TEXT;
ALTER TABLE tender_document ADD COLUMN IF NOT EXISTS file_ref  TEXT;

-- Mavjud (xt-xarid) yozuvlar uchun kalit = uuid matni
UPDATE tender_document SET file_ref = file_id::text WHERE file_ref IS NULL;

-- TARTIB MUHIM: avval PK olib tashlanadi, keyingina file_id NOT NULL'dan
-- bo'shatiladi (PK tarkibidagi ustunni NULL qilib bo'lmaydi).
ALTER TABLE tender_document DROP CONSTRAINT IF EXISTS tender_document_pkey;

-- UzEx'da uuid yo'q — file_id endi majburiy emas
ALTER TABLE tender_document ALTER COLUMN file_id DROP NOT NULL;

ALTER TABLE tender_document ALTER COLUMN file_ref SET NOT NULL;
ALTER TABLE tender_document ADD PRIMARY KEY (tender_id, file_ref);


-- ---------------------------------------------------------------------------
-- 3. HUDUDLAR — UzEx o'z kod fazasidan foydalanadi (region id=2, district id=2423)
--    Bizning dim_area xt-xarid nuqtali yo'llarini saqlaydi ('33.2137.2138').
--    Kesishmasligi uchun UzEx hududlarini prefiks bilan yozamiz:
--        'uzex:2'         (viloyat)
--        'uzex:2.2423'    (tuman)
--    Shunda backend'dagi IERARXIK PREFIKS filtri o'zgarishsiz ishlayveradi:
--        area_path = :region OR area_path LIKE :region || '.%'
--    ('uzex:2' -> 'uzex:2.2423' ni tutadi, lekin 'uzex:21.x' ni TUTMAYDI)
--    Sxema o'zgarishi shart emas — area_id allaqachon TEXT.
-- ---------------------------------------------------------------------------
-- (o'zgarish yo'q — izoh sifatida qoldirildi)
