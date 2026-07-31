"""
Hujjatlar to'liqligi cheklisti (P0-8) sinovi.

Ishga tushirish (loyiha ildizidan):
    .venv/Scripts/python.exe _tests/compliance_test.py

Ikki qism:
  1) SOF MANTIQ — DB'siz: naqsh aniqlash (uch alifboda), bazaviy ro'yxat,
     "bazada bor/yo'q", muddat holatlari, bo'sh matn.
  2) HAQIQIY BAZA — company_document ga sinov yozuvlari qo'yiladi, bir necha
     haqiqiy tenderда cheklist yig'iladi, so'ng yozuvlar TOZALANADI.

Uvicorn ISHGA TUSHIRILMAYDI — modul to'g'ridan-to'g'ri chaqiriladi.
"""
import datetime as _dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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

    head("3b. Chegara holatlari")
    check(C.doc_status(doc("x", days=0), TODAY) == "expiring_soon",
          "bugun tugaydi -> expiring_soon (hali tugamagan)")
    check(C.doc_status(doc("x", days=-1), TODAY) == "expired",
          "kecha tugagan -> expired")
    check(C.doc_status(doc("x", days=C.EXPIRING_SOON_DAYS), TODAY) == "expiring_soon",
          f"{C.EXPIRING_SOON_DAYS} kun -> expiring_soon")
    check(C.doc_status(doc("x", days=C.EXPIRING_SOON_DAYS + 1), TODAY) == "ok",
          f"{C.EXPIRING_SOON_DAYS + 1} kun -> ok")
    check(C.doc_status(None, TODAY) == "missing", "hujjat yo'q -> missing")
    # ISO satr ham qabul qilinishi kerak (DB drayveri date beradi, JSON satr)
    check(C.doc_status({"valid_until": "2020-01-01"}, TODAY) == "expired",
          "ISO satr sana ham tushuniladi")

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
def test_db():
    head("4. Haqiqiy baza — company_document + haqiqiy tenderlar")
    from api import db

    db.init_pool()
    ids = []
    try:
        # --- sinov yozuvlari (keyin O'CHIRILADI) ---
        seed = [
            ("reg_certificate", "[SINOV] Guvohnoma", None),
            ("license", "[SINOV] Litsenziya", TODAY + _dt.timedelta(days=365)),
            ("conformity_certificate", "[SINOV] Sertifikat",
             TODAY - _dt.timedelta(days=3)),          # muddati tugagan
            ("bank_details", "[SINOV] Rekvizitlar",
             TODAY + _dt.timedelta(days=7)),          # tugayapti
        ]
        for code, name, vu in seed:
            row = db.execute_returning(C.DOC_INSERT_SQL, {
                "doc_type": code, "name": name, "number": "TEST-1",
                "issued_at": None, "valid_until": vu,
                "file_name": None, "file_ref": None, "note": "avtomatik sinov",
            })
            ids.append(row["id"])
        check(len(ids) == 4, "4 ta sinov hujjati yozildi")

        rows = db.query(C.DOCS_LIST_SQL)
        check(any(r["name"] == "[SINOV] Guvohnoma" for r in rows),
              "DOCS_LIST_SQL yozuvlarni qaytardi")

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
            check(st.get("bank_details") == "expiring_soon",
                  f"tender {tid}: 7 kun qolgan rekvizit expiring_soon")
            check(st.get("reg_certificate") == "ok",
                  f"tender {tid}: muddatsiz guvohnoma ok")
            check(st.get("power_of_attorney") == "missing",
                  f"tender {tid}: yo'q ishonchnoma missing")

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
            "id": ids[0], "doc_type": "reg_certificate",
            "name": "[SINOV] Guvohnoma-2", "number": "TEST-2",
            "issued_at": None, "valid_until": None,
            "file_name": None, "file_ref": None, "note": None})
        check(upd and upd["name"] == "[SINOV] Guvohnoma-2", "UPDATE ishladi")

    finally:
        # --- TOZALASH: sinov yozuvlari bazada qolmasin ---
        from api import db as _db
        for i in ids:
            _db.execute_returning(C.DOC_DELETE_SQL, {"id": i})
        left = _db.query("SELECT id FROM company_document WHERE note='avtomatik sinov' "
                         "OR name LIKE '[SINOV]%%'")
        check(len(left) == 0, "sinov yozuvlari bazadan tozalandi", str(left))
        _db.close_pool()


if __name__ == "__main__":
    test_detect()
    test_base_list()
    test_status()
    try:
        test_db()
    except Exception as e:                     # noqa: BLE001
        print(f"  DIQQAT: baza sinovi bajarilmadi: {e}")
        _fail += 1
    print(f"\n{'=' * 50}\nNATIJA: {_pass} ta o'tdi, {_fail} ta xato")
    sys.exit(1 if _fail else 0)
