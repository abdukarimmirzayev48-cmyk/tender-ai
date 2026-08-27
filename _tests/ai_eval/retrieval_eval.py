#!/usr/bin/env python3
"""
RETRIEVAL EVAL — moslashtirish usullarini BIR XIL o'lchov bilan taqqoslash.

NEGA MUSTAQIL ORACLE: `tender_category.code` ni `etl_categorize.py` qo'ygan,
embedding emas. Ya'ni o'lchov tekshirayotgan narsaning xatosini TAKRORLAMAYDI
(grill-me 1-sinf). Agar oracle ham embeddingdan kelganida, har qanday
"yaxshilanish" o'z-o'zini tasdiqlash bo'lardi.

Nima o'lchanadi — precision@K: top-K natijaning nechtasi HAQIQATAN kutilgan
kategoriyada.

Usullar:
    substring  — hozirgi `matching.product_matches` (bo'lak-satr)
    xom        — markazlashsiz kosinus
    markazli   — markazlashtirilgan kosinus
    gibrid     — markazli kosinus + leksik (tsvector), RRF bilan

Ishga tushirish:
    .venv\\Scripts\\python.exe _tests\\ai_eval\\retrieval_eval.py
    .venv\\Scripts\\python.exe _tests\\ai_eval\\retrieval_eval.py --k 20
"""
import argparse
import os
import sys

import psycopg2
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
load_dotenv(os.path.join(ROOT, ".env"))

from api import ai_chat as AC          # noqa: E402
from api import matching, translit     # noqa: E402

# ---------------------------------------------------------------------
# SINOV TO'PLAMI — har biri: (yorliq, katalog mahsuloti, kutilgan kategoriya)
#
# `mahsulot` AYNAN katalogdagi shaklda: nom + kalit so'zlar. Ya'ni bu
# "ideal so'rov" emas, foydalanuvchi haqiqatan yozadigan narsa.
# ---------------------------------------------------------------------
HOLATLAR = [
    ("dori",        {"name": "dori", "keywords": []},                         "tibbiyot"),
    ("tibbiy usk.", {"name": "tibbiy uskuna",
                     "keywords": ["monitor", "apparat"]},                     "tibbiyot"),
    ("kamera",      {"name": "Hikvision kamera", "keywords": ["kamera"]},     "elektronika"),
    ("kompyuter",   {"name": "kompyuter", "keywords": ["noutbuk", "monitor"]}, "elektronika"),
    ("mebel",       {"name": "ofis mebeli", "keywords": ["stol", "stul"]},    "mebel"),
    ("oziq-ovqat",  {"name": "oziq-ovqat mahsulotlari",
                     "keywords": ["go'sht", "un"]},                            "oziq"),
]


def kengaytir(p: dict) -> str:
    """Katalog mahsulotidan SEMANTIK so'rov matnini quradi.

    NEGA KENGAYTIRISH: o'lchandi — bitta so'z ("dori") e5 uchun juda
    zaif signal; korpusdagi eng yaqin 6 ta natija bir-biridan 0.007 ga
    farq qilardi. Nom + kalit so'zlar birga berilsa ajralish oshadi.
    """
    qismlar = [p.get("name") or ""] + list(p.get("keywords") or [])
    return ", ".join(x for x in qismlar if x)


SQL_XOM = """
SELECT e.tender_id FROM tender_embedding e JOIN tender t ON t.id = e.tender_id
WHERE t.status = 'open' ORDER BY e.embedding <=> %(v)s::vector LIMIT %(k)s
"""

SQL_MARKAZLI = """
SELECT e.tender_id FROM tender_embedding e JOIN tender t ON t.id = e.tender_id
WHERE t.status = 'open' AND e.embedding_c IS NOT NULL
ORDER BY e.embedding_c <=> %(v)s::vector LIMIT %(k)s
"""

SQL_GIBRID = """
WITH sem AS (
    SELECT e.tender_id,
           ROW_NUMBER() OVER (ORDER BY e.embedding_c <=> %(v)s::vector) AS rnk
    FROM tender_embedding e JOIN tender t ON t.id = e.tender_id
    WHERE t.status = 'open' AND e.embedding_c IS NOT NULL
    ORDER BY e.embedding_c <=> %(v)s::vector LIMIT 50
),
lex AS (
    SELECT t.id AS tender_id,
           ROW_NUMBER() OVER (
               ORDER BY ts_rank_cd(t.search_tsv, to_tsquery('simple', %(tsq)s)) DESC) AS rnk
    FROM tender t
    WHERE t.status = 'open' AND t.search_tsv @@ to_tsquery('simple', %(tsq)s)
    LIMIT 50
)
SELECT COALESCE(sem.tender_id, lex.tender_id) AS tender_id,
       COALESCE(1.0/(60 + sem.rnk), 0) + COALESCE(1.0/(60 + lex.rnk), 0) AS score
FROM sem FULL OUTER JOIN lex USING (tender_id)
ORDER BY score DESC LIMIT %(k)s
"""


