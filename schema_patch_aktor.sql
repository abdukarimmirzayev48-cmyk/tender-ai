-- =====================================================================
-- AKTOR KIMLIGI VA AUDIT — inson qarorini KIMGA bog'lash
-- =====================================================================
--
-- O'LCHANGAN MUAMMO (2026-08-31, `xtxarid` bazasi va `api/` tekshirildi).
--
-- Tender-AI ga KOMPANIYA kiradi, odam emas — bu ATAYLAB
-- (`schema_patch_auth_2.sql`, hodimlar ERP da: `erp.app_user`). Lekin
-- tizimda INSON qarorlari bor va ular uch xil, bir-biriga MOS
-- KELMAYDIGAN usulda yozilardi:
--
--   +-------------------------------+----------------------+-------------+
--   | Qayerda                       | Aktor qanday saqlanadi| Ishonchlimi |
--   +-------------------------------+----------------------+-------------+
--   | tender_requirement.reviewed_by| INT -> company_account| Ha, LEKIN u |
--   |                               | (sessiyadan)          | KOMPANIYA,  |
--   |                               |                       | odam emas   |
--   | kod_qaror.kim                 | TEXT (sessiya login)  | O'sha muammo|
--   | tender_routing.broker_nomi    | TEXT, `body.broker`   | YO'Q —      |
--   |                               | ya'ni MIJOZDAN        | ixtiyoriy   |
--   |                               |                       | matn        |
--   +-------------------------------+----------------------+-------------+
--
--   Ya'ni bugungi eng nozik atribut — "qaysi KOMPANIYA", "qaysi ODAM"
--   emas. Va bitta yo'lda (`routing`) aktor umuman tekshirilmasdan
--   mijozdan qabul qilinardi.
--
--   O'lchandi: 30 ta yo'naltirish qarorida `inson_qaror` bor,
--   `broker_nomi` esa 0 tasida yozilgan. Ya'ni HOZIRGACHA yolg'on
--   yozuv yo'q, lekin yo'l ochiq edi.
--
-- QAROR: CHEKLANGAN INTEGRATSIYA XARITASI (ADR — batafsil
-- `docs/erp_kimlik.md`).
--
--   Uch yo'l qaraldi:
--
--   A) ERP bergan ishonchli kontekst. `erp.app_user` AYNAN SHU bazada
--      (boshqa sxemada) va unda haqiqiy hodimlar bor. LEKIN chegara
--      shartnomasi SIMMETRIK va VIEW orqali: tender-ai `erp.*` ning
--      JADVALLARINI o'qimaydi, faqat ERP kafolatlagan view ni
--      (`erp.v_tender_status`, `erp.v_stock_balance`). `erp.app_user`
--      ga to'g'ridan-to'g'ri bog'lanish shu shartnomani buzardi.
--
--   B) Mahalliy sub-foydalanuvchi tizimi. Bu `erp.app_user` ni
--      TAKRORLASH bo'lardi — aynan `schema_patch_auth_2.sql` olib
--      tashlagan narsa ("IKKI joyda ikki xil"). Rad etildi.
--
--   C) CHEKLANGAN XARITA — tanlandi. Bu yerda `actor` jadvali
--      KIMLIK OMBORI EMAS, XARITA: parol yo'q, sessiya yo'q, kirish
--      yo'q. U faqat "shu ijarachida shu ERP hodimi shu rol bilan
--      ishlaydi" deydi.
--
-- ISHONCHNI O'LCHASH — YORLIQ DALILDAN OSHMAYDI
-- ---------------------------------------------
--   Tender-AI hodimni O'ZI autentifikatsiya QILA OLMAYDI (A va B
--   yuqorida rad etildi). Shuning uchun har atribut yoniga UNING
--   QANCHALIK ISHONCHLI ekani ham yoziladi:
--
--     erp_sessiya          — ODAM ISBOTLANGAN: ERP sessiyasi tekshirildi
--                            (ERP `erp.v_tai_actor` view ini chop
--                            etganda; `docs/erp_kimlik.md` §4)
--     aktor_elon           — ODAM E'LON QILINGAN: kompaniya sessiyasi
--                            ro'yxatdagi aktorni ko'rsatdi, lekin
--                            odamning O'ZI isbotlanmadi
--     kompaniya_sessiyasi  — FAQAT KOMPANIYA ma'lum. Aktor YO'Q va
--                            shunday deb yoziladi — "noma'lum odam"
--                            o'rniga soxta ism qo'yilmaydi
--     servis               — odam YO'Q (ERP service kaliti)
--     kuzatuvdan_oldin     — bu patchdan OLDIN yozilgan qator; kim
--                            qilgani NOMA'LUM va shunday deyiladi
--
--   `erp_sessiya` va `aktor_elon` ATAYLAB AJRATILGAN: birinchisi
--   tekshirilgan, ikkinchisi aytilgan. Ularni bitta qiymatga qo'shish
--   aynan shu loyihada tuzatilgan xatoni takrorlardi (mashina holati
--   inson tasdig'i bo'lib ko'rinishi).
--
--   Bu loyihada allaqachon ishlaydigan naqsh: `ok` va `bootstrap`
--   (bajarilgan / o'lchangan), `inson_tasdiqladi` va
--   `mashina_ishonchli`. Yorliq dalildan oshmaydi.
--
-- IJARACHI IZOLYATSIYASI — KOD EMAS, KOMPOZIT FK
-- ----------------------------------------------
--   `actor` da `UNIQUE (company_id, id)` bor va har qaror jadvali
--   `(company_id, actor_id)` ni KOMPOZIT FK bilan bog'laydi.
--   Natijada BOSHQA ijarachining aktorini yozish JISMONAN mumkin
--   emas — ilova kodi nima qilishidan qat'i nazar. Bu loyihada
--   qoidani izohda qoldirish qanday tugashini ko'rdik (1 487 ta
--   soxta `approved`).
--
-- Idempotent: bir necha marta yurgizsa bo'ladi.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1) actor — XARITA, kimlik ombori EMAS
-- ---------------------------------------------------------------------
-- BU JADVALDA ATAYLAB YO'Q: `password_hash`, `token`, `session`,
-- `last_login_at`. Ular paydo bo'lsa — bu ikkinchi kimlik tizimi
-- bo'lardi va B varianti qaytib kelardi. `_tests/aktor_test.py` shu
-- ustunlar YO'QLIGINI tekshiradi.
CREATE TABLE IF NOT EXISTS actor (
    id           BIGSERIAL PRIMARY KEY,
    company_id   INT  NOT NULL REFERENCES company_account(id) ON DELETE CASCADE,

    -- Aktor QAYERDAN kelgan.
    --   erp      — `erp.app_user` dagi hodimga xarita (`erp_user_id`)
    --   mahalliy — ERP da yo'q odam (masalan tashqi maslahatchi).
    --              Bu YO'L ATAYLAB TOR: u kirish huquqi bermaydi,
    --              faqat qarorni kimgadir bog'laydi.
    manba        TEXT NOT NULL,

    -- `erp.app_user.id` ga YUMSHOQ havola. FK ATAYLAB QO'YILMAGAN:
    -- FK `erp.app_user` JADVALIGA bog'lanardi, chegara shartnomasi esa
    -- VIEW orqali ishlashni talab qiladi (ERP ichini o'zgartira olsin).
    -- Mos kelishi `api/aktor.py:erp_moslikni_tekshir()` bilan
    -- O'LCHANADI va nomuvofiqlik KO'RSATILADI — jimgina qolmaydi.
    erp_user_id  INT,

    login        TEXT NOT NULL,
    ism          TEXT NOT NULL,
    rol          TEXT NOT NULL,
    active       BOOLEAN NOT NULL DEFAULT true,
    izoh         TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- KOMPOZIT FK UCHUN. `id` allaqachon PK, lekin ijarachi
    -- izolyatsiyasini FK darajasida qulflash uchun shu juftlik kerak.
    CONSTRAINT actor_ijarachi_kaliti UNIQUE (company_id, id)
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='actor_manba_chk') THEN
        ALTER TABLE actor ADD CONSTRAINT actor_manba_chk
            CHECK (manba IN ('erp', 'mahalliy'));
    END IF;

    -- ERP aktorida `erp_user_id` BO'LISHI SHART, mahalliyda BO'LMASLIGI.
    -- Aks holda "ERP dan" degan yorliq dalilsiz qo'yilardi.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='actor_manba_dalil_chk') THEN
        ALTER TABLE actor ADD CONSTRAINT actor_manba_dalil_chk
            CHECK ((manba = 'erp'      AND erp_user_id IS NOT NULL)
                OR (manba = 'mahalliy' AND erp_user_id IS NULL));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='actor_rol_chk') THEN
        ALTER TABLE actor ADD CONSTRAINT actor_rol_chk
            CHECK (rol IN ('kuzatuvchi', 'koruvchi', 'tasdiqlovchi', 'admin'));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='actor_login_chk') THEN
        ALTER TABLE actor ADD CONSTRAINT actor_login_chk
            CHECK (length(btrim(login)) > 0 AND length(btrim(ism)) > 0);
    END IF;
