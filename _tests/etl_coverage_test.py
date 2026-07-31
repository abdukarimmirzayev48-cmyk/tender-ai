#!/usr/bin/env python3
"""
SINOV: ETL QAMROVI (P0-1 — "1-2 platformani soatiga bir marta kuzatish")
========================================================================
Nima tekshiriladi:
  1. dim_status  — ref_selection_public keltirgan IKKI yangi status lug'atda
                   bormi va nomi bo'sh emasmi (bo'lmasa frontend status
                   filtrida BO'SH nom chiqadi)
  2. status yetimlari — bazadagi har bir tender.status dim_status'da bormi
  3. qamrov      — xt-xarid'da type='selection' va uzex'da type='selection'
                   yozuvlar bazaga tushdimi (ikkinchi reyestrlar ishlayaptimi)
  4. type        — uzex TypeId=1 yozuvlari 'tender' emas, 'selection' bo'ldimi
  5. ID to'qnashuvi — manba darajasida ikki reyestr ID fazolari kesishmaydimi
                   (kesishsa bir yozuv ikkinchisini UPSERT bilan bosib ketardi)
  6. run_etl.py  — XT_DB_DSN muhitda BO'LMAGANDA ham .env dan o'qib ishga
                   tushadimi va bola-jarayon chiqishi YO'QOLMAYDIMI
                   (cp1251 -> UnicodeDecodeError regressiyasi)

Ishga tushirish:
    .venv\\Scripts\\python.exe _tests\\etl_coverage_test.py
    .venv\\Scripts\\python.exe _tests\\etl_coverage_test.py --offline   # tarmoqsiz
    .venv\\Scripts\\python.exe _tests\\etl_coverage_test.py --skip-orchestrator

DIQQAT: sinov manba API'lariga so'rov yuboradi, lekin REQUEST_DELAY
o'zgartirilmaydi va orkestrator FAQAT --limit 1 bilan yurgiziladi
(to'liq yurish uzex TypeId=1 uchun ~10 daqiqa oladi).
"""
import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))

import psycopg2  # noqa: E402

# Tekshiriladigan konstantalar (kod bilan sinxron bo'lishi uchun modullardan)
import etl_tenders  # noqa: E402
import etl_uzex     # noqa: E402

NEW_STATUSES = ("tech_check_docs", "agree_objections")

_results = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _results.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" -- {detail}" if detail else ""))
    return ok


def db():
    dsn = os.environ.get("XT_DB_DSN")
    if not dsn:
        sys.exit("XATO: XT_DB_DSN topilmadi (.env ni tekshiring).")
    return psycopg2.connect(dsn)


