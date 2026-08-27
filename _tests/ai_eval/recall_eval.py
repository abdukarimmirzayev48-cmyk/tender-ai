#!/usr/bin/env python3
"""
RECALL EVAL — "katalogimga tegishli tenderlarning nechtasini UMUMAN ko'ryapman?"

NEGA RECALL, PRECISION EMAS: foydalanuvchining shikoyati aynan qamrov
haqida — "faqat 'dori' matni bor tenderlargina chiqmoqda". Precision@10
buni O'LCHAMAYDI: 4 ta natija qaytarib 3 tasi to'g'ri bo'lsa 75% chiqadi,
lekin 44 ta mos tenderning 40 tasi ko'rinmay qolgani hisobga olinmaydi.

ORACLE: `tender_category.code` (`etl_categorize.py` qo'ygan, embedding
EMAS). Kategoriyasiz tenderlar hisobdan CHIQARILADI — ular "noto'g'ri"
emas, "noma'lum". Ilgari ular xato deb sanalgani o'lchovni buzgan edi.

Ishga tushirish:
    .venv\\Scripts\\python.exe _tests\\ai_eval\\recall_eval.py
    .venv\\Scripts\\python.exe _tests\\ai_eval\\recall_eval.py --k 50
"""
import argparse
import os
import sys

import psycopg2
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
load_dotenv(os.path.join(ROOT, ".env"))

from api import ai_chat as AC      # noqa: E402
from api import matching           # noqa: E402

# (yorliq, katalog mahsuloti AYNAN foydalanuvchi yozganday, kutilgan kategoriya)
HOLATLAR = [
    ("dori",       {"name": "dori", "keywords": [], "category_code": None},   "tibbiyot"),
    ("kamera",     {"name": "Hikvision kamera", "keywords": ["kamera"],
                    "category_code": "elektr"},                                "elektronika"),
    ("kompyuter",  {"name": "kompyuter", "keywords": [], "category_code": None}, "elektronika"),
    ("mebel",      {"name": "ofis mebeli", "keywords": [], "category_code": None}, "mebel"),
    ("oziq-ovqat", {"name": "oziq-ovqat", "keywords": [], "category_code": None}, "oziq"),
]

SQL_MARKAZLI = """
SELECT e.tender_id FROM tender_embedding e JOIN tender t ON t.id = e.tender_id
WHERE t.status = 'open' AND e.embedding_c IS NOT NULL
ORDER BY e.embedding_c <=> %(v)s::vector LIMIT %(k)s
"""

SQL_LEX = """
SELECT t.id FROM tender t
WHERE t.status='open' AND t.search_tsv @@ to_tsquery('simple', %(tsq)s)
ORDER BY ts_rank_cd(t.search_tsv, to_tsquery('simple', %(tsq)s)) DESC
LIMIT %(k)s
"""

SQL_GIBRID = """
WITH sem AS (
    SELECT e.tender_id,
           ROW_NUMBER() OVER (ORDER BY e.embedding_c <=> %(v)s::vector) AS rnk
    FROM tender_embedding e JOIN tender t ON t.id = e.tender_id
    WHERE t.status='open' AND e.embedding_c IS NOT NULL
    ORDER BY e.embedding_c <=> %(v)s::vector LIMIT %(k)s
),
lex AS (
    SELECT t.id AS tender_id,
           ROW_NUMBER() OVER (
               ORDER BY ts_rank_cd(t.search_tsv, to_tsquery('simple', %(tsq)s)) DESC) AS rnk
    FROM tender t
    WHERE t.status='open' AND t.search_tsv @@ to_tsquery('simple', %(tsq)s)
    LIMIT %(k)s
)
SELECT COALESCE(sem.tender_id, lex.tender_id) AS tid,
       COALESCE(1.0/(60+sem.rnk),0) + COALESCE(1.0/(60+lex.rnk),0) AS s
FROM sem FULL OUTER JOIN lex USING (tender_id)
ORDER BY s DESC LIMIT %(k)s
"""


def substring_all(cur, mahsulot):
    """Hozirgi tizim — CHEKLOVSIZ: u nechta nomzod TOPA OLADI?"""
    cur.execute("""
        SELECT t.id, t.name,
               COALESCE(string_agg(DISTINCT g.name,' '),'') AS goods_blob,
               ARRAY(SELECT code FROM tender_category tc WHERE tc.tender_id=t.id) AS category_codes
        FROM tender t LEFT JOIN tender_good g ON g.tender_id=t.id
        WHERE t.status='open' GROUP BY t.id""")
    return [r[0] for r in cur.fetchall()
            if matching.product_matches(
                {"name": r[1], "goods_blob": r[2], "category_codes": r[3]}, mahsulot)]


