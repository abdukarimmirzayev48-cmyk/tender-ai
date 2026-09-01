#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SINOV: VEKTORLASH QAMROVI — HOLAT, NUSXALASH, MODEL VERSIYASI
==============================================================

O'LCHANGAN HOLAT (2026-08-30):

    doc_chunk        157 266
    vektorlangan      95 874
    vektorsiz         61 392   (qamrov 60.96%)

IKKI SABAB, IKKALASI HAM O'LCHANGAN:

  1. QUVVAT ZAXIRADAN ORQADA. 2026-08-28 da 36 560 yangi bo'lak keldi,
     2 758 tasi vektorlandi. Soatlik RAG vazifasi `--vector-budget
     1000` bilan yuradi va o'zi ham muntazam `0xC000013A` bilan
     o'ldirilardi.

  2. TAKROR MATN QAYTA HISOBLANARDI. Vektorsiz 61 392 bo'lakdan
     31 138 tasining (51%) matni ALLAQACHON vektorlangan.
     `content_hash` ustuni bor edi, lekin vektorlash undan
     FOYDALANMASDI.

Uchinchi, ko'rinmas muammo: `embedding IS NULL` UCH XIL narsani
anglatardi — "navbatda", "yiqildi", "yaroqsiz". Ular ajratilmagani
uchun "nega vektorlanmagan" degan savolga javob YO'Q edi.

Ishga tushirish:
    .venv\\Scripts\\python.exe _tests\\embed_qamrov_test.py
    .venv\\Scripts\\python.exe _tests\\embed_qamrov_test.py --offline
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
#: Sinov bo'laklari shu tender ostida — oxirida tozalanadi.
SINOV_FILE = "zzsinov/embed/"

HOLATLAR = ("navbatda", "ok", "eskirgan", "yiqildi", "butunlay_yiqildi",
            "yaroqsiz", "otkazildi")


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
        cur.execute("DELETE FROM doc_chunk WHERE file_ref LIKE %s",
                    (SINOV_FILE + "%",))


def _kodsiz(src: str) -> str:
    """Izohlarni olib tashlaydi — sinov KODNI tekshirsin, izohni emas."""
    qatorlar = [ln for ln in src.splitlines() if not ln.lstrip().startswith("#")]
    return " ".join(" ".join(qatorlar).split())


# =====================================================================
# 1) STATIK
# =====================================================================
def test_statik() -> None:
    section("Kod: nusxalash, xato izolyatsiyasi, model versiyasi")
    src = io.open(os.path.join(ROOT, "etl_embed.py"), encoding="utf-8").read()
    tekis = _kodsiz(src)

    check("XESHDAN NUSXALASH SQL i bor", "NUSXALA_SQL" in src,
          "o'lchangan: navbatning 51% i takror matn")
    check("nusxalash MODELNI tekshiradi",
          "embed_model = %(model)s" in tekis and "NUSXALA_SQL" in src,
          "boshqa model vektorini nusxalash masofani ma'nosiz qilardi")
    check("nusxalangan qator `embed_manba='xesh'` oladi",
          "embed_manba        = 'xesh'" in src,
          "tezlik o'lchovi nusxalar bilan shishmasin")
    check("model yo'li `embed_manba='model'` yozadi",
          "embed_manba        = 'model'" in src)

    check("bitta bo'lak yiqilishi ALOHIDA yoziladi", "YIQILDI_SQL" in src)
    check("partiya yiqilsa YURISH TO'XTAMAYDI",
          "except Exception as e:" in src and "partiya yiqildi" in src,
          "ilgari istisno butun yurishni to'xtatardi va sabab yo'qolardi")
    check("urinishlar tugagach `butunlay_yiqildi`",
          "butunlay_yiqildi" in tekis and "MAX_URINISH" in src,
          "buzuq bo'lak navbat boshida abadiy aylanmasin")

    check("model o'zgarishi BOSHQARILADIGAN", "MODEL_OZGARDI_SQL" in src
          and "--model-ozgardi" in src,
          "ETL o'zi soatlab qayta hisoblashni boshlab yubormasin")
    check("matn o'zgarishi ham kuzatiladi", "MATN_OZGARDI_SQL" in src)
    check("qayta belgilash VEKTORNI O'CHIRMAYDI",
          "eski vektorlar O" in src,
          "qidiruv qayta hisoblash tugagunga qadar ham ishlasin")

    check("`--qamrov` buyrug'i bor", "def qamrov_korsat" in src)
    check("navbat HOLAT bo'yicha tanlanadi",
          "embed_holat_aniqla(c.embed_holat, false, c.text)" in tekis,
          "`yaroqsiz` va `butunlay_yiqildi` navbatga tushmasin")
    check("vektor bilan birga METAMA'LUMOT ham yoziladi",
          all(x in src for x in ("embed_dims         = %(dims)s",
                                 "embedded_at        = now()",
                                 "embed_content_hash = content_hash")))


