-- =====================================================================
-- J3 — SOXTA "TASDIQLANGAN" TALABLAR: MASHINA HOLATI INSON QARORIDAN
--      AJRATILADI VA INVARIANT BAZADA QULFLANADI
-- =====================================================================
--
-- O'LCHANGAN NUQSON (2026-08-30):
--
--     SELECT review_status, method, count(*),
--            count(*) FILTER (WHERE reviewed_by IS NOT NULL)
--     FROM tender_requirement GROUP BY 1,2;
--
--       pending   naqsh     7298    inson ko'rgan: 0
--       approved  reyestr   1487    inson ko'rgan: 0    <-- SOXTA
--
-- 1 487 qator "approved" bo'lib turibdi va ularni HECH KIM ko'rmagan.
--
-- QAYERDAN KELDI: `schema_patch_requirement_3.sql` dagi migratsiya
--
--     UPDATE tender_requirement
--        SET review_status = CASE WHEN method = 'reyestr'
--                                 THEN 'approved' ELSE 'pending' END;
--
-- va `api/requirement.py` dagi reyestr yozuv yo'li
-- (`"review_status": "approved"`).
--
-- NIYAT TUSHUNARLI, XULOSA XATO. Reyestr pozitsiyasi haqiqatan ham
-- manba platformasining RASMIY yozuvi — model taxmini emas, va unga
-- ishonsa bo'ladi. Lekin "ishonchli ma'lumot" va "inson tasdiqladi"
-- IKKI BOSHQA GAP. Bitta ustunga ikkalasini yuklash ularni bir-biriga
-- aylantirdi.
--
-- OQIBATLARI O'LCHANGAN (§16.67, schema_patch_requirement_7.sql):
--   * `v_review_disagreement` da 12 ta avto-tasdiq "inson roziligi"
--     deb sanalib, "yuqori ishonchda 0% kelishmovchilik" degan SOXTA
--     raqam bergan;
--   * `n_reviewed` shishgan va `sekund_talabga` shuncha kam chiqqan —
--     inson haqiqiydan TEZROQ ko'ringan.
--
-- Ikkalasi ham O'SHANDA nuqtama-nuqta yamalgan (`reviewed_by IS NOT
-- NULL` sharti qo'shilgan), lekin SABAB — ustunning ikki ma'noliligi —
-- QOLGAN. Har yangi iste'molchi shu tuzoqqa qaytadan tushardi.
--
-- BU PATCH SABABNI OLIB TASHLAYDI:
--
--   1. `mashina_holat` — MASHINA o'qi. Faqat ajratish yozadi.
--   2. `review_status` — endi FAQAT INSON o'qi.
--   3. Invariant IZOH bilan emas, CHECK bilan qulflanadi:
--        approved/rejected/corrected  =>  reviewed_by IS NOT NULL
--                                         AND reviewed_by <> 0
--                                         AND reviewed_at IS NOT NULL
--                                         AND review_action IS NOT NULL
--      va TESKARISI ham:
--        extracted/pending_review     =>  reviewed_by IS NULL
--                                         AND reviewed_at IS NULL
--
-- NEGA CHECK, IZOH EMAS: shu loyihada aynan shu qoida
-- `schema_patch_requirement_3.sql` da IZOH bilan yozilgan edi
-- ("reyestr avtomatik approved") va 1 487 qator shu izohdan o'tib
-- ketdi. Izoh migratsiyani to'xtatmaydi, CHECK to'xtatadi.
--
-- HOLAT LUG'ATI:
--     extracted       mashina chiqardi, navbatda EMAS (reyestr)
--     pending_review  navbatda, INSONNI kutmoqda
--     approved        INSON tasdiqladi
--     rejected        INSON rad etdi
--     corrected       INSON tuzatdi
--
-- Idempotent: bir necha marta yurgizsa bo'ladi.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 0. KO'CHIRISHDAN OLDINGI HOLATNI YOZIB OLAMIZ
-- ---------------------------------------------------------------------
-- Migratsiya "nima qildim" deb ayta olishi SHART. Bu jadval bir
-- martalik emas: keyinchalik "1 487 qator qayerdan keldi" degan savol
-- albatta tug'iladi va javob KODDA emas, BAZADA turishi kerak.
CREATE TABLE IF NOT EXISTS requirement_migratsiya_jurnali (
    id            SERIAL PRIMARY KEY,
    patch         TEXT        NOT NULL,
    bajarildi_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    tavsif        TEXT        NOT NULL,
    oldin         JSONB,
    keyin         JSONB
);

COMMENT ON TABLE requirement_migratsiya_jurnali IS
    'Talab holatlariga tegilgan migratsiyalar tarixi. "Bu qatorlar '
    'qayerdan keldi" savoliga javob KODDA emas, BAZADA turishi kerak.';

-- ---------------------------------------------------------------------
-- 1. YANGI USTUNLAR
-- ---------------------------------------------------------------------
ALTER TABLE tender_requirement
    -- MASHINA o'qi. `review_status` dan MUSTAQIL.
    ADD COLUMN IF NOT EXISTS mashina_holat   TEXT,
    -- Inson AYNAN nima qildi. Holatdan kelib chiqadi, lekin ALOHIDA
    -- yoziladi: holat keyin o'zgarsa ham (qayta ajratish) amal
    -- tarixi qolishi kerak.
    ADD COLUMN IF NOT EXISTS review_action   TEXT,
    -- Tuzatishdan OLDINGI qiymat. `corrected_value` "nimaga"
    -- degan savolga javob berardi, "nimadan" degani yo'q edi.
    ADD COLUMN IF NOT EXISTS previous_value  TEXT,
    -- MASHINA tomonining izohi (migratsiya, avtomatik qaror sababi).
    -- `review_note` INSON maydoni bo'lib qoladi — ikkalasini
    -- aralashtirish aynan shu patch tuzatayotgan xato sinfi.
    ADD COLUMN IF NOT EXISTS mashina_izoh    TEXT;

COMMENT ON COLUMN tender_requirement.mashina_holat IS
    'MASHINA o''qi (inson qarori EMAS): manba — platformaning rasmiy '
    'reyestr yozuvi; ajratilgan — matndan naqsh yoki model chiqargan. '
    'Ishonchlilik SHU ustundan o''qiladi, `review_status` dan EMAS.';
COMMENT ON COLUMN tender_requirement.review_action IS
    'Inson AYNAN nima qildi: approve | reject | correct. NULL = inson '
    'tegmagan. `review_status` bilan CHECK orqali bog''langan.';
COMMENT ON COLUMN tender_requirement.previous_value IS
    'Tuzatishdan OLDINGI amaldagi qiymat. `corrected_value` "nimaga" '
    'ni aytadi, bu "nimadan" ni.';
COMMENT ON COLUMN tender_requirement.mashina_izoh IS
    'Mashina tomonining izohi (migratsiya yozuvi, avtomatik qaror '
    'sababi). `review_note` INSON maydoni — aralashtirilmaydi.';

-- ---------------------------------------------------------------------
-- 2. MASHINA HOLATINI TO'LDIRAMIZ
-- ---------------------------------------------------------------------
-- `method` dan KELIB CHIQADI, lekin ALOHIDA ustun bo'lishi SHART:
-- iste'molchi "bu ishonchlimi" deb so'raganda usul ro'yxatini
-- (`reyestr`/`naqsh`/`llm`) bilishi shart bo'lmasin. Yangi usul
-- qo'shilganda 4-bo'limdagi CHECK ni ATAYLAB tahrirlashga majbur
-- qiladi — ya'ni "yangi usul ishonchlimi" degan savol JAVOBSIZ
-- o'tib ketmaydi.
UPDATE tender_requirement
   SET mashina_holat = CASE WHEN method = 'reyestr' THEN 'manba'
                            ELSE 'ajratilgan' END
 WHERE mashina_holat IS NULL;

ALTER TABLE tender_requirement
    ALTER COLUMN mashina_holat SET NOT NULL;
ALTER TABLE tender_requirement
    ALTER COLUMN mashina_holat SET DEFAULT 'ajratilgan';

-- ---------------------------------------------------------------------
-- 3. HOLAT LUG'ATINI KO'CHIRAMIZ
-- ---------------------------------------------------------------------
-- ESKI CHECK ni OLDIN olib tashlaymiz, aks holda yangi qiymatlar
-- yozilmaydi.
ALTER TABLE tender_requirement
    DROP CONSTRAINT IF EXISTS tender_requirement_review_chk;

DO $$
DECLARE
    n_soxta   INT;
    n_kutayot INT;
    n_inson   INT;
BEGIN
    SELECT count(*) INTO n_soxta FROM tender_requirement
     WHERE review_status = 'approved' AND reviewed_by IS NULL;
    SELECT count(*) INTO n_kutayot FROM tender_requirement
     WHERE review_status = 'pending';
    SELECT count(*) INTO n_inson FROM tender_requirement
     WHERE reviewed_by IS NOT NULL;

    IF n_soxta > 0 OR n_kutayot > 0 THEN
        INSERT INTO requirement_migratsiya_jurnali (patch, tavsif, oldin, keyin)
        VALUES (
            'schema_patch_requirement_8.sql',
            'Soxta "approved" (inson ko''rmagan) qatorlar "extracted" ga '
            'ko''chirildi; "pending" -> "pending_review". Hech qanday '
            'qator O''CHIRILMADI, provenance (source/method/confidence/'
            'citation/attrs) TEGILMADI.',
            jsonb_build_object(
                'approved_reviewed_by_null', n_soxta,
                'pending', n_kutayot,
                'inson_korgan', n_inson),
            jsonb_build_object(
                'extracted', n_soxta,
                'pending_review', n_kutayot,
                'inson_korgan', n_inson));
        RAISE NOTICE 'Migratsiya: % ta soxta approved -> extracted, % ta pending -> pending_review',
                     n_soxta, n_kutayot;
    END IF;
END $$;

-- 3a. SOXTA TASDIQ -> `extracted`.
--
--     QATOR O'CHIRILMAYDI VA MA'LUMOTI TEGILMAYDI. O'zgaradigan
--     yagona narsa — YOLG'ON yorliq. Provenance to'liq joyida:
--       source            'api'        (tegilmadi)
--       method            'reyestr'    (tegilmadi)
--       confidence        1.00         (tegilmadi)
--       attrs             asl qiymat   (tegilmadi)
--       file_ref/char_*   iqtibos      (tegilmadi)
--       extracted_at      ajratilgan vaqt (tegilmadi)
--       mashina_holat     'manba'      (2-bo'limda qo'yildi)
UPDATE tender_requirement
   SET review_status = 'extracted',
       mashina_izoh  = COALESCE(mashina_izoh || E'\n', '')
           || 'migratsiya 2026-08-30 (schema_patch_requirement_8.sql): '
           || 'holat "approved" edi, lekin reviewed_by IS NULL — ya''ni '
           || 'INSON KO''RMAGAN. "approved" endi FAQAT inson qarorini '
           || 'bildiradi, shuning uchun bu qator "extracted" ga '
           || 'ko''chirildi. Ma''lumotning o''zi o''zgarmadi.'
 WHERE review_status = 'approved'
   AND reviewed_by IS NULL;

-- 3b. HAQIQIY inson tasdig'i bo'lsa — `review_action` ni to'ldiramiz
--     (yangi CHECK talab qiladi). Bugungi bazada bunday qator YO'Q
--     (o'lchandi: 0), lekin migratsiya shunga tayanmaydi.
UPDATE tender_requirement
   SET review_action = CASE review_status
                           WHEN 'approved'  THEN 'approve'
                           WHEN 'rejected'  THEN 'reject'
                           WHEN 'corrected' THEN 'correct' END
 WHERE reviewed_by IS NOT NULL
   AND review_action IS NULL
   AND review_status IN ('approved', 'rejected', 'corrected');

-- 3c. `corrected` uchun `previous_value` majburiy bo'ladi. Eski
--     qatorlarda u yo'q — asl qiymatdan tiklaymiz (`attrs->>'qiymat'`
--     ATAYLAB o'zgarmas saqlanadi, shuning uchun bu TIKLASH, taxmin
--     emas).
UPDATE tender_requirement
   SET previous_value = COALESCE(previous_value, attrs->>'qiymat', '(noma''lum)')
 WHERE review_status = 'corrected'
   AND previous_value IS NULL;

-- 3d. `pending` -> `pending_review`.
--
--     NOMI ATAYLAB O'ZGARTIRILDI. "pending" nimani kutayotganini
--     AYTMAYDI, va aynan shu noaniqlik "reyestr ham bir turdagi
--     tasdiq" degan xulosaga yo'l ochgan. Yangi lug'atda holatning
--     o'zi kimga tegishli ekanini aytadi.
UPDATE tender_requirement
   SET review_status = 'pending_review'
 WHERE review_status = 'pending';

-- 3e. Har ehtimolga qarshi: inson tegmagan qatorda inson izlari
--     qolmasin (yangi CHECK talabi).
UPDATE tender_requirement
   SET reviewed_by = NULL, reviewed_at = NULL, review_action = NULL
 WHERE review_status IN ('extracted', 'pending_review')
   AND (reviewed_by IS NOT NULL OR reviewed_at IS NOT NULL
        OR review_action IS NOT NULL);

-- ---------------------------------------------------------------------
-- 4. INVARIANTLAR — BAZA DARAJASIDA
-- ---------------------------------------------------------------------
DO $$
BEGIN
    -- Holat lug'ati.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'tender_requirement_review_chk') THEN
        ALTER TABLE tender_requirement ADD CONSTRAINT tender_requirement_review_chk
            CHECK (review_status IN
                   ('extracted', 'pending_review', 'approved', 'rejected', 'corrected'));
    END IF;

    -- Mashina holati lug'ati.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'tender_requirement_mashina_chk') THEN
        ALTER TABLE tender_requirement ADD CONSTRAINT tender_requirement_mashina_chk
            CHECK (mashina_holat IN ('manba', 'ajratilgan'));
    END IF;

    -- Mashina holati va usul MOS. Yangi usul qo'shilganda bu cheklov
    -- ATAYLAB yiqiladi va "bu usul ishonchlimi" degan savolni
    -- javobsiz o'tkazmaydi.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'tender_requirement_mashina_usul_chk') THEN
        ALTER TABLE tender_requirement ADD CONSTRAINT tender_requirement_mashina_usul_chk
            CHECK ((mashina_holat = 'manba') = (method = 'reyestr'));
    END IF;

    -- ============ ASOSIY INVARIANT ============
    -- INSON QARORI => INSON DALILI.
    -- Bu cheklovsiz 1 487 qator qayta paydo bo'lishi mumkin.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'tender_requirement_inson_qarori_chk') THEN
        ALTER TABLE tender_requirement ADD CONSTRAINT tender_requirement_inson_qarori_chk
            CHECK (
                review_status NOT IN ('approved', 'rejected', 'corrected')
                OR (reviewed_by IS NOT NULL
                    AND reviewed_by <> 0
                    AND reviewed_at IS NOT NULL
                    AND review_action IS NOT NULL)
            );
    END IF;

    -- TESKARI INVARIANT: mashina holatida inson izlari BO'LMAYDI.
    --
    -- NEGA KERAK: birinchi cheklov yolg'on "approved" ni to'sadi,
    -- lekin yarim yozilgan holatni to'smaydi — masalan
    -- `reviewed_by` qo'yilib, holat `pending_review` qolishi.
    -- O'shanda navbat "ko'rilmagan" derdi, hisoblagich esa
    -- "ko'rilgan" — va ikkalasi ham bazadan o'qilardi.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'tender_requirement_mashina_toza_chk') THEN
        ALTER TABLE tender_requirement ADD CONSTRAINT tender_requirement_mashina_toza_chk
            CHECK (
                review_status NOT IN ('extracted', 'pending_review')
                OR (reviewed_by IS NULL
                    AND reviewed_at IS NULL
                    AND review_action IS NULL)
            );
    END IF;

    -- `review_action` holatga MOS bo'lsin. Aks holda "approved,
    -- lekin amal reject" degan o'qib bo'lmaydigan qator paydo bo'lardi.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'tender_requirement_amal_chk') THEN
        ALTER TABLE tender_requirement ADD CONSTRAINT tender_requirement_amal_chk
            CHECK (
                review_action IS NULL
                OR (review_action = 'approve'  AND review_status = 'approved')
                OR (review_action = 'reject'   AND review_status = 'rejected')
                OR (review_action = 'correct'  AND review_status = 'corrected')
            );
    END IF;

    -- `reviewed_by = 0` — ATAYLAB ALOHIDA cheklov. FK `company_account`
    -- ga bog'lasa ham, 0 "noma'lum foydalanuvchi" sifatida yozilib
    -- qolishi mumkin bo'lgan klassik qiymat va topshiriq uni aniq
    -- talab qiladi.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'tender_requirement_kim_chk') THEN
        ALTER TABLE tender_requirement ADD CONSTRAINT tender_requirement_kim_chk
            CHECK (reviewed_by IS NULL OR reviewed_by > 0);
    END IF;

    -- Tuzatishda "nimadan" ham, "nimaga" ham bo'lishi shart.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'tender_requirement_oldingi_chk') THEN
        ALTER TABLE tender_requirement ADD CONSTRAINT tender_requirement_oldingi_chk
            CHECK (review_status <> 'corrected' OR previous_value IS NOT NULL);
    END IF;
END $$;

COMMENT ON COLUMN tender_requirement.review_status IS
    'FAQAT INSON o''qi. extracted — mashina chiqardi, navbatda emas; '
    'pending_review — insonni kutmoqda; approved/rejected/corrected — '
    'INSON qarori (CHECK reviewed_by + reviewed_at + review_action ni '
    'TALAB QILADI). Ishonchlilik uchun `mashina_holat` va `confidence` '
    'ga qarang — bu ustun unga JAVOB BERMAYDI.';

-- ---------------------------------------------------------------------
-- 5. INDEKS — nomi o'zgargan holatga moslanadi
-- ---------------------------------------------------------------------
DROP INDEX IF EXISTS tender_requirement_pending_idx;
CREATE INDEX IF NOT EXISTS tender_requirement_navbat_idx
    ON tender_requirement (company_id, tender_id)
    WHERE review_status = 'pending_review';

-- Inson ko'rgan qatorlar bo'yicha hisob — hisoblagichlar shundan.
CREATE INDEX IF NOT EXISTS tender_requirement_korilgan_idx
    ON tender_requirement (company_id, reviewed_at DESC)
    WHERE reviewed_by IS NOT NULL;

-- ---------------------------------------------------------------------
-- 6. KO'RINISHLAR — yangi lug'atga moslanadi
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_requirement_review AS
SELECT r.company_id, r.tender_id, t.name AS tender_name, t.close_at,
       count(*)                                            AS kutayotgan,
       count(*) FILTER (WHERE r.method = 'llm')            AS modeldan,
       count(*) FILTER (WHERE r.method = 'naqsh')          AS naqshdan,
       min(r.confidence)                                   AS eng_past_ishonch,
       count(*) FILTER (WHERE r.confidence < 0.60)         AS past_ishonchli,
       max(r.extracted_at)                                 AS ajratilgan
FROM tender_requirement r
JOIN tender t ON t.id = r.tender_id
WHERE r.review_status = 'pending_review'
GROUP BY r.company_id, r.tender_id, t.name, t.close_at
ORDER BY t.close_at, min(r.confidence);

COMMENT ON VIEW v_requirement_review IS
    'Ko`rib chiqish navbati — FAQAT `pending_review`. `extracted` '
    '(reyestr) bu yerga TUSHMAYDI: u insonni kutmaydi.';

