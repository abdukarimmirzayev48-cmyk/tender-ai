-- =============================================================================
-- Sxema patch — KIRISH URINISHLARI JURNALI (parol tanlashdan himoya)
-- Ishga tushirish (idempotent, bir necha marta ishlatsa ham xavfsiz):
--   psql "dbname=xtxarid user=postgres host=localhost" -f schema_patch_auth_4.sql
-- Talab: schema_patch_auth_2.sql (kompaniya hisobi).
--
-- MUAMMO: kirish sahifasi cheksiz urinishga ochiq edi. Parol xeshi kuchli
-- (PBKDF2, 240 000 iteratsiya) va u bitta urinishni sekinlashtiradi, lekin
-- HECH NARSA urinishlar SONINI cheklamaydi. Bu — TASHQI eshik: tender-ai
-- ga kompaniya hisobi bilan kiriladi va u ERP dan ko'ra ochiqroq turadi.
--
-- NEGA ALOHIDA JADVAL (`erp.login_attempt` ni ishlatmaymiz):
-- Chegara qoidasi ikki tomonga ham teng ishlaydi — tender-ai `erp.*` ga
-- YOZMAYDI (u faqat ikki VIEW ni o'qiydi). Ikki tizimning kirish jurnali
-- bir jadvalga qo'shilsa, bu qoida buzilardi va "kim kimning ma'lumotini
-- yozdi" degan savol paydo bo'lardi. Har tizim o'z eshigini o'zi qo'riqlaydi.
--
-- NEGA JURNAL, "xato urinishlar soni" USTUNI EMAS:
-- Ustun "5 marta xato" deydi, lekin QACHON, QAYERDAN va QAYSI login bilan
-- ekanini ayta olmaydi. Jurnaldan bloklash HISOBLANADI va shu bilan birga
-- "kim kirishga urindi" degan savolga real javob chiqadi.
--
-- HISOBNI BLOKLAMAYMIZ — bu ataylab:
-- Kompaniya hisobi BITTA. Agar u 5 xatodan keyin yopilsa, loginni bilgan
-- har kim butun kompaniyani tizimdan uzib qo'ya oladi. Bu brute-force dan
-- ko'ra og'irroq zarar. Shuning uchun to'siq VAQTINCHA va (login + IP)
-- juftligi bo'yicha; hisobning o'zi tegilmaydi.
--
-- PAROL BU YERGA YOZILMAYDI — na ochiq, na xesh ko'rinishida.
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.login_attempt (
    id          bigserial PRIMARY KEY,
    -- Login MAVJUD bo'lmasligi ham mumkin: aynan yo'q loginlar bilan
    -- urinish hujumning eng ko'p uchraydigan ko'rinishi, shuning uchun
    -- bu yerda FK yo'q va yozuv baribir saqlanadi.
    username    text        NOT NULL,
    ip          inet,
    ok          boolean     NOT NULL,
    user_agent  text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.login_attempt IS
    'KOMPANIYA kirish urinishlari jurnali. Bloklash shu jadvaldan '
    'HISOBLANADI (alohida hisoblagich ustuni yo''q). Parol saqlanmaydi. '
    'ERP ning o''z jurnali alohida: erp.login_attempt.';
COMMENT ON COLUMN public.login_attempt.username IS
    'Kiritilgan login — mavjud bo''lmasligi ham mumkin (FK ataylab yo''q).';
COMMENT ON COLUMN public.login_attempt.ok IS
    'Urinish muvaffaqiyatlimi. Muvaffaqiyatli kirish oldingi xatolar '
    'zanjirini UZADI.';

-- Bloklash so'rovi aynan shu ikki kesimda o'qiydi: (login + IP) va (IP).
CREATE INDEX IF NOT EXISTS login_attempt_user_idx
    ON public.login_attempt (username, created_at DESC);
CREATE INDEX IF NOT EXISTS login_attempt_ip_idx
    ON public.login_attempt (ip, created_at DESC);