def test_idempotentlik_shartlari() -> None:
    section("Idempotentlik: navbat sharti va partiya commit i")
    src = io.open(os.path.join(ROOT, "etl_embed.py"), encoding="utf-8").read()
    tekis = _kodsiz(src)

    check("navbat sharti `embedding IS NULL`",
          "WHERE c.embedding IS NULL" in tekis,
          "qayta yurgizilsa vektorlangan bo'lak QAYTA olinmaydi")
    check("HAR PARTIYADAN KEYIN commit", "conn.commit()" in src)
    check("nusxalash ham `c.embedding IS NULL` shartida",
          "AND c.embedding IS NULL" in tekis,
          "poyga holatida ikki marta yozilmasin")
    check("bir vaqtda ikki yurish TO'SILADI",
          "_qulf_ol(conn, LOCK_VECTORS)" in src,
          "baza maslahat qulfi")
    check("o'tkazib yuborish SANALADI va ogohlantiradi",
          "OTKAZISH_OGOH" in src,
          "qulf band bo'lsa jimgina chiqib ketmasin")


# =====================================================================
# 2) QAMROV YIG'ILADI
# =====================================================================
def test_qamrov(conn) -> None:
    section("Qamrov 100% ga yig'iladi")
    if conn is None:
        check("baza kerak", False, "o'tkazib yuborildi")
        return
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM v_embedding_coverage")
        cols = [c[0] for c in cur.description]
        v = dict(zip(cols, cur.fetchone()))

    check("`hisobga_olinmagan` = 0", v["hisobga_olinmagan"] == 0,
          str(v["hisobga_olinmagan"]))
    yigindi = sum(v[k] for k in ("vektorlangan", "yaroqsiz", "otkazildi",
                                 "butunlay_yiqildi", "navbatda", "eskirgan",
                                 "yiqildi"))
    check("jami == holatlar yig'indisi", yigindi == v["jami"],
          f"{yigindi} vs {v['jami']}")

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM v_embedding_state WHERE holat IS NULL")
        check("holatsiz bo'lak = 0", cur.fetchone()[0] == 0)
        cur.execute("SELECT DISTINCT holat FROM v_embedding_state")
        topilgan = {r[0] for r in cur.fetchall()}
    check("barcha holatlar LUG'ATDA", topilgan <= set(HOLATLAR),
          str(sorted(topilgan - set(HOLATLAR))))

    check("qamrov foizi hisoblangan", v["qamrov_foiz"] is not None,
          f"{v['qamrov_foiz']}%")
    check("maxraj YAROQLI bo'laklar (yaroqsiz kirmaydi)",
          v["yaroqli"] == v["jami"] - v["yaroqsiz"] - v["otkazildi"],
          f"yaroqli={v['yaroqli']} jami={v['jami']}")
    print(f"      jami={v['jami']:,} vektorlangan={v['vektorlangan']:,} "
          f"navbatda={v['navbatda']:,} qamrov={v['qamrov_foiz']}%")


def test_sabab_korinishi(conn) -> None:
    section("Har vektorlanmagan bo'lak NEGA vektorlanmagani")
    if conn is None:
        check("baza kerak", False, "o'tkazib yuborildi")
        return
    with conn.cursor() as cur:
        cur.execute("SELECT holat, sabab, soni FROM v_embedding_pending_reason")
        r = cur.fetchall()
        cur.execute("SELECT count(*) FROM v_embedding_state WHERE holat <> 'ok'")
        jami = cur.fetchone()[0]
    check("sabab ko'rinishi ishlaydi", True, f"{len(r)} ta sabab")
    check("sabablar yig'indisi = vektorlanmaganlar soni",
          sum(x[2] for x in r) == jami, f"{sum(x[2] for x in r)} vs {jami}")
    for x in r:
        check(f"sabab bo'sh emas: {x[0]}", bool(x[1]), str(x))


