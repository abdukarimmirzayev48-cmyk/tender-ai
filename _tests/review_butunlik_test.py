#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SINOV: INSON KO'RIB CHIQISH BUTUNLIGI (tender_requirement)
==========================================================

NEGA BU SINOV BOR (o'lchangan sabab)
-------------------------------------
2026-08-30 da bazada:

    review_status  method    soni    reviewed_by IS NOT NULL
    ------------------------------------------------------
    pending        naqsh     7298    0
    approved       reyestr   1487    0      <-- SOXTA

1 487 qator "inson tasdiqlagan" deb ko'rinardi va ularni HECH KIM
ko'rmagan edi.

QAYERDAN KELDI: bitta `review_status` ustuni IKKI boshqa savolga
javob berardi — "bu ma'lumotga ishonsa bo'ladimi" (mashina) va "buni
inson tasdiqladimi" (inson). Reyestr pozitsiyalari birinchisiga "ha"
bergani uchun ikkinchisiga ham "ha" yozilgan edi.

Oqibati IKKI MARTA yamalgan (`schema_patch_requirement_7.sql`,
`api/main.py`), lekin SABAB qolgan edi. Bu sinov sababning
qaytmasligini tekshiradi.

SINOVNING ASOSIY SAVOLI: **ILOVA XATOSI SOXTA TASDIQ YOZA OLADIMI?**

Javob "yo'q" bo'lishi kerak va u IZOHGA emas, BAZA CHEKLOVIGA
tayanishi kerak. Shuning uchun bu yerda ilovani CHETLAB O'TIB,
to'g'ridan-to'g'ri SQL bilan soxta qator yozishga urinamiz.

Ishga tushirish:
    .venv\\Scripts\\python.exe _tests\\review_butunlik_test.py
    .venv\\Scripts\\python.exe _tests\\review_butunlik_test.py --offline
"""
import argparse
import io
import json
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


from dotenv import load_dotenv                                # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))

try:
    import psycopg2
except ImportError:                                           # pragma: no cover
    psycopg2 = None

_results = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    return ok


def section(t: str) -> None:
    print(f"\n--- {t} ---")


def db():
    dsn = os.environ.get("XT_DB_DSN")
    if not dsn or psycopg2 is None:
        return None
    try:
        c = psycopg2.connect(dsn, connect_timeout=8)
        c.autocommit = True
        return c
    except Exception as e:                                    # noqa: BLE001
        print(f"  [i] baza yetib bo'lmadi: {str(e)[:90]}")
        return None


# =====================================================================
# 1) STATIK — kodda soxta tasdiq yozadigan yo'l qolmadimi
# =====================================================================
def test_kodda_soxta_yol_yoq() -> None:
    section("Kodda soxta tasdiq yozadigan yo'l qolmadi")

    req = io.open(os.path.join(ROOT, "api", "requirement.py"),
                  encoding="utf-8").read()

    # ENG MUHIM STATIK TEKSHIRUV: ajratish yo'li `approved` YOZMASIN.
    # Aynan shu qator (`"review_status": "approved"`) 1 487 qatorni
    # tug'dirgan.
    check("reyestr yo'li 'approved' YOZMAYDI",
          '"review_status": "approved"' not in req,
          "aynan shu qator 1487 ta soxta tasdiqni tug'dirgan")
    check("reyestr yo'li 'extracted' yozadi",
          '"review_status": "extracted"' in req)
    check("reyestr yo'li mashina_holat='manba' yozadi",
          '"mashina_holat": "manba"' in req)

    for fayl, kutilgan in (("requirement_ai.py", "pending_review"),
                           ("requirement_naqsh.py", "pending_review")):
        s = io.open(os.path.join(ROOT, "api", fayl), encoding="utf-8").read()
        check(f"{fayl}: '{kutilgan}' yozadi",
              f'"review_status": "{kutilgan}"' in s)
        check(f"{fayl}: eski 'pending' YO'Q",
              '"review_status": "pending"' not in s)

    # Eski lug'at hech qayerda qolmasin. Qolgan joy JIMGINA 0 qator
    # qaytarardi — navbat bo'sh ko'rinardi va hech qanday xato
    # chiqmasdi.
    for fayl in ("api/requirement.py", "api/main.py", "api/qualification.py",
                 "api/requirement_ai.py", "api/requirement_naqsh.py"):
        s = io.open(os.path.join(ROOT, fayl), encoding="utf-8").read()
        # `review_status` bilan bir qatorda turgan `'pending'` ni
        # qidiramiz — boshqa kontekstdagi 'pending' (hujjat matni
        # holati) tegishli emas.
        yomon = [ln for ln in s.splitlines()
                 if "review_status" in ln and "'pending'" in ln
                 and "pending_review" not in ln and "Ilgari" not in ln]
        check(f"{fayl}: eski `review_status='pending'` qolmadi",
              not yomon, "; ".join(yomon)[:120])

    # `review_set` INSON dalilini talab qiladi.
    #
    # 20-vazifadan keyin xato O'ZBEKCHA MATN emas, KOD bilan
    # ko'tariladi (`api/xatolar.py`) — javob uch tilli interfeysga
    # bog'lanishi uchun. Shuning uchun manba tekshiruvi ham KOD
    # bo'yicha: u tilga bog'liq emas va tarjima o'zgarganda
    # yiqilmaydi.
    check("review_set/bulk: `by` majburiy",
          req.count('Xato("FIELD_REQUIRED", {"maydon": "by"})') == 2,
          f"{req.count(chr(88))}")
    check("review_set: mashina holatlarini QO'YA OLMAYDI",
          "INSON_QARORLARI" in req and "MASHINA_HOLATLARI" in req)
    check("review_set/bulk: ishonch darajasi tekshiriladi",
          req.count('Xato("TRUST_LEVEL_INVALID"') == 2)
    check("review_set/bulk: `aktor_elon` aktorsiz o'tmaydi",
          req.count('Xato("ACTOR_REQUIRED_FOR_TRUST"') == 2)

    main = io.open(os.path.join(ROOT, "api", "main.py"), encoding="utf-8").read()
    check("API sxemasi holatni Literal bilan qulflaydi",
          'Literal["approved", "rejected", "corrected"]' in main
          and 'Literal["approved", "rejected"]' in main,
          "noto'g'ri holat FastAPI darajasida 422 beradi")


def test_konstantalar() -> None:
    section("Holat lug'ati — ikki o'q aralashmaydi")
    from api import requirement as R

    check("MASHINA_HOLATLARI = extracted + pending_review",
          R.MASHINA_HOLATLARI == {"extracted", "pending_review"},
          str(sorted(R.MASHINA_HOLATLARI)))
    check("INSON_QARORLARI = approved + rejected + corrected",
          R.INSON_QARORLARI == {"approved", "rejected", "corrected"},
          str(sorted(R.INSON_QARORLARI)))
    check("ikki to'plam KESISHMAYDI",
          not (R.MASHINA_HOLATLARI & R.INSON_QARORLARI),
          "bir holat ikkala o'qqa tegishli bo'lolmaydi")
    check("har inson qarorining AMALI bor",
          set(R.AMAL) == R.INSON_QARORLARI, str(R.AMAL))


# =====================================================================
# 2) BAZA CHEKLOVI — ILOVANI CHETLAB O'TIB soxta qator yozamiz
# =====================================================================
def _namuna(**ozgartir):
    """Sinov qatori uchun to'liq maydonlar to'plami."""
    q = {
        "company_id": None, "tender_id": None, "lot_id": None,
        "source": "document", "method": "naqsh", "position_no": 1,
        "name": "[SINOV] butunlik", "attrs": json.dumps({"qiymat": "12 oy"}),
        "qty": None, "unit": None, "delivery_days": None,
        "is_mandatory": False, "confidence": 0.75, "raw_snippet": None,
        "file_ref": None, "char_start": None, "char_end": None, "model": None,
        "review_status": "pending_review", "mashina_holat": "ajratilgan",
        "reviewed_by": None, "reviewed_at": None, "review_action": None,
        "corrected_value": None, "previous_value": None,
    }
    q.update(ozgartir)
    return q


SQL_XOM = """
INSERT INTO tender_requirement
  (company_id, tender_id, lot_id, source, method, position_no, name, attrs,
   qty, unit, delivery_days, is_mandatory, confidence, raw_snippet,
   file_ref, char_start, char_end, model, review_status, mashina_holat,
   reviewed_by, reviewed_at, review_action, corrected_value, previous_value)
VALUES
  (%(company_id)s, %(tender_id)s, %(lot_id)s, %(source)s, %(method)s,
   %(position_no)s, %(name)s, %(attrs)s::jsonb, %(qty)s, %(unit)s,
   %(delivery_days)s, %(is_mandatory)s, %(confidence)s, %(raw_snippet)s,
   %(file_ref)s, %(char_start)s, %(char_end)s, %(model)s,
   %(review_status)s, %(mashina_holat)s,
   %(reviewed_by)s, %(reviewed_at)s, %(review_action)s,
   %(corrected_value)s, %(previous_value)s)
RETURNING id
"""


def test_baza_soxtani_rad_etadi(conn, cid, tid) -> None:
    section("BAZA soxta tasdiqni RAD ETADI (ilova chetlab o'tilgan)")
    if conn is None:
        check("baza kerak", False, "o'tkazib yuborildi")
        return

    import psycopg2 as pg

    def urin(nom: str, **ozg) -> bool:
        """Xom SQL bilan yozishga urinadi. `True` = BAZA RAD ETDI."""
        q = _namuna(company_id=cid, tender_id=tid, **ozg)
        try:
            with conn.cursor() as cur:
                cur.execute(SQL_XOM, q)
                yangi = cur.fetchone()[0]
            with conn.cursor() as cur:
                cur.execute("DELETE FROM tender_requirement WHERE id=%s", (yangi,))
            return False                       # qabul qilindi — YOMON
        except pg.Error:
            return True                        # rad etildi — YAXSHI

    # ============ ASOSIY INVARIANT ============
    # Har biri 1 487 qatorni qayta tug'dirishi mumkin bo'lgan yo'l.
    check("RAD: approved + reviewed_by NULL",
          urin("a", review_status="approved", position_no=101),
          "AYNAN shu 1487 ta soxta qatorni tug'dirgan")
    check("RAD: approved + reviewed_by = 0",
          urin("b", review_status="approved", reviewed_by=0,
               reviewed_at="now()", review_action="approve", position_no=102))
    check("RAD: approved + reviewed_at NULL",
          urin("c", review_status="approved", reviewed_by=cid,
               review_action="approve", position_no=103))
    check("RAD: approved + review_action NULL",
          urin("d", review_status="approved", reviewed_by=cid,
               reviewed_at="2026-08-30", position_no=104))
    check("RAD: rejected + reviewed_by NULL",
          urin("e", review_status="rejected", position_no=105))
    check("RAD: corrected + reviewed_by NULL",
          urin("f", review_status="corrected", corrected_value="24 oy",
               previous_value="12 oy", position_no=106))

    # ============ TESKARI INVARIANT ============
    # Yarim yozilgan holat ham RAD ETILADI: navbat va hisoblagich
    # bir xil bazadan ikki xil javob bermasin.
    check("RAD: pending_review + reviewed_by to'ldirilgan",
          urin("g", review_status="pending_review", reviewed_by=cid,
               reviewed_at="2026-08-30", position_no=107),
          "'navbatda, lekin inson ko'rgan' — o'qib bo'lmaydigan holat")
    check("RAD: extracted + reviewed_by to'ldirilgan",
          urin("h", review_status="extracted", method="reyestr",
               mashina_holat="manba", reviewed_by=cid,
               reviewed_at="2026-08-30", position_no=108))

    # ============ AMAL HOLATGA MOS ============
    check("RAD: approved + review_action='reject'",
          urin("i", review_status="approved", reviewed_by=cid,
               reviewed_at="2026-08-30", review_action="reject",
               position_no=109),
          "'tasdiqladim, lekin amal rad etish' — o'qib bo'lmaydi")

    # ============ TUZATISHDA IKKALA QIYMAT ============
    check("RAD: corrected + corrected_value NULL",
          urin("j", review_status="corrected", reviewed_by=cid,
               reviewed_at="2026-08-30", review_action="correct",
               previous_value="12 oy", position_no=110))
    check("RAD: corrected + previous_value NULL",
          urin("k", review_status="corrected", reviewed_by=cid,
               reviewed_at="2026-08-30", review_action="correct",
               corrected_value="24 oy", position_no=111))

    # ============ LUG'ATLAR ============
    check("RAD: notanish review_status",
          urin("l", review_status="tasdiqlandi", position_no=112))
    check("RAD: notanish mashina_holat",
          urin("m", mashina_holat="ishonchli", position_no=113))
    check("RAD: mashina_holat='manba' + method='naqsh'",
          urin("n", mashina_holat="manba", method="naqsh", position_no=114),
          "manba = FAQAT reyestr; yangi usul qo'shilsa qaror talab qilinsin")

    # ============ TO'G'RI QATORLAR QABUL QILINADI ============
    # Cheklov haddan tashqari qattiq emasligini ham tekshiramiz —
    # aks holda "hech narsa yozilmaydi" ham bu sinovdan o'tardi.
    def qabul(nom: str, **ozg) -> bool:
        q = _namuna(company_id=cid, tender_id=tid, **ozg)
        try:
            with conn.cursor() as cur:
                cur.execute(SQL_XOM, q)
                yangi = cur.fetchone()[0]
            with conn.cursor() as cur:
                cur.execute("DELETE FROM tender_requirement WHERE id=%s", (yangi,))
            return True
        except pg.Error as e:
            print(f"      ({nom} rad etildi: {str(e)[:90]})")
            return False

    check("QABUL: pending_review, inson izlari yo'q",
          qabul("o", position_no=201))
    check("QABUL: extracted + manba + reyestr",
          qabul("p", review_status="extracted", method="reyestr",
                mashina_holat="manba", source="api", confidence=1.00,
                position_no=202))
    check("QABUL: approved + to'liq inson dalili",
          qabul("q", review_status="approved", reviewed_by=cid,
                reviewed_at="2026-08-30", review_action="approve",
                position_no=203))
    check("QABUL: corrected + ikkala qiymat",
          qabul("r", review_status="corrected", reviewed_by=cid,
                reviewed_at="2026-08-30", review_action="correct",
                corrected_value="24 oy", previous_value="12 oy",
                position_no=204))


# =====================================================================
# 3) ILOVA QATLAMI — review_set / review_bulk
# =====================================================================
def test_ilova_qatlami(conn, cid, tid) -> None:
    section("Ilova qatlami: review_set / review_bulk")
    if conn is None:
        check("baza kerak", False, "o'tkazib yuborildi")
        return

    from api import db as _db, requirement as R
    try:
        _db.init_pool()
    except Exception:                                          # noqa: BLE001
        pass

    # Sinov qatori.
    with conn.cursor() as cur:
        cur.execute(SQL_XOM, _namuna(company_id=cid, tender_id=tid,
                                     position_no=301,
                                     name="[SINOV] ilova qatlami"))
        rid = cur.fetchone()[0]
    try:
        # `by=None` — 1 487 qatorni tug'dirgan chaqiruv shakli.
        for by in (None, 0, -1):
            try:
                R.review_set(rid, cid, "approved", by=by, ishonch="kompaniya_sessiyasi")
                check(f"review_set(by={by}) RAD ETILDI", False, "qabul qilindi!")
            except ValueError as e:
                check(f"review_set(by={by}) RAD ETILDI", True, str(e)[:70])

        # Mashina holatini API orqali qo'yib bo'lmaydi.
        for holat in ("extracted", "pending_review", "pending"):
            try:
                R.review_set(rid, cid, holat, by=cid, ishonch="kompaniya_sessiyasi")
                check(f"review_set('{holat}') RAD ETILDI", False, "qabul qilindi!")
            except ValueError:
                check(f"review_set('{holat}') RAD ETILDI", True)

        # `corrected` uchun qiymat SHART.
        try:
            R.review_set(rid, cid, "corrected", by=cid, ishonch="kompaniya_sessiyasi")
            check("review_set('corrected') qiymatsiz RAD ETILDI", False)
        except ValueError:
            check("review_set('corrected') qiymatsiz RAD ETILDI", True)

        # HAQIQIY inson qarori ISHLAYDI va audit maydonlarini to'ldiradi.
        row = R.review_set(rid, cid, "approved", by=cid, ishonch="kompaniya_sessiyasi")
        check("HAQIQIY inson tasdig'i yozildi", bool(row), str(row)[:80])
        if row:
            check("review_action = 'approve'", row.get("review_action") == "approve",
                  str(row.get("review_action")))
            check("reviewed_by yozildi", row.get("reviewed_by") == cid,
                  str(row.get("reviewed_by")))
            check("reviewed_at yozildi", row.get("reviewed_at") is not None)

        # TUZATISH: previous_value AVTOMATIK to'ladi.
        row2 = R.review_set(rid, cid, "corrected", corrected="24 oy", by=cid, ishonch="kompaniya_sessiyasi")
        check("tuzatish: review_action='correct'",
              bool(row2) and row2.get("review_action") == "correct")
        check("tuzatish: previous_value AVTOMATIK to'ldi",
              bool(row2) and row2.get("previous_value") is not None,
              str(row2 and row2.get("previous_value")))
        check("tuzatish: corrected_value yozildi",
              bool(row2) and row2.get("corrected_value") == "24 oy")

        # `review_bulk` ham `by` talab qiladi.
        for by in (None, 0):
            try:
                R.review_bulk(tid, cid, "approved", by=by, ishonch="kompaniya_sessiyasi")
                check(f"review_bulk(by={by}) RAD ETILDI", False, "qabul qilindi!")
            except ValueError:
                check(f"review_bulk(by={by}) RAD ETILDI", True)
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tender_requirement WHERE id=%s", (rid,))


# =====================================================================
# 4) QAYTA AJRATISH — tasdiq bekor bo'lsa inson izlari TOZALANADI
# =====================================================================
def test_qayta_ajratish(conn, cid, tid) -> None:
    section("Qayta ajratish: qiymat o'zgarsa tasdiq bekor va izlar tozalanadi")
    if conn is None:
        check("baza kerak", False, "o'tkazib yuborildi")
        return

    from api import db as _db, requirement as R
    try:
        _db.init_pool()
    except Exception:                                          # noqa: BLE001
        pass

    baza = {
        "company_id": cid, "tender_id": tid, "lot_id": None,
        "source": "document", "method": "naqsh", "position_no": 401,
        "name": "[SINOV] qayta ajratish",
        "attrs": json.dumps({"tur": "kafolat", "qiymat": "12 oy"}),
        "qty": None, "unit": None, "delivery_days": None,
        "is_mandatory": False, "confidence": 0.75, "raw_snippet": None,
        "file_ref": None, "char_start": None, "char_end": None, "model": None,
        "review_status": "pending_review", "mashina_holat": "ajratilgan",
    }
    rid = None
    try:
        r = _db.execute_returning(R.SQL_UPSERT, baza)
        rid = r["id"]
        R.review_set(rid, cid, "approved", by=cid, ishonch="kompaniya_sessiyasi")

        with conn.cursor() as cur:
            cur.execute("SELECT review_status, reviewed_by FROM tender_requirement "
                        "WHERE id=%s", (rid,))
            oldin = cur.fetchone()
        check("tasdiqlandi", oldin == ("approved", cid), str(oldin))

        # AYNI qiymat bilan qayta ajratish — tasdiq QOLADI.
        _db.execute_returning(R.SQL_UPSERT, baza)
        with conn.cursor() as cur:
            cur.execute("SELECT review_status, reviewed_by FROM tender_requirement "
                        "WHERE id=%s", (rid,))
            xuddi = cur.fetchone()
        check("qiymat o'zgarmasa tasdiq QOLADI", xuddi == ("approved", cid),
              str(xuddi))

        # QIYMAT O'ZGARDI — tasdiq bekor, inson izlari TOZALANADI.
        # Cheklov buni MAJBURLAYDI: izlar qolsa UPSERT ning o'zi
        # yiqilardi.
        yangi = dict(baza,
                     attrs=json.dumps({"tur": "kafolat", "qiymat": "24 oy"}))
        _db.execute_returning(R.SQL_UPSERT, yangi)
        with conn.cursor() as cur:
            cur.execute("SELECT review_status, reviewed_by, reviewed_at, "
                        "review_action, review_note FROM tender_requirement "
                        "WHERE id=%s", (rid,))
            keyin = cur.fetchone()
        check("qiymat o'zgarsa NAVBATGA qaytdi",
              keyin[0] == "pending_review", str(keyin[0]))
        check("inson izlari TOZALANDI (reviewed_by)", keyin[1] is None)
        check("inson izlari TOZALANDI (reviewed_at)", keyin[2] is None)
        check("inson izlari TOZALANDI (review_action)", keyin[3] is None)
        check("sabab JURNALGA yozildi",
              "qiymat_ozgardi" in (keyin[4] or ""), (keyin[4] or "")[:80])
    finally:
        if rid:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM tender_requirement WHERE id=%s", (rid,))


# =====================================================================
# 5) HISOBLAGICHLAR — holat va dalil AYNAN teng
# =====================================================================
def test_hisoblagichlar(conn) -> None:
    section("Hisoblagichlar: holat va dalil AYNAN teng")
    if conn is None:
        check("baza kerak", False, "o'tkazib yuborildi")
        return

    with conn.cursor() as cur:
        cur.execute("""SELECT count(*) FROM tender_requirement
                       WHERE review_status IN ('approved','rejected','corrected')
                         AND (reviewed_by IS NULL OR reviewed_by = 0
                              OR reviewed_at IS NULL)""")
        soxta = cur.fetchone()[0]
    check("SOXTA inson qarori = 0", soxta == 0, str(soxta))

    with conn.cursor() as cur:
        cur.execute("""SELECT
            count(*) FILTER (WHERE review_status IN
                             ('approved','rejected','corrected')) AS holat,
            count(*) FILTER (WHERE reviewed_by IS NOT NULL)       AS dalil,
            count(*) FILTER (WHERE review_status = 'pending')     AS eski
            FROM tender_requirement""")
        h, d, eski = cur.fetchone()
    check("holat = dalil", h == d, f"holat={h} dalil={d}")
    check("eski 'pending' holati QOLMADI", eski == 0, str(eski))

    with conn.cursor() as cur:
        cur.execute("SELECT * FROM v_requirement_holat")
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    check("v_requirement_holat ishlaydi", bool(rows))
    for r in rows:
        check(f"kompaniya {r['company_id']}: holat = dalil",
              r["inson_qarori_holat"] == r["inson_qarori_dalil"],
              f"{r['inson_qarori_holat']} vs {r['inson_qarori_dalil']}")
        check(f"kompaniya {r['company_id']}: yig'indi = jami",
              (r["mashina_chiqargan"] + r["navbatda"] + r["inson_tasdiqladi"]
               + r["inson_rad_etdi"] + r["inson_tuzatdi"]) == r["jami"],
              f"jami={r['jami']}")

    # `v_requirement_labeled` — INSON yorliqlagani. Mashina qatori
    # bu yerga TUSHMASLIGI shart.
    with conn.cursor() as cur:
        cur.execute("""SELECT count(*) FROM v_requirement_labeled
                       WHERE reviewed_by IS NULL""")
        check("v_requirement_labeled da inson tegmagan qator YO'Q",
              cur.fetchone()[0] == 0)

    # Navbat ko'rinishi BO'SH BO'LMASIN — nomni o'zgartirganda
    # "jimgina 0 qator" eng xavfli natija bo'lardi.
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM tender_requirement "
                    "WHERE review_status='pending_review'")
        n_navbat = cur.fetchone()[0]
        cur.execute("SELECT coalesce(sum(kutayotgan),0) FROM v_requirement_review")
        n_view = cur.fetchone()[0]
    check("navbat ko'rinishi jadval bilan MOS",
          n_navbat == n_view, f"jadval={n_navbat} ko'rinish={n_view}")
    check("navbat BO'SH EMAS (nom o'zgarishi jimgina buzmadi)",
          n_navbat > 0, str(n_navbat))


def test_migratsiya_jurnali(conn) -> None:
    section("Migratsiya jurnali: 1487 qator qayerga ketgani YOZILGAN")
    if conn is None:
        check("baza kerak", False, "o'tkazib yuborildi")
        return
    with conn.cursor() as cur:
        cur.execute("SELECT patch, oldin, keyin FROM requirement_migratsiya_jurnali "
                    "WHERE patch = 'schema_patch_requirement_8.sql'")
        r = cur.fetchone()
    check("jurnal yozuvi bor", bool(r))
    if r:
        oldin, keyin = r[1], r[2]
        check("oldingi soxta tasdiq soni yozilgan",
              oldin.get("approved_reviewed_by_null", 0) > 0,
              str(oldin))
        check("ko'chirilgan soni MOS",
              oldin.get("approved_reviewed_by_null") == keyin.get("extracted"),
              f"{oldin.get('approved_reviewed_by_null')} -> {keyin.get('extracted')}")

    # Qatorlar O'CHIRILMAGAN va provenance JOYIDA.
    #
    # DIQQAT — `extracted` qatorlarning HAMMASI migratsiyadan kelmaydi.
    # Migratsiyadan KEYIN ajratilgan yangi reyestr qatorlari ham
    # `extracted` bo'ladi va ularda migratsiya izohi BO'LMAYDI —
    # bu to'g'ri. Shuning uchun ikki narsa ALOHIDA tekshiriladi:
    #   1) HAR `extracted` qatorda provenance to'liq;
    #   2) MIGRATSIYA TEKKAN qatorlarda izoh saqlangan.
    with conn.cursor() as cur:
        cur.execute("""SELECT count(*),
               count(*) FILTER (WHERE method = 'reyestr'),
               count(*) FILTER (WHERE source = 'api'),
               count(*) FILTER (WHERE confidence = 1.00),
               count(*) FILTER (WHERE mashina_holat = 'manba'),
               count(*) FILTER (WHERE attrs IS NOT NULL),
               count(*) FILTER (WHERE extracted_at IS NOT NULL)
            FROM tender_requirement WHERE review_status = 'extracted'""")
        (n, m, src, conf, mash, attrs, vaqt) = cur.fetchone()
    check("qatorlar O'CHIRILMAGAN", n > 0, f"{n} ta")
    for nom, qiymat in (("method='reyestr'", m), ("source='api'", src),
                        ("confidence=1.00", conf), ("mashina_holat='manba'", mash),
                        ("attrs saqlangan", attrs), ("extracted_at saqlangan", vaqt)):
        check(f"provenance saqlandi: {nom}", qiymat == n, f"{qiymat}/{n}")

    with conn.cursor() as cur:
        cur.execute("""SELECT count(*),
               count(*) FILTER (WHERE review_status = 'extracted'),
               count(*) FILTER (WHERE mashina_holat = 'manba'),
               count(*) FILTER (WHERE reviewed_by IS NULL)
            FROM tender_requirement
            WHERE mashina_izoh LIKE '%schema_patch_requirement_8%'""")
        (mn, mext, mman, mrev) = cur.fetchone()
    check("migratsiya TEKKAN qatorlar bor", mn > 0, f"{mn} ta")
    check("migratsiya qatorlari 'extracted' holatida", mext == mn, f"{mext}/{mn}")
    check("migratsiya qatorlari mashina_holat='manba'", mman == mn, f"{mman}/{mn}")
    check("migratsiya qatorlarida inson qarori YO'Q", mrev == mn, f"{mrev}/{mn}")

    # Migratsiya izohi jurnaldagi son bilan MOS bo'lishi shart —
    # kamayishi mumkin (qator o'chirilsa), OSHISHI mumkin EMAS.
    if r:
        kutilgan = r[2].get("extracted") or 0
        check("migratsiya izohli qator soni jurnaldan OSHMAYDI",
              mn <= kutilgan, f"{mn} <= {kutilgan}")


# =====================================================================
def main() -> None:
    ap = argparse.ArgumentParser(description="Ko'rib chiqish butunligi sinovi")
    ap.add_argument("--offline", action="store_true",
                    help="Faqat statik tekshiruvlar (bazasiz)")
    args = ap.parse_args()

    print("=" * 70)
    print("SINOV: INSON KO'RIB CHIQISH BUTUNLIGI")
    print("=" * 70)

    test_kodda_soxta_yol_yoq()
    test_konstantalar()

    conn = db()
    if conn is None or args.offline:
        if conn is None:
            print("\n[i] Baza yo'q — cheklov sinovlari o'tkazib yuborildi.")
        else:
            print("\n[i] --offline: baza sinovlari o'tkazib yuborildi.")
            conn.close()
    else:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM company_account ORDER BY id LIMIT 1")
            r = cur.fetchone()
            cid = r[0] if r else None
            cur.execute("SELECT tender_id FROM tender_requirement LIMIT 1")
            r2 = cur.fetchone()
            tid = r2[0] if r2 else None
        if cid is None or tid is None:
            print("\n[i] Sinov uchun kompaniya/tender topilmadi.")
        else:
            # Sinov qoldiqlarini oldindan tozalaymiz.
            with conn.cursor() as cur:
                cur.execute("DELETE FROM tender_requirement "
                            "WHERE name LIKE '[SINOV]%'")
            test_baza_soxtani_rad_etadi(conn, cid, tid)
            test_ilova_qatlami(conn, cid, tid)
            test_qayta_ajratish(conn, cid, tid)
            with conn.cursor() as cur:
                cur.execute("DELETE FROM tender_requirement "
                            "WHERE name LIKE '[SINOV]%'")
        test_hisoblagichlar(conn)
        test_migratsiya_jurnali(conn)
        conn.close()

    otdi = sum(1 for _n, ok, _d in _results if ok)
    jami = len(_results)
    print("\n" + "=" * 70)
    for n, ok, d in _results:
        if not ok:
            print(f"  YIQILDI: {n}" + (f" -- {d}" if d else ""))
    print(f"NATIJA: {otdi}/{jami} o'tdi")
    print("=" * 70)
    sys.exit(0 if otdi == jami else 1)


if __name__ == "__main__":
    main()