END $$;

-- Bitta ERP hodimi bitta ijarachida BIR MARTA. Ikki marta bo'lsa
-- "kim qildi" savoliga ikkita javob chiqardi.
CREATE UNIQUE INDEX IF NOT EXISTS actor_erp_bir_marta
    ON actor (company_id, erp_user_id) WHERE erp_user_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS actor_login_bir_marta
    ON actor (company_id, lower(login));

CREATE INDEX IF NOT EXISTS actor_faol_idx ON actor (company_id) WHERE active;

COMMENT ON TABLE actor IS
    'ERP hodimi -> ijarachi XARITASI. Kimlik ombori EMAS: parol, token '
    'va sessiya YO''Q. Kirish huquqi bermaydi — faqat qarorni kimgadir '
    'bog''laydi.';

-- ---------------------------------------------------------------------
-- 2) Ishonch darajasi — yagona lug'at
-- ---------------------------------------------------------------------
-- Funksiya sifatida, ENUM emas: ENUM ga qiymat qo'shish
-- (`ALTER TYPE ... ADD VALUE`) tranzaksiyada yurmaydi va migratsiya
-- yurgizuvchisi uchun alohida holat bo'lardi.
CREATE OR REPLACE FUNCTION ishonch_yaroqli(d TEXT) RETURNS BOOLEAN
    LANGUAGE sql IMMUTABLE AS $$
    SELECT d IN ('erp_sessiya', 'aktor_elon', 'kompaniya_sessiyasi',
                 'servis', 'kuzatuvdan_oldin')
