-- =====================================================================
-- TOVAR / XIZMAT AJRATISH — matn mosligining soxta musbatlariga qarshi
-- =====================================================================
--
-- O'LCHANGAN MUAMMO (2026-08-31, 784 ochiq tender, haqiqiy katalog).
--
--   Matn mosligining deyarli HAMMASI bitta keng atamadan kelardi:
--
--       matn mosligi (juftlik)                    328
--       shundan KABEL atamali mahsulotdan         328  (100.0%)
--       shundan YALANG'OCH `Кабель` kalit so'zidan 325  (99.1%)
--
--   `Кабель` atamasi 784 ochiq tenderdan 13 tasiga mos keldi.
--   YORLIQ HAQIQIY DALILDAN olindi — tenderda 27.3x (kabel/sim)
--   loti bormi (davlat portali bergan rasmiy tasnif, sintetik emas):
--
--       TP = 9   FP = 4   precision = 69.2%
--
--   TO'RTALA SOXTA MOSLIK HAM XIZMAT edi:
--       42.22  Услуга по прокладке ... кабеля связи   (kabel yotqizish)
--       43.29  Строительно-монтажные работы           (tender NOMIDA)
--       61.10  Услуга по широкополосному доступу      (tender NOMIDA)
--       33.x/71.20  Услуга по ... испытанию изоляции  (sinov xizmati)
--
--   Ya'ni "кабель" so'zi TOVAR emas, XIZMAT tavsifida yoki tender
--   SARLAVHASIDA uchragan.
--
-- QAROR: `Кабель` QORA RO'YXATGA OLINMAYDI. Buning o'rniga matn
-- mosligi DALILI TOVAR LOTIDAN kelishi talab qilinadi.
--
--   - tender NOMI yolg'iz o'zi yetarli EMAS;
--   - XIZMAT loti nomi yetarli EMAS.
--
-- XIZMAT BELGISI MA'LUMOTDAN, TAXMINDAN EMAS. `dim_good_code.name_ru`
-- va lot nomi "Услуга"/"Работы" bilan boshlanadi. Belgining haqiqiy
-- ekani bo'lim kesimida o'lchandi:
--
--       16-32 bo'limlar (ishlab chiqarish)   xizmat  0-2%
--       33 (ta'mirlash)                      xizmat   90%
--       41, 49, 68                           xizmat  100%
--       66, 71 (moliya, texnik sinov)        xizmat  89-98%
--
-- IKKALA SIGNAL HAM TEKSHIRILADI. Ular 2.7% holatda ZID keladi
-- (lot nomi "Услуга" deydi, lug'atdagi kod nomi boshqacha). Precision
-- birinchi bo'lgani uchun BIRI xizmat desa — tovar dalili emas.
--
-- LUG'ATDA KOD YO'Q BO'LSA — NOMA'LUM, va u tovar deb HISOBLANMAYDI.
-- Ilgari `COALESCE(name_ru,'')` uni jimgina tovarga aylantirardi va
-- aynan shu 4-chi soxta moslikni o'tkazib yuborgandi.
--
-- SIMULYATSIYA (yorliqlangan namuna, kod yozilmasdan o'lchandi):
--
--       ESKI    mos 13   TP 9   FP 4   precision  69.2%   recall 56.2%
--       YANGI   mos  9   TP 9   FP 0   precision 100.0%   recall 56.2%
--
--   Recall O'ZGARMADI — birorta haqiqiy moslik yo'qolmadi.
--
-- KOD MOSLIGI USTUNLIGI SAQLANADI: `matching.product_matches()` kodni
-- BIRINCHI ko'radi va kodi bor mahsulot matn yo'liga UMUMAN tushmaydi.
-- Bu patch faqat MATN yo'liga tegadi.
--
-- Idempotent.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1) Xizmat belgisi — YAGONA MANBA
-- ---------------------------------------------------------------------
-- Funksiya sifatida: SQL ham, ko'rinish ham, sinov ham SHU YERDAN
-- oladi. Ikki joyda yozilsa ular vaqt o'tib ajralib ketardi.
CREATE OR REPLACE FUNCTION xizmat_nomimi(nom TEXT) RETURNS BOOLEAN
    LANGUAGE sql IMMUTABLE AS $$
    SELECT COALESCE(nom, '') ILIKE 'Услуга%'
        OR COALESCE(nom, '') ILIKE 'Работы%'
        OR COALESCE(nom, '') ILIKE 'Xizmat%'
        OR COALESCE(nom, '') ILIKE 'Ish %'
$$;

COMMENT ON FUNCTION xizmat_nomimi(TEXT) IS
    'Nom XIZMATni bildiradimi. Rasmiy tasniflagich nomlari '
    '"Услуга"/"Работы" bilan boshlanadi — bu o''lchangan naqsh, '
    'taxmin emas.';

-- LOT tovar dalili bo'la oladimi.
--
-- UCHTA shart va ular ATAYLAB qat'iy:
--   1. kod lug'atda BOR (yo'q bo'lsa NOMA'LUM — tovar deb
--      hisoblanmaydi);
--   2. lug'atdagi nom xizmat EMAS;
--   3. lotning O'Z nomi xizmat EMAS.
CREATE OR REPLACE FUNCTION lot_tovarmi(lot_kod TEXT, lot_nom TEXT)
    RETURNS BOOLEAN LANGUAGE sql STABLE AS $$
    SELECT EXISTS (
        SELECT 1 FROM dim_good_code d
         WHERE d.code = left(lot_kod, 8)
           AND NOT xizmat_nomimi(d.name_ru)
    ) AND NOT xizmat_nomimi(lot_nom)
$$;

COMMENT ON FUNCTION lot_tovarmi(TEXT, TEXT) IS
    'Lot TOVAR dalili bo''la oladimi. Lug''atda kod yo''q bo''lsa '
    'NOMA''LUM -> false: noma''lum jimgina tovarga aylanmaydi.';

-- ---------------------------------------------------------------------
-- 2) O'lchov ko'rinishi
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_lot_tovar_xizmat;
CREATE VIEW v_lot_tovar_xizmat AS
SELECT left(g.good_code, 2)                                   AS bolim,
       count(*)                                               AS lot,
       count(*) FILTER (WHERE lot_tovarmi(g.good_code, g.name)) AS tovar,
       count(*) FILTER (WHERE NOT lot_tovarmi(g.good_code, g.name)) AS xizmat,
       count(*) FILTER (WHERE NOT EXISTS (
           SELECT 1 FROM dim_good_code d WHERE d.code = left(g.good_code, 8)
       ))                                                     AS lugatsiz
  FROM tender_good g
 WHERE g.good_code IS NOT NULL
 GROUP BY 1;

COMMENT ON VIEW v_lot_tovar_xizmat IS
    'Bo''lim kesimida tovar/xizmat taqsimoti. `lugatsiz` — kodi '
    'lug''atda yo''q lotlar; ular NOMA''LUM va tovar deb sanalmaydi.';

-- Indeks: `tovar_blob` har moslik so'rovida hisoblanadi.
CREATE INDEX IF NOT EXISTS tender_good_tender_kod_idx
    ON tender_good (tender_id) INCLUDE (good_code);

COMMIT;
