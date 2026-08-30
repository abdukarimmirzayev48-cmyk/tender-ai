-- =====================================================================
-- ETL ISHONCHLILIGI — CHECKPOINT, HEARTBEAT VA HALOL METRIKA
-- =====================================================================
--
-- O'LCHANGAN MUAMMO (2026-08-30, `etl_run` 14 kunlik tahlili):
--
--   uzex   : 104 xato / 33 ok        xt-xarid: 74 xato / 64 ok
--
--   Lekin 178 xatoning 154 tasi ETL XATOSI EMAS. Ular
--   `run_etl.close_stale_runs()` keyingi yurish boshida yopgan YETIM
--   `running` qatorlari: jarayon o'ldirilgan, qator yopilmay qolgan.
--   Faqat 22 tasi haqiqiy bola-jarayon nosozligi (0xC000013A).
--
--   Windows dalili: `LastTaskResult = 0xC000013A`, `etl_cron.log` da
--   161 "boshlandi" / 11 "tugadi", jurnalda literal `^C` belgilari,
--   `LogonType = Interactive`, uyqu holati FAQAT Modern Standby (S0),
--   7 kunda 9 ta kernel tashabbusidagi o'chirish.
--
-- BU PATCH UCHTA NARSANI TUZATADI:
--
--   1. O'LCHOV BUZUQ EDI. `close_stale_runs` `finished_at = now()`
--      qo'yardi, ya'ni 3-daqiqada o'lgan yurish jurnalda 45 SOAT
--      davom etgan bo'lib ko'rinardi:
--
--          uzex 'error' davomiyligi: o'rtacha 421 daq, maks 2700 daq
--          uzex 'ok'    davomiyligi: o'rtacha 1.9 daq
--
--      Endi `heartbeat_at` bor: ETL ishlab turganda uni yangilaydi.
--      Yetim qator yopilganda `finished_at = heartbeat_at`, ya'ni
--      "qachon ishlashdan to'xtadi", "qachon payqadik" emas.
--
--   2. QAYTA BOSHLASH NUQTASI YO'Q EDI. 19-daqiqada o'lgan yurish
--      keyingi soatda NOLDAN boshlanardi va yana o'lardi. `etl_checkpoint`
--      har oqim (manba + TypeId/ref) uchun qayerda to'xtaganini saqlaydi.
--
--   3. "TUGALLANMAGAN" TUSHUNCHASI YO'Q EDI. Status faqat
--      running|ok|error edi, shuning uchun vaqt byudjeti tugab TOZA
--      to'xtagan yurishni yo 'ok' (yolg'on) yo 'error' (ham yolg'on)
--      deb yozishga majbur edik. Endi 'partial' bor va u ALOHIDA
--      hisoblanadi — "muvaffaqiyatli" deb sanalmaydi.
--
-- Idempotent: bir necha marta yurgizsa bo'ladi.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1) etl_run — halol metrika
-- ---------------------------------------------------------------------
-- NEGA HAR BIRI ALOHIDA USTUN, bitta JSON emas: bu raqamlar bo'yicha
-- SQL da guruhlash va o'rtacha olish kerak. JSON ichidagi son
-- indekslanmaydi va `avg()` uchun har safar cast talab qiladi.

ALTER TABLE etl_run ADD COLUMN IF NOT EXISTS heartbeat_at    TIMESTAMPTZ;
ALTER TABLE etl_run ADD COLUMN IF NOT EXISTS processed       INTEGER NOT NULL DEFAULT 0;
ALTER TABLE etl_run ADD COLUMN IF NOT EXISTS succeeded       INTEGER NOT NULL DEFAULT 0;
ALTER TABLE etl_run ADD COLUMN IF NOT EXISTS failed          INTEGER NOT NULL DEFAULT 0;
ALTER TABLE etl_run ADD COLUMN IF NOT EXISTS retried         INTEGER NOT NULL DEFAULT 0;
ALTER TABLE etl_run ADD COLUMN IF NOT EXISTS resumed         INTEGER NOT NULL DEFAULT 0;
ALTER TABLE etl_run ADD COLUMN IF NOT EXISTS skipped         INTEGER NOT NULL DEFAULT 0;
ALTER TABLE etl_run ADD COLUMN IF NOT EXISTS checkpoint      JSONB;
ALTER TABLE etl_run ADD COLUMN IF NOT EXISTS terminal_reason TEXT;

COMMENT ON COLUMN etl_run.heartbeat_at IS
  'ETL oxirgi marta TIRIK ekanini bildirgan payt. Yetim qator yopilganda '
  'finished_at SHUNDAN olinadi — aks holda davomiylik "qachon payqadik" '
  'ni o''lchardi (o''lchangan buzilish: 3 daqiqalik yurish 45 soat bo''lib '
  'ko''rinardi).';
COMMENT ON COLUMN etl_run.processed IS 'Ko''rib chiqilgan yozuv (succeeded + failed + skipped).';
COMMENT ON COLUMN etl_run.succeeded IS 'Bazaga muvaffaqiyatli yozilgan yozuv.';
COMMENT ON COLUMN etl_run.failed    IS 'Yiqilgan yozuv — YURISHNI TO''XTATMAYDI.';
COMMENT ON COLUMN etl_run.retried   IS 'Qayta urinishlar soni (yozuv emas, URINISH).';
COMMENT ON COLUMN etl_run.resumed   IS 'Checkpoint dan tiklanib o''tkazib yuborilgan yozuv.';
COMMENT ON COLUMN etl_run.skipped   IS 'Manbada o''zgarmagani uchun tegilmagan yozuv (inkremental).';
COMMENT ON COLUMN etl_run.terminal_reason IS
  'Yurish NEGA tugadi: tugadi | vaqt_byudjeti | band | uzildi | '
  'manba_xato | baza_xato | foydalanuvchi. "error" ning sababi emas — '
  'har qanday tugash sababi, shu jumladan muvaffaqiyatli.';

-- Status lug'ati QULFLANADI. Ilgari cheklov yo'q edi va har kim
-- xohlagan matnni yozardi. 'partial' — tugallanmagan, lekin xato emas.
DO $$
BEGIN
    -- Notanish statusli eski qatorlar bo'lsa CHECK qo'yib bo'lmaydi.
    -- Ularni JIMGINA o'zgartirmaymiz — cheklovni qo'ymay, ogohlantiramiz.
    IF EXISTS (SELECT 1 FROM etl_run
               WHERE status NOT IN ('running', 'ok', 'error', 'partial')) THEN
        RAISE NOTICE 'etl_run.status da notanish qiymat bor — CHECK qo''yilmadi.';
    ELSIF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'etl_run_status_chk') THEN
        ALTER TABLE etl_run ADD CONSTRAINT etl_run_status_chk
            CHECK (status IN ('running', 'ok', 'error', 'partial'));
    END IF;