$$;

COMMENT ON FUNCTION ishonch_yaroqli(TEXT) IS
    'Atribut QANCHALIK ishonchli ekanining lug''ati. `erp_sessiya` — '
    'odam ISBOTLANGAN; `aktor_elon` — odam E''LON QILINGAN, isbotlanmagan; '
    '`kompaniya_sessiyasi` — faqat kompaniya ma''lum, aktor yo''q; '
    '`servis` — odam yo''q; `kuzatuvdan_oldin` — aktor kuzatuvi joriy '
    'etilishidan oldin.';

-- ---------------------------------------------------------------------
-- 3) audit_jurnal — QO'SHISH MUMKIN, O'ZGARTIRISH MUMKIN EMAS
-- ---------------------------------------------------------------------
-- Ustun nomlari `erp.doc_audit` bilan MA'NO JIHATIDAN mos (entity,
-- entity_id, action, old/new, actor, created_at) — bu loyihadagi
-- mavjud naqsh, yangisi o'ylab topilmadi.
CREATE TABLE IF NOT EXISTS audit_jurnal (
    id          BIGSERIAL PRIMARY KEY,
    company_id  INT  NOT NULL REFERENCES company_account(id) ON DELETE CASCADE,

    -- NULL = odam emas (servis kaliti). "Noma'lum odam" EMAS —
    -- farqni `ishonch` ustuni aytadi.
    actor_id    BIGINT,
    ishonch     TEXT NOT NULL,

    amal        TEXT   NOT NULL,
    entity      TEXT   NOT NULL,
    entity_id   BIGINT NOT NULL,

    -- OLDINGI va YANGI holat. JSONB — chunki har jadvalning maydonlari
    -- boshqacha va ularni matnga aylantirish taqqoslashni yo'q qilardi.
    oldin       JSONB,
    keyin       JSONB,

    izoh        TEXT,
    ip          TEXT,
    user_agent  TEXT,
    at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- IJARACHI IZOLYATSIYASI FK DARAJASIDA. `actor_id` NULL bo'lsa
    -- (servis) MATCH SIMPLE bo'yicha cheklov qo'llanmaydi — bu
    -- KUTILGAN xulq.
    CONSTRAINT audit_jurnal_aktor_fk
        FOREIGN KEY (company_id, actor_id) REFERENCES actor (company_id, id)
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='audit_jurnal_ishonch_chk') THEN
        ALTER TABLE audit_jurnal ADD CONSTRAINT audit_jurnal_ishonch_chk
            CHECK (ishonch_yaroqli(ishonch));
    END IF;

    -- AKTOR BOR DEYILSA — BO'LISHI SHART; YO'Q DEYILSA — BO'LMASLIGI.
    -- Busiz `ishonch` va `actor_id` bir-biriga zid bo'lishi mumkin edi:
    -- masalan "servis" deb yozib, yoniga odam qo'yish.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='audit_jurnal_aktor_chk') THEN
        ALTER TABLE audit_jurnal ADD CONSTRAINT audit_jurnal_aktor_chk
            CHECK ((ishonch IN ('erp_sessiya', 'aktor_elon')
                        AND actor_id IS NOT NULL)
                OR (ishonch IN ('servis', 'kuzatuvdan_oldin',
                                'kompaniya_sessiyasi')
                        AND actor_id IS NULL));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='audit_jurnal_amal_chk') THEN
        ALTER TABLE audit_jurnal ADD CONSTRAINT audit_jurnal_amal_chk
            CHECK (length(btrim(amal)) > 0 AND length(btrim(entity)) > 0);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS audit_jurnal_entity_idx
    ON audit_jurnal (company_id, entity, entity_id, at DESC);
