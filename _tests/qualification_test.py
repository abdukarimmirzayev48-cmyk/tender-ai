# -*- coding: utf-8 -*-
"""SINOV: MALAKA TEKSHIRUVI va BROKERGA YO'NALTIRISH.

Modelga CHIQMAYDI, PUL SARFLAMAYDI — ikkala modul ham deterministik.

Nima tekshiriladi:
  A. QARORNING MANBASI   — `go` musbat dalildan chiqadimi
  B. `is_mandatory`      — DARVOZA sifatida ishlatilmaydimi
  C. SINOV YORLIG'I      — natija bilan birga yuradimi
  D. NORMALLASHTIRISH    — uch alifbo (Литсензия / лицензия / litsenziya)
  E. YO'NALTIRISH        — inson qarori qayta yozilmaydimi
  F. IZOLYATSIYA         — har so'rovda `company_id` bormi
  G. O'LCHOVSIZLIK       — xulosaga aylanmaydimi
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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

from dotenv import load_dotenv                              # noqa: E402
load_dotenv(os.path.join(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))), ".env"))

from api import compliance, db, qualification as Q, routing as R  # noqa: E402

PASS = FAIL = 0
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: `is_mandatory` DARVOZA sifatida ishlatilganini topadigan naqsh.
#:
#: KENGAYTIRILDI — birinchi shakli (`is_mandatory\s*(=|==|IS|AND|WHERE)`)
#: ikkita haqiqiy buzilishni O'TKAZIB YUBORARDI:
#:
#:     if r['is_mandatory'] == True:          indeks ustunni ajratardi
#:     [x for x in t if x['is_mandatory']]    YALANG'OCH rostlik
#:
#: Ikkinchisi eng ehtimoli. Endi naqsh nomdan KEYINGI qavsni ham,
#: `if`/`filter` ichidagi yalang'och ishlatishni ham tutadi.
MANDATORY_NAQSH = (
    r"(?:"
    r"is_mandatory[\"'\]\s]*\s*(?:=|==|!=|IS\b|AND\b|OR\b)"   # taqqoslash
    r"|WHERE[^\n]*is_mandatory"                                  # SQL sharti
    r"|\bif\b[^\n]*is_mandatory"                                # if sharti
    r"|\bfilter\b[^\n]*is_mandatory"                            # filter()
    r"|\bnot\s+[\w\[\]\"'.]*is_mandatory"                      # not x[...]
    r")"
)
_yozilgan = []          # routing id lari — oxirida tozalanadi

#: SINOV QARORLARINING BELGISI.
#:
#: `tozala()` faqat shu yurishda yozilgan id larni o'chiradi. Yurish
#: O'LDIRILSA (Ctrl+C, seans uzilishi) qoldiq qoladi va uni haqiqiy
#: ma'lumotdan ajratadigan hech narsa bo'lmaydi. Amalda shunday
#: bo'ldi: bitta yozuv qolib, `v_routing_agreement` "moslik 100%"
#: ko'rsatdi.
#:
#: Endi har sinov qarori shu nom bilan yoziladi va tozalash BOSHDA
#: ham yuradi.
_BROKER = "ZZTEST-sinov"


def check(nom: str, shart: bool, izoh: str = "") -> None:
    global PASS, FAIL
    if shart:
        PASS += 1
        print(f"  OK   {nom}")
    else:
        FAIL += 1
        print(f"  XATO {nom}" + (f"\n       {izoh}" if izoh else ""))


def section(t: str) -> None:
    print(f"\n=== {t} ===")


def _cid() -> int:
    """Navbati eng katta kompaniya.

    `ORDER BY id LIMIT 1` NOTO'G'RI bo'lardi: birinchi kompaniyaning
    navbatida talab yo'q va butun sinov bo'sh ma'lumot ustida
    yurardi — ya'ni hech narsani o'lchamasdi.
    """
    return db.scalar("""SELECT company_id FROM v_requirement_review
                        GROUP BY company_id ORDER BY count(*) DESC LIMIT 1""")


# =====================================================================
def test_qaror_manbasi():
    """A. `go` MUSBAT dalildan chiqsin, "to'siq topilmadi" dan emas.

    Bu loyihada uch marta takrorlangan sinf (§16.58): muvaffaqiyat
    signali salbiy shartdan olinadi va signalning o'zi tekshirilmaydi.
    Malaka tekshiruvida bu eng xavfli shaklda bo'lardi — profil bo'sh
    bo'lgan kompaniya HAR tenderga "malakali" chiqardi.
    """
    section("A. Qarorning manbasi")

    src = io.open(os.path.join(ROOT, "api", "qualification.py"),
                  encoding="utf-8").read()
    check("`go` uchun MINIMAL `ok` soni belgilangan",
          "GO_MIN_OK" in src and "n_ok >= GO_MIN_OK" in src,
          "`go` faqat `fail` yo'qligidan chiqmasin")

    # HECH NARSA O'LCHANMAGAN holat: barcha mezon `malumot_yoq`.
    bosh = {"decision": None, "criteria": [
        {"key": k, "label": k, "status": "malumot_yoq", "izoh": "", "dalillar": []}
        for k in [c["key"] for c in Q.CRITERIA]]}
    n_ok = sum(1 for m in bosh["criteria"] if m["status"] == "ok")
    check("nol o'lchovda `ok` soni nol", n_ok == 0)

    # Haqiqiy tenderda tekshiramiz.
    cid = _cid()
    tid = db.scalar("""SELECT tender_id FROM v_requirement_review
                       WHERE company_id = %(c)s LIMIT 1""", {"c": cid})
    r = Q.check(tid, cid)
    check("qaror ro'yxatdan", r["decision"] in Q.DECISIONS, r["decision"])
    check("o'lchangan mezon soni qaytariladi", "olchandi" in r)
    check("o'lchanmagan mezon `ok` ga qo'shilmaydi",
          r["ok"] + r["fail"] + r["risk"] == r["olchandi"],
          f"ok={r['ok']} fail={r['fail']} risk={r['risk']} "
          f"olchandi={r['olchandi']}")

    # BALL maxraji — o'lchangan mezonlar, JAMI emas.
    b = R._ball({"ok": 3, "olchandi": 3, "jami_mezon": 7})
    check("ball maxraji O'LCHANGAN mezon", b == 1.0, str(b))
    b0 = R._ball({"ok": 0, "olchandi": 0, "jami_mezon": 7})
    check("nol o'lchovda ball 0", b0 == 0.0, str(b0))

    # QAMROV sababda ko'rinsin: `3/3 o'tdi` + `ball 1.000` "mukammal"
    # deb o'qiladi, holbuki 4 mezon umuman o'lchanmagan.
    out = R.yonaltir(tid, cid, barchasi=True)
    if out:
        _yozilgan.append(out["routing_id"])
        row = db.query_one("SELECT ai_sabab FROM tender_routing "
                           "WHERE id = %(i)s", {"i": out["routing_id"]})
        olchanmadi = out["jami_mezon"] - out["olchandi"]
        if olchanmadi:
            check("sabab O'LCHANMAGAN mezonni aytadi",
                  "O'LCHANMADI" in (row["ai_sabab"] or ""),
                  row["ai_sabab"])


# =====================================================================
def test_is_mandatory_darvoza_emas():
    """B. `is_mandatory` DARVOZA sifatida ishlatilmasin.

    Bazadagi HAMMA qatorda u `False` (naqsh majburiylikni ajrata
    olmaydi, LLM qatlami bloklangan). `WHERE is_mandatory` shartli
    darvoza HAMMA NARSANI JIMGINA o'tkazardi va ishlayotgandek
    ko'rinardi.
    """
    section("B. `is_mandatory` mina")

    n_true = db.scalar("SELECT count(*) FROM tender_requirement "
                       "WHERE is_mandatory")
    n_all = db.scalar("SELECT count(*) FROM tender_requirement")
    check("bazada `is_mandatory` HALI HAM hammasi False",
          n_true == 0, f"{n_true}/{n_all} true")
    if n_true:
        print("       [i] LLM qatlami yurgan bo'lsa bu sinov yangilansin")

    for nom in ("qualification.py", "routing.py"):
        src = io.open(os.path.join(ROOT, "api", nom), encoding="utf-8").read()
        kod = "\n".join(x for x in src.split("\n")
                        if not x.lstrip().startswith("#"))
        # Docstring'dagi tushuntirish hisoblanmaydi — faqat KOD.
        kod = re.sub(r'"""[\s\S]*?"""', "", kod)
        check(f"{nom} `is_mandatory` ni FILTR qilmaydi",
              not re.search(MANDATORY_NAQSH, kod, re.I),
              "hamma qator False — bunday filtr hech narsani to'smaydi")

    # --- SKANERNI SINAYMIZ ---
    #
    # Loyihada qoida bor: salbiy sinovlar (xato KUTILGAN holatlar)
    # qulflansin — ular jimgina "o'tib" ketishi eng oson. Bu skaner
    # o'sha qoidasiz yozilgan edi va IKKI shaklni o'tkazib yuborardi:
    #
    #     if r['is_mandatory'] == True:            <- indeks aralashgan
    #     [x for x in t if x['is_mandatory']]      <- YALANG'OCH rostlik
    #
    # Ikkinchisi eng ehtimoli — darvozani odam aynan shunday yozadi.
    for yomon in (
            "WHERE is_mandatory AND tur = 'x'",              # skaner-namuna
            "if r['is_mandatory'] == True:",                 # skaner-namuna
            "AND r.is_mandatory IS TRUE",                    # skaner-namuna
            "kerak = [x for x in t if x['is_mandatory']]",   # skaner-namuna
            'if row["is_mandatory"]:',                       # skaner-namuna
            "filter(lambda r: r.is_mandatory, rows)",        # skaner-namuna
    ):
        check(f"skaner TUTADI: {yomon[:42]}",
              bool(re.search(MANDATORY_NAQSH, yomon, re.I)), yomon)

    # TO'G'RI uslub tutilmasin — aks holda skaner ishni to'sardi.
    for yaxshi in (
            "d['tasdiqlanmagan'] = not tasdiq",               # skaner-namuna
            "# `is_mandatory` ga tayanmaymiz",                # skaner-namuna
            'SELECT id, name FROM tender_requirement',        # skaner-namuna
    ):
        check(f"skaner TUTMAYDI: {yaxshi[:42]}",
              not re.search(MANDATORY_NAQSH, yaxshi, re.I), yaxshi)


# =====================================================================
def test_sinov_yorligi():
    """C. SINOV MA'LUMOTI yorlig'i natija bilan BIRGA yursin.

    Profil o'ylab topilgan qiymatlar bilan to'ldirilgan. "147 ta
    tender navbatda" degan raqam SHU qiymatlarni o'lchaydi. Yorliq
    yo'qolsa, olti oydan keyin uni haqiqiy deb o'qishardi — katalog
    sun'iy to'ldirilmagani bilan bir xil sabab (§16.6).
    """
    section("C. Sinov ma'lumoti yorlig'i")

    cid = _cid()
    tid = db.scalar("""SELECT tender_id FROM v_requirement_review
                       WHERE company_id = %(c)s LIMIT 1""", {"c": cid})
    r = Q.check(tid, cid)
    prof = db.query_one("SELECT is_sample, sample_note FROM company_profile "
                        "WHERE company_id = %(c)s", {"c": cid}) or {}
    check("natijada `is_sample` bor", "is_sample" in r)
    check("yorliq PROFILDAN keladi",
          r["is_sample"] == bool(prof.get("is_sample")),
          f"natija={r['is_sample']} profil={prof.get('is_sample')}")

    # BAZA CHEKLOVI: bayroq yoqilgan bo'lsa izoh bo'sh qolmasin.
    xato = None
    try:
        db.execute_returning(
            "UPDATE company_profile SET is_sample = true, sample_note = NULL "
            "WHERE company_id = %(c)s RETURNING company_id", {"c": cid})
    except Exception as e:                                  # noqa: BLE001
        xato = type(e).__name__
    check("izohsiz `is_sample` BAZA darajasida rad etiladi",
          xato is not None, "izoh emas, CHEKLOV himoya qilsin")

    if prof.get("is_sample"):
        out = R.yonaltir(tid, cid, barchasi=True)
        if out:
            _yozilgan.append(out["routing_id"])
            row = db.query_one("SELECT ai_sabab FROM tender_routing "
                               "WHERE id = %(i)s", {"i": out["routing_id"]})
            check("yorliq YO'NALTIRISH sababiga ham tushadi",
                  "SINOV" in (row["ai_sabab"] or "").upper(),
                  row["ai_sabab"])

    # TO'LIQLIK ko'rinishi SON qaytarsin, NULL emas.
    check("profil to'liqligi NULL emas",
          not db.query("SELECT 1 FROM v_profile_completeness "
                       "WHERE toldirilgan IS NULL"),
          "bo'sh massiv butun yig'indini NULL qilardi")


# =====================================================================
def test_normallashtirish():
    """D. UCH ALIFBO — 'Литсензия', 'лицензия', 'litsenziya'.

    Bu loyihada TO'RT marta takrorlangan xato sinfi. Shuning uchun
    `qualification` o'z lug'atini YOZMAYDI, `compliance.match_doc_type()`
    ni chaqiradi — ikkinchi nusxa jimgina ajralib ketardi.
    """
    section("D. Uch alifbo")

    for matn, kutilgan in [
        ("Литсензия", "license"),            # o'zbekcha kirill
        ("лицензия", "license"),             # ruscha
        ("litsenziya", "license"),           # lotin
        ("Muvofiqlik sertifikati", "conformity_certificate"),
        ("Kafolat xati", "guarantee_letter"),
    ]:
        check(f"'{matn}' -> {kutilgan}",
              compliance.match_doc_type(matn) == kutilgan,
              str(compliance.match_doc_type(matn)))

    src = io.open(os.path.join(ROOT, "api", "qualification.py"),
                  encoding="utf-8").read()
    check("qualification O'Z lug'atini yozmaydi",
          "match_doc_type" in src and "DOC_TYPES = [" not in src,
          "ikkinchi nusxa jimgina ajralib ketardi")


# =====================================================================
def test_yonaltirish():
    """E. INSON QARORI qayta yozilmasin."""
    section("E. Yo'naltirish")

    cid = _cid()
    tid = db.scalar("""SELECT tender_id FROM v_requirement_review
                       WHERE company_id = %(c)s LIMIT 1""", {"c": cid})
    out = R.yonaltir(tid, cid, barchasi=True)
    check("yo'naltirish yozuvi yaratildi", out and out["routing_id"],
          str(out)[:120] if out else "None")
    rid = out["routing_id"]
    _yozilgan.append(rid)

    # IDEMPOTENT: o'zgarmagan baholash `updated_at` ni surmasin, aks
    # holda navbat har soat "yangilangan" bo'lib ko'rinardi.
    oldin = db.query_one("SELECT updated_at FROM tender_routing "
                         "WHERE id = %(i)s", {"i": rid})["updated_at"]
    R.yonaltir(tid, cid, barchasi=True)
    keyin = db.query_one("SELECT updated_at FROM tender_routing "
                         "WHERE id = %(i)s", {"i": rid})["updated_at"]
    check("o'zgarmagan baho `updated_at` ni SURMAYDI", oldin == keyin,
          f"{oldin} -> {keyin}")

    # OCHILDI -> QAROR -> qayta ochilmaydi
    check("navbatdagi yozuv ochiladi", bool(R.ochildi(rid, cid, _BROKER)))
    q = R.qaror(rid, cid, "olindi", "sinov", ishonch="kompaniya_sessiyasi")
    check("broker qarori yozildi", q and q["inson_qaror"] == "olindi", str(q))
    check("holat 'yopildi'", q and q["holat"] == "yopildi")
    check("yopilgan yozuv QAYTA OCHILMAYDI",
          R.ochildi(rid, cid) is None,
          "qaror berilgan yozuv qayta ochilsa hisobot buzilardi")

    # AI QARORI inson qarorini QAYTA YOZMAYDI.
    R.yonaltir(tid, cid, barchasi=True)
    row = db.query_one("SELECT ai_qaror, inson_qaror, holat FROM tender_routing "
                       "WHERE id = %(i)s", {"i": rid})
    check("qayta baholash INSON QARORINI o'chirmaydi",
          row["inson_qaror"] == "olindi", str(row))
    check("qayta baholash holatni ORQAGA qaytarmaydi",
          row["holat"] == "yopildi", str(row))

    # NOMA'LUM qaror rad etilsin.
    xato = None
    try:
        R.qaror(rid, cid, "bilmadim", ishonch="kompaniya_sessiyasi")
    except ValueError as e:
        xato = str(e)
    check("noma'lum qaror rad etiladi", xato is not None, str(xato))

    # NAVBAT faqat OCHIQ tenderlarni bersin.
    yopiq = db.scalar("""SELECT count(*) FROM v_routing_queue q
        JOIN tender t ON t.id = q.tender_id
        WHERE t.close_at IS NOT NULL AND t.close_at <= now()""")
    check("navbatda MUDDATI O'TGAN tender yo'q", yopiq == 0, str(yopiq))


# =====================================================================
def test_qaror_eskirishi():
    """H. INSON QARORI ESKIRGANINI bilib turadimi.

    HAQIQIY XAVF: broker "olindi" deb qaror beradi. Ertasiga hujjat
    qayta ajratiladi, yangi sertifikat talabi topiladi, `ai_qaror`
    `go` dan `no_go` ga o'tadi — va broker BUNDAN XABAR TOPMAYDI.

    Bu himoya `routing.py` izohida TASVIRLANGAN edi, lekin
    YOZILMAGAN: `grep ai_ozgardi` bitta natija bergan — o'sha
    izohning o'zi. Izoh himoya emas (§16.58).
    """
    section("H. Qaror eskirishi")

    cid = _cid()
    # OCHIQ tender SHART: `v_routing_queue` yopilganini ko'rsatmaydi
    # va sinov "navbatda ko'rinmadi" deb KOD XATOSI EMAS, TASODIF
    # tufayli yiqilardi. Aynan shunday bo'ldi — tanlangan tender
    # o'sha kuni ertalab yopilgan edi (7-sinf).
    tid = db.scalar("""SELECT v.tender_id FROM v_requirement_review v
        JOIN tender t ON t.id = v.tender_id
        WHERE v.company_id = %(c)s
          AND (t.close_at IS NULL OR t.close_at > now())
          AND NOT EXISTS (
            SELECT 1 FROM tender_routing r
             WHERE r.company_id = v.company_id
               AND r.tender_id = v.tender_id) LIMIT 1""", {"c": cid})
    if not tid:
        check("sinov uchun OCHIQ tender topildi", False,
              "navbatda bo'sh joy yo'q — eskirish tekshirilmadi")
        return

    out = R.yonaltir(tid, cid, barchasi=True)
    rid = out["routing_id"]
    _yozilgan.append(rid)

    # 1. Inson qaror beradi.
    R.qaror(rid, cid, "olindi", "sinov", ishonch="kompaniya_sessiyasi")
    row = db.query_one("SELECT ai_qaror, ai_ozgardi FROM tender_routing "
                       "WHERE id = %(i)s", {"i": rid})
    check("qarordan keyin bayroq TOZA", row["ai_ozgardi"] is False,
          str(row))

    # 2. AI qarori QO'LDA o'zgartiriladi — keyingi baholash uni
    #    boshqacha ko'rgan holatni taqlid qiladi.
    boshqa = "no_go" if row["ai_qaror"] != "no_go" else "go"
    db.execute_returning(
        "UPDATE tender_routing SET ai_qaror = %(q)s WHERE id = %(i)s "
        "RETURNING id", {"q": boshqa, "i": rid})

    # 3. Qayta baholash — bayroq QO'YILISHI kerak.
    R.yonaltir(tid, cid, barchasi=True)
    row2 = db.query_one("""SELECT ai_qaror, ai_ozgardi, ai_qaror_eski,
        inson_qaror FROM tender_routing WHERE id = %(i)s""", {"i": rid})
    check("AI qarori o'zgarganda bayroq QO'YILADI",
          row2["ai_ozgardi"] is True, str(row2))
    check("ESKI qaror saqlanadi", row2["ai_qaror_eski"] == boshqa,
          f"kutilgan {boshqa}, keldi {row2['ai_qaror_eski']}")
    check("inson qarori TEGILMAYDI", row2["inson_qaror"] == "olindi")

    # 4. ESKIRGAN yozuv navbatga QAYTADI va TEPADA turadi.
    nav = R.navbat(cid, limit=50)
    topildi = [i for i, x in enumerate(nav) if x["id"] == rid]
    check("eskirgan qaror navbatda ko'rinadi", bool(topildi),
          "aks holda broker uni boshqa ko'rmasdi")
    if topildi:
        check("eskirgan qaror TEPADA", topildi[0] == 0,
              f"{topildi[0]}-o'rinda — yolg'on ishonch eng shoshilinch")

    # 5. YANGI qaror bayroqni yopadi.
    R.qaror(rid, cid, "rad", "qayta ko'rildi", ishonch="kompaniya_sessiyasi")
    row3 = db.query_one("SELECT ai_ozgardi, ai_qaror_eski "
                        "FROM tender_routing WHERE id = %(i)s", {"i": rid})
    check("yangi qaror bayroqni YOPADI", row3["ai_ozgardi"] is False,
          str(row3))
    check("eski qaror ham tozalanadi", row3["ai_qaror_eski"] is None,
          "cheklov: NOT ai_ozgardi OR ai_qaror_eski IS NOT NULL")

    # 6. CHEKLOV BAZADA — bayroq eski qarorsiz yozilmasin.
    xato = None
    try:
        db.execute_returning(
            "UPDATE tender_routing SET ai_ozgardi = true, "
            "ai_qaror_eski = NULL WHERE id = %(i)s RETURNING id",
            {"i": rid})
    except Exception as e:                                  # noqa: BLE001
        xato = type(e).__name__
    check("eski qarorsiz bayroq BAZADA rad etiladi", xato is not None,
          "izoh emas, CHEKLOV himoya qilsin")


# =====================================================================
def test_izolyatsiya():
    """F. Har so'rovda `company_id` bo'lsin — IDOR himoyasi."""
    section("F. Izolyatsiya")

    cid = _cid()
    boshqa = db.scalar("SELECT id FROM company_account WHERE id <> %(c)s "
                       "ORDER BY id LIMIT 1", {"c": cid})
    rid = db.scalar("SELECT id FROM tender_routing WHERE company_id = %(c)s "
                    "LIMIT 1", {"c": cid})
    if boshqa and rid:
        check("BOSHQA kompaniya yozuvni ocholmaydi",
              R.ochildi(rid, boshqa) is None)
        check("BOSHQA kompaniya qaror bera olmaydi",
              R.qaror(rid, boshqa, "olindi", ishonch="kompaniya_sessiyasi") is None)

    for nom in ("qualification.py", "routing.py"):
        src = io.open(os.path.join(ROOT, "api", nom), encoding="utf-8").read()
        sorovlar = re.findall(r'"""\s*\n?(SELECT|UPDATE|INSERT)[\s\S]*?"""', src)
        n_sorov = len(re.findall(r"(SELECT|UPDATE|INSERT)\s", src))
        n_cid = src.count("company_id")
        check(f"{nom} da `company_id` keng ishlatiladi",
              n_cid >= n_sorov / 2,
              f"{n_cid} ta company_id, ~{n_sorov} ta so'rov")


# =====================================================================
def test_olchovsizlik():
    """G. O'LCHOVSIZLIK XULOSAGA AYLANMASIN.

    "Moslik 0%" va "hali o'lchanmagan" BOSHQA-BOSHQA narsa. Birinchisi
    modelni ayblaydi, ikkinchisi rost gapiradi.
    """
    section("G. O'lchovsizlik")

    cid = _cid()
    m = R.moslik(cid)
    check("moslik hisoboti qaytadi", isinstance(m, dict))
    check("o'lchanganmi degan bayroq bor", "olchandi" in m, str(m)[:100])

    # BITTA QARORDAN FOIZ CHIQMASIN.
    #
    # O'LCHANGAN XATO: bazada bitta sinov yozuvi qolgan edi va
    # interfeys "Moslik (1 qaror bo'yicha): no_go: 100%" ko'rsatdi.
    # Bitta kuzatuvdan foiz chiqarish statistika emas — u haqiqiy
    # o'lchov kabi ko'rinadi va shuning uchun zararli.
    check("moslik uchun MINIMAL qaror soni belgilangan",
          R.MOSLIK_MIN >= 10, str(R.MOSLIK_MIN))
    if m["inson_qarorlari"] < R.MOSLIK_MIN:
        check("yetarli qaror yo'q -> `olchandi` False",
              m["olchandi"] is False,
              f"{m['inson_qarorlari']} qaror, kerak {R.MOSLIK_MIN}")
        check("yetarli qaror yo'q -> FOIZ berilmaydi",
              m["qatorlar"] == [],
              f"{len(m['qatorlar'])} qator qaytdi")
        check("izoh sababni AYTADI", bool(m["izoh"]), str(m["izoh"])[:90])
        check("izohda qaror soni ko'rinadi",
              str(m["inson_qarorlari"]) in (m["izoh"] or ""),
              str(m["izoh"])[:90])

    # VALYUTA mos kelmasa TAXMIN QILINMASIN.
    src = io.open(os.path.join(ROOT, "api", "qualification.py"),
                  encoding="utf-8").read()
    check("valyuta farqi `malumot_yoq` beradi",
          "Valyutalar har xil" in src,
          "kurs bu modulning ishi emas — taxmin qilinmasin")

    # TAJRIBA — QOIDANI tekshiramiz, HOLATNI emas.
    #
    # Avval sinov `status == 'malumot_yoq'` deb yozilgan edi. U ESKI
    # XULQNI qulflab qo'yardi: tender tomonida ajratgich paydo
    # bo'lishi bilan sinov yiqilardi, garchi kod TO'G'RI ishlagan
    # bo'lsa ham. Qoida esa o'zgarmaydi: TALAB YO'Q bo'lsa `ok`
    # BERILMAYDI — to'siq yo'qligi malaka emas.
    tekshirildi = 0
    for tid in [x["tender_id"] for x in db.query(
            """SELECT tender_id FROM v_requirement_review
               WHERE company_id = %(c)s LIMIT 25""", {"c": cid})]:
        r = Q.check(tid, cid)
        taj = next(m for m in r["criteria"] if m["key"] == "tajriba")
        bor = any(d for d in taj["dalillar"])
        if not bor:
            tekshirildi += 1
            if taj["status"] == "ok":
                check("talabsiz tajriba `ok` BO'LMAYDI", False,
                      f"tender {tid}: {taj['izoh']}")
                break
    else:
        check("talabsiz tajriba `ok` BO'LMAYDI", True,
              f"{tekshirildi} ta tenderda tekshirildi")
    check("tajriba mezoni dalil qaytaradi",
          "dalillar" in next(m for m in Q.check(
              db.scalar("""SELECT tender_id FROM v_requirement_review
                           WHERE company_id = %(c)s LIMIT 1""", {"c": cid}),
              cid)["criteria"] if m["key"] == "tajriba"))


# =====================================================================
def test_http():
    """I. ENDPOINTLAR HTTP ORQALI ishlaydimi.

    Modul sinovi `routing.navbat()` ni to'g'ridan-to'g'ri chaqiradi —
    u `company_id_of()` ni, so'rov parametrlarini va javob shaklini
    UMUMAN sinamaydi. Ro'yxatda ko'ringan endpoint ishlayotganini
    bildirmaydi (3-sinf).
    """
    section("I. HTTP")

    try:
        from fastapi.testclient import TestClient
        from api import auth as A
        from api.main import app
    except Exception as e:                                  # noqa: BLE001
        check("TestClient mavjud", False, str(e)[:120])
        return

    USER, PAROL = "zzbroker_test", "Zz!broker#2026"
    cur = db.query_one(A.ACC_BY_NAME_SQL, {"username": USER})
    if cur:
        A.update_account(cur["id"], {"active": True})
        A.set_password(cur["id"], PAROL)
        acc_id = cur["id"]
    else:
        acc_id = A.create_account(USER, "ZZBROKER MChJ", PAROL)["id"]

    # `base_url` HTTPS bo'lishi SHART: sessiya cookie'si `Secure`
    # bayrog'i bilan qo'yiladi va `http://testserver` da brauzer
    # (va TestClient) uni QAYTA YUBORMAYDI. Natijada kirish 200
    # bo'ladi-yu, keyingi har so'rov 401 chiqadi.
    with TestClient(app, base_url="https://testserver") as c:
        r = c.post("/auth/login", json={"username": USER, "password": PAROL})
        check("kirish muvaffaqiyatli", r.status_code == 200,
              f"{r.status_code}: {r.text[:120]}")
        if r.status_code != 200:
            return
        # CSRF tokeni JAVOB TANASIDA emas, `HttpOnly` BO'LMAGAN
        # cookie'da keladi (`tai_csrf`) — brauzer JS uni shu yerdan
        # o'qiydi. Javobdan olishga urinish bo'sh satr berardi va
        # har o'zgartiruvchi so'rov 403 chiqardi.
        csrf = c.cookies.get("tai_csrf") or ""
        check("CSRF tokeni cookie'dan olindi", bool(csrf),
              "`tai_csrf` — HttpOnly EMAS, ataylab")
        bosh = {"X-CSRF-Token": csrf}

        # --- NAVBAT ---
        q = c.get("/routing/queue?limit=5")
        check("GET /routing/queue 200", q.status_code == 200,
              f"{q.status_code}: {q.text[:120]}")
        if q.status_code == 200:
            j = q.json()
            for maydon in ("items", "jami", "moslik"):
                check(f"javobda `{maydon}` bor", maydon in j, str(j)[:120])
            # IZOLYATSIYA: yangi hisobning navbati BO'SH bo'lishi kerak.
            check("YANGI hisob boshqa kompaniya navbatini KO'RMAYDI",
                  j["jami"] == 0,
                  f"{j['jami']} ta yozuv ko'rindi — IDOR!")
            # O'LCHOVSIZLIK xulosaga aylanmasin.
            check("moslik `olchandi` bayrog'ini qaytaradi",
                  "olchandi" in j["moslik"], str(j["moslik"])[:120])

        # --- NOMA'LUM HOLAT rad etilsin ---
        bad = c.get("/routing/queue?holat=bilmadim")
        check("noma'lum holat 400 beradi", bad.status_code == 400,
              f"{bad.status_code}: {bad.text[:100]}")

        # --- MALAKA ---
        tid = db.scalar("SELECT id FROM tender LIMIT 1")
        m = c.get(f"/tenders/{tid}/qualification")
        check("GET /tenders/{id}/qualification 200", m.status_code == 200,
              f"{m.status_code}: {m.text[:120]}")
        if m.status_code == 200:
            mj = m.json()
            for maydon in ("decision", "criteria", "olchandi",
                           "jami_mezon", "is_sample"):
                check(f"malaka javobida `{maydon}` bor", maydon in mj,
                      str(mj)[:120])
            check("mezonlar soni to'liq",
                  len(mj["criteria"]) == mj["jami_mezon"],
                  f"{len(mj['criteria'])} != {mj['jami_mezon']}")

        yoq = c.get("/tenders/999999999999/qualification")
        check("mavjud bo'lmagan tender 404", yoq.status_code == 404,
              f"{yoq.status_code}")

        # --- BOSHQA KOMPANIYA yozuvi (IDOR) ---
        begona = db.scalar("SELECT id FROM tender_routing "
                           "WHERE company_id <> %(c)s LIMIT 1", {"c": acc_id})
        if begona:
            o = c.post(f"/routing/{begona}/open", headers=bosh)
            check("BEGONA yozuvni ocholmaydi (404)", o.status_code == 404,
                  f"{o.status_code}: {o.text[:100]}")
            d = c.post(f"/routing/{begona}/decision",
                       json={"qaror": "olindi"}, headers=bosh)
            check("BEGONA yozuvga qaror bera olmaydi (404)",
                  d.status_code == 404, f"{d.status_code}: {d.text[:100]}")

        # --- NOMA'LUM QAROR ---
        oz = db.scalar("SELECT id FROM tender_routing "
                       "WHERE company_id = %(c)s LIMIT 1", {"c": acc_id})
        if oz:
            b = c.post(f"/routing/{oz}/decision",
                       json={"qaror": "bilmadim"}, headers=bosh)
            check("noma'lum qaror 400", b.status_code == 400,
                  f"{b.status_code}")

    # TestClient kontekstdan chiqqanda ilova `shutdown` ni bajaradi
    # va DB PULINI YOPADI — shuning uchun tozalash uchun uni qayta
    # ochamiz. Busiz sinov "DB pool ishga tushmagan" bilan yiqilardi.
    db.init_pool()
    db.execute_returning("DELETE FROM company_account WHERE id = %(i)s "
                         "RETURNING id", {"i": acc_id})


# =====================================================================
def qoldiqni_supur() -> int:
    """OLDINGI yurishdan qolgan sinov yozuvlarini o'chiradi.

    BOSHDA ham, OXIRIDA ham chaqiriladi. Boshda kerak, chunki
    o'ldirilgan yurish qoldiq qoldiradi va u `v_routing_agreement`
    ni ifloslantiradi.
    """
    n = 0
    while True:
        r = db.execute_returning(
            "DELETE FROM tender_routing WHERE broker_nomi = %(b)s "
            "RETURNING id", {"b": _BROKER})
        if not r:
            break
        n += 1
    return n


def tozala():
    n = 0
    for rid in set(x for x in _yozilgan if x):
        db.execute_returning("DELETE FROM tender_routing WHERE id = %(i)s "
                             "RETURNING id", {"i": rid})
        n += 1
    # SENTINEL bo'yicha ham: `_yozilgan` ga tushmay qolgan yozuv
    # bo'lishi mumkin (masalan `yonaltir_hammasi` qayta yaratsa).
    n += qoldiqni_supur()

    # MUSBAT TASDIQ: qoldiq HAQIQATAN qolmadimi.
    qoldi = db.scalar("SELECT count(*) FROM tender_routing "
                      "WHERE broker_nomi = %(b)s", {"b": _BROKER}) or 0
    check("sinov qoldig'i qolmadi", qoldi == 0, f"{qoldi} ta yozuv")
    print(f"\nTozalandi: {n} ta yo'naltirish yozuvi. "
          f"Navbatda qolgan: {db.scalar('SELECT count(*) FROM tender_routing')}")


def main() -> None:
    print("=" * 62)
    print("MALAKA + YO'NALTIRISH — modelga chiqmaydi, PUL SARFLAMAYDI")
    print("=" * 62)
    db.init_pool()
    try:
        if not db.scalar("SELECT to_regclass('public.tender_routing')"):
            check("schema_patch_routing.sql qo'llangan", False,
                  "psql -d xtxarid -f schema_patch_routing.sql")
        else:
            # OLDINGI yurish o'ldirilgan bo'lsa qoldiq qolgan bo'ladi.
            eski = qoldiqni_supur()
            if eski:
                print(f"[i] oldingi yurishdan {eski} ta qoldiq o'chirildi")
            test_qaror_manbasi()
            test_is_mandatory_darvoza_emas()
            test_sinov_yorligi()
            test_normallashtirish()
            test_yonaltirish()
            test_qaror_eskirishi()
            test_izolyatsiya()
            test_http()
            test_olchovsizlik()
    finally:
        try:
            tozala()
        finally:
            db.close_pool()

    print("\n" + "=" * 62)
    print(f"NATIJA: {PASS}/{PASS + FAIL} o'tdi")
    print("=" * 62)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
