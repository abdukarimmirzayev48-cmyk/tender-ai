-- =============================================================================
-- AUDIT JURNALI — TUZATISH YOZUVI va uni KO'RSATADIGAN KO'RINISH (M-3)
--
--   psql "dbname=xtxarid user=postgres host=localhost" -f schema_patch_audit_tuzatish.sql
--
-- O'LCHANGAN HOLAT (2026-09-01)
-- -----------------------------
-- HAQIQIY ijarachining (`company_id=2`) audit jurnalida IKKI qator:
--
--   id=62  yonaltirish_olindi   HAQIQIY inson amali. Haqiqiy tender
--                               (20000509558), haqiqiy IP va brauzer,
--                               `keyin` da qaror mazmuni.
--   id=37  huquq_sinov          SINOV ARTEFAKTI. `entity='x'`,
--                               `entity_id=1`, IP yo'q, brauzer yo'q.
--                               12-vazifadagi huquq tekshiruvi paytida
--                               QO'LDA yozilgan.
--
-- Ya'ni ikkita yozuvdan BIRI haqiqiy emas, lekin ular jurnalda
-- BIR XIL ko'rinadi.
--
-- NEGA O'CHIRILMAYDI
-- ------------------
-- `audit_jurnal_ozgarmas_trg` `UPDATE` va `DELETE` ni to'sadi. Bu
-- ATAYLAB: audit jurnali o'zgarmas bo'lmasa, u audit emas.
--
-- Triggerning O'Z xato matni yo'lni ko'rsatadi:
--
--     'Tuzatish kerak bo''lsa YANGI qator qo''shing (amal=''tuzatish'')'
--
-- Shuning uchun bu yerda ARTEFAKT O'CHIRILMAYDI — uning ustiga
-- TUZATISH yozuvi qo'shiladi. Bu buxgalteriyadagi storno yozuvi
-- bilan bir xil naqsh: xato yozuv qoladi, uning noto'g'ri ekani
-- ALOHIDA yozuv bilan qayd etiladi.
--
-- TAKRORLANMAYDI: `huquq_sinov` amali KODDA HECH QAYERDA yo'q
-- (`grep` bilan tekshirildi) — u bir martalik qo'lda yozuv edi.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. TUZATISH YOZUVI — bir marta
-- ---------------------------------------------------------------------
-- `ishonch='servis'` — bu yozuvni ODAM emas, migratsiya qo'shdi va
-- `audit_jurnal_aktor_chk` shunda `actor_id IS NULL` ni talab qiladi.
INSERT INTO audit_jurnal
    (company_id, actor_id, ishonch, amal, entity, entity_id,
     oldin, keyin, izoh)
SELECT a.company_id, NULL, 'servis', 'tuzatish', 'audit_jurnal', a.id,
       to_jsonb(a) - 'oldin' - 'keyin',
       jsonb_build_object('sinov_artefakti', true,
                          'sabab', '12-vazifadagi huquq tekshiruvi'),
       'M-3: bu qator SINOV artefakti — haqiqiy inson amali EMAS. '
       'Jadval append-only, shuning uchun o''chirilmadi; '
       'v_audit_jurnal_haqiqiy dan CHIQARILDI.'
  FROM audit_jurnal a
 WHERE a.id = 37 AND a.amal = 'huquq_sinov' AND a.entity = 'x'
   AND NOT EXISTS (SELECT 1 FROM audit_jurnal t
                    WHERE t.amal = 'tuzatish'
                      AND t.entity = 'audit_jurnal'
                      AND t.entity_id = a.id);

-- ---------------------------------------------------------------------
-- 2. KO'RINISH — tuzatilgan yozuvlar AJRATILADI
-- ---------------------------------------------------------------------
-- Jurnalning O'ZI to'liq qoladi (u audit), lekin o'quvchi
-- "haqiqiy amallar" ni so'raganda artefakt CHIQMAYDI.
--
-- `tuzatish` yozuvlarining O'ZI ham chiqarilmaydi: ular jurnal
-- haqidagi metama'lumot, ijarachi amali emas.
CREATE OR REPLACE VIEW v_audit_jurnal_haqiqiy AS
SELECT a.*
  FROM audit_jurnal a
 WHERE a.amal <> 'tuzatish'
   AND NOT EXISTS (SELECT 1 FROM audit_jurnal t
                    WHERE t.amal = 'tuzatish'
                      AND t.entity = 'audit_jurnal'
                      AND t.entity_id = a.id);

COMMENT ON VIEW v_audit_jurnal_haqiqiy IS
    'Audit jurnali, TUZATILGAN yozuvlarsiz. Jurnalning o''zi to''liq '
    'qoladi (u append-only va shunday bo''lishi kerak) — bu ko''rinish '
    'faqat "haqiqiy amallar" savoliga javob beradi. M-3.';

-- ---------------------------------------------------------------------
-- 3. O'LCHOV
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_audit_tuzatish AS
SELECT t.company_id,
       t.entity_id                       AS tuzatilgan_id,
       t.izoh,
       t.at                              AS tuzatilgan_vaqt,
       (a.id IS NOT NULL)                AS asl_qator_bor,
       a.amal                            AS asl_amal
  FROM audit_jurnal t
  LEFT JOIN audit_jurnal a ON a.id = t.entity_id
 WHERE t.amal = 'tuzatish' AND t.entity = 'audit_jurnal';

COMMENT ON VIEW v_audit_tuzatish IS
    'M-3: qaysi audit yozuvlari tuzatilgan va NEGA. Bo''sh bo''lishi '
    'ideal; bo''sh emasligi nuqson EMAS — bu HALOL tuzatish izi.';

COMMIT;