# ---------------------------------------------------------------------------
# 1-2) Lug'at
# ---------------------------------------------------------------------------
def test_dim_status(conn) -> None:
    print("\n[1] dim_status — yangi statuslar lug'atda bormi")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status_code, COALESCE(name_uz, name_ru) "
            "FROM dim_status WHERE domain='tender' AND status_code = ANY(%s)",
            (list(NEW_STATUSES),))
        found = dict(cur.fetchall())
    for code in NEW_STATUSES:
        check(f"dim_status['{code}'] mavjud", code in found)
        check(f"dim_status['{code}'] nomi bo'sh emas",
              bool((found.get(code) or "").strip()),
              found.get(code) or "(bo'sh)")

    print("\n[2] status yetimlari — har bir tender.status lug'atda bormi")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT t.status, count(*) FROM tender t
            LEFT JOIN dim_status s
                   ON s.status_code = t.status AND s.domain='tender'
            WHERE t.status IS NOT NULL AND s.status_code IS NULL
            GROUP BY t.status ORDER BY 2 DESC""")
        orphans = cur.fetchall()
    check("lug'atda yo'q status qolmadi", not orphans,
          "; ".join(f"{s}={n}" for s, n in orphans) or "yetim yo'q")


# ---------------------------------------------------------------------------
# 3-4) Qamrov va tur
# ---------------------------------------------------------------------------
def test_coverage(conn) -> None:
    print("\n[3] qamrov — ikkinchi reyestrlar bazaga tushdimi")
    with conn.cursor() as cur:
        cur.execute("SELECT source_platform, type, count(*) FROM tender "
                    "GROUP BY 1,2 ORDER BY 1,2")
        rows = cur.fetchall()
    counts = {(p, t): n for p, t, n in rows}
    for p, t, n in rows:
        print(f"        {p:10s} type={str(t):10s} {n}")

    check("xt-xarid: type='selection' yozuvlar bor",
          counts.get(("xt-xarid", "selection"), 0) > 0,
          f"{counts.get(('xt-xarid', 'selection'), 0)} ta")
    check("xt-xarid: type='tender' yozuvlar saqlanib qoldi",
          counts.get(("xt-xarid", "tender"), 0) > 0,
          f"{counts.get(('xt-xarid', 'tender'), 0)} ta")

    print("\n[4] type — uzex TypeId=1 'tender' emas, 'selection' bo'ldimi")
    check("etl_uzex.TYPE_BY_ID[1] == 'selection'",
          etl_uzex.TYPE_BY_ID.get(1) == "selection",
          str(etl_uzex.TYPE_BY_ID))
    check("etl_uzex.TYPE_BY_ID[2] == 'tender'",
          etl_uzex.TYPE_BY_ID.get(2) == "tender")
    check("uzex: type='selection' yozuvlar bor",
          counts.get(("uzex", "selection"), 0) > 0,
          f"{counts.get(('uzex', 'selection'), 0)} ta")

    # Ochiq lotlar soni - P0-1 ning asosiy o'lchovi
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM tender WHERE status='open'")
        n_open = cur.fetchone()[0]
    check("ochiq lotlar 66 dan ko'p (eski qamrov)", n_open > 66, f"{n_open} ta ochiq")


# ---------------------------------------------------------------------------
# 5) ID to'qnashuvi
# ---------------------------------------------------------------------------
def test_id_collisions(conn, offline: bool) -> None:
    print("\n[5] ID to'qnashuvi — reyestrlar ID fazolari kesishmaydimi")

    # Baza darajasi: uzex ofseti xt-xarid ID diapazoniga tushib qolmasin
    with conn.cursor() as cur:
        cur.execute("SELECT min(id), max(id) FROM tender WHERE source_platform='xt-xarid'")
        xt_lo, xt_hi = cur.fetchone()
        cur.execute("SELECT min(id), max(id) FROM tender WHERE source_platform='uzex'")
        uz_lo, uz_hi = cur.fetchone()
    check("uzex global ID diapazoni xt-xarid bilan kesishmaydi",
          xt_hi is None or uz_lo is None or uz_lo > xt_hi,
          f"xt=[{xt_lo}..{xt_hi}] uzex=[{uz_lo}..{uz_hi}]")

    if offline:
        print("        (--offline: manba darajasidagi tekshiruv o'tkazib yuborildi)")
        return

    # Manba darajasi: xt-xarid ikki reyestri
    t_ids = {r["id"] for r in etl_tenders.fetch_all_tenders(["open"], "ref_tender_public")}
    s_ids = {r["id"] for r in etl_tenders.fetch_all_tenders(["open"], "ref_selection_public")}
    inter = t_ids & s_ids
    check("xt-xarid: ref_tender_public vs ref_selection_public kesishmaydi",
          not inter,
          f"tender={len(t_ids)}, selection={len(s_ids)}, umumiy={len(inter)}")

    # Manba darajasi: uzex ikki TypeId (faqat ro'yxat, GetTrade chaqirilmaydi)
    u2 = {int(r["id"]) for r in etl_uzex.fetch_list(2)}
    u1 = {int(r["id"]) for r in etl_uzex.fetch_list(1)}
    inter_u = u1 & u2
    check("uzex: TypeId=1 vs TypeId=2 kesishmaydi",
          not inter_u,
          f"TypeId2={len(u2)}, TypeId1={len(u1)}, umumiy={len(inter_u)}")


# ---------------------------------------------------------------------------
# 6) Orkestrator
# ---------------------------------------------------------------------------
def test_orchestrator() -> None:
    print("\n[6] run_etl.py — .env dan DSN + bola-jarayon chiqishi yo'qolmaydi")

    # XT_DB_DSN ni MUHITDAN OLIB TASHLAYMIZ: run_etl.py uni .env dan
    # o'qishi shart (Windows'dagi asosiy regressiya shu edi).
    env = {k: v for k, v in os.environ.items() if k != "XT_DB_DSN"}
    env["PYTHONIOENCODING"] = "utf-8"

    res = subprocess.run(
        [sys.executable, os.path.join(ROOT, "run_etl.py"),
         "--limit", "1", "--skip-categorize"],
        cwd=ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=900)
    out = (res.stdout or "") + (res.stderr or "")

    check("run_etl.py XT_DB_DSN'siz muhitda ham ishga tushdi",
          "XT_DB_DSN o'rnatilmagan" not in out,
          "chiqishda 'XT_DB_DSN o'rnatilmagan' yo'q")
    check("UnicodeDecodeError chiqmadi",
          "UnicodeDecodeError" not in out)
    check("bola-jarayon chiqishi ko'rinadi (jimgina yo'qolmadi)",
          "etl_tenders.py" in out and "etl_uzex.py" in out)
    check("ikkala ochiq reyestr chaqirildi",
          "ref_tender_public" in out and "ref_selection_public" in out)
    check("uzex ikkala TypeId chaqirildi",
          out.count("etl_uzex.py --type-id") >= 2 or
          ("--type-id 1" in out and "--type-id 2" in out))
    check("etl_run jurnaliga ikkala platforma yozildi",
          "=> xt-xarid:" in out and "=> uzex:" in out)
    check("run_etl.py 0 kod bilan tugadi", res.returncode == 0,
          f"returncode={res.returncode}")

    if res.returncode != 0:
        print("        --- chiqishning oxiri ---")
        for ln in out.strip().splitlines()[-15:]:
            print("        " + ln)


def test_etl_run_log(conn) -> None:
    print("\n[7] etl_run jurnali — oxirgi yurishlar sog'lom")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT ON (source_platform)
                   source_platform, status, found, new, finished_at
            FROM etl_run ORDER BY source_platform, started_at DESC""")
        rows = cur.fetchall()
    for p, st, found, new, fin in rows:
        print(f"        {p:10s} {st:8s} jami={found} yangi={new} {fin}")
    check("etl_run'da ikkala platforma bor",
          {r[0] for r in rows} >= {"xt-xarid", "uzex"},
          str(sorted(r[0] for r in rows)))
    # 'running' — sinov ETL yurayotgan paytda ishga tushirilgan bo'lishi mumkin,
    # bu nosozlik emas. Faqat 'error' haqiqiy muammo.
    check("oxirgi yurishlarda xato yo'q",
          all(r[1] != "error" for r in rows),
          "; ".join(f"{r[0]}={r[1]}" for r in rows))


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="ETL qamrovi sinovi")
    ap.add_argument("--offline", action="store_true",
                    help="Manba API'ga chiqmaydigan tekshiruvlargina")
    ap.add_argument("--skip-orchestrator", action="store_true",
                    help="run_etl.py sinovini o'tkazib yubor (u ~1 daqiqa)")
    args = ap.parse_args()

    print("=" * 70)
    print("ETL QAMROVI SINOVI (P0-1)")
    print("=" * 70)

    conn = db()
    try:
        test_dim_status(conn)
        test_coverage(conn)
        test_id_collisions(conn, args.offline)
        if not (args.skip_orchestrator or args.offline):
            test_orchestrator()
        test_etl_run_log(conn)
    finally:
        conn.close()

    failed = [n for n, ok, _ in _results if not ok]
    print("\n" + "=" * 70)
    print(f"NATIJA: {len(_results) - len(failed)}/{len(_results)} o'tdi")
    for n in failed:
        print(f"  FAIL: {n}")
    print("=" * 70)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