# =====================================================================
# 3) BAZA QULFLARI
# =====================================================================
def test_baza_qulflari(conn, tid) -> None:
    section("Baza: yolg'on 'ok' va noma'lum holat RAD ETILADI")
    if conn is None:
        check("baza kerak", False, "o'tkazib yuborildi")
        return
    import psycopg2 as pg
    tozala(conn)

    SQL = ("INSERT INTO doc_chunk (tender_id, file_ref, chunk_no, text, "
           " char_start, char_end, content_hash, embed_holat, embed_model, "
           " embedded_at, embed_content_hash, embed_manba, embed_urinish, "
           " embed_xato, embed_xato_at) "
           "VALUES (%(t)s, %(f)s, %(n)s, %(x)s, 0, 100, %(h)s, %(hol)s, "
           " %(m)s, %(at)s, %(ech)s, %(mb)s, %(u)s, %(e)s, %(ea)s)")

    def p(**o):
        d = {"t": tid, "f": SINOV_FILE + "q", "n": 1, "x": "a" * 200,
             "h": "xesh1", "hol": "navbatda", "m": None, "at": None,
             "ech": None, "mb": None, "u": 0, "e": None, "ea": None}
        d.update(o)
        return d

    def urin(**o) -> bool:
        try:
            with conn.cursor() as cur:
                cur.execute(SQL, p(**o))
            tozala(conn)
            return False
        except pg.Error:
            return True

    # `ok` VEKTORSIZ yozilmasin — "vektorlandi" degan yolg'on holat.
    check("RAD: holat 'ok', lekin vektor YO'Q",
          urin(hol="ok", m="multilingual-e5-small", at="2026-08-30",
               ech="xesh1"),
          "yorliq bor, dalil yo'q — takroriy nuqson sinfi")
    check("RAD: noma'lum holat", urin(hol="hisoblanmoqda"))
    check("RAD: noma'lum manba", urin(mb="qoldan"))
    check("RAD: manfiy urinish", urin(u=-1))
    check("RAD: xato vaqti bor, xato matni YO'Q", urin(ea="2026-08-30"))

    def qabul(**o) -> bool:
        try:
            with conn.cursor() as cur:
                cur.execute(SQL, p(**o))
            tozala(conn)
            return True
        except pg.Error as e:
            print(f"      (rad etildi: {str(e)[:100]})")
            return False

    check("QABUL: navbatda", qabul())
    check("QABUL: yaroqsiz + sabab",
          qabul(hol="yaroqsiz", e="matn juda qisqa", ea="2026-08-30"))
    check("QABUL: yiqildi + dalil",
          qabul(hol="yiqildi", e="model xatosi", ea="2026-08-30", u=2))
    tozala(conn)


