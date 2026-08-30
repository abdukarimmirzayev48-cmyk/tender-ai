"""
Hujjatlar to'liqligi cheklisti (P0-8) sinovi.

Ishga tushirish (loyiha ildizidan):
    .venv/Scripts/python.exe _tests/compliance_test.py

Uch qism:
  1) SOF MANTIQ — DB'siz: naqsh aniqlash (uch alifboda), bazaviy ro'yxat,
     "bazada bor/yo'q", muddat holatlari, bo'sh matn.
  2) SHABLON — DB'siz: .xlsx/.csv yasash, to'ldirilgan faylni qayta o'qish
     (round-trip), sana va hujjat turini tanish, xato/ogohlantirishlar.
  3) HAQIQIY BAZA — company_document ga sinov yozuvlari qo'yiladi, bir necha
     haqiqiy tenderда cheklist yig'iladi, so'ng yozuvlar TOZALANADI.

Uvicorn ISHGA TUSHIRILMAYDI — modul to'g'ridan-to'g'ri chaqiriladi.
"""
import datetime as _dt
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# KONSOL KODLASHI — Windows kod sahifasidan MUSTAQIL UTF-8.
#
# Chiqish QUVUR yoki FAYLGA yo'naltirilganda (ya'ni CI da) Python
# `locale.getpreferredencoding()` ni oladi — bu mashinada `cp1251`.
# O'zbek kirill (`ҳ`, `қ`, `ў`) va to'liq kenglikdagi belgilar
# (`）`) u yerda YO'Q va chop etish `UnicodeEncodeError` bilan
# BUTUN TO'PLAMNI o'ldiradi. `import_test` aynan shu sababdan
# 143 ta tekshiruvni bajarmasdan yiqilardi. Tafsilot: _tests/konsol.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import konsol  # noqa: E402

konsol.sozla()

# Windows konsoli cp1251 da ochiladi va o'zbek KIRILL harflarini (ҳ, қ, ў)
# chiqara olmaydi — sinov xabari o'rniga UnicodeEncodeError chiqardi.
# Alifbo bu modulning asosiy mavzusi, shuning uchun chiqishni utf-8 ga
# o'tkazamiz; qo'llab-quvvatlanmasa `replace` xatoga yo'l qo'ymaydi.

from dotenv import load_dotenv

load_dotenv()

from api import compliance as C  # noqa: E402

TODAY = _dt.date(2026, 7, 28)

_fail = 0
_pass = 0


def check(cond, msg, extra=""):
    global _fail, _pass
    if cond:
        _pass += 1
        print(f"  OK   {msg}")
    else:
        _fail += 1
        print(f"  XATO {msg}" + (f"\n       -> {extra}" if extra else ""))


def head(t):
    print(f"\n=== {t} ===")


# ---------------------------------------------------------------------------
# 1. NAQSH ANIQLASH — uch alifbo
# ---------------------------------------------------------------------------
RU = ("Заявка должна включать: свидетельство о государственной регистрации, "
      "доверенность на подписанта, лицензию на осуществление деятельности, "
      "сертификат соответствия, гарантийное письмо, банковские реквизиты, "
      "справку об отсутствии налоговой задолженности.")
UZ_LAT = ("Ariza tarkibiga quyidagilar kiritiladi: davlat ro'yxatidan o'tganlik "
          "guvohnomasi, ishonchnoma, faoliyat turi uchun litsenziya, muvofiqlik "
          "sertifikati, kafolat xati, bank rekvizitlari.")
UZ_CYR = ("Ариза таркибига қуйидагилар киритилади: давлат рўйхатидан ўтганлик "
          "тўғрисидаги гувоҳнома, ишончнома, фаолият учун лицензия, мувофиқлик "
          "сертификати, кафолат хати, банк реквизитлари.")

SIX = {"reg_certificate", "power_of_attorney", "license",
       "conformity_certificate", "guarantee_letter", "bank_details"}


