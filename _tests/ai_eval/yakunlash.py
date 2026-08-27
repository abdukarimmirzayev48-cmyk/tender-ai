# -*- coding: utf-8 -*-
"""VEKTORLASH TUGAGACH bajariladigan ketma-ketlik — bitta buyruq.

    python _tests/ai_eval/yakunlash.py            # tekshiradi va rejani chiqaradi
    python _tests/ai_eval/yakunlash.py --indeks   # indeksni qayta quradi
    python _tests/ai_eval/yakunlash.py --eval     # evalni to'liq yurgizadi (PUL)

Nima uchun alohida skript: qadamlar TARTIBI muhim va ular orasida
tekshiruv bor. Qo'lda yurgizilsa bittasi unutiladi — masalan indeks
qurilmasdan eval yurgizilsa, natija sekin va boshqacha chiqadi.
"""
import argparse
import os
import subprocess
import sys
import time

BU = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(BU))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv                              # noqa: E402
load_dotenv(os.path.join(ROOT, ".env"))

from api import db                                          # noqa: E402

# --- INDEKS PARAMETRLARI ---------------------------------------------
# `ef_construction` 64 -> 100: qurish sekinroq, lekin BIR MARTALIK,
# qidiruv sifati esa yaxshiroq. `m=16` — pgvector standarti, 384
# o'lchovli vektor uchun yetarli.
#
# `maintenance_work_mem` — standart 64 MB da 80k vektorli HNSW juda
# sekin quriladi (disk ustida birlashtirish). 2 GB berilsa xotirada
# quriladi.
INDEKS_SQL = """
SET maintenance_work_mem = '2GB';
DROP INDEX IF EXISTS doc_chunk_vec_idx;
CREATE INDEX doc_chunk_vec_idx ON doc_chunk
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 100);
"""


def holat() -> dict:
    r = db.query_one("SELECT count(*) AS n, count(embedding) AS v FROM doc_chunk")
    i = db.query_one("""SELECT indexrelname AS nom,
                               pg_size_pretty(pg_relation_size(indexrelid)) AS h
                        FROM pg_stat_user_indexes
                        WHERE indexrelname = 'doc_chunk_vec_idx'""")
    return {"bolak": r["n"], "vektor": r["v"], "indeks": i}


def qadam(nom: str, buyruq: list) -> bool:
    print(f"\n{'=' * 60}\n>>> {nom}\n{'=' * 60}")
    t0 = time.time()
    p = subprocess.run(buyruq, cwd=ROOT)
    print(f"    ({time.time() - t0:.0f} s, chiqish kodi {p.returncode})")
    return p.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--indeks", action="store_true",
                    help="HNSW indeksini qayta quradi (~10-30 daqiqa)")
    ap.add_argument("--eval", action="store_true",
                    help="Evalni to'liq yurgizadi — PUL SARFLAYDI (~$3)")
    ap.add_argument("--runs", type=int, default=5)
    args = ap.parse_args()

    db.init_pool()
    try:
        h = holat()
        qolgan = h["bolak"] - h["vektor"]
        print(f"Bo'lak      : {h['bolak']:,}")
        print(f"Vektorlangan: {h['vektor']:,} ({100*h['vektor']/max(1,h['bolak']):.1f}%)")
        print(f"Qolgan      : {qolgan:,}")
        print(f"HNSW indeks : {h['indeks']['h'] if h['indeks'] else 'YO`Q (tashlangan)'}")

        if qolgan:
            print(f"\nVEKTORLASH TUGAMAGAN — {qolgan:,} bo'lak qoldi.")
            print("  python etl_embed.py --vectors")
            print("\nIndeks va eval undan KEYIN. To'xtatildi.")
            return 1

        print("\nVektorlash tugagan.")

        if args.indeks:
            print(f"\n{'=' * 60}\n>>> HNSW indeksini qurish\n{'=' * 60}")
            t0 = time.time()
            with db.get_conn() as conn:
                eski = conn.autocommit
                conn.autocommit = True          # CREATE INDEX tranzaksiyasiz
                with conn.cursor() as cur:
                    for bolak in INDEKS_SQL.strip().split(";"):
                        if bolak.strip():
                            cur.execute(bolak)
                    cur.execute("ANALYZE doc_chunk")
                conn.autocommit = eski
            h2 = holat()
            print(f"    tayyor: {h2['indeks']['h']} ({time.time() - t0:.0f} s)")
        elif not h["indeks"]:
            print("\nINDEKS YO'Q — vektorlashni tezlashtirish uchun tashlangan.")
            print("  Qurish: python _tests/ai_eval/yakunlash.py --indeks")
            if args.eval:
                print("  Indekssiz eval yurgizilmaydi. To'xtatildi.")
                return 1

        if args.eval:
            ok = qadam("EVAL — to'liq to'plam (PUL SARFLAYDI)",
                       [sys.executable, os.path.join(BU, "run_eval.py"),
                        "--runs", str(args.runs),
                        "--out", "yakuniy_kengaytirilgan.jsonl"])
            if not ok:
                print("\nEvalda yiqilgan holatlar bor — natijani ko'ring.")
        else:
            print("\nKeyingi qadam:")
            print("  python _tests/ai_eval/yakunlash.py --indeks --eval")
        return 0
    finally:
        db.close_pool()


if __name__ == "__main__":
    raise SystemExit(main())