def substring_top(cur, mahsulot: dict, k: int):
    """Hozirgi tizim: `matching.product_matches` bilan filtrlash."""
    cur.execute("""
        SELECT t.id, t.name,
               COALESCE(string_agg(DISTINCT g.name, ' '), '') AS goods_blob,
               ARRAY(SELECT code FROM tender_category tc WHERE tc.tender_id=t.id) AS category_codes
        FROM tender t LEFT JOIN tender_good g ON g.tender_id = t.id
        WHERE t.status='open' GROUP BY t.id
        ORDER BY t.close_at ASC NULLS LAST""")
    out = []
    for r in cur.fetchall():
        cand = {"name": r[1], "goods_blob": r[2], "category_codes": r[3]}
        how = matching.product_matches(cand, mahsulot)
        if how:
            # Hozirgi shkala: kategoriya=100, nom=70
            out.append((r[0], 100 if how == "category" else 70))
    out.sort(key=lambda x: -x[1])
    return [i for i, _ in out[:k]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=10)
    args = ap.parse_args()
    K = args.k

    conn = psycopg2.connect(os.environ["XT_DB_DSN"])
    cur = conn.cursor()

    # Oracle: har tenderning kategoriyalari
    cur.execute("SELECT tender_id, array_agg(code) FROM tender_category GROUP BY 1")
    kat = {t: set(c) for t, c in cur.fetchall()}

    def togri(tid: int, kutilgan: str) -> bool:
        """Kategoriya prefiksi bilan mos (roll-up: 'qurilish' -> 'qurilish/umumiy')."""
        return any(c == kutilgan or c.startswith(kutilgan + "/")
                   for c in kat.get(tid, ()))

    cur.execute("""SELECT count(*) FROM tender t WHERE t.status='open'
                   AND EXISTS (SELECT 1 FROM tender_category tc
                               WHERE tc.tender_id=t.id)""")
    print(f"Oracle: {cur.fetchone()[0]} ta ochiq tender kategoriyalangan · K={K}\n")

    usullar = ["substring", "xom", "markazli", "gibrid"]
    jami = {u: [0, 0] for u in usullar}          # [topilgan_togri, jami_qaytgan]

    bosh = f"{'holat':<13}" + "".join(f"{u:>12}" for u in usullar)
    print(bosh)
    print("-" * len(bosh))

    for yorliq, mahsulot, kutilgan in HOLATLAR:
        q = kengaytir(mahsulot)
        vec = AC.vec_literal(AC.embed_query(q))
        tsq = AC.tsquery(q)
        natija = {}

        natija["substring"] = substring_top(cur, mahsulot, K)

        cur.execute(SQL_XOM, {"v": vec, "k": K})
        natija["xom"] = [r[0] for r in cur.fetchall()]

        cur.execute(SQL_MARKAZLI, {"v": vec, "k": K})
        natija["markazli"] = [r[0] for r in cur.fetchall()]

        if tsq:
            cur.execute(SQL_GIBRID, {"v": vec, "tsq": tsq, "k": K})
            natija["gibrid"] = [r[0] for r in cur.fetchall()]
        else:
            natija["gibrid"] = natija["markazli"]

        qator = f"{yorliq:<13}"
        for u in usullar:
            ids = natija[u]
            n_ok = sum(1 for i in ids if togri(i, kutilgan))
            jami[u][0] += n_ok
            jami[u][1] += len(ids)
            # "n/m" — m < K bo'lsa usul YETARLI NOMZOD TOPMAGAN (recall muammosi)
            qator += f"{n_ok:>7}/{len(ids):<4}"
        print(qator)

    print("-" * len(bosh))
    xul = f"{'JAMI':<13}"
    for u in usullar:
        ok, n = jami[u]
        xul += f"{(ok / n * 100 if n else 0):>10.0f}% "
    print(xul)
    print(f"\n{'(n/m: m — usul umuman qaytargan natija soni; m<K = nomzod topolmadi)'}")

    # QAMROV (recall) alohida: usul kutilgan kategoriyadagi tenderlarning
    # necha foizini UMUMAN ko'ra oldi.
    print("\nQAMROV — kutilgan kategoriyada jami nechta ochiq tender bor:")
    for yorliq, _m, kutilgan in HOLATLAR:
        n = sum(1 for t, cs in kat.items()
                if any(c == kutilgan or c.startswith(kutilgan + "/") for c in cs))
        cur.execute("SELECT count(*) FROM tender WHERE status='open' AND id = ANY(%s)",
                    ([t for t in kat if togri(t, kutilgan)],))
        print(f"  {yorliq:<13} {kutilgan:<13} ochiq: {cur.fetchone()[0]}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