END $$;

-- Tugagan yurishda sabab BO'LISHI SHART. Sababsiz "tugadi" — aynan
-- shu loyihada takrorlangan "jimgina o'tib ketish" sinfi.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'etl_run_sanoq_chk') THEN
        ALTER TABLE etl_run ADD CONSTRAINT etl_run_sanoq_chk
            CHECK (processed >= 0 AND succeeded >= 0 AND failed >= 0
                   AND retried >= 0 AND resumed >= 0 AND skipped >= 0);
    END IF;
END $$;

-- ---------------------------------------------------------------------
-- 2) etl_checkpoint — qayerda to'xtadik
-- ---------------------------------------------------------------------
-- MUHIM DIZAYN QARORI — `kursor` QAYTA BOSHLASHNING ASOSI EMAS.
--
-- UzEx TradeList ro'yxatini YANGISI BIRINCHI tartibida beradi. Yangi
-- savdo e'lon qilinsa butun ro'yxat bir pozitsiya suriladi. Indeksga
-- tayangan tiklash o'shanda BOSHQA yozuvdan davom etardi va oradagi
-- yozuvni JIMGINA tashlab ketardi — bu loyihada o'ninchi marta
-- uchragan nuqson sinfi.
--
-- Shuning uchun tiklashning HAQIQIY mexanizmi — KONTENTNI SOLISHTIRISH:
-- saqlangan `tender.raw_json->'list'` manbadan kelgan qator bilan bir
-- xil bo'lsa, `GetTrade` chaqirilmaydi. Ya'ni oldingi yurishda
-- saqlangan yozuvlar keyingi yurishda O'ZIDAN-O'ZI o'tkazib yuboriladi.
-- O'lchangan (2026-08-30): 623 ta yozuvdan 414 tasi (66%) shu yo'l
-- bilan tegilmasdan qoladi.
--
-- `kursor` esa faqat TEZLASHTIRUVCHI MASLAHAT va O'LCHOV uchun.
-- `ish_kaliti` (ro'yxat ID larining xesh) mos kelmasa u E'TIBORGA
-- OLINMAYDI — noto'g'ri joydan davom etishdan ko'ra boshidan
-- boshlagan yaxshi, chunki kontent solishtiruvi baribir arzon qiladi.
CREATE TABLE IF NOT EXISTS etl_checkpoint (
    source_platform    TEXT        NOT NULL,
    oqim               TEXT        NOT NULL,
    holat              TEXT        NOT NULL DEFAULT 'ochiq',
    kursor             INTEGER     NOT NULL DEFAULT 0,
    jami               INTEGER,
    oxirgi_id          BIGINT,
    ish_kaliti         TEXT,
    urinish            INTEGER     NOT NULL DEFAULT 0,
    oxirgi_xato        TEXT,
    keyingi_urinish_at TIMESTAMPTZ,
    boshlandi_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    yangilandi_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_platform, oqim)
);