# =====================================================================
# 4) NUSXALASH VA QAYTA YURGIZISH
# =====================================================================
def test_nusxalash(conn, tid) -> None:
    section("Xeshdan nusxalash: bir xil matn IKKI MARTA hisoblanmaydi")
    if conn is None:
        check("baza kerak", False, "o'tkazib yuborildi")
        return
    tozala(conn)
    from etl_embed import NUSXALA_SQL
    try:
        matn = "Sinov matni " * 30
        xesh = "zzsinov_xesh_1"
        vek = "[" + ",".join(["0.1"] * 384) + "]"
        with conn.cursor() as cur:
            # MANBA — allaqachon vektorlangan bo'lak.
            cur.execute(
                "INSERT INTO doc_chunk (tender_id, file_ref, chunk_no, text, "
                " char_start, char_end, content_hash, embedding, embed_model, "
                " embed_holat, embedded_at, embed_content_hash, embed_dims, "
                " embed_manba) "
                "VALUES (%s,%s,1,%s,0,100,%s,%s::vector,'multilingual-e5-small',"
                " 'ok', now(), %s, 384, 'model')",
                (tid, SINOV_FILE + "manba", matn, xesh, vek, xesh))
            # NISHON — bir xil matnli, vektorsiz.
            for i in (2, 3):
                cur.execute(
                    "INSERT INTO doc_chunk (tender_id, file_ref, chunk_no, "
                    " text, char_start, char_end, content_hash) "
                    "VALUES (%s,%s,%s,%s,0,100,%s)",
                    (tid, SINOV_FILE + "nishon", i, matn, xesh))
            cur.execute("SELECT id FROM doc_chunk WHERE file_ref=%s",
                        (SINOV_FILE + "nishon",))
            idlar = [r[0] for r in cur.fetchall()]

        with conn.cursor() as cur:
            cur.execute(NUSXALA_SQL, {"model": "multilingual-e5-small",
                                      "dims": 384, "hashes": [xesh],
                                      "ids": idlar})
            nusxalandi = [r[0] for r in cur.fetchall()]
        check("ikkala nishon ham NUSXALANDI", len(nusxalandi) == 2,
              str(len(nusxalandi)))

        with conn.cursor() as cur:
            cur.execute("SELECT embed_holat, embed_manba, embed_model, "
                        "       embed_dims, embedded_at IS NOT NULL, "
                        "       embed_content_hash, embedding IS NOT NULL "
                        "FROM doc_chunk WHERE id = ANY(%s)", (idlar,))
            rows = cur.fetchall()
        for r in rows:
            check("nusxa holati 'ok'", r[0] == "ok", str(r[0]))
            check("nusxa manbai 'xesh'", r[1] == "xesh", str(r[1]))
            check("nusxa modeli yozildi", r[2] == "multilingual-e5-small")
            check("nusxa o'lchami yozildi", r[3] == 384)
            check("`embedded_at` yozildi", r[4] is True)
            check("`embed_content_hash` yozildi", r[5] == xesh)
            check("vektor haqiqatan ko'chirildi", r[6] is True)

        # QAYTA YURGIZISH — DUBLIKAT YARATMAYDI.
        with conn.cursor() as cur:
            cur.execute(NUSXALA_SQL, {"model": "multilingual-e5-small",
                                      "dims": 384, "hashes": [xesh],
                                      "ids": idlar})
            takror = cur.fetchall()
        check("QAYTA yurgizish HECH NARSA o'zgartirmaydi", len(takror) == 0,
              f"{len(takror)} qator — `embedding IS NULL` sharti to'sadi")

        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM doc_chunk WHERE file_ref LIKE %s",
                        (SINOV_FILE + "%",))
            check("qator soni O'ZGARMADI (dublikat yo'q)",
                  cur.fetchone()[0] == 3)

        # BOSHQA MODEL vektorini nusxalamaydi.
        with conn.cursor() as cur:
            cur.execute("UPDATE doc_chunk SET embedding=NULL, embed_holat=NULL, "
                        " embed_manba=NULL, embed_model=NULL, embedded_at=NULL, "
                        " embed_content_hash=NULL, embed_dims=NULL "
                        "WHERE id = ANY(%s)", (idlar,))
            cur.execute(NUSXALA_SQL, {"model": "voyage-4-nano", "dims": 1024,
                                      "hashes": [xesh], "ids": idlar})
            boshqa = cur.fetchall()
        check("BOSHQA model vektori NUSXALANMAYDI", len(boshqa) == 0,
              "modellarni aralashtirish masofani ma'nosiz qilardi")
    finally:
        tozala(conn)