CREATE INDEX IF NOT EXISTS audit_jurnal_aktor_idx
    ON audit_jurnal (company_id, actor_id, at DESC);
CREATE INDEX IF NOT EXISTS audit_jurnal_vaqt_idx
    ON audit_jurnal (at DESC);

-- --- APPEND-ONLY ---------------------------------------------------
-- Audit tarixi JIMGINA qayta yozilmasligi kerak. Bu qoida ILOVADA
-- emas, BAZADA: `UPDATE` va `DELETE` trigger bilan to'siladi.
--
-- HALOL CHEKLOV: superuser triggerni o'chira oladi va bu har qanday
-- baza ichidagi himoya uchun o'rinli. To'siq "imkonsiz" degani emas —
-- "tasodifan yoki oddiy ilova xatosi bilan bo'lmaydi va iz qoldirmay
-- ketmaydi" degani.
CREATE OR REPLACE FUNCTION audit_jurnal_ozgarmas() RETURNS trigger
    LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'audit_jurnal FAQAT QO''SHILADI: % taqiqlangan. Tuzatish kerak '
        'bo''lsa YANGI qator qo''shing (amal=''tuzatish'').', TG_OP;
END $$;

DROP TRIGGER IF EXISTS audit_jurnal_ozgarmas_trg ON audit_jurnal;
CREATE TRIGGER audit_jurnal_ozgarmas_trg
    BEFORE UPDATE OR DELETE ON audit_jurnal
    FOR EACH ROW EXECUTE FUNCTION audit_jurnal_ozgarmas();

COMMENT ON TABLE audit_jurnal IS
    'Inson o''zgartirishlari jurnali. FAQAT QO''SHILADI — `UPDATE`/'
    '`DELETE` trigger bilan to''silgan.';

-- ---------------------------------------------------------------------
-- 4) Qaror jadvallariga aktor — KOMPOZIT FK bilan
-- ---------------------------------------------------------------------
ALTER TABLE tender_requirement
    ADD COLUMN IF NOT EXISTS reviewed_actor_id BIGINT,
    ADD COLUMN IF NOT EXISTS reviewed_ishonch  TEXT;

ALTER TABLE tender_routing
    ADD COLUMN IF NOT EXISTS qaror_actor_id BIGINT,
    ADD COLUMN IF NOT EXISTS qaror_ishonch  TEXT;

ALTER TABLE kod_qaror
    ADD COLUMN IF NOT EXISTS actor_id BIGINT,
    ADD COLUMN IF NOT EXISTS ishonch  TEXT;