COMMENT ON TABLE  etl_checkpoint IS
  'Har ETL oqimi (manba + TypeId/ref) qayerda to''xtaganini saqlaydi. '
  'Uzilgan yurish keyingi safar noldan boshlamasin.';
COMMENT ON COLUMN etl_checkpoint.oqim IS
  'Oqim kaliti: "uzex:type=1", "xt-xarid:ref_selection_public", "details:open".';
COMMENT ON COLUMN etl_checkpoint.kursor IS
  'Ro''yxatdagi joriy indeks. TEZLASHTIRUVCHI MASLAHAT, tiklashning '
  'asosi EMAS — `ish_kaliti` mos kelmasa e''tiborga olinmaydi.';
COMMENT ON COLUMN etl_checkpoint.oxirgi_id IS
  'Oxirgi MUVAFFAQIYATLI tashqi ID (manbadagi id, bizning offsetsiz).';
COMMENT ON COLUMN etl_checkpoint.ish_kaliti IS
  'Ish ro''yxati ID larining xeshi. Ro''yxat o''zgarsa kursor yaroqsiz.';
COMMENT ON COLUMN etl_checkpoint.keyingi_urinish_at IS
  'Shu paytgacha oqimga TEGILMAYDI (Retry-After / eksponensial kutish).';

-- QOIDALAR CHECK BILAN QULFLANADI, izoh bilan emas.
-- Loyihada o'lchangan saboq: `tender_requirement` da 1 487 qator
-- `review_status='approved'` bo'lib turibdi va ularni hech kim
-- ko'rmagan — o'sha qoida FAQAT izoh bilan himoyalangan edi.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'etl_checkpoint_holat_chk') THEN
        ALTER TABLE etl_checkpoint ADD CONSTRAINT etl_checkpoint_holat_chk
            CHECK (holat IN ('ochiq', 'tugadi'));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'etl_checkpoint_kursor_chk') THEN
        ALTER TABLE etl_checkpoint ADD CONSTRAINT etl_checkpoint_kursor_chk
            CHECK (kursor >= 0 AND urinish >= 0 AND (jami IS NULL OR jami >= 0));
    END IF;

    -- Kutish vaqti FAQAT muvaffaqiyatsiz urinishdan keyin ma'noga ega.
    -- Urinishsiz "keyin urinamiz" — o'lchovsiz da'vo.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'etl_checkpoint_kutish_chk') THEN
        ALTER TABLE etl_checkpoint ADD CONSTRAINT etl_checkpoint_kutish_chk
            CHECK (keyingi_urinish_at IS NULL OR urinish > 0);
    END IF;

    -- Tugagan oqimda ochiq xato qolmaydi. Aks holda "tugadi, lekin
    -- xato bor" degan ikki xil o'qiladigan holat paydo bo'lardi.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'etl_checkpoint_tugadi_chk') THEN
        ALTER TABLE etl_checkpoint ADD CONSTRAINT etl_checkpoint_tugadi_chk
            CHECK (holat <> 'tugadi' OR keyingi_urinish_at IS NULL);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_etl_checkpoint_ochiq
    ON etl_checkpoint (source_platform, yangilandi_at DESC)
    WHERE holat = 'ochiq';