-- `v_requirement_labeled` — INSON YORLIQLAGAN to'plam (ground truth).
-- `reviewed_by IS NOT NULL` sharti endi CHECK bilan kafolatlangan,
-- lekin ko'rinishda ham QOLADI: ko'rinish o'z shartini o'zi aytsin,
-- o'quvchi cheklovni izlab yurmasin.
-- `CREATE OR REPLACE` ISHLAMAYDI: ustunlar ro'yxati o'zgaradi
-- (`previous_value`, `mashina_holat`, `review_action` qo'shildi) va
-- PostgreSQL mavjud ko'rinishning ustun tartibini o'zgartirishga
-- ruxsat bermaydi. `CASCADE` ATAYLAB ISHLATILMAYDI: bog'liq obyekt
-- bo'lsa DROP yiqilsin va biz uni KO'RAYLIK — jimgina o'chirib
-- yuborish shu loyihada takrorlangan nuqson sinfi.
DROP VIEW IF EXISTS v_requirement_labeled;
CREATE VIEW v_requirement_labeled AS
SELECT company_id, tender_id, id AS requirement_id, name,
       attrs->>'qiymat'                                AS qiymat,
       COALESCE(corrected_value, attrs->>'qiymat')     AS amaldagi_qiymat,
       previous_value,
       attrs->>'tur'                                   AS tur,
       method, mashina_holat, confidence, is_mandatory, doc_type,
       review_status, review_action, reviewed_by, reviewed_at
FROM tender_requirement r
WHERE review_status IN ('approved', 'corrected', 'rejected')
  AND reviewed_by IS NOT NULL
  AND doc_type IS NOT NULL;

COMMENT ON VIEW v_requirement_labeled IS
    'INSON yorliqlagan to`plam — moslashtiruv ground truth i. '
    'Mashina chiqargan (`extracted`) qatorlar bu yerda YO`Q.';

-- ---------------------------------------------------------------------
-- 7. HALOL HISOBLAGICHLAR
-- ---------------------------------------------------------------------
-- Ilgari "nechta tasdiqlangan" degan savolga javob ikki xil chiqardi:
-- `review_status='approved'` (1 487) va `reviewed_by IS NOT NULL` (0).
-- Endi ular AYNAN bir xil bo'lishi CHECK bilan kafolatlanadi va bu
-- ko'rinish ikkalasini yonma-yon ko'rsatadi.
CREATE OR REPLACE VIEW v_requirement_holat AS
SELECT
    company_id,
    count(*)                                                    AS jami,
    count(*) FILTER (WHERE review_status = 'extracted')         AS mashina_chiqargan,
    count(*) FILTER (WHERE review_status = 'pending_review')    AS navbatda,
    count(*) FILTER (WHERE review_status = 'approved')          AS inson_tasdiqladi,
    count(*) FILTER (WHERE review_status = 'rejected')          AS inson_rad_etdi,
    count(*) FILTER (WHERE review_status = 'corrected')         AS inson_tuzatdi,
    count(*) FILTER (WHERE reviewed_by IS NULL)                 AS korilmagan,
    -- NAZORAT: bu ikkisi HAR DOIM teng bo'lishi SHART. Farq
    -- chiqsa cheklov buzilgan degani (ya'ni imkonsiz) — ko'rinish
    -- shuni ko'rsatib turadi.
    count(*) FILTER (WHERE review_status IN ('approved','rejected','corrected'))
                                                                AS inson_qarori_holat,
    count(*) FILTER (WHERE reviewed_by IS NOT NULL)             AS inson_qarori_dalil,
    count(*) FILTER (WHERE mashina_holat = 'manba')             AS manbadan,
    count(*) FILTER (WHERE mashina_holat = 'ajratilgan')        AS ajratilgan
FROM tender_requirement
GROUP BY company_id;

COMMENT ON VIEW v_requirement_holat IS
    'Talab holatlarining HALOL hisobi. `inson_qarori_holat` va '
    '`inson_qarori_dalil` HAR DOIM teng bo`lishi shart — farq '
    'invariant buzilganini bildiradi (CHECK buni imkonsiz qiladi).';

-- ---------------------------------------------------------------------
-- 8. MUSBAT TASDIQ — patch O'ZI tekshiradi
-- ---------------------------------------------------------------------
-- "Xato chiqmadi" = "ish bajarildi" EMAS. Natija ALOHIDA o'qiladi.
DO $$
DECLARE
    n_soxta   INT;
    n_eski    INT;
    n_holat   INT;
    n_dalil   INT;
BEGIN
    SELECT count(*) INTO n_soxta FROM tender_requirement
     WHERE review_status IN ('approved','rejected','corrected')
       AND (reviewed_by IS NULL OR reviewed_by = 0 OR reviewed_at IS NULL);
    IF n_soxta > 0 THEN
        RAISE EXCEPTION 'Migratsiya TUGALLANMADI: % ta soxta inson qarori qoldi', n_soxta;
    END IF;

    SELECT count(*) INTO n_eski FROM tender_requirement
     WHERE review_status = 'pending';
    IF n_eski > 0 THEN
        RAISE EXCEPTION 'Eski "pending" holati qoldi: % qator', n_eski;
    END IF;

    SELECT count(*) INTO n_holat FROM tender_requirement
     WHERE review_status IN ('approved','rejected','corrected');
    SELECT count(*) INTO n_dalil FROM tender_requirement
     WHERE reviewed_by IS NOT NULL;
    IF n_holat <> n_dalil THEN
        RAISE EXCEPTION 'Holat (%) va dalil (%) mos kelmadi', n_holat, n_dalil;
    END IF;

    RAISE NOTICE 'TASDIQ: soxta inson qarori = 0, holat = dalil = %', n_holat;
END $$;

COMMIT;