def prf_kengaytir(cur, q: str, vec: str, n_doc: int = 5, n_term: int = 12) -> str:
    """PSEUDO-RELEVANCE FEEDBACK — so'rovni MODELSIZ kengaytiradi.

    "dori" kabi bitta so'z e5 uchun juda zaif signal (o'lchandi: top-6
    ning ajralishi 0.007). Klassik IR yechimi: birinchi natijalarni
    "to'g'ri" deb faraz qilib, ulardan tez-tez uchraydigan atamalarni
    so'rovga qo'shish. AI CHAQIRILMAYDI — bu sof statistika.
    """
    cur.execute("""
        SELECT t.name || ' ' || COALESCE(string_agg(g.name,' '),'')
        FROM tender_embedding e
        JOIN tender t ON t.id = e.tender_id
        LEFT JOIN tender_good g ON g.tender_id = t.id
        WHERE t.status='open' AND e.embedding_c IS NOT NULL
        GROUP BY t.id, t.name, e.embedding_c
        ORDER BY e.embedding_c <=> %(v)s::vector LIMIT %(n)s""",
                {"v": vec, "n": n_doc})
    import collections
    import re
    c = collections.Counter()
    for (txt,) in cur.fetchall():
        for w in re.findall(r"\w{4,}", (txt or "").lower()):
            c[w] += 1
    qoshimcha = [w for w, k in c.most_common(n_term) if k >= 2]
    return q + ", " + ", ".join(qoshimcha) if qoshimcha else q


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=50)
    args = ap.parse_args()
    K = args.k

    conn = psycopg2.connect(os.environ["XT_DB_DSN"])
    cur = conn.cursor()

    cur.execute("""SELECT tc.tender_id, array_agg(tc.code) FROM tender_category tc
                   JOIN tender t ON t.id=tc.tender_id WHERE t.status='open'
                   GROUP BY 1""")
    kat = {t: set(cs) for t, cs in cur.fetchall()}

    def mos(tid, kut):
        return any(c == kut or c.startswith(kut + "/") for c in kat.get(tid, ()))

    print(f"Oracle: {len(kat)} ta ochiq tender kategoriyalangan · K={K}")
    print("Kategoriyasiz tenderlar hisobdan CHIQARILDI (noma'lum, noto'g'ri emas)\n")

    usullar = ["substring", "leksik", "markazli", "gibrid", "gibrid+PRF"]
    print(f"{'holat':<12}{'nishon':>7}" + "".join(f"{u:>13}" for u in usullar))
    print("-" * (19 + 13 * len(usullar)))

    yigindi = {u: [0, 0] for u in usullar}
    for yorliq, mahsulot, kut in HOLATLAR:
        nishon = {t for t in kat if mos(t, kut)}
        q = ", ".join([mahsulot["name"]] + list(mahsulot["keywords"] or []))
        vec = AC.vec_literal(AC.embed_query(q))
        tsq = AC.tsquery(q)

        got = {}
        got["substring"] = substring_all(cur, mahsulot)

        if tsq:
            cur.execute(SQL_LEX, {"tsq": tsq, "k": K})
            got["leksik"] = [r[0] for r in cur.fetchall()]
        else:
            got["leksik"] = []

        cur.execute(SQL_MARKAZLI, {"v": vec, "k": K})
        got["markazli"] = [r[0] for r in cur.fetchall()]

        if tsq:
            cur.execute(SQL_GIBRID, {"v": vec, "tsq": tsq, "k": K})
            got["gibrid"] = [r[0] for r in cur.fetchall()]
        else:
            got["gibrid"] = got["markazli"]

        q2 = prf_kengaytir(cur, q, vec)
        vec2 = AC.vec_literal(AC.embed_query(q2))
        tsq2 = AC.tsquery(q2)
        if tsq2:
            cur.execute(SQL_GIBRID, {"v": vec2, "tsq": tsq2, "k": K})
            got["gibrid+PRF"] = [r[0] for r in cur.fetchall()]
        else:
            got["gibrid+PRF"] = got["gibrid"]

        qator = f"{yorliq:<12}{len(nishon):>7}"
        for u in usullar:
            topildi = len(nishon & set(got[u]))
            yigindi[u][0] += topildi
            yigindi[u][1] += len(nishon)
            pct = topildi / len(nishon) * 100 if nishon else 0
            qator += f"{topildi:>5}({pct:>3.0f}%)"
        print(qator)

    print("-" * (19 + 13 * len(usullar)))
    x = f"{'RECALL':<12}{'':>7}"
    for u in usullar:
        ok, n = yigindi[u]
        x += f"{(ok / n * 100 if n else 0):>11.0f}%  "
    print(x)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