def test_detect():
    head("1. Naqsh aniqlash — ruscha / o'zbek lotin / o'zbek kirill")
    for label, text in (("ruscha kirill", RU), ("o'zbek lotin", UZ_LAT),
                        ("o'zbek kirill", UZ_CYR)):
        got = {d["doc_type"] for d in C.detect_required([("sinov", text)])}
        check(SIX <= got, f"{label}: 6 ta bazaviy hujjat topildi",
              f"topilmadi: {sorted(SIX - got)}")

    # translit: o'zak bitta alifboda yozilgan bo'lsa ham ikkalasi topiladi
    got_ru = {d["doc_type"] for d in C.detect_required([("s", RU)])}
    check("tax_reference" in got_ru, "ruscha matnda soliq ma'lumotnomasi topildi")

    head("1b. Dalil (evidence) — qaysi matndan olingani ko'rinadi")
    det = C.detect_required([{"source": "Tender izohi", "text": UZ_LAT}])
    d0 = next(d for d in det if d["doc_type"] == "conformity_certificate")
    check(d0["source"] == "Tender izohi", "dalil manbasi ko'rsatilgan")
    check("sertifikat" in d0["evidence"].lower(),
          "dalil ASL matn bo'lagi (yig'ilgan emas)", d0["evidence"])
    check(0 < d0["confidence"] <= 100, "confidence berilgan")

    head("1c. SOXTA moslik bo'lmasligi (haqiqiy bazadan olingan holatlar)")
    fp = [
        ("в соответствии с Заключением ГУП ЦКЭПиИК", "conformity_certificate",
         "«...ga muvofiq» — sertifikat talabi emas"),
        ("Лицензия (бессрочная) для программного обеспечения",
         "license", "sotib olinayotgan dastur litsenziyasi"),
        ("Гарантийные обязательства. Гарантийный срок эксплуатации товара "
         "не менее 24 месяцев", "guarantee_letter", "tovar kafolat muddati"),
        ("для обработки и передачи аналоговых и цифровых данных",
         "tax_reference", "«анаЛОГОВых» — «налогов» emas"),
        ("Разработка финансовой модели. Отчет по разработке графиков",
         "financial_report", "xarid qilinayotgan xizmat"),
        ("постановление о развитии банковской системы Республики",
         "bank_details", "bank tizimi — rekvizit emas"),
        ("комплекс средств сбора и регистрации данных, датчик",
         "reg_certificate", "«регистрация данных» — guvohnoma emas"),
    ]
    for text, code, why in fp:
        got = {d["doc_type"] for d in C.detect_required([("s", text)])}
        check(code not in got, f"soxta moslik yo'q: {why}", f"topildi: {got}")


# ---------------------------------------------------------------------------
# 2. BAZAVIY RO'YXAT va BO'SH MATN
# ---------------------------------------------------------------------------
def test_base_list():
    head("2. Bazaviy ro'yxat DOIM chiqadi + bo'sh matnda halol holat")
    res = C.build_checklist([], [], today=TODAY)
    codes = [i["doc_type"] for i in res["items"]]
    check(set(codes) == set(C.BASE_CODES), "bo'sh tenderда bazaviy 6 ta band",
          str(codes))
    check(res["summary"]["detected_from_tender"] is False,
          "detected_from_tender = False")
    check("topilmadi" in res["summary"]["note"],
          "xabar HALOL: 'aniq hujjat talabi topilmadi'", res["summary"]["note"])
    check(all(i["required_by"] == "bazaviy" for i in res["items"]),
          "hammasi required_by='bazaviy'")
    check(all(i["evidence"] for i in res["items"]),
          "bazaviy bandda ham dalil (manbasi) yozilgan")

    # bo'sh matn ro'yxati — umuman matn yo'q
    check(C.detect_required([]) == [], "bo'sh manba ro'yxati -> bo'sh natija")
    check(C.detect_required([("s", None), ("s", "")]) == [],
          "bo'sh matnlar -> bo'sh natija")

    head("2b. Tenderда topilgani bazaviy ro'yxat USTIGA qo'shiladi")
    det = C.detect_required([("Tender izohi", RU)])
    res2 = C.build_checklist(det, [], today=TODAY)
    codes2 = {i["doc_type"] for i in res2["items"]}
    check("tax_reference" in codes2, "bazaviy bo'lmagan tur qo'shildi")
    check(set(C.BASE_CODES) <= codes2, "bazaviy turlar joyida qoldi")
    tr = next(i for i in res2["items"] if i["doc_type"] == "tax_reference")
    check(tr["required_by"] == "tender", "topilgan band required_by='tender'")
    check(res2["summary"]["detected_from_tender"] is True,
          "detected_from_tender = True")


# ---------------------------------------------------------------------------
# 3. "BAZADA BOR" va MUDDAT holatlari
# ---------------------------------------------------------------------------
def doc(code, days=None, **kw):
    """Sinov hujjati. days=None -> muddatsiz; aks holda TODAY dan siljish."""
    return {
        "id": kw.get("id", 1), "doc_type": code, "name": kw.get("name", code),
        "number": None, "issued_at": None,
        "valid_until": None if days is None else TODAY + _dt.timedelta(days=days),
        "file_name": None, "file_ref": None, "note": None,
    }


