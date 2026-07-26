#!/usr/bin/env python3
"""
KATEGORIYALASH (B bosqich) — tenderlarni yagona kategoriyaga bog'laydi
=====================================================================
AI'siz, deterministik: tovar kodi (good_code) 2-xonali prefiksi -> NACE
bo'limi -> kategoriya (api/categories.py OKED_MAP).

Daraxtni (dim_category_uz) ham api/categories.py dan ekadi — yagona manba.

Ishga tushirish:
    export XT_DB_DSN="dbname=xtxarid user=a1234 password=... host=localhost"
    python3 etl_categorize.py
    python3 etl_categorize.py --dry-run   # DBsiz, taqsimotni ko'rsatadi
"""
import argparse
import os
import re
import sys
from collections import Counter
from typing import Dict, List, Set

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import psycopg2
    from psycopg2.extras import execute_values, RealDictCursor
except ImportError:
    psycopg2 = None

from api import categories as C

DIVISION_RE = re.compile(r"^\s*(\d{2})")


def seed_tree(conn) -> None:
    """dim_category_uz ni api/categories.py CATEGORY_TREE dan ekadi."""
    with conn.cursor() as cur:
        # Parent avval kelishi uchun: NULL-parent yozuvlar birinchi
        ordered = sorted(C.CATEGORY_TREE, key=lambda r: (r[1] is not None, r[3]))
        execute_values(cur,
            """INSERT INTO dim_category_uz (code, parent, name_uz, sort_order)
               VALUES %s
               ON CONFLICT (code) DO UPDATE SET
               parent=EXCLUDED.parent, name_uz=EXCLUDED.name_uz,
               sort_order=EXCLUDED.sort_order""",
            [(code, parent, name, sort) for code, parent, name, sort in ordered])
    conn.commit()


def fetch_tenders(conn) -> List[dict]:
    """Har tender uchun: platforma + tovar kodlari (kategoriyalash uchun)."""
    sql = """
    SELECT t.id, t.source_platform,
           ARRAY(SELECT g.good_code FROM tender_good g
                 WHERE g.tender_id = t.id AND g.good_code IS NOT NULL) AS codes
    FROM tender t
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql)
        return [dict(r) for r in cur.fetchall()]


def categorize(row: dict) -> Set[str]:
    """Bitta tenderning kategoriya kodlari to'plami — tovar kodi prefiksi bo'yicha."""
    codes: Set[str] = set()

    for gc in (row.get("codes") or []):
        m = DIVISION_RE.match(gc or "")
        if m:
            codes.add(C.code_for_division(m.group(1)))

    if not codes:
        codes.add("boshqa")
    return codes


def main() -> None:
    ap = argparse.ArgumentParser(description="Tenderlarni kategoriyalash")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--dsn", default=os.environ.get("XT_DB_DSN"))
    args = ap.parse_args()

    if psycopg2 is None:
        sys.exit("XATO: pip install psycopg2-binary")
    if not args.dsn:
        sys.exit("XATO: DSN yo'q (XT_DB_DSN).")

    conn = psycopg2.connect(args.dsn)
    if not args.dry_run:
        seed_tree(conn)
        print(f"[1/3] Daraxt ekildi: {len(C.CATEGORY_TREE)} tugun.")

    rows = fetch_tenders(conn)
    print(f"[2/3] {len(rows)} tender kategoriyalanmoqda...")

    links: List[tuple] = []
    dist: Counter = Counter()
    for r in rows:
        for code in categorize(r):
            links.append((r["id"], code))
            dist[code] += 1

    # Faqat OCHIQ tenderlar taqsimoti (foydalanuvchi shuni ko'radi)
    open_ids = {r["id"] for r in rows}  # hammasi; ochiqni alohida sanaymiz
    print(f"[2/3] {len(links)} bog'lanish. Kategoriya taqsimoti (barcha):")
    for code, n in sorted(dist.items(), key=lambda x: -x[1])[:20]:
        name = next((t[2] for t in C.CATEGORY_TREE if t[0] == code), code)
        print(f"      {n:5}  {code:24} {name}")

    if args.dry_run:
        print("\n--dry-run: DBga yozilmadi.")
        conn.close()
        return

    with conn.cursor() as cur:
        cur.execute("TRUNCATE tender_category")
        execute_values(cur,
            "INSERT INTO tender_category (tender_id, code) VALUES %s ON CONFLICT DO NOTHING",
            links)
    conn.commit()
    conn.close()
    print(f"\n[3/3] Tayyor. {len(links)} bog'lanish yozildi.")


if __name__ == "__main__":
    main()
