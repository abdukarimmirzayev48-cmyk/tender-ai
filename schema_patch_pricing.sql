-- =============================================================================
-- Sxema patch — TAVSIYA ETILGAN NARX HISOBI (REJA.md P0-7)
-- Ishga tushirish:
--   psql "dbname=xtxarid user=postgres host=localhost" -f schema_patch_pricing.sql
--
-- MUAMMO: tizim tenderni topadi, tahlil qiladi, "qatnashaymi?" degan savolga
-- javob beradi — lekin "QANCHA NARX QO'YAMIZ?" degan savol ochiq qolgan edi.
-- Broker smetani Excelda yuritardi: tannarx + logistika + zaxira + ustama.
--
-- YECHIM: ikkita jadval.
--   1) `pricing_settings` — kompaniyaning ODATIY parametrlari (bitta faol yozuv).
--      Har tenderda noldan kiritmaslik uchun boshlang'ich qiymat manbai.
--   2) `tender_pricing`  — AYNAN SHU tender uchun saqlangan smeta: kiruvchi
--      parametrlar (JSONB), hisoblangan natija (JSONB) va broker qo'lda
--      kiritgan narx.
--
-- NEGA JSONB: smeta tarkibi (pozitsiyalar ro'yxati, bosqichlar) o'zgaruvchan
-- va faqat BUTUNLIGICHA o'qiladi — uni normallashtirilgan jadvallarga yoyish
-- hech qanday so'rov imkoniyati bermaydi, faqat murakkablik qo'shadi.
-- Hisobot uchun kerak bo'ladigan ikki qiymat (`manual_price`, `currency`)
-- ATAYLAB alohida ustunga chiqarilgan — ular bo'yicha SQL filtr/agregat kerak
-- bo'ladi (masalan "qaysi tenderlarga qo'lda narx qo'yilgan").
--
-- MUHIM: bu patch `company_profile` va `catalog_product` jadvallariga TEGMAYDI.
-- `min_margin_percent` (minimal maqbul foyda) profildan faqat O'QILADI.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. ODATIY PARAMETRLAR — bitta faol yozuv (auth yo'q, `catalog_state` bilan
--    bir xil uslub: singleton CHECK (id = 1)).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pricing_settings (
    id                   INTEGER PRIMARY KEY DEFAULT 1,

    -- Ustama (markup): jami xarajat ustiga qo'shiladigan foyda foizi.
    -- 15% — ehtiyotkor boshlang'ich qiymat; foydalanuvchi o'zgartiradi.
    markup_percent       NUMERIC(6,2) NOT NULL DEFAULT 15,

    -- Xavf zaxirasi: kutilmagan xarajat (kurs, brak, qayta yetkazish) uchun.
    -- Foiz VA belgilangan summa — ikkalasi ham bor, chunki amaliyotda ikkala
    -- usul ham uchraydi ("+5%" yoki "+30 USD"). Ikkalasi birga qo'shiladi.
    risk_reserve_percent NUMERIC(6,2) NOT NULL DEFAULT 5,
    risk_reserve_fixed   NUMERIC(18,2) NOT NULL DEFAULT 0,

    -- Logistika: yetkazib berish xarajati. Yuqoridagi kabi foiz + belgilangan.
    logistics_percent    NUMERIC(6,2) NOT NULL DEFAULT 0,
    logistics_fixed      NUMERIC(18,2) NOT NULL DEFAULT 0,

    -- QQS. O'zbekistonda 2026 yil holatiga 12% — LEKIN bu qat'iy emas:
    -- nol stavkali/ozod operatsiyalar bor, import sxemasi boshqacha bo'lishi
    -- mumkin. Shuning uchun DEFAULT, tahrirlanadigan.
    vat_percent          NUMERIC(6,2) NOT NULL DEFAULT 12,

    -- Odatiy valyuta: 'UZS' | 'USD' | NULL (har tenderda alohida tanlanadi).
    -- KURS KONVERTATSIYASI YO'Q — turli valyutali qiymatlar QO'SHILMAYDI.
    currency             CHAR(3),

    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pricing_settings_singleton CHECK (id = 1)
);

-- Bitta yozuv doim mavjud bo'lsin — GET /pricing/settings hech qachon
-- bo'sh qaytarmaydi, frontend "yo'q" holatini alohida qayta ishlamaydi.
INSERT INTO pricing_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

COMMENT ON TABLE  pricing_settings IS
    'Narx hisobining odatiy parametrlari (bitta faol yozuv). Har tender uchun '
    'boshlang''ich qiymat manbai; tenderda o''zgartirilgani tender_pricing.inputs da.';
COMMENT ON COLUMN pricing_settings.vat_percent IS
    'QQS foizi. O''zbekistonda odatda 12%, lekin ozod/nol stavkali holatlar bor '
    '— shuning uchun tahrirlanadi.';


-- ---------------------------------------------------------------------------
-- 2. TENDER SMETASI — har tender uchun bitta saqlangan hisob
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tender_pricing (
    tender_id    BIGINT PRIMARY KEY REFERENCES tender(id) ON DELETE CASCADE,

    -- Kiruvchi parametrlar — `api.pricing.calculate()` ga berilgan AYNAN
    -- o'sha obyekt: {items:[{name,qty,unit_cost,unit,currency}],
    -- markup_percent, risk_reserve_percent, risk_reserve_fixed,
    -- logistics_percent, logistics_fixed, vat_percent, currency,
    -- manual_price, budget, budget_currency, min_margin_percent}.
    -- Shu bilan hisob HAR DOIM qayta tiklanadi (audit): saqlangan natija
    -- shubhali bo'lsa, kiruvchidan qayta hisoblab solishtirish mumkin.
    inputs       JSONB NOT NULL,

    -- Hisoblangan natija: {ok, currency, steps:[{key,label,rule,formula,value}],
    -- totals:{...}, warnings:[...], errors:[...]}.
    -- `steps` ATAYLAB saqlanadi — TZ ning shaffoflik talabi: foydalanuvchi
    -- keyin ham QAYSI formula bilan qanday natija chiqqanini ko'ra oladi.
    result       JSONB NOT NULL,

    -- Broker qo'lda kiritgan yakuniy narx (NULL = tizim tavsiyasi qabul
    -- qilingan). `inputs` ichida ham bor — bu yerda ALOHIDA ustun, chunki
    -- u bo'yicha SQL so'rov kerak bo'ladi ("qo'lda tuzatilgan smetalar").
    manual_price NUMERIC(18,2),

    -- Smeta valyutasi — `inputs.currency` nusxasi, hisobot uchun.
    currency     CHAR(3),

    -- Brokerning izohi: nega narx o'zgartirildi ("raqobatchi past qo'yadi").
    note         TEXT,

    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tender_pricing_updated ON tender_pricing(updated_at DESC);

COMMENT ON COLUMN tender_pricing.inputs IS
    'Hisobning kiruvchi parametrlari — natijani qayta tiklash uchun yetarli (audit).';
COMMENT ON COLUMN tender_pricing.result IS
    'Hisob natijasi, bosqichlar ro''yxati bilan. Qora quti bo''lmasligi uchun '
    'har bosqichning formulasi ham saqlanadi.';
