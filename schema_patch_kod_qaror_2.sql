-- =====================================================================
-- KOD QARORI — O'LCHOVNI TUZATISH
-- =====================================================================
--
-- Birinchi patch uch raqamni yozib olardi, lekin ikkitasi JIMGINA
-- noto'g'ri chiqardi. So'roqda o'lchandi (2026-08-30):
--
--   1. VAQT. `ochilgan_at` NOT NULL DEFAULT now() edi. `qaror_yoz()`
--      ochiq qator topmasa YANGI yakunlangan qator qo'yadi va u holda
--      `ochilgan_at = qaror_at = now()`, ya'ni O'TGAN VAQT = 0.
--      "O'lchanmadi" va "0 soniya ketdi" BIR XIL ko'rinardi va
--      `ortacha_sek` nolga tortilardi. O'lchangan: uchta sinov
--      qarordan keyin `ortacha_sek = 0`.
--
--      Endi `ochilgan_at` NULL bo'la oladi va u AYNAN "o'lchanmadi"
--      degani. Ko'rinish bunday qatorlarni o'rtachaga QO'SHMAYDI va
--      ularni alohida sanaydi (`olchovsiz`). O'lchovsiz da'vo
--      qilinmaydi — nol deb ham hisoblanmaydi.
--
--   2. QAROR SONI. `qaror_soni` QATORLARNI sanaydi. Bir atamani uch
--      marta "o'tkazish" qilish 3 ta qator qo'yadi (o'lchandi) va
--      "40 qaror" maqsadiga soxta yaqinlashtiradi. `UNIQUE(kalit)`
--      ATAYLAB yo'q (bir atamaga ikki kod — o'lchanadigan holat),
--      shuning uchun qator soni saqlanadi, lekin yoniga AJRATILGAN
--      ATAMA soni qo'yiladi. Ikkisi yonma-yon tursin: farq katta
--      bo'lsa takror bosilgani KO'RINADI.
--
-- Qo'llash:
--   psql "$XT_DB_DSN" -f schema_patch_kod_qaror_2.sql
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. "O'LCHANMADI" ni ifodalash mumkin bo'lsin
-- ---------------------------------------------------------------------
-- DEFAULT ham olib tashlanadi: aks holda `qaror_yoz()` ning zaxira
-- INSERT i jimgina `now()` qo'yib, yana 0 soniya yozardi.
ALTER TABLE kod_qaror ALTER COLUMN ochilgan_at DROP DEFAULT;
ALTER TABLE kod_qaror ALTER COLUMN ochilgan_at DROP NOT NULL;

-- OCHIQ qatorda soat MAJBURIY ishga tushgan bo'lsin. Aks holda
-- `qaror_ochish()` ni chetlab o'tgan kod ochiq qator yaratardi va
-- keyingi qaror uchun vaqt yana o'lchanmasdi — bu safar jimgina.
ALTER TABLE kod_qaror DROP CONSTRAINT IF EXISTS kod_qaror_ochiq_soat;
ALTER TABLE kod_qaror ADD CONSTRAINT kod_qaror_ochiq_soat
    CHECK (qaror IS NOT NULL OR ochilgan_at IS NOT NULL);

-- Qaror vaqti ochilishdan OLDIN bo'lmasin — poyga yoki soat siljishi
-- manfiy davomiylik bermasin (u o'rtachani jimgina pasaytirardi).
ALTER TABLE kod_qaror DROP CONSTRAINT IF EXISTS kod_qaror_vaqt_tartibi;
ALTER TABLE kod_qaror ADD CONSTRAINT kod_qaror_vaqt_tartibi
    CHECK (ochilgan_at IS NULL OR qaror_at IS NULL OR qaror_at >= ochilgan_at);

COMMENT ON COLUMN kod_qaror.ochilgan_at IS
    'Qator ko''rib chiqishga OCHILGAN vaqt. NULL = O''LCHANMADI '
    '(qaror ochilishsiz yozilgan). NULL ni 0 soniya deb hisoblash '
    'MUMKIN EMAS — `v_kod_qaror_olchov` uni o''rtachaga qo''shmaydi.';

-- ---------------------------------------------------------------------
-- 2. KO'RINISH — o'lchangan va o'lchanmagan AJRATILADI
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_kod_qaror_olchov;

CREATE VIEW v_kod_qaror_olchov AS
SELECT company_id,
       count(*) FILTER (WHERE qaror IS NOT NULL)              AS qaror_soni,
       -- AJRATILGAN ATAMA soni. `qaror_soni` dan FARQ QILADI: bir
       -- atama takror bosilsa qator ko'payadi, atama esa ko'paymaydi.
       count(DISTINCT kalit) FILTER (WHERE qaror IS NOT NULL)  AS atama_soni,
       count(*) FILTER (WHERE qaror = 'kod')                  AS kod_berildi,
       count(*) FILTER (WHERE qaror = 'talabsiz')             AS talabsiz,
       count(*) FILTER (WHERE qaror = 'otkazildi')            AS otkazildi,
       -- 1. VAQT — FAQAT o'lchangan qatorlar bo'yicha.
       round(avg(extract(epoch FROM (qaror_at - ochilgan_at)))
             FILTER (WHERE qaror IS NOT NULL
                       AND ochilgan_at IS NOT NULL))          AS ortacha_sek,
       count(*) FILTER (WHERE qaror IS NOT NULL
                          AND ochilgan_at IS NOT NULL)        AS olchangan,
       -- O'LCHANMAGANLAR JIMGINA YO'QOLMAYDI. Bu raqam katta bo'lsa
       -- `ortacha_sek` ozchilikni ifodalaydi va shundayligi ko'rinadi.
       count(*) FILTER (WHERE qaror IS NOT NULL
                          AND ochilgan_at IS NULL)            AS olchovsiz,
       -- 2. MANBA — "qidiruv yordam berdimi"
       count(*) FILTER (WHERE manba = 'taklif')               AS taklifdan,
       count(*) FILTER (WHERE manba = 'qidiruv')              AS qidiruvdan,
       count(*) FILTER (WHERE manba = 'qolda')                AS qoldan,
       -- 3. QIDIRUVSIZ "talabsiz" — avtomatik o'lchovga ISHONILGAN holat.
       count(*) FILTER (WHERE qaror = 'talabsiz' AND qidiruv_soni = 0)
                                                              AS talabsiz_qidiruvsiz,
       count(*) FILTER (WHERE qaror = 'talabsiz' AND qidiruv_soni > 0)
                                                              AS talabsiz_qidiruvli,
       (SELECT count(*) FROM (
           SELECT kalit FROM kod_qaror k2
            WHERE k2.company_id = k.company_id AND k2.qaror = 'kod'
            GROUP BY kalit HAVING count(*) > 1) x)             AS kop_kodli_atama
FROM kod_qaror k
GROUP BY company_id;

COMMENT ON VIEW v_kod_qaror_olchov IS
    'Uch savolning javobi. `ortacha_sek` FAQAT `ochilgan_at IS NOT NULL` '
    'qatorlar bo''yicha — o''lchanmagan qator nol deb sanalmaydi, '
    '`olchovsiz` da ko''rinadi. `atama_soni` takror bosishni '
    '`qaror_soni` dan ajratadi.';

COMMIT;
