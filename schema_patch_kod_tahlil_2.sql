-- =====================================================================
-- KATALOG KODLASH — KUCHSIZ DALIL BANDI
-- =====================================================================
--
-- O'LCHANGAN SABAB (2026-08-31). Avtomatik takliflar INSON bergan
-- keng kod bilan solishtirildi — 383 ta haqiqiy juftlik:
--
--     umumiy moslik (5 belgi)     382/383   99.7%
--     division moslik (26.xx)     383/383  100.0%
--
--   Ya'ni klassifikator aniq. LEKIN band bo'yicha ajratilganda:
--
--     ishonch 1.000 (yagona oila)   170 ta,  o'rtacha dalil  4.6
--     ishonch 0.80-0.89             297 ta,  o'rtacha dalil 18.0
--     ishonch 0.75-0.79              34 ta,  o'rtacha dalil  3.0
--                                    ^^^ moslik 3/4 (75%)
--
--   Yagona nomuvofiqlik shu bandda edi: bitta umumiy token (`shkaf`),
--   ishonch AYNAN chegarada (0.750), dalil 3/4. Inson 26.30 degan,
--   avtomatik 26.20.40 taklif qilgan.
--
-- QAROR: chegara O'ZGARMAYDI, band NAVBATGA yo'naltiriladi.
--
--   `MIN_SHARE` ni ko'tarish 297 ta KUCHLI taklifni (o'rtacha dalil
--   18.0) ham to'sardi — bu 1 ta xatoni tuzatib 297 tasini
--   yo'qotardi. Bandni ajratish aniqroq javob va u recall ni
--   yo'qotmaydi: taklif navbatda ko'rinadi, faqat AVTOMATIK
--   qo'llanmaydi.
--
-- HALOL CHEKLOV: 3/4 — namuna KICHIK (n=4). U yolg'iz o'zi yetarli
-- dalil emas. Lekin mexanizm izchil (kam dalil + chegara cheti),
-- precision recall dan muhimroq, va bandning narxi kichik (501 dan
-- 34 ta, 6.8%).
--
-- Idempotent.
-- =====================================================================

BEGIN;

ALTER TABLE catalog_kod_tahlil
    ADD COLUMN IF NOT EXISTS kuchsiz_dalil BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN catalog_kod_tahlil.kuchsiz_dalil IS
    'Kod topildi, LEKIN ishonch chegara chetida va dalil kam — '
    'avtomatik QO''LLANMAYDI, navbatga boradi. Chegara o''zgarmaydi.';

-- Navbat bandni ko'rsatsin va u boshqa ish talab qilishini aytsin.
DROP VIEW IF EXISTS v_catalog_kod_navbat;
CREATE VIEW v_catalog_kod_navbat AS
SELECT t.company_id,
       t.product_id,
       p.name                AS mahsulot,
       p.category_code,
       t.sabab,
       t.kuchsiz_dalil,
       t.taklif_code,
       t.ishonch,
       t.dalil,
       t.jami,
       t.tokenlar,
       t.kodlar,
       t.misollar,
       t.ochiq_tender,
       t.tarixiy_lot,
       -- Ochiq tender KUCHLIROQ signal (bugungi imkoniyat);
       -- tarixiy lot — barqarorlik belgisi.
       (t.ochiq_tender * 10 + t.tarixiy_lot) AS ustuvorlik,
       CASE
           WHEN t.sabab = 'kod' AND t.kuchsiz_dalil
               THEN 'kod bor, lekin DALIL KAM va ishonch chegarada — odam tasdiqlaydi'
           WHEN t.sabab = 'kod'
               THEN 'avtomatik kod tayyor — qo''llash mumkin'
           WHEN t.sabab = 'noaniq'
               THEN 'bir nechta kod oilasi teng — odam tanlaydi'
           WHEN t.sabab = 'dalil_kam'
               THEN 'dalil kam (korpus o''ssa hal bo''lishi mumkin)'
           WHEN t.sabab = 'sozlar_mos_emas'
               THEN 'nom korpusdagi atama bilan mos emas'
           WHEN t.sabab = 'nomzodsiz'
               THEN 'korpusda umuman uchramaydi'
           WHEN t.sabab = 'tokensiz'
               THEN 'nomdan ma''noli so''z chiqmadi (model/SKU)'
       END AS nima_kerak
  FROM catalog_kod_tahlil t
  JOIN catalog_product p ON p.id = t.product_id AND p.company_id = t.company_id
 WHERE NOT EXISTS (SELECT 1 FROM v_catalog_code_active v
                    WHERE v.product_id = t.product_id
                      AND v.company_id = t.company_id
                      AND length(v.code) >= 8);

COMMENT ON VIEW v_catalog_kod_navbat IS
    'Aniq kodi YO''Q mahsulotlar, biznes qiymati bo''yicha. '
    '`nima_kerak` — sabab har xil ishni talab qiladi.';

-- KOD TAKLIFI SIFATI — avtomatik qo'llanadigan va navbatga
-- boradiganlar ALOHIDA sanaladi. Ularni qo'shish "hammasi
-- avtomatik" degan yolg'on berardi.
DROP VIEW IF EXISTS v_catalog_kod_sifat;
CREATE VIEW v_catalog_kod_sifat AS
SELECT company_id,
       count(*) FILTER (WHERE sabab = 'kod')                       AS taklif,
       count(*) FILTER (WHERE sabab = 'kod' AND NOT kuchsiz_dalil) AS avtomatik,
       count(*) FILTER (WHERE sabab = 'kod' AND kuchsiz_dalil)     AS navbatga,
       count(*) FILTER (WHERE sabab = 'noaniq')                    AS noaniq,
       count(*) FILTER (WHERE sabab = 'dalil_kam')                 AS dalil_kam,
       count(*) FILTER (WHERE sabab IN ('nomzodsiz', 'sozlar_mos_emas',
                                        'tokensiz'))               AS dalilsiz,
       round(avg(ishonch) FILTER (WHERE sabab = 'kod'), 3)         AS ortacha_ishonch
  FROM catalog_kod_tahlil
 GROUP BY company_id;

COMMENT ON VIEW v_catalog_kod_sifat IS
    'Taklif sifati. AVTOMATIK va NAVBATGA alohida — ularni qo''shish '
    '"hammasi avtomatik" degan yolg''on berardi.';

COMMIT;
