-- =====================================================================
-- MANBA HAVOLASI — har yozuv ommaviy manbaga QAYTARIB bog'lansin
-- =====================================================================
--
-- O'LCHANGAN BO'SHLIQ (2026-08-31):
--
--   Kelib chiqish metama'lumoti TO'LIQ: `tender.source_platform`,
--   `source_id`, `source_ref`, `fetched_at`, `first_seen_at` —
--   3 605 qatorda 0 ta NULL. `tender_document.file_ref`,
--   `source_platform`, `fetched_at` — 10 634 qatorda 0 ta NULL.
--
--   LEKIN ommaviy sahifa HAVOLASINI qurish qoidasi FAQAT frontendda
--   edi (`frontend/src/format.ts:SOURCE_URLS`). Ya'ni bazadan yoki
--   API dan so'ralganda "bu yozuv qayerdan olingan" degan savolga
--   MASHINA O'QIY OLADIGAN javob yo'q edi — auditor naqshni
--   frontend kodidan qo'lda ko'chirishi kerak bo'lardi.
--
-- BU PATCH shu naqshni BAZAGA ko'chiradi: SQL da ham, API da ham
-- bir xil javob chiqsin va u BITTA joyda saqlansin.
--
-- MUHIM: manbadagi ASL `source_id` ishlatiladi. Bizning `tender.id`
-- global (source_id + platforma ofseti) va u manba saytida MAVJUD
-- EMAS — o'sha id bilan havola qurish YOLG'ON havola berardi.
--
-- Idempotent.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1) Tenderning ommaviy sahifasi
-- ---------------------------------------------------------------------
-- NOMA'LUM PLATFORMA UCHUN NULL QAYTADI, taxminiy havola EMAS.
-- Yolg'on havola "manbani tekshirdim" degan yolg'on ishonch berardi.
CREATE OR REPLACE FUNCTION manba_url(platforma TEXT, manba_id BIGINT)
    RETURNS TEXT LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN manba_id IS NULL THEN NULL
        WHEN platforma = 'xt-xarid'
            THEN 'https://xt-xarid.uz/procedure/' || manba_id || '/core'
        WHEN platforma = 'uzex'
            THEN 'https://etender.uzex.uz/lot/' || manba_id
        ELSE NULL
    END
$$;

COMMENT ON FUNCTION manba_url(TEXT, BIGINT) IS
    'Tenderning MANBA platformadagi rasmiy sahifasi. Noma''lum '
    'platforma uchun NULL — taxminiy havola qaytarilmaydi.';

-- ---------------------------------------------------------------------
-- 2) Kelib chiqish ko'rinishi — auditor uchun yagona nuqta
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_tender_manba;
CREATE VIEW v_tender_manba AS
SELECT t.id                                   AS ichki_id,
       t.source_platform                      AS platforma,
       t.source_id                            AS manbadagi_id,
       t.source_ref                           AS manba_reyestri,
       manba_url(t.source_platform, t.source_id) AS ommaviy_url,
       t.first_seen_at                        AS birinchi_korilgan,
       t.fetched_at                           AS oxirgi_olingan,
       t.publicated_at                        AS manbada_elon_qilingan,
       t.close_at                             AS yopilish_vaqti,
       t.name                                 AS nomi,
       t.company_name                         AS buyurtmachi
  FROM tender t;

COMMENT ON VIEW v_tender_manba IS
    'Har tenderning ommaviy manbaga qaytish yo''li. Huquqiy '
    'tekshiruv uchun yagona nuqta: `ommaviy_url` NULL bo''lsa — '
    'platforma naqshi noma''lum, taxmin qilinmagan.';

-- HUJJATLAR. `file_ref` — manbadagi kanonik ishora; yuklab olish
-- `/documents/{tender_id}/download?ref=...` orqali PROKSI qilinadi
-- (fayl bizda saqlanmaydi, faqat MATNI ajratiladi).
DROP VIEW IF EXISTS v_hujjat_manba;
CREATE VIEW v_hujjat_manba AS
SELECT d.tender_id,
       d.file_ref,
       d.name                                    AS hujjat_nomi,
       d.file_type,
       d.source_platform                         AS platforma,
       manba_url(d.source_platform, t.source_id) AS tender_ommaviy_url,
       d.discovered_at                           AS birinchi_korilgan,
       d.fetched_at                              AS oxirgi_olingan,
       d.holat                                   AS qayta_ishlash_holati,
       (x.file_ref IS NOT NULL)                  AS matni_ajratilgan,
       length(x.text)                            AS matn_belgilari
  FROM tender_document d
  LEFT JOIN tender t ON t.id = d.tender_id
  LEFT JOIN tender_document_text x
         ON x.file_ref = d.file_ref AND x.tender_id = d.tender_id;

COMMENT ON VIEW v_hujjat_manba IS
    'Har hujjatning manbaga qaytish yo''li va matni ajratilganmi. '
    'FAYLNING O''ZI saqlanmaydi — yuklab olish manbadan proksi '
    'qilinadi.';

-- ---------------------------------------------------------------------
-- 3) Kelib chiqish TO'LIQLIGI — o'lchov, da'vo emas
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_manba_qamrov;
CREATE VIEW v_manba_qamrov AS
SELECT 'tender'::TEXT AS jadval,
       count(*)                                              AS jami,
       count(*) FILTER (WHERE source_platform IS NULL)       AS platformasiz,
       count(*) FILTER (WHERE source_id IS NULL)             AS manba_idsiz,
       count(*) FILTER (WHERE fetched_at IS NULL)            AS vaqtsiz,
       count(*) FILTER (WHERE manba_url(source_platform, source_id) IS NULL)
                                                             AS urlsiz
  FROM tender
UNION ALL
SELECT 'tender_document',
       count(*),
       count(*) FILTER (WHERE source_platform IS NULL),
       count(*) FILTER (WHERE file_ref IS NULL),
       count(*) FILTER (WHERE fetched_at IS NULL),
       count(*) FILTER (WHERE tender_id IS NULL)
  FROM tender_document
UNION ALL
SELECT 'doc_chunk',
       count(*), 0, count(*) FILTER (WHERE file_ref IS NULL),
       count(*) FILTER (WHERE created_at IS NULL),
       count(*) FILTER (WHERE tender_id IS NULL)
  FROM doc_chunk;

COMMENT ON VIEW v_manba_qamrov IS
    'Kelib chiqish metama''lumoti QANCHA yozuvda yetishmaydi. '
    'Nol bo''lmagan ustun — kelib chiqishi yo''q yozuvlar bor.';

COMMIT;