def test_status():
    head("3. Bazada bor / yo'q va muddat holatlari")
    docs = [
        doc("reg_certificate"),                 # muddatsiz
        doc("license", days=400, id=2),         # uzoq — ok
        doc("conformity_certificate", days=-5, id=3),   # muddati tugagan
        doc("bank_details", days=10, id=4),     # tugashiga oz qoldi
    ]
    res = C.build_checklist([], docs, today=TODAY)
    st = {i["doc_type"]: i for i in res["items"]}

    check(st["reg_certificate"]["in_base"] is True, "bazada BOR aniqlandi")
    check(st["reg_certificate"]["status"] == "ok",
          "muddatsiz hujjat = ok (ma'lumot yo'q emas)")
    check(st["license"]["status"] == "ok", "uzoq muddatli = ok")
    check(st["conformity_certificate"]["status"] == "expired",
          "muddati tugagan = expired", st["conformity_certificate"]["status"])
    check(st["conformity_certificate"]["in_base"] is True,
          "muddati tugagan bo'lsa ham 'bazada bor' rost")
    check(st["bank_details"]["status"] == "expiring_soon",
          "10 kun qolgan = expiring_soon", st["bank_details"]["status"])
    check(st["bank_details"]["days_left"] == 10, "days_left to'g'ri")
    check(st["power_of_attorney"]["in_base"] is False,
          "yo'q hujjat: in_base=False")
    check(st["power_of_attorney"]["status"] == "missing", "yo'q hujjat = missing")
    check(st["power_of_attorney"]["document"] is None, "yo'q hujjatда document=None")

    s = res["summary"]
    check(s["total"] == 6, "jami 6 band")
    check(s["ready"] == 2 and s["expired"] == 1 and s["expiring_soon"] == 1
          and s["missing"] == 2, "xulosa sanoqlari to'g'ri", str(s))
    check(s["blocking"] == 3, "blocking = missing + expired", str(s["blocking"]))

    head("3b. Chegara holatlari — QOIDA TO'LIQ QOPLANADI")
    #
    # QOIDA (api/compliance.doc_status docstring i bilan AYNAN bir xil):
    #
    #   BIZNES KUNI  Asia/Tashkent (UTC+5), `compliance.bugun()`
    #   valid_until  hujjat yaroqli OXIRGI kun, va u KIRADI
    #
    #       hujjat yo'q                            -> missing
    #       valid_until IS NULL                    -> ok (MUDDATSIZ)
    #       valid_until <  bugun                   -> expired
    #       0 <= (valid_until - bugun) <= CHEGARA  -> expiring_soon
    #       (valid_until - bugun) >  CHEGARA       -> ok
    #
    #   USTUVORLIK: `expired` `expiring_soon` DAN OLDIN.
    #   CHEGARA IKKI TOMONDAN KIRADI.
    CH = C.EXPIRING_SOON_DAYS
    chegaralar = [
        (None,   "ok",            "muddatsiz (NULL) -> ok, 'noma'lum' EMAS"),
        (-30,    "expired",       "30 kun oldin tugagan -> expired"),
        (-1,     "expired",       "KECHA tugagan -> expired"),
        (0,      "expiring_soon", "BUGUN tugaydi -> expiring_soon "
                                  "(kun oxirigacha yaroqli)"),
        (1,      "expiring_soon", "+1 kun -> expiring_soon"),
        (6,      "expiring_soon", "+6 kun -> expiring_soon"),
        (7,      "expiring_soon", "+7 kun -> expiring_soon"),
        (CH - 1, "expiring_soon", f"+{CH - 1} kun (chegaradan bir kun oldin)"),
        (CH,     "expiring_soon", f"+{CH} kun — CHEGARA O'ZI KIRADI"),
        (CH + 1, "ok",            f"+{CH + 1} kun — chegaradan tashqari -> ok"),
        (365,    "ok",            "+365 kun -> ok"),
    ]
    for kun, kutilgan, izoh in chegaralar:
        natija = C.doc_status(doc("x", days=kun), TODAY)
        check(natija == kutilgan, izoh, f"olindi: {natija}")
        # `days_left` HOLAT bilan bir xil sanaga qarab hisoblanadi.
        kutilgan_kun = None if kun is None else kun
        check(C._days_left(doc("x", days=kun)["valid_until"], TODAY)
              == kutilgan_kun,
              f"days_left({kun}) = {kutilgan_kun}")

    check(C.doc_status(None, TODAY) == "missing", "hujjat yo'q -> missing")
    check(C.doc_status({}, TODAY) == "missing", "bo'sh dict -> missing")
    check(C.doc_status({"valid_until": None}, TODAY) == "ok",
          "valid_until=None -> ok (muddatsiz)")
    check(C.doc_status({"valid_until": ""}, TODAY) == "ok",
          "bo'sh satr ham muddatsiz deb qaraladi")
    # ISO satr ham qabul qilinishi kerak (DB drayveri date beradi, JSON satr)
    check(C.doc_status({"valid_until": "2020-01-01"}, TODAY) == "expired",
          "ISO satr sana ham tushuniladi")
    check(C.doc_status({"valid_until": TODAY.isoformat()}, TODAY)
          == "expiring_soon", "ISO satr: bugungi sana -> expiring_soon")
    # `datetime` (mintaqasiz va mintaqali) ham SANAGA aylanadi.
    check(C.doc_status({"valid_until": _dt.datetime.combine(
              TODAY, _dt.time(23, 59))}, TODAY) == "expiring_soon",
          "mintaqasiz datetime -> sana sifatida o'qiladi")
    check(C.doc_status({"valid_until": _dt.datetime.combine(
              TODAY, _dt.time(3, 0), tzinfo=C.BIZNES_TZ)}, TODAY)
          == "expiring_soon", "mintaqali datetime -> biznes sanasi")

    head("3b-2. VAQT MINTAQASI — biznes kuni Asia/Tashkent")
    #
    # O'LCHANGAN NUQSON: `doc_status()` `datetime.date.today()` ni
    # ishlatardi — u JARAYONNING mintaqasiga qarab ishlaydi, baza esa
    # `Asia/Tashkent` da yuradi. Server UTC da bo'lsa har kuni
    # 19:00–24:00 UTC oralig'ida sana BIR KUN orqada bo'lardi va
    # sinovlar kunning soatiga qarab goh o'tib, goh yiqilardi.
    check(C.BIZNES_TZ.utcoffset(None) == _dt.timedelta(hours=5),
          "biznes mintaqasi UTC+5 (yozgi vaqt yo'q)")
    kutilgan_bugun = (_dt.datetime.now(_dt.timezone.utc)
                      .astimezone(C.BIZNES_TZ).date())
    check(C.bugun() == kutilgan_bugun,
          "bugun() Toshkent sanasini beradi", f"{C.bugun()} vs {kutilgan_bugun}")
    src = io.open(os.path.join(ROOT, "api", "compliance.py"),
                  encoding="utf-8").read()
    kod = " ".join(ln for ln in src.splitlines()
                   if not ln.lstrip().startswith("#"))
    check("_dt.date.today()" not in kod,
          "kodda `date.today()` QOLMADI — sana yagona manbadan",
          "u serverning mintaqasiga bog'liq va mo'rt sinov manbai edi")

    head("3b-3. ENG YAXSHI NUSXA — muddatsiz hujjat ustun keladi")
    #
    # AYNAN SHU XATTI-HARAKAT 2026-08-27 dan beri beshta integratsiya
    # tekshiruvini yiqitgan edi: sinov o'z 7 kunlik fixture'ini
    # kutardi, kompaniyada esa MUDDATSIZ haqiqiy hujjat bor edi.
    # Xatti-harakat TO'G'RI — amal qiluvchi muddatsiz hujjat bo'lsa,
    # band "tugayapti" deb ogohlantirilishi noto'g'ri bo'lardi.
    juftlik = [doc("bank_details", days=7, id=1, name="tugayapti"),
               doc("bank_details", days=None, id=2, name="muddatsiz")]
    eng = C._pick_best(juftlik, TODAY)
    check(eng["name"] == "muddatsiz",
          "muddatsiz nusxa tugayaptidan USTUN")
    check(C.doc_status(eng, TODAY) == "ok",
          "natijada band `ok` bo'ladi — bu TO'G'RI")
    # Tartib TESKARI bo'lsa ham natija bir xil (tanlov barqaror).
    check(C._pick_best(list(reversed(juftlik)), TODAY)["name"] == "muddatsiz",
          "tanlov ro'yxat TARTIBIGA bog'liq emas")
    # Muddati tugagan + tugayapti -> tugayapti tanlanadi.
    check(C._pick_best([doc("x", days=-10, id=1, name="tugagan"),
                        doc("x", days=5, id=2, name="tugayapti")],
                       TODAY)["name"] == "tugayapti",
          "tugagan nusxa tufayli band bloklanmaydi")
    # Ikki muddatli nusxadan UZOQROG'I tanlanadi.
    check(C._pick_best([doc("x", days=5, id=1, name="yaqin"),
                        doc("x", days=25, id=2, name="uzoq")],
                       TODAY)["name"] == "uzoq",
          "ikki tugayaptidan UZOQROG'I tanlanadi")

    head("3c. Eski va yangi nusxa birga — YANGISI tanlanadi")
    two = [doc("license", days=-100, id=9, name="eski"),
           doc("license", days=200, id=10, name="yangi")]
    r = C.build_checklist([], two, today=TODAY)
    lic = next(i for i in r["items"] if i["doc_type"] == "license")
    check(lic["status"] == "ok" and lic["document"]["name"] == "yangi",
          "eski nusxa tufayli band 'expired' bo'lib qolmadi",
          str(lic["status"]))

    head("3d. Cheklistga kirmagan hujjatlar alohida ro'yxatда")
    r = C.build_checklist([], [doc("charter", id=11, name="Ustav")], today=TODAY)
    check(len(r["extra_documents"]) == 1 and
          r["extra_documents"][0]["doc_type"] == "charter",
          "extra_documents to'ldirildi")
    check(all(i["doc_type"] != "charter" for i in r["items"]),
          "u majburiy bandlar orasiga qo'shilmadi")