def test_model_ozgarishi(conn, tid) -> None:
    section("Model o'zgarishi: BOSHQARILADIGAN qayta vektorlash")
    if conn is None:
        check("baza kerak", False, "o'tkazib yuborildi")
        return
    tozala(conn)
    from etl_embed import MODEL_OZGARDI_SQL, MATN_OZGARDI_SQL
    try:
        vek = "[" + ",".join(["0.1"] * 384) + "]"
        with conn.cursor() as cur:
            # Eski model bilan hisoblangan bo'lak.
            cur.execute(
                "INSERT INTO doc_chunk (tender_id, file_ref, chunk_no, text, "
                " char_start, char_end, content_hash, embedding, embed_model, "
                " embed_holat, embedded_at, embed_content_hash, embed_dims) "
                "VALUES (%s,%s,1,%s,0,100,'zz_h1',%s::vector,'voyage-4-nano',"
                " 'ok', now(), 'zz_h1', 1024)",
                (tid, SINOV_FILE + "eski", "a" * 200, vek))
            # Matni o'zgargan bo'lak (xesh mos emas).
            cur.execute(
                "INSERT INTO doc_chunk (tender_id, file_ref, chunk_no, text, "
                " char_start, char_end, content_hash, embedding, embed_model, "
                " embed_holat, embedded_at, embed_content_hash, embed_dims) "
                "VALUES (%s,%s,2,%s,0,100,'zz_YANGI',%s::vector,"
                " 'multilingual-e5-small','ok', now(), 'zz_ESKI', 384)",
                (tid, SINOV_FILE + "matn", "b" * 200, vek))

        with conn.cursor() as cur:
            cur.execute(MODEL_OZGARDI_SQL, {"model": "multilingual-e5-small"})
            n_model = cur.rowcount
            cur.execute(MATN_OZGARDI_SQL)
            n_matn = cur.rowcount
        check("boshqa model -> 'eskirgan'", n_model >= 1, str(n_model))
        check("matn o'zgargan -> 'eskirgan'", n_matn >= 1, str(n_matn))

        with conn.cursor() as cur:
            cur.execute("SELECT embed_holat, embedding IS NOT NULL "
                        "FROM doc_chunk WHERE file_ref LIKE %s ORDER BY chunk_no",
                        (SINOV_FILE + "%",))
            rows = cur.fetchall()
        for r in rows:
            check("holat 'eskirgan'", r[0] == "eskirgan", str(r[0]))
            check("ESKI VEKTOR O'CHIRILMADI", r[1] is True,
                  "qidiruv qayta hisoblash tugagunga qadar ham ishlasin")

        # `eskirgan` NAVBATGA tushadi.
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM v_embedding_state "
                        "WHERE file_ref LIKE %s AND holat='eskirgan'",
                        (SINOV_FILE + "%",))
            check("`eskirgan` qamrovda ko'rinadi", cur.fetchone()[0] == 2)
            cur.execute("SELECT hisobga_olinmagan FROM v_embedding_coverage")
            check("qamrov buzilmadi", cur.fetchone()[0] == 0)
    finally:
        tozala(conn)


def test_yiqilish_izolyatsiyasi(conn, tid) -> None:
    section("Bitta yiqilgan bo'lak navbatni to'smaydi")
    if conn is None:
        check("baza kerak", False, "o'tkazib yuborildi")
        return
    tozala(conn)
    from etl_embed import YIQILDI_SQL, MAX_URINISH
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO doc_chunk (tender_id, file_ref, chunk_no, text, "
                " char_start, char_end, content_hash) "
                "VALUES (%s,%s,1,%s,0,100,'zz_yiq') RETURNING id",
                (tid, SINOV_FILE + "yiqilgan", "c" * 200))
            cid = cur.fetchone()[0]

        for i in range(1, MAX_URINISH + 1):
            with conn.cursor() as cur:
                cur.execute(YIQILDI_SQL, {"id": cid, "xato": "model xatosi",
                                          "max": MAX_URINISH})
                cur.execute("SELECT embed_holat, embed_urinish, embed_xato "
                            "FROM doc_chunk WHERE id=%s", (cid,))
                r = cur.fetchone()
            kutilgan = "butunlay_yiqildi" if i >= MAX_URINISH else "yiqildi"
            check(f"{i}-urinish -> '{kutilgan}'", r[0] == kutilgan,
                  f"{r[0]} urinish={r[1]}")
            check(f"{i}-urinish: xato SAQLANDI", r[2] == "model xatosi")

        # `butunlay_yiqildi` NAVBATGA TUSHMAYDI.
        with conn.cursor() as cur:
            cur.execute("""SELECT count(*) FROM doc_chunk c
                WHERE c.id=%s AND c.embedding IS NULL
                  AND embed_holat_aniqla(c.embed_holat, false, c.text)
                      IN ('navbatda','eskirgan','yiqildi')""", (cid,))
            check("`butunlay_yiqildi` NAVBATGA tushmaydi",
                  cur.fetchone()[0] == 0,
                  "buzuq bo'lak navbat boshida abadiy aylanmasin")
            cur.execute("SELECT hisobga_olinmagan FROM v_embedding_coverage")
            check("qamrov buzilmadi", cur.fetchone()[0] == 0)
    finally:
        tozala(conn)