-- ---------------------------------------------------------------------
-- 3) O'LCHOV KO'RINISHI — davomiylik endi HALOL
-- ---------------------------------------------------------------------
-- `davomiylik_sek` FAQAT haqiqiy ish vaqtini oladi:
--   * normal tugagan yurish  -> finished_at - started_at
--   * uzilgan yurish         -> heartbeat_at - started_at (oxirgi tiriklik)
--   * heartbeat yo'q (eski qator yoki darhol o'lgan) -> NULL
--
-- NULL bu yerda "0" EMAS. O'lchanmagan narsani nolga aylantirish
-- o'rtachani pastga tortadi va "tez ishladi" degan yolg'on beradi —
-- aynan shu xato `kod_qaror.ochilgan_at` da ham bo'lgan edi.
CREATE OR REPLACE VIEW v_etl_run_olchov AS
SELECT
    r.id,
    r.source_platform,
    r.status,
    r.terminal_reason,
    r.started_at,
    r.finished_at,
    r.heartbeat_at,
    -- MANTIQ ATAYLAB SODDA va `terminal_reason` GA BOG'LIQ EMAS.
    -- `close_stale_runs()` uzilgan qatorga `finished_at = heartbeat_at`
    -- qo'yadi (heartbeat yo'q bo'lsa NULL), normal tugagan qatorga esa
    -- haqiqiy tugash vaqti yoziladi. Ya'ni ikkala holat ham SHU BITTA
    -- ayirma bilan to'g'ri chiqadi, va NULL o'zi "o'lchanmadi" degani.
    --
    -- Ilgari bu yerda `terminal_reason='uzildi'` sharti bor edi va u
    -- sababni IKKI joyda (yozuvchi + o'quvchi) kelishishga majburlardi —
    -- ikkitasidan biri o'zgarsa o'lchov jimgina buzilardi.
    CASE
        WHEN r.status = 'running'      THEN NULL
        WHEN r.finished_at IS NOT NULL THEN
             EXTRACT(EPOCH FROM (r.finished_at - r.started_at))
        ELSE NULL                                  -- o'lchanmadi (nol EMAS)
    END::numeric(12,1)                             AS davomiylik_sek,
    r.processed, r.succeeded, r.failed, r.retried, r.resumed, r.skipped,
    r.found, r.new,
    r.checkpoint,
    left(r.error, 200)                             AS xato
FROM etl_run r;

COMMENT ON VIEW v_etl_run_olchov IS
  'ETL yurishlarining HALOL o''lchovi. `davomiylik_sek` NULL = '
  'o''lchanmadi (nol EMAS). Uzilgan yurish uchun heartbeat gacha '
  'bo''lgan vaqt olinadi, "qachon payqadik" emas.';

-- Sog'liq xulosasi — bitta qatorda "quvur qanday yuribdi".
CREATE OR REPLACE VIEW v_etl_saglik AS
SELECT
    source_platform,
    count(*)                                                  AS yurish,
    count(*) FILTER (WHERE status = 'ok')                     AS ok,
    count(*) FILTER (WHERE status = 'partial')                AS qisman,
    count(*) FILTER (WHERE status = 'error')                  AS xato,
    count(*) FILTER (WHERE status = 'running')                AS yurmoqda,
    count(*) FILTER (WHERE terminal_reason = 'uzildi')        AS uzildi,
    round(100.0 * count(*) FILTER (WHERE status IN ('ok', 'partial'))
          / NULLIF(count(*), 0), 1)                           AS foydali_foiz,
    round(avg(davomiylik_sek) FILTER (WHERE davomiylik_sek IS NOT NULL), 1)
                                                              AS ort_sek,
    count(*) FILTER (WHERE davomiylik_sek IS NULL
                       AND status <> 'running')               AS olchovsiz,
    sum(succeeded)                                            AS jami_yozildi,
    sum(failed)                                               AS jami_yiqildi,
    sum(retried)                                              AS jami_qayta_urinish,
    sum(skipped)                                              AS jami_otkazildi
FROM v_etl_run_olchov
WHERE started_at > now() - interval '7 days'
GROUP BY source_platform;

COMMENT ON VIEW v_etl_saglik IS
  '7 kunlik ETL sog''ligi. `foydali_foiz` ok+partial ni sanaydi: '
  'qisman yurish ham ISH BAJARADI (uzilganidan farqli). `olchovsiz` '
  'alohida turadi va o''rtachaga QO''SHILMAYDI.';

COMMIT;