# ---------------------------------------------------------------------------
# 4. HAQIQIY BAZA
# ---------------------------------------------------------------------------
TEST_COMPANY_ID = None   # test_db() da to'ldiriladi


def test_db():
    head("4. Haqiqiy baza — company_document + haqiqiy tenderlar")
    from api import auth, db

    db.init_pool()
    # J1.6: hujjatlar KOMPANIYAGA bog'landi. Sinov mavjud faol hisobdan
    # foydalanadi — o'zi hisob yaratmaydi.
    global TEST_COMPANY_ID
    TEST_COMPANY_ID = auth.sole_company_id()
    print(f"     (sinov kompaniyasi: id={TEST_COMPANY_ID})")
    ids = []
    try:
        # --- sinov yozuvlari (keyin O'CHIRILADI) ---
        # DIQQAT: sanalar HAQIQIY bugundan siljitiladi, yuqoridagi qotirilgan
        # TODAY dan emas. Sabab: `compliance.check()` ish vaqtidagi funksiya
        # va sanani parametr sifatida olmaydi — u har doim haqiqiy bugunga
        # qaraydi. Fixture qotirilgan sanaga bog'lansa, sinov shu sanadan
        # keyin o'z-o'zidan yiqila boshlaydi (aynan shunday bo'lgan edi).
        real_today = _dt.date.today()
        seed = [
            ("reg_certificate", "[SINOV] Guvohnoma", None),
            ("license", "[SINOV] Litsenziya", real_today + _dt.timedelta(days=365)),
            ("conformity_certificate", "[SINOV] Sertifikat",
             real_today - _dt.timedelta(days=3)),     # muddati tugagan
            ("bank_details", "[SINOV] Rekvizitlar",
             real_today + _dt.timedelta(days=7)),     # tugayapti
        ]
        for code, name, vu in seed:
            row = db.execute_returning(C.DOC_INSERT_SQL, {
                "company_id": TEST_COMPANY_ID,
                "doc_type": code, "name": name, "number": "TEST-1",
                "issued_at": None, "valid_until": vu,
                "file_name": None, "file_ref": None, "note": "avtomatik sinov",
            })
            ids.append(row["id"])
        check(len(ids) == 4, "4 ta sinov hujjati yozildi")

        rows = db.query(C.DOCS_LIST_SQL, {"company_id": TEST_COMPANY_ID})
        check(any(r["name"] == "[SINOV] Guvohnoma" for r in rows),
              "DOCS_LIST_SQL yozuvlarni qaytardi")

        # FIXTURE NING O'ZI to'g'ri baholanadimi — bu `check()` ning
        # eng yaxshi hujjat tanlashidan MUSTAQIL tekshiruv.
        rekv = next((r for r in rows if r["name"] == "[SINOV] Rekvizitlar"), None)
        check(rekv is not None, "7 kunlik fixture bazada bor")
        if rekv:
            check(C.doc_status(rekv, real_today) == "expiring_soon",
                  "7 kun qolgan fixture -> expiring_soon",
                  C.doc_status(rekv, real_today))
            check(C.shape_document(rekv, real_today)["days_left"] == 7,
                  "fixture days_left = 7")

        # --- haqiqiy tenderlar ---
        tids = [r["id"] for r in db.query(
            "SELECT id FROM tender ORDER BY publicated_at DESC NULLS LAST LIMIT 5")]
        check(len(tids) > 0, "sinov uchun tender topildi")
        for tid in tids:
            res = C.check(tid)
            s = res["summary"]
            st = {i["doc_type"]: i["status"] for i in res["items"]}
            print(f"       tender {tid}: bandlar={s['total']} tayyor={s['ready']} "
                  f"yo'q={s['missing']} tugagan={s['expired']} "
                  f"tugayapti={s['expiring_soon']} "
                  f"tenderдan={s['detected_count']} manbalar={len(res['text_sources'])}")
            check(s["total"] >= 6, f"tender {tid}: kamida 6 band")
            check(st.get("conformity_certificate") == "expired",
                  f"tender {tid}: muddati tugagan sertifikat expired")
            check(st.get("reg_certificate") == "ok",
                  f"tender {tid}: muddatsiz guvohnoma ok")
            check(st.get("power_of_attorney") == "missing",
                  f"tender {tid}: yo'q ishonchnoma missing")

            # ═══════════════ NEGA `bank_details` ENDI BOSHQACHA ═══════════════
            #
            # ILGARI shu yerda `st["bank_details"] == "expiring_soon"` turardi
            # va u 2026-08-27 dan beri BESH TENDERDA HAM YIQILARDI.
            #
            # SABAB — MAHSULOT XATOSI EMAS, SINOV IZOLYATSIYASI:
            # sinov o'z fixture'ini REAL kompaniyaning hujjatlari orasiga
            # yozadi va o'zining 7 kunlik `bank_details` yozuvi YAGONA deb
            # hisoblardi. 2026-08-27 da kompaniya HAQIQIY "BARAKA PROFIT
            # bank rekvizitlari" hujjatini import qildi — `valid_until`
            # NULL, ya'ni MUDDATSIZ.
            #
            # `_pick_best()` bir turdagi hujjatlardan ENG YAROQLISINI
            # tanlaydi (ok=0 > expiring_soon=1). Muddatsiz hujjat
            # to'g'ri ravishda ustun keladi va band `ok` bo'ladi.
            # Kompaniyada amal qiluvchi muddatsiz rekvizit BOR — u
            # "tugayapti" deb ogohlantirilishi XATO bo'lardi.
            #
            # Ya'ni ESKI TEKSHIRUV NOTO'G'RI NARSANI kutayotgan edi.
            # Kutilgan qiymatni "yashil bo'lsin" deb o'zgartirmaymiz —
            # uning O'RNIGA HAQIQIY SHARTNOMA tekshiriladi:
            #   band holati == O'SHA TURDAGI ENG YAXSHI hujjat holati
            # Bu invariant boshqa hujjatlar borligiga BOG'LIQ EMAS.
            bank_docs = [r for r in rows if r["doc_type"] == "bank_details"]
            kutilgan = C.doc_status(C._pick_best(bank_docs, real_today),
                                    real_today)
            check(st.get("bank_details") == kutilgan,
                  f"tender {tid}: bank_details holati ENG YAXSHI hujjatniki "
                  f"({kutilgan})", str(st.get("bank_details")))

        # --- talabi aniqlanadigan tender (technical_proposal) ---
        found = db.query("""
            SELECT DISTINCT i.tender_id AS id FROM tender_item i
            WHERE i.spec ILIKE '%%texnik topshiriq%%' LIMIT 1""")
        if found:
            res = C.check(found[0]["id"])
            check(res["summary"]["detected_from_tender"] is True,
                  f"tender {found[0]['id']}: matndan talab aniqlandi")
            det = [i for i in res["items"] if i["required_by"] == "tender"]
            check(bool(det) and all(i["evidence"] for i in det),
                  "aniqlangan bandda dalil bor",
                  str(det[0]["evidence"])[:80] if det else "")

        # --- yangilash / o'chirish yo'li ---
        upd = db.execute_returning(C.DOC_UPDATE_SQL, {
            "company_id": TEST_COMPANY_ID,
            "id": ids[0], "doc_type": "reg_certificate",
            "name": "[SINOV] Guvohnoma-2", "number": "TEST-2",
            "issued_at": None, "valid_until": None,
            "file_name": None, "file_ref": None, "note": None})
        check(upd and upd["name"] == "[SINOV] Guvohnoma-2", "UPDATE ishladi")

    finally:
        # --- TOZALASH: sinov yozuvlari bazada qolmasin ---
        from api import db as _db
        for i in ids:
            _db.execute_returning(C.DOC_DELETE_SQL,
                                  {"id": i, "company_id": TEST_COMPANY_ID})
        left = _db.query("SELECT id FROM company_document WHERE note='avtomatik sinov' "
                         "OR name LIKE '[SINOV]%%'")
        check(len(left) == 0, "sinov yozuvlari bazadan tozalandi", str(left))
        _db.close_pool()