DO $$
BEGIN
    -- BOSHQA IJARACHINING AKTORINI YOZIB BO'LMAYDI — FK darajasida.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='tender_requirement_aktor_fk') THEN
        ALTER TABLE tender_requirement ADD CONSTRAINT tender_requirement_aktor_fk
            FOREIGN KEY (company_id, reviewed_actor_id)
            REFERENCES actor (company_id, id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='tender_routing_aktor_fk') THEN
        ALTER TABLE tender_routing ADD CONSTRAINT tender_routing_aktor_fk
            FOREIGN KEY (company_id, qaror_actor_id)
            REFERENCES actor (company_id, id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='kod_qaror_aktor_fk') THEN
        ALTER TABLE kod_qaror ADD CONSTRAINT kod_qaror_aktor_fk
            FOREIGN KEY (company_id, actor_id)
            REFERENCES actor (company_id, id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='tender_requirement_ishonch_chk') THEN
        ALTER TABLE tender_requirement ADD CONSTRAINT tender_requirement_ishonch_chk
            CHECK (reviewed_ishonch IS NULL OR ishonch_yaroqli(reviewed_ishonch));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='tender_routing_ishonch_chk') THEN
        ALTER TABLE tender_routing ADD CONSTRAINT tender_routing_ishonch_chk
            CHECK (qaror_ishonch IS NULL OR ishonch_yaroqli(qaror_ishonch));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='kod_qaror_ishonch_chk') THEN
        ALTER TABLE kod_qaror ADD CONSTRAINT kod_qaror_ishonch_chk
            CHECK (ishonch IS NULL OR ishonch_yaroqli(ishonch));
    END IF;

    -- INSON QARORI BO'LSA ISHONCH DARAJASI YOZILGAN BO'LISHI SHART.
    -- `tender_requirement` da bu bugun 0 ta qatorga tegadi (o'lchandi:
    -- approved/rejected/corrected = 0), ya'ni mavjud ma'lumot buzilmaydi.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='tender_requirement_inson_ishonch_chk') THEN
        ALTER TABLE tender_requirement ADD CONSTRAINT tender_requirement_inson_ishonch_chk
            CHECK (review_status NOT IN ('approved', 'rejected', 'corrected')
                OR reviewed_ishonch IS NOT NULL);
    END IF;

    -- MASHINA HOLATIDA AKTOR IZI QOLMASIN. `tender_requirement_mashina_toza_chk`
    -- allaqachon `reviewed_by`/`reviewed_at`/`review_action` uchun shuni
    -- talab qiladi; yangi ustunlar ham o'sha qoidaga bo'ysunadi, aks
    -- holda qiymat o'zgarib holat navbatga qaytganda ESKIRGAN aktor
    -- yorlig'i qolardi va "navbatda, lekin kimdir tasdiqlagan" degan
    -- yarim holat qaytib kelardi.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='tender_requirement_mashina_aktor_chk') THEN
        ALTER TABLE tender_requirement ADD CONSTRAINT tender_requirement_mashina_aktor_chk
            CHECK (review_status NOT IN ('extracted', 'pending_review')
                OR (reviewed_actor_id IS NULL AND reviewed_ishonch IS NULL));
    END IF;
END $$;

-- ---------------------------------------------------------------------
-- 5) Mavjud qarorlar — DALILSIZ AKTOR BERILMAYDI
-- ---------------------------------------------------------------------
-- O'lchandi: 30 ta yo'naltirish qarorida `inson_qaror` bor va ularning
-- KIM tomonidan qilingani NOMA'LUM (`broker_nomi` 0 tasida yozilgan).
--
-- Ularga aktor TAXMIN QILINMAYDI. `kuzatuvdan_oldin` deb belgilanadi —
-- bu "aktor kuzatuvi joriy etilishidan oldin yozilgan, kim qilgani
-- ma'lum emas" degani. Soxta atributdan ko'ra ochiq "noma'lum" afzal.
UPDATE tender_routing
   SET qaror_ishonch = 'kuzatuvdan_oldin'
 WHERE inson_qaror IS NOT NULL AND qaror_ishonch IS NULL;

DO $$
DECLARE n INT;
BEGIN
    SELECT count(*) INTO n FROM tender_routing
     WHERE qaror_ishonch = 'kuzatuvdan_oldin';
    RAISE NOTICE 'Aktori NOMA''LUM yo''naltirish qarorlari: % ta '
                 '(kuzatuvdan_oldin deb belgilandi).', n;
END $$;

-- Endi yo'naltirishda ham qoida qulflanadi.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='tender_routing_inson_ishonch_chk') THEN
        ALTER TABLE tender_routing ADD CONSTRAINT tender_routing_inson_ishonch_chk
            CHECK (inson_qaror IS NULL OR qaror_ishonch IS NOT NULL);
    END IF;
END $$;

