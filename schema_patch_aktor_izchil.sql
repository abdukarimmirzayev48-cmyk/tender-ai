-- =============================================================================
-- AKTOR va ISHONCH IZCHILLIGI — BAZA DARAJASIDA (M-2)
--
--   psql "dbname=xtxarid user=postgres host=localhost" -f schema_patch_aktor_izchil.sql
--
-- O'LCHANGAN HOLAT (2026-09-01)
-- -----------------------------
-- Reyestrda M-2 "30 ta inson qarorining AKTORI noma'lum" deb
-- yozilgan edi. Qayta o'lchandi va DA'VO ANIQLASHTIRILDI: ular
-- noma'lum EMAS, ular ANIQ BELGILANGAN —
--
--     qaror_ishonch = 'kuzatuvdan_oldin'   30 ta
--
-- Bu 11-vazifada ataylab qo'yilgan yorliq: "aktor kuzatuvi joriy
-- etilishidan OLDIN yozilgan, kim ekani NOMA'LUM". Ya'ni tizim
-- noma'lumni noma'lum deb saqlagan — bu TO'G'RI xulq.
--
-- ASL BO'SHLIQ BOSHQA EKAN
-- ------------------------
-- `ishonch` va `actor_id` ORASIDAGI IZCHILLIK qoidasi:
--
--     erp_sessiya | aktor_elon                    -> aktor SHART
--     servis | kuzatuvdan_oldin | kompaniya_...   -> aktor BO'LMAYDI
--
-- Bu qoida `audit_jurnal` da CHECK bilan himoyalangan
-- (`audit_jurnal_aktor_chk`), lekin QAROR jadvallarida FAQAT
-- KODDA edi (`routing.qaror()`, `requirement.review_set()`,
-- `kodlash`). O'lchandi:
--
--     jadval                buzuq   aktor_CHECK
--     tender_routing          0         YO'Q
--     tender_requirement      0         YO'Q
--     kod_qaror               0         YO'Q
--     audit_jurnal            —         BOR
--
-- Ya'ni hozir buzuq qator yo'q (kod yo'lini ushlab turibdi), lekin
-- BAZA uni to'xtatmaydi. To'g'ridan-to'g'ri SQL, migratsiya yoki
-- yangi chaqiruv yo'li quyidagilarni yozishi mumkin edi:
--
--     "isbotlangan kimlik, lekin ODAM YO'Q"      (erp_sessiya + NULL)
--     "faqat kompaniya, lekin ODAM BOR"          (kompaniya_ + aktor)
--     yangi qaror "kuzatuvdan_oldin" deb         (eski yorliq ortiga
--       yozilishi                                 yashirinish)
--
-- "Qoida faqat izoh bilan himoyalangan" — loyihada takrorlangan
-- nuqson sinfi. Endi u UCHALA qaror jadvalida ham CHECK.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. IZCHILLIK CHEKLOVLARI
-- ---------------------------------------------------------------------
-- `audit_jurnal_aktor_chk` bilan AYNI qoida — ataylab bir xil, chunki
-- bu BITTA qoida. Ikki xil yozilsa ular vaqt o'tib bir-biridan
-- uzoqlashardi.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'tender_routing_aktor_izchil_chk') THEN
        ALTER TABLE tender_routing ADD CONSTRAINT tender_routing_aktor_izchil_chk
            CHECK (qaror_ishonch IS NULL
                OR (qaror_ishonch IN ('erp_sessiya', 'aktor_elon')
                        AND qaror_actor_id IS NOT NULL)
                OR (qaror_ishonch IN ('servis', 'kuzatuvdan_oldin',
                                      'kompaniya_sessiyasi')
                        AND qaror_actor_id IS NULL));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'tender_requirement_aktor_izchil_chk') THEN
        ALTER TABLE tender_requirement
            ADD CONSTRAINT tender_requirement_aktor_izchil_chk
            CHECK (reviewed_ishonch IS NULL
                OR (reviewed_ishonch IN ('erp_sessiya', 'aktor_elon')
                        AND reviewed_actor_id IS NOT NULL)
                OR (reviewed_ishonch IN ('servis', 'kuzatuvdan_oldin',
                                         'kompaniya_sessiyasi')
                        AND reviewed_actor_id IS NULL));
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'kod_qaror')
       AND NOT EXISTS (SELECT 1 FROM pg_constraint
                        WHERE conname = 'kod_qaror_aktor_izchil_chk') THEN
        ALTER TABLE kod_qaror ADD CONSTRAINT kod_qaror_aktor_izchil_chk
            CHECK (ishonch IS NULL
                OR (ishonch IN ('erp_sessiya', 'aktor_elon')
                        AND actor_id IS NOT NULL)
                OR (ishonch IN ('servis', 'kuzatuvdan_oldin',
                                'kompaniya_sessiyasi')
                        AND actor_id IS NULL));
    END IF;
END $$;

COMMENT ON CONSTRAINT tender_routing_aktor_izchil_chk ON tender_routing IS
    'M-2: `ishonch` va `actor_id` bir-biriga ZID bo''lmasin. '
    '"isbotlangan kimlik, lekin odam yo''q" yoki "faqat kompaniya, '
    'lekin odam bor" holatlari O''QIB BO''LMAYDI.';

-- ---------------------------------------------------------------------
-- 2. ESKI YORLIQ MUZLATILADI
-- ---------------------------------------------------------------------
-- `kuzatuvdan_oldin` — MIGRATSIYA yorlig'i, ish yorlig'i emas. Yangi
-- qaror unga yozilsa, "kim qaror qildi" savoli qonuniy ravishda
-- javobsiz qoldirilardi.
--
-- Kod yo'li buni allaqachon rad etadi (`routing.qaror()` uchta
-- qiymatni qabul qiladi), lekin bu ham FAQAT KODDA edi.
CREATE OR REPLACE VIEW v_aktor_eski_yorliq AS
SELECT 'tender_routing'::TEXT AS jadval,
       count(*)               AS soni,
       max(qaror_vaqti)       AS eng_yangi
  FROM tender_routing WHERE qaror_ishonch = 'kuzatuvdan_oldin'
UNION ALL
SELECT 'tender_requirement', count(*), max(reviewed_at)
  FROM tender_requirement WHERE reviewed_ishonch = 'kuzatuvdan_oldin';

COMMENT ON VIEW v_aktor_eski_yorliq IS
    'M-2: `kuzatuvdan_oldin` — MIGRATSIYA yorlig''i. Soni O''SMASLIGI '
    'kerak; o''ssa yangi qaror eski yorliq ortiga yashiringan.';

COMMIT;