def _csv_bytes(rows):
    """Qatorlardan .csv baytlari (shablon bilan bir xil dialekt)."""
    import csv as _csv
    import io as _io
    buf = _io.StringIO()
    w = _csv.writer(buf, delimiter=";", lineterminator="\r\n")
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode("utf-8-sig")


def _parse(data, filename):
    """Fayl -> (qabul qilinganlar, xatolar, ogohlantirishlar)."""
    from api import importer
    rows, _fmt = importer.read_table(data, filename)
    hi, mapping, _unknown = C._find_header(rows)
    return C.parse_document_rows(rows, mapping, hi)


def test_template():
    """SHABLON: yasash -> qayta o'qish -> tanish qoidalari (DB'siz)."""
    print("\n== SHABLON: yasash va qayta o'qish ==")

    # --- Shablonning o'zi: hamma kanonik tur bo'lishi shart -----------------
    xlsx, csvb = C.template_xlsx(), C.template_csv()
    check(xlsx[:2] == b"PK", "xlsx yasaldi (ZIP imzosi)")
    check(len(csvb) > 200 and csvb[:3] == b"\xef\xbb\xbf", "csv yasaldi (BOM bilan)")

    for name, blob in (("xlsx", xlsx), ("csv", csvb)):
        ok, errs, warns = _parse(blob, "hujjatlar_shablon." + name)
        # Bo'sh shablonda faqat misol qator o'tadi, xato bo'lmasligi shart:
        # ya'ni tizim O'ZI yasagan faylni O'ZI muammosiz o'qiy oladi.
        check(len(errs) == 0, f"{name}: bo'sh shablonda xato yo'q", str(errs[:1]))
        # O'ZGARTIRILMAGAN shablon HECH NARSA import qilmasligi kerak: misol
        # qator ham, bo'sh qatorlar ham foydalanuvchining ma'lumoti emas.
        check(len(ok) == 0, f"{name}: tegilmagan shablondan 0 ta hujjat "
                            f"({len(ok)} ta)", str([r['name'] for r in ok]))
        check(any("misol qator" in w["message"] for w in warns),
              f"{name}: misol qator haqida ogohlantirish bor",
              str([w["message"][:50] for w in warns]))
        check(any(str(len(C.DOC_TYPES)) in w["message"] for w in warns),
              f"{name}: to'ldirilmagan qatorlar BITTA yig'ma xabar bo'ldi",
              str([w["message"][:50] for w in warns]))

    # Misol qatorning BITTA katagi tahrirlansa — u foydalanuvchi ma'lumoti
    rows_ = C._template_rows()
    edited = [C.TEMPLATE_HEADERS, [*rows_[0]]]
    edited[1][1] = "Bizning guvohnomamiz"          # faqat "Hujjat nomi"
    ok_e, errs_e, _w = _parse(_csv_bytes(edited), "tahrirlangan.csv")
    check(len(ok_e) == 1 and not errs_e and ok_e[0]["name"] == "Bizning guvohnomamiz",
          "misol qator tahrirlansa — normal import bo'ladi", str(errs_e[:1]))

    # Shablon ro'yxati DOC_TYPES bilan bir xilmi (ikkinchi ro'yxat yo'q)
    rows = C._template_rows()
    labels = [r[0] for r in rows[1:]]
    check(labels == [d["label"] for d in C.DOC_TYPES],
          f"shablonda {len(C.DOC_TYPES)} ta kanonik tur, tartibi ham bir xil")

    # --- Hujjat turini tanish: uch alifbo + kod + qavsli izoh ---------------
    for raw, want in (
        ("Litsenziya / faoliyat ruxsatnomasi", "license"),
        ("Литсензия", "license"),               # o'zbek kirill
        ("Лицензия", "license"),                # rus
        ("license", "license"),                 # kod
        ("Litsenziya (qurilish)", "license"),   # qavsli izoh
        ("Сертификат соответствия", "conformity_certificate"),
        ("Гувоҳнома", "reg_certificate"),
        ("Доверенность", "power_of_attorney"),
        ("Банковские реквизиты", "bank_details"),
    ):
        check(C.match_doc_type(raw) == want, f"tur tanildi: {raw!r} -> {want}",
              str(C.match_doc_type(raw)))
    check(C.match_doc_type("Nomalum tur") is None, "notanish tur -> None (taxmin yo'q)")
    check(C.match_doc_type("") is None, "bo'sh katak -> None")

    # --- Sana o'qish -------------------------------------------------------
    for raw, want in (("31.12.2026", _dt.date(2026, 12, 31)),
                      ("2026-12-31", _dt.date(2026, 12, 31)),
                      ("31/12/2026", _dt.date(2026, 12, 31)),
                      (_dt.date(2026, 12, 31), _dt.date(2026, 12, 31))):
        d, e, p = C.parse_date(raw)
        check(d == want and not e, f"sana o'qildi: {raw!r}", f"{d} / {e}")
    d, e, p = C.parse_date("muddatsiz")
    check(d is None and not e and p, "“muddatsiz” -> muddatsiz bayrog'i")
    d, e, p = C.parse_date("aniqmas")
    check(d is None and e and not p, "noto'g'ri sana -> XATO (taxmin qilinmaydi)", str(e))

    # --- To'ldirilgan shablon: to'g'ri va xato qatorlar ---------------------
    HDR = C.TEMPLATE_HEADERS
    filled = [
        HDR,
        ["Davlat ro'yxatidan o'tganlik guvohnomasi", "Guvohnoma AA",
         "AA 1234567", "12.03.2019", "muddatsiz", "g.pdf", "https://d/g.pdf", ""],
        ["Литсензия", "IT litsenziyasi", "L-902", "01.02.2024", "01.02.2027", "", "", ""],
        ["Litsenziya / faoliyat ruxsatnomasi", "Qurilish litsenziyasi",
         "L-889", "2021-05-01", "2026-05-01", "", "", ""],
        ["Kafolat xati", "Kafolat 2025", "KX-1", "10.01.2025", "aniqmas", "", "", ""],
        ["Nomalum tur", "Nimadir", "X-1", "", "2027-01-01", "", "", ""],
        ["Ishonchnoma", "", "IN-5", "", "2026-12-31", "", "", ""],
        ["Litsenziya / faoliyat ruxsatnomasi", "Qurilish litsenziyasi",
         "L-889", "", "2026-05-01", "", "", ""],
        ["Muvofiqlik sertifikati", "Sertifikat X", "S-1", "2025-01-01", "2024-01-01",
         "", "", ""],
        ["Bank rekvizitlari", "Asosiy hisob", "", "", "", "", "https://d/bank", ""],
        ["Ustav / ta'sis hujjatlari", "Ustav 2020", "", "", "", "", "", ""],
    ]
    ok, errs, warns = _parse(_csv_bytes(filled), "toldirilgan.csv")
    by_row = {e["row"]: e for e in errs}
    got = {(r["doc_type"], r["name"]) for r in ok}

    check(len(ok) == 4, f"4 ta to'g'ri qator qabul qilindi ({len(ok)} ta)", str(got))
    check(("license", "IT litsenziyasi") in got and
          ("license", "Qurilish litsenziyasi") in got,
          "bir turdagi IKKI hujjat ham saqlandi (nomi bilan farqlanadi)")
    check(by_row.get(5, {}).get("field") == "valid_until", "5-qator: noto'g'ri sana xato")
    check(by_row.get(6, {}).get("field") == "doc_type", "6-qator: notanish tur xato")
    check(by_row.get(7, {}).get("field") == "name", "7-qator: bo'sh nom xato")
    check("takrorlangan" in by_row.get(8, {}).get("message", ""),
          "8-qator: takror (tur+nom) xato")
    check(by_row.get(9, {}).get("field") == "valid_until",
          "9-qator: muddat berilgan sanadan oldin — xato")
    # 11-qator umuman to'ldirilmagan -> import qilinmaydi (jimgina "yashil"
    # bo'lib qolmasin). Bu shablon dizaynining asosiy qoidasi.
    check(all(r["row"] != 11 for r in ok), "to'ldirilmagan qator import QILINMADI")
    check(any(w["row"] == 10 and "MUDDATSIZ" in w["message"] for w in warns),
          "muddat ko'rsatilmagan qator uchun ogohlantirish bor",
          str([(w["row"], w["message"][:40]) for w in warns]))

    # --- Sarlavhalar boshqa tilda bo'lsa ham tanilishi -------------------
    ru = [["Тип документа", "Наименование", "Номер", "Дата выдачи",
           "Срок действия", "Файл", "Ссылка", "Примечание"],
          ["Ishonchnoma", "Ishonchnoma 2026", "IN-7", "01.01.2026", "31.12.2026",
           "", "", ""]]
    ok2, errs2, _ = _parse(_csv_bytes(ru), "ru.csv")
    check(len(ok2) == 1 and not errs2 and ok2[0]["doc_type"] == "power_of_attorney",
          "ruscha sarlavhali fayl ham o'qildi", str(errs2[:1]))

    # --- Butun faylga tegishli xato ---------------------------------------
    from api import importer
    try:
        _parse(_csv_bytes([["Foo", "Bar"], ["a", "b"]]), "bad.csv")
        check(False, "sarlavhasiz fayl rad etilishi kerak edi")
    except importer.ImportFormatError as e:
        check("Hujjat turi" in str(e), "sarlavhasiz fayl tushunarli xato berdi", str(e))


if __name__ == "__main__":
    test_detect()
    test_base_list()
    test_status()
    test_template()
    try:
        test_db()
    except Exception as e:                     # noqa: BLE001
        print(f"  DIQQAT: baza sinovi bajarilmadi: {e}")
        _fail += 1
    print(f"\n{'=' * 50}\nNATIJA: {_pass} ta o'tdi, {_fail} ta xato")
    sys.exit(1 if _fail else 0)