-- ---------------------------------------------------------------------
-- 6) Aktor majburiyligi — IJARACHI BO'YICHA, ASTA-SEKIN yoqiladi
-- ---------------------------------------------------------------------
-- `false` (standart) — hozirgi xulq saqlanadi: kompaniya sessiyasi
-- o'zi qaror qo'ya oladi va atribut `kompaniya_sessiyasi` bo'ladi.
-- `true` — inson qarori uchun ANIQ aktor SHART.
--
-- NEGA STANDART `false`: bu patch 22 ta sinov to'plami va ishlab
-- turgan interfeysga tegadi. Majburiyatni darhol yoqish ularni
-- to'xtatardi. Yoqish — ijarachining ONGLI qarori.
ALTER TABLE company_account
    ADD COLUMN IF NOT EXISTS aktor_majburiy BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN company_account.aktor_majburiy IS
    'true bo''lsa inson qarori uchun ANIQ aktor shart '
    '(`kompaniya_sessiyasi` yetarli emas).';

-- ---------------------------------------------------------------------
-- 7) Ko'rinishlar
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_audit_tolik;
CREATE VIEW v_audit_tolik AS
SELECT a.id, a.company_id, a.at, a.amal, a.entity, a.entity_id,
       a.ishonch,
       a.actor_id,
       ak.login  AS actor_login,
       ak.ism    AS actor_ism,
       ak.rol    AS actor_rol,
       ak.manba  AS actor_manba,
       a.oldin, a.keyin, a.izoh, a.ip
  FROM audit_jurnal a
  LEFT JOIN actor ak ON ak.id = a.actor_id AND ak.company_id = a.company_id;

COMMENT ON VIEW v_audit_tolik IS
    'Audit + aktor nomi. `actor_id` NULL bo''lsa odam yo''q edi — '
    'sababi `ishonch` ustunida.';

-- ATRIBUT SIFATI. "Nechta qaror haqiqiy odamga bog'langan" degan
-- savolga javob beradi va uni YASHIRMAYDI.
DROP VIEW IF EXISTS v_atribut_sifati;
CREATE VIEW v_atribut_sifati AS
SELECT 'tender_routing'::TEXT AS jadval, company_id,
       count(*)                                                       AS inson_qarori,
       count(*) FILTER (WHERE qaror_ishonch = 'erp_sessiya')          AS isbotlangan,
       count(*) FILTER (WHERE qaror_ishonch = 'aktor_elon')           AS elon_qilingan,
       count(*) FILTER (WHERE qaror_ishonch = 'kompaniya_sessiyasi')  AS faqat_kompaniya,
       count(*) FILTER (WHERE qaror_ishonch = 'kuzatuvdan_oldin')     AS nomalum,
       count(*) FILTER (WHERE qaror_actor_id IS NOT NULL)             AS aktorli
  FROM tender_routing WHERE inson_qaror IS NOT NULL
 GROUP BY company_id
UNION ALL
SELECT 'tender_requirement', company_id,
       count(*),
       count(*) FILTER (WHERE reviewed_ishonch = 'erp_sessiya'),
       count(*) FILTER (WHERE reviewed_ishonch = 'aktor_elon'),
       count(*) FILTER (WHERE reviewed_ishonch = 'kompaniya_sessiyasi'),
       count(*) FILTER (WHERE reviewed_ishonch = 'kuzatuvdan_oldin'),
       count(*) FILTER (WHERE reviewed_actor_id IS NOT NULL)
  FROM tender_requirement
 WHERE review_status IN ('approved', 'rejected', 'corrected')
 GROUP BY company_id
UNION ALL
SELECT 'kod_qaror', company_id,
       count(*),
       count(*) FILTER (WHERE ishonch = 'erp_sessiya'),
       count(*) FILTER (WHERE ishonch = 'aktor_elon'),
       count(*) FILTER (WHERE ishonch = 'kompaniya_sessiyasi'),
       count(*) FILTER (WHERE ishonch = 'kuzatuvdan_oldin'),
       count(*) FILTER (WHERE actor_id IS NOT NULL)
  FROM kod_qaror WHERE qaror IS NOT NULL
 GROUP BY company_id;

COMMENT ON VIEW v_atribut_sifati IS
    'Inson qarorlarining QANCHASI haqiqiy aktorga bog''langan. '
    '`nomalum` ustuni yashirilmaydi — u qarzning o''lchovi.';

COMMIT;