def test_yaroqsiz(conn, tid) -> None:
    section("Yaroqsiz bo'lak: qamrov MAXRAJIGA kirmaydi")
    if conn is None:
        check("baza kerak", False, "o'tkazib yuborildi")
        return
    tozala(conn)
    # GLOBAL SANOQ DELTASIGA TAYANMAYMIZ.
    #
    # O'lchangan (2026-08-30): sinov paytida rejalashtirilgan RAG
    # vazifasi yurib turgan edi va `jami` bir necha soniyada 165 304
    # dan 167 038 ga o'zgardi. "Jami aynan 1 ga oshdi" degan tekshiruv
    # jonli tizimda YOLG'ON yiqiladi va bu sinovni ishonchsiz qiladi.
    #
    # Shuning uchun INVARIANT tekshiriladi: `yaroqli` maxraji
    # `yaroqsiz` va `otkazildi` ni O'Z ICHIGA OLMAYDI — bu qamrov
    # foizining ta'rifi va u global o'zgarishlarga bog'liq emas.
    try:
        with conn.cursor() as cur:
            # Juda qisqa matnli bo'lak — vektorlash MA'NOSIZ.
            cur.execute(
                "INSERT INTO doc_chunk (tender_id, file_ref, chunk_no, text, "
                " char_start, char_end, content_hash) "
                "VALUES (%s,%s,1,'qisqa',0,5,'zz_q') RETURNING id",
                (tid, SINOV_FILE + "qisqa"))
            qid = cur.fetchone()[0]
            cur.execute("SELECT holat FROM v_embedding_state WHERE id=%s", (qid,))
            check("qisqa matn DALILDAN 'yaroqsiz'",
                  cur.fetchone()[0] == "yaroqsiz")

            # Shu QATOR maxrajga kirmasligini ANIQ tekshiramiz.
            cur.execute("""SELECT count(*) FROM v_embedding_state
                WHERE id = %s AND holat NOT IN ('yaroqsiz','otkazildi')""",
                        (qid,))
            check("yaroqsiz bo'lak MAXRAJGA kirmaydi", cur.fetchone()[0] == 0)

            # Ta'rif invarianti: yaroqli == jami - yaroqsiz - otkazildi.
            cur.execute("SELECT yaroqli, jami, yaroqsiz, otkazildi "
                        "FROM v_embedding_coverage")
            v = cur.fetchone()
        check("yaroqli == jami - yaroqsiz - otkazildi",
              v[0] == v[1] - v[2] - v[3],
              f"{v[0]} vs {v[1]}-{v[2]}-{v[3]}")
        check("yaroqsiz sanoqda KO'RINADI", v[2] >= 1, str(v[2]))
    finally:
        tozala(conn)


# =====================================================================
def main() -> None:
    ap = argparse.ArgumentParser(description="Vektorlash qamrovi sinovi")
    rejim.bayroqlar(ap)
    args = rejim.moslash(ap.parse_args())

    print("=" * 70)
    print("SINOV: VEKTORLASH QAMROVI")
    print("=" * 70)

    test_statik()
    test_idempotentlik_shartlari()

    conn = db_conn()
    if conn is None or args.bazasiz:
        if conn is None:
            print("\n[i] Baza yo'q — qamrov sinovlari o'tkazib yuborildi.")
        else:
            print("\n[i] --offline: baza sinovlari o'tkazib yuborildi.")
            conn.close()
    else:
        with conn.cursor() as cur:
            cur.execute("SELECT tender_id FROM doc_chunk LIMIT 1")
            r = cur.fetchone()
        tid = r[0] if r else None
        tozala(conn)
        test_qamrov(conn)
        test_sabab_korinishi(conn)
        if tid is not None:
            test_baza_qulflari(conn, tid)
            test_nusxalash(conn, tid)
            test_model_ozgarishi(conn, tid)
            test_yiqilish_izolyatsiyasi(conn, tid)
            test_yaroqsiz(conn, tid)
        tozala(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT hisobga_olinmagan FROM v_embedding_coverage")
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
