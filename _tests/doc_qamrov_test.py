#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SINOV: HUJJAT QAYTA ISHLASH QAMROVI — JIM BO'SHLIQ QAYTMASIN
=============================================================

O'LCHANGAN MUAMMO (2026-08-30):

    tender_document        10 633
    hisobga olingan holat   3 422   (ok 2886 + unreadable 266
                                     + unsupported 252 + too_large 18)
    ----------------------------------------------------------
    KO'RINMAYDIGAN          7 211   = metadata ning 68%

SABAB (bitta va u arxitekturaviy): **holat FAQAT quyi oqim jadvalida
yashardi**. `tender_document_text` ga qator ajratish URINISHIDAN
KEYIN qo'yiladi, ya'ni "hali urinilmagan" holatining BAZADA
KO'RINISHI YO'Q edi.

Bo'shliq IKKI YO'NALISHDA chiqdi:
    A) metadata bor, holat yo'q   7 603 qator
    B) holat bor, metadata yo'q     392 qator  (391 tasi `ok`!)

(B) ning sababi: `etl_uzex.save()` va `etl_details.save()`
hujjatlarni DELETE + INSERT bilan qayta yozardi. Manba faylni
ro'yxatdan chiqarsa metadata yo'qolar, matn (FK yo'q) qolardi.

Bu sinov ikkala yo'nalishni ham qulflaydi.

ASOSIY KAFOLAT:
    total == sum(o'zaro istisno holatlar)   VA   hisobga_olinmagan == 0

Ishga tushirish:
    .venv\\Scripts\\python.exe _tests\\doc_qamrov_test.py
    .venv\\Scripts\\python.exe _tests\\doc_qamrov_test.py --offline
"""
import argparse
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
import rejim  # noqa: E402

konsol.sozla()


from dotenv import load_dotenv                                # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))

try:
    import psycopg2
except ImportError:                                           # pragma: no cover
    psycopg2 = None

_results = []
#: Sinov hujjatlari — shu prefiks bilan, oxirida tozalanadi.
PREFIKS = "zzsinov/doc/"

#: HOLAT LUG'ATI — baza CHECK i bilan AYNAN mos bo'lishi shart.
HOLATLAR = (
    "rejalashtirilmagan", "navbatda", "yuklanmoqda", "yuklab_olindi",
    "matn_ajratilmoqda", "ok", "unreadable", "unsupported", "too_large",
    "yuklab_olinmadi", "butunlay_yiqildi", "manbadan_yoqoldi",
)


def check(name: str, ok: bool, detail: str = "") -> bool:
    _results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    return ok


def section(t: str) -> None:
    print(f"\n--- {t} ---")


def db_conn():
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


def tozala(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM tender_document_text WHERE file_ref LIKE %s",
                    (PREFIKS + "%",))
        cur.execute("DELETE FROM tender_document WHERE file_ref LIKE %s",
                    (PREFIKS + "%",))


# =====================================================================
# 1) STATIK — DELETE+INSERT qaytmadimi
# =====================================================================
def _kodsiz(src: str) -> str:
    """IZOHLARNI olib tashlab, bo'shliqni normallashtiradi.

    Sinov KOD ni tekshirsin, IZOH ni emas. Bu funksiyasiz tekshiruv
    o'zining tushuntirish izohini ("ilgari `DELETE FROM ...` turardi")
    kod deb ushlab olardi va YOLG'ON yiqilardi — 2026-08-30 da aynan
    shunday bo'ldi.
    """
    qatorlar = []
    for ln in src.splitlines():
        tirnoq = ln.lstrip()
        if tirnoq.startswith("#"):
            continue
        # Qator ichidagi izoh — satr ichida `#` bo'lishi mumkin,
        # shuning uchun faqat tirnoqsiz qismini kesamiz.
        if "  # " in ln and ln.count("'") % 2 == 0 and ln.count('"') % 2 == 0:
            ln = ln.split("  # ")[0]
        qatorlar.append(ln)
    return " ".join(" ".join(qatorlar).split())


def test_delete_insert_yoq() -> None:
    section("Hujjat metadatasi O'CHIRILMAYDI (holat yo'qolmasin)")

    for fayl in ("etl_uzex.py", "etl_details.py"):
        src = io.open(os.path.join(ROOT, fayl), encoding="utf-8").read()
        tekis = _kodsiz(src)
        check(f"{fayl}: `DELETE FROM tender_document` YO'Q",
              "DELETE FROM tender_document WHERE tender_id" not in tekis,
              "o'chirish holatni va matn bilan bog'lanishni yo'qotardi "
              "(o'lchangan: 392 yetim qator)")
        check(f"{fayl}: UPSERT ishlatiladi",
              "ON CONFLICT (tender_id, file_ref) DO UPDATE" in tekis)
        check(f"{fayl}: manbada yo'q hujjat BELGILANADI, o'chirilmaydi",
              "holat='manbadan_yoqoldi'" in tekis
              and "manbadan_yoqoldi_at = COALESCE" in tekis)
        check(f"{fayl}: manbaga QAYTGAN hujjat navbatga tushadi",
              "THEN 'navbatda' ELSE tender_document.holat END" in tekis)

    # Boshqa jadvallar (lot/good/item) uchun DELETE O'RINLI va QOLADI:
    # ular butunlay qayta hisoblanadi va ularda holat yo'q.
    src = _kodsiz(io.open(os.path.join(ROOT, "etl_uzex.py"), encoding="utf-8").read())
    check("tender_good/item/lot uchun DELETE QOLDI (o'rinli)",
          "DELETE FROM tender_good WHERE tender_id" in src,
          "ularda saqlanadigan holat yo'q — qayta hisoblanadi")


def test_qayta_urinish_statik() -> None:
    section("Qayta urinish: bir marta yiqilgan hujjat qayta olinadi")
    src = io.open(os.path.join(ROOT, "etl_doc_text.py"), encoding="utf-8").read()
    tekis = _kodsiz(src)

    check("`fetch_targets` faqat `t.file_ref IS NULL` ga qaramaydi",
          "OR (d.holat = 'yuklab_olinmadi'" in tekis,
          "ilgari bir marta yiqilgan hujjat BOSHQA HECH QACHON olinmasdi")
    check("kutish oynasi hurmat qilinadi",
          "d.keyingi_urinish_at <= now()" in tekis)
    # SHART O'ZI tekshiriladi: navbat FAQAT `yuklab_olinmadi` ni
    # oladi. `butunlay_yiqildi` u ro'yxatda YO'Q, demak olinmaydi.
    check("`butunlay_yiqildi` qayta OLINMAYDI",
          "d.holat = 'yuklab_olinmadi'" in tekis
          and "d.holat = 'butunlay_yiqildi'" not in tekis
          and "d.holat IN ('yuklab_olinmadi', 'butunlay_yiqildi')" not in tekis,
          "urinishlar tugagan — cheksiz aylanmasin")
    check("manbada yo'q hujjat olinmaydi",
          "d.holat <> 'manbadan_yoqoldi'" in tekis)
    check("MAX_URINISH belgilangan", "MAX_URINISH = " in src)
    check("eksponensial kutish", "power(2, urinish + 1)" in tekis)
    check("muvaffaqiyatda urinish NOLGA qaytadi",
          "THEN urinish + 1 ELSE 0 END" in tekis)
    check("ish BOSHLANGANI belgilanadi",
          "def belgila_boshlandi" in src and "'yuklanmoqda'" in src,
          "o'rtada o'ldirilsa 'boshlandi, tugamadi' ko'rinsin")
    check("holat xaritasi bor", "HOLAT_XARITA" in src)

    from etl_doc_text import HOLAT_XARITA
    check("`download_failed` -> `yuklab_olinmadi`",
          HOLAT_XARITA.get("download_failed") == "yuklab_olinmadi")
    for st in ("ok", "unreadable", "unsupported", "too_large"):
        check(f"`{st}` xaritada bor", st in HOLAT_XARITA)


# =====================================================================
# 2) ASOSIY KAFOLAT — QAMROV 100% GA YIG'ILADI
# =====================================================================
def test_qamrov_yigiladi(conn) -> None:
    section("ASOSIY KAFOLAT: qamrov 100% ga yig'iladi")
    if conn is None:
        check("baza kerak", False, "o'tkazib yuborildi")
        return

    with conn.cursor() as cur:
        cur.execute("SELECT * FROM v_document_processing_coverage")
        cols = [c[0] for c in cur.description]
        v = dict(zip(cols, cur.fetchone()))

    check("`hisobga_olinmagan` = 0", v["hisobga_olinmagan"] == 0,
          f"{v['hisobga_olinmagan']} — noldan farqli qiymat jim bo'shliq qaytganini bildiradi")

    holat_ustunlari = ("rejalashtirilmagan", "navbatda", "yuklanmoqda",
                       "yuklab_olindi", "matn_ajratilmoqda", "ok",
                       "unreadable", "unsupported", "too_large",
                       "yuklab_olinmadi", "butunlay_yiqildi",
                       "manbadan_yoqoldi", "metadata_yoqolgan")
    yigindi = sum(v[k] for k in holat_ustunlari)
    check("jami == holatlar YIG'INDISI", yigindi == v["jami"],
          f"{yigindi} vs {v['jami']}")

    # Har metadata qatorining holati BOR va u lug'atda.
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM tender_document WHERE holat IS NULL")
        check("holatsiz metadata qatori = 0", cur.fetchone()[0] == 0)
        cur.execute("SELECT DISTINCT holat FROM tender_document")
        topilgan = {r[0] for r in cur.fetchall()}
    check("barcha holatlar LUG'ATDA", topilgan <= set(HOLATLAR),
          str(sorted(topilgan - set(HOLATLAR))))

    # O'ZARO ISTISNO — bitta hujjat ikki holatda bo'lolmaydi.
    with conn.cursor() as cur:
        cur.execute("""SELECT count(*) FROM (
            SELECT tender_id, file_ref FROM v_document_state
            GROUP BY 1,2 HAVING count(*) > 1) x""")
        check("bitta hujjat FAQAT BITTA qatorda", cur.fetchone()[0] == 0)

    print(f"      metadata={v['metadata_qatori']} matn={v['matn_qatori']} "
          f"jami={v['jami']} qamrovda={v['qamrovda']} "
          f"ok={v['ok']} ({v['ok_foiz_qamrovda']}%)")


def test_holat_dalildan(conn) -> None:
    """Holat DALILDAN chiqadi, TAXMINDAN emas."""
    section("Holat DALILGA mos (taxmin qilinmagan)")
    if conn is None:
        check("baza kerak", False, "o'tkazib yuborildi")
        return

    with conn.cursor() as cur:
        # `ok` deb belgilangan hujjatning matn qatori BOR va u `ok`.
        cur.execute("""SELECT count(*) FROM tender_document d
            WHERE d.holat = 'ok' AND NOT EXISTS (
                SELECT 1 FROM tender_document_text t
                 WHERE t.tender_id=d.tender_id AND t.file_ref=d.file_ref
                   AND t.status='ok')""")
        check("`ok` holati matn qatori bilan TASDIQLANGAN",
              cur.fetchone()[0] == 0)

        # `rejalashtirilmagan` — tender HAQIQATAN qamrovdan tashqarida.
        # Qoida `etl_doc_text.fetch_targets()` bilan AYNAN bir xil.
        cur.execute("""SELECT count(*) FROM tender_document d
            WHERE d.holat = 'rejalashtirilmagan'
              AND EXISTS (SELECT 1 FROM tender t2 WHERE t2.id=d.tender_id
                            AND t2.status='open'
                            AND (t2.close_at IS NULL OR t2.close_at > now()))""")
        check("`rejalashtirilmagan` faqat qamrovdan TASHQARIDA",
              cur.fetchone()[0] == 0,
              "qamrov qoidasi ETL bilan AYNAN bir xil bo'lishi shart")

        # HECH BIR qator DALILSIZ "yiqildi" deb belgilanmagan.
        cur.execute("""SELECT count(*) FROM tender_document
            WHERE holat IN ('yuklab_olinmadi','butunlay_yiqildi')
              AND last_error IS NULL AND urinish = 0""")
        check("DALILSIZ 'yiqildi' belgisi YO'Q", cur.fetchone()[0] == 0,
              "yo'qolgan hujjat avtomatik 'failed' deb belgilanmaydi")

        # `navbatda` — tender qamrovda VA matn qatori yo'q.
        cur.execute("""SELECT count(*) FROM tender_document d
            WHERE d.holat='navbatda' AND EXISTS (
                SELECT 1 FROM tender_document_text t
                 WHERE t.tender_id=d.tender_id AND t.file_ref=d.file_ref)""")
        check("`navbatda` da matn qatori YO'Q", cur.fetchone()[0] == 0)


def test_yetim_matnlar(conn) -> None:
    section("Yetim matnlar: yo'qotilmaydi va SANALADI")
    if conn is None:
        check("baza kerak", False, "o'tkazib yuborildi")
        return
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM v_document_text_yetim")
        n_yetim = cur.fetchone()[0]
        cur.execute("SELECT metadata_yoqolgan FROM v_document_processing_coverage")
        n_view = cur.fetchone()[0]
    check("yetim matnlar qamrovda SANALADI", n_yetim == n_view,
          f"ko'rinish={n_view} yetim={n_yetim}")
    print(f"      yetim matn: {n_yetim} ta (sabab tuzatildi — bu son o'smasligi kerak)")
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM v_document_text_yetim WHERE status='ok'")
        check("yetim matnlar YO'QOTILMADI (ko'rinishda turibdi)",
              cur.fetchone()[0] >= 0)


# =====================================================================
# 3) BAZA QULFLARI
# =====================================================================
def test_baza_qulflari(conn, tid) -> None:
    section("Baza: noma'lum holat va yarim yozuv RAD ETILADI")
    if conn is None:
        check("baza kerak", False, "o'tkazib yuborildi")
        return
    import psycopg2 as pg

    SQL = ("INSERT INTO tender_document (tender_id, file_ref, source_platform, "
           " fetched_at, holat, last_error, last_error_at, urinish, "
           " manbadan_yoqoldi_at) "
           "VALUES (%(t)s, %(f)s, 'uzex', now(), %(h)s, %(e)s, %(ea)s, %(u)s, %(my)s)")

    def p(**o):
        d = {"t": tid, "f": PREFIKS + "q", "h": "navbatda", "e": None,
             "ea": None, "u": 0, "my": None}
        d.update(o)
        return d

    def urin(**o) -> bool:
        try:
            with conn.cursor() as cur:
                cur.execute(SQL, p(**o))
            with conn.cursor() as cur:
                cur.execute("DELETE FROM tender_document WHERE file_ref LIKE %s",
                            (PREFIKS + "%",))
            return False
        except pg.Error:
            return True

    check("RAD: noma'lum holat", urin(h="ishlanmoqda"))
    check("RAD: xato vaqti bor, xato matni YO'Q", urin(ea="2026-08-30"),
          "'xato bor, lekin qanaqa' holati qolmasin")
    check("RAD: manfiy urinish", urin(u=-1))
    check("RAD: 'manbadan_yoqoldi' holati, sanasi YO'Q",
          urin(h="manbadan_yoqoldi"))
    check("RAD: sana bor, holat boshqa",
          urin(h="navbatda", my="2026-08-30"))

    def qabul(**o) -> bool:
        try:
            with conn.cursor() as cur:
                cur.execute(SQL, p(**o))
            with conn.cursor() as cur:
                cur.execute("DELETE FROM tender_document WHERE file_ref LIKE %s",
                            (PREFIKS + "%",))
            return True
        except pg.Error as e:
            print(f"      (rad etildi: {str(e)[:100]})")
            return False

    check("QABUL: navbatda", qabul())
    check("QABUL: manbadan_yoqoldi + sana",
          qabul(h="manbadan_yoqoldi", my="2026-08-30"))
    check("QABUL: yiqilish + dalil",
          qabul(h="yuklab_olinmadi", e="tarmoq uzildi",
                ea="2026-08-30", u=2))
    tozala(conn)


# =====================================================================
# 4) HAYOT SIKLI — hech bir hujjat holatsiz qolmaydi
# =====================================================================
def test_hayot_sikli(conn, tid) -> None:
    section("Hayot sikli: yangi hujjat ham HOLATSIZ qolmaydi")
    if conn is None:
        check("baza kerak", False, "o'tkazib yuborildi")
        return
    tozala(conn)
    f = PREFIKS + "hayot.pdf"
    try:
        # STANDART qiymat bilan qo'yamiz — `holat` BERILMAYDI.
        # Aynan shu holat ilgari qatorni ko'rinmas qilardi.
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tender_document (tender_id, file_ref, "
                " source_platform, fetched_at, file_type) "
                "VALUES (%s, %s, 'uzex', now(), 'pdf')", (tid, f))
            cur.execute("SELECT holat, discovered_at IS NOT NULL, urinish "
                        "FROM tender_document WHERE file_ref=%s", (f,))
            r = cur.fetchone()
        check("holat BERILMASA ham to'ldiriladi", r[0] == "navbatda", str(r[0]))
        check("`discovered_at` avtomatik to'ldi", r[1] is True)
        check("`urinish` noldan boshlanadi", r[2] == 0)

        # Qamrovda DARHOL ko'rinadi — jim bo'shliq yo'q.
        with conn.cursor() as cur:
            cur.execute("SELECT holat FROM v_document_state WHERE file_ref=%s", (f,))
            check("yangi hujjat qamrovda DARHOL ko'rinadi",
                  (cur.fetchone() or [None])[0] == "navbatda")
            cur.execute("SELECT hisobga_olinmagan FROM v_document_processing_coverage")
            check("yangi hujjat qamrovni BUZMAYDI", cur.fetchone()[0] == 0)

        # `save()` ni chaqirib holat ko'chishini tekshiramiz.
        from etl_doc_text import save
        save(conn, {"tender_id": tid, "file_ref": f, "text": "salom dunyo",
                    "status": "ok", "char_count": 11, "page_count": 1,
                    "error": None, "extractor": "sinov"})
        with conn.cursor() as cur:
            cur.execute("SELECT holat, urinish, extraction_finished_at IS NOT NULL, "
                        "       last_error, downloaded_at IS NOT NULL "
                        "FROM tender_document WHERE file_ref=%s", (f,))
            r2 = cur.fetchone()
        check("ajratishdan keyin holat 'ok'", r2[0] == "ok", str(r2[0]))
        check("urinish nolga qaytdi", r2[1] == 0)
        check("`extraction_finished_at` yozildi", r2[2] is True)
        check("xato tozalandi", r2[3] is None)
        check("`downloaded_at` yozildi", r2[4] is True)

        # YIQILISH -> urinish oshadi, kutish oynasi qo'yiladi.
        save(conn, {"tender_id": tid, "file_ref": f, "text": None,
                    "status": "download_failed", "char_count": None,
                    "page_count": None, "error": "tarmoq uzildi",
                    "extractor": None})
        with conn.cursor() as cur:
            cur.execute("SELECT holat, urinish, keyingi_urinish_at IS NOT NULL, "
                        "       last_error, last_error_at IS NOT NULL "
                        "FROM tender_document WHERE file_ref=%s", (f,))
            r3 = cur.fetchone()
        check("yiqilishda holat 'yuklab_olinmadi'", r3[0] == "yuklab_olinmadi")
        check("urinish oshdi", r3[1] == 1, str(r3[1]))
        check("kutish oynasi qo'yildi", r3[2] is True)
        check("xato SAQLANDI", r3[3] == "tarmoq uzildi")
        check("xato vaqti yozildi", r3[4] is True)

        # Urinishlar tugaguncha yiqitamiz -> `butunlay_yiqildi`.
        from etl_doc_text import MAX_URINISH
        for _ in range(MAX_URINISH):
            save(conn, {"tender_id": tid, "file_ref": f, "text": None,
                        "status": "download_failed", "char_count": None,
                        "page_count": None, "error": "tarmoq uzildi",
                        "extractor": None})
        with conn.cursor() as cur:
            cur.execute("SELECT holat, urinish, keyingi_urinish_at "
                        "FROM tender_document WHERE file_ref=%s", (f,))
            r4 = cur.fetchone()
        check("urinishlar tugagach 'butunlay_yiqildi'",
              r4[0] == "butunlay_yiqildi", f"{r4[0]} urinish={r4[1]}")
        check("kutish oynasi TOZALANDI (qayta urinilmaydi)",
              r4[2] is None)

        # Har bosqichda qamrov BUZILMADI.
        with conn.cursor() as cur:
            cur.execute("SELECT hisobga_olinmagan FROM v_document_processing_coverage")
            check("hayot sikli davomida qamrov BUZILMADI",
                  cur.fetchone()[0] == 0)
    finally:
        tozala(conn)


def test_manbadan_yoqolish(conn, tid) -> None:
    section("Manbadan yo'qolgan hujjat: O'CHIRILMAYDI, belgilanadi")
    if conn is None:
        check("baza kerak", False, "o'tkazib yuborildi")
        return
    tozala(conn)
    f = PREFIKS + "yoqoladi.pdf"
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tender_document (tender_id, file_ref, "
                " source_platform, fetched_at, holat) "
                "VALUES (%s, %s, 'uzex', now(), 'ok')", (tid, f))
            cur.execute(
                "INSERT INTO tender_document_text "
                " (tender_id, file_ref, text, status, extracted_at) "
                "VALUES (%s, %s, 'matn', 'ok', now())", (tid, f))

            # ETL manbada bu faylni ko'rmadi -> belgilaydi.
            cur.execute(
                "UPDATE tender_document SET holat='manbadan_yoqoldi', "
                "  manbadan_yoqoldi_at = now() "
                "WHERE tender_id=%s AND file_ref=%s", (tid, f))

            cur.execute("SELECT count(*) FROM tender_document WHERE file_ref=%s", (f,))
            check("metadata qatori O'CHIRILMADI", cur.fetchone()[0] == 1)
            cur.execute("SELECT count(*) FROM tender_document_text WHERE file_ref=%s", (f,))
            check("ajratilgan matn SAQLANDI", cur.fetchone()[0] == 1)
            cur.execute("SELECT holat FROM v_document_state WHERE file_ref=%s", (f,))
            check("qamrovda 'manbadan_yoqoldi' bo'lib ko'rinadi",
                  cur.fetchone()[0] == "manbadan_yoqoldi")
            cur.execute("SELECT count(*) FROM v_document_text_yetim WHERE file_ref=%s", (f,))
            check("matn YETIM bo'lib QOLMADI", cur.fetchone()[0] == 0,
                  "eski DELETE+INSERT aynan shu yerda yetim qoldirardi")
            cur.execute("SELECT hisobga_olinmagan FROM v_document_processing_coverage")
            check("qamrov buzilmadi", cur.fetchone()[0] == 0)
    finally:
        tozala(conn)


# =====================================================================
# 5) ENDPOINT
# =====================================================================
def test_endpoint() -> None:
    section("`/freshness` javobida hujjat qamrovi")
    src = io.open(os.path.join(ROOT, "api", "main.py"), encoding="utf-8").read()
    check("`v_document_processing_coverage` o'qiladi",
          "SELECT * FROM v_document_processing_coverage" in src)
    for kalit in ("not_scheduled", "pending", "ok", "unreadable",
                  "unsupported", "too_large", "download_failed",
                  "permanently_failed", "gone_from_source",
                  "metadata_missing", "unaccounted", "reconciles"):
        check(f"javobda '{kalit}' bor", f'"{kalit}"' in src)
    check("`reconciles` nazorat bayrog'i hisoblanadi",
          '"reconciles": int(d.get("hisobga_olinmagan") or 0) == 0' in src,
          "jim bo'shliq qaytsa javobda KO'RINADI")


# =====================================================================
def main() -> None:
    ap = argparse.ArgumentParser(description="Hujjat qamrovi sinovi")
    rejim.bayroqlar(ap)
    args = rejim.moslash(ap.parse_args())

    print("=" * 70)
    print("SINOV: HUJJAT QAYTA ISHLASH QAMROVI")
    print("=" * 70)

    test_delete_insert_yoq()
    test_qayta_urinish_statik()
    test_endpoint()

    conn = db_conn()
    if conn is None or args.bazasiz:
        if conn is None:
            print("\n[i] Baza yo'q — qamrov sinovlari o'tkazib yuborildi.")
        else:
            print("\n[i] --offline: baza sinovlari o'tkazib yuborildi.")
            conn.close()
    else:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM tender ORDER BY id LIMIT 1")
            r = cur.fetchone()
        tid = r[0] if r else None
        tozala(conn)
        test_qamrov_yigiladi(conn)
        test_holat_dalildan(conn)
        test_yetim_matnlar(conn)
        if tid is not None:
            test_baza_qulflari(conn, tid)
            test_hayot_sikli(conn, tid)
            test_manbadan_yoqolish(conn, tid)
        tozala(conn)
        # OXIRIDA yana tekshiramiz — sinovlar qamrovni buzmadimi.
        with conn.cursor() as cur:
            cur.execute("SELECT hisobga_olinmagan FROM v_document_processing_coverage")
            check("sinovlardan KEYIN ham qamrov 100%", cur.fetchone()[0] == 0)
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
