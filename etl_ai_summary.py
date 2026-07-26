#!/usr/bin/env python3
"""
AI TAHLIL ETL (5a bosqich) — o'zbekcha xulosa + kategoriya normalizatsiyasi
==========================================================================
Bazadagi tenderlarni Claude bilan tahlil qilib, natijani `ai_analysis`
jadvaliga saqlaydi.

XARAJAT NAZORATI (eng muhim xususiyat):
    Har tenderning kirish matni hash'lanadi. Agar shu hash bilan natija
    allaqachon bo'lsa — AI CHAQIRILMAYDI. Ya'ni:
      - qayta ishga tushirish deyarli bepul
      - faqat yangi/o'zgargan tenderlar tahlil qilinadi
    `--force` bilan keshni chetlab o'tish mumkin.

Ishga tushirish:
    export XT_DB_DSN="dbname=xtxarid user=a1234 password=... host=localhost"
    export ANTHROPIC_API_KEY="sk-ant-..."

    python3 etl_ai_summary.py --limit 3 --dry-run   # xarajatsiz: nima yuboriladi
    python3 etl_ai_summary.py --limit 3             # 3 ta tenderni tahlil qilish
    python3 etl_ai_summary.py                       # barcha OCHIQ tenderlar
    python3 etl_ai_summary.py --all                 # bazadagi hammasi (qimmat!)
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None

from api import ai  # noqa: E402

# Tender + lot + tovar + pozitsiya ma'lumotini bitta so'rovда yig'amiz
FETCH_SQL = """
SELECT
    t.id, t.type, t.name, t.company_name, t.totalcost, t.currency,
    COALESCE(a.name_uz, a.name_ru)          AS region_name,
    COALESCE(td.doc_count, 0)               AS doc_count,
    ARRAY(SELECT DISTINCT g.name FROM tender_good g
          WHERE g.tender_id = t.id AND g.name IS NOT NULL
          ORDER BY g.name LIMIT 25)          AS goods,
    (SELECT json_agg(json_build_object('lot_id', l.lot_id, 'title', l.title)
                     ORDER BY l.lot_id)
       FROM tender_lot l WHERE l.tender_id = t.id) AS lots,
    (SELECT json_agg(json_build_object(
                'name', i.name, 'unit', i.unit,
                'delivery_period', i.delivery_period, 'guarantee', i.guarantee,
                'spec', i.spec, 'properties', i.properties))
       FROM tender_item i WHERE i.tender_id = t.id) AS items,
    ax.content_hash AS cached_hash
FROM tender t
LEFT JOIN dim_area     a  ON a.area_id = t.area_leaf_id
LEFT JOIN tender_detail td ON td.tender_id = t.id
LEFT JOIN ai_analysis  ax ON ax.tender_id = t.id AND ax.kind = %(kind)s
{where}
ORDER BY t.close_at DESC NULLS LAST
{limit}
"""

UPSERT_SQL = """
INSERT INTO ai_analysis (tender_id, kind, content_hash, result, model,
                         input_tokens, output_tokens)
VALUES (%(tender_id)s, %(kind)s, %(content_hash)s, %(result)s, %(model)s,
        %(input_tokens)s, %(output_tokens)s)
ON CONFLICT (tender_id, kind) DO UPDATE SET
    content_hash = EXCLUDED.content_hash,
    result       = EXCLUDED.result,
    model        = EXCLUDED.model,
    input_tokens = EXCLUDED.input_tokens,
    output_tokens= EXCLUDED.output_tokens,
    created_at   = now()
"""


def fetch_candidates(conn, only_open: bool, limit: int | None) -> List[dict]:
    where = "WHERE t.status = 'open'" if only_open else ""
    lim = f"LIMIT {int(limit)}" if limit else ""
    sql = FETCH_SQL.format(where=where, limit=lim)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, {"kind": ai.KIND})
        return [dict(r) for r in cur.fetchall()]


def main() -> None:
    ap = argparse.ArgumentParser(description="AI tahlil ETL (o'zbekcha xulosa)")
    ap.add_argument("--all", action="store_true",
                    help="Barcha tenderlar (standart: faqat ochiq)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--force", action="store_true",
                    help="Keshni chetlab o'tib qayta tahlil qilish")
    ap.add_argument("--dry-run", action="store_true",
                    help="AI CHAQIRILMAYDI — faqat nima yuborilishini ko'rsatadi")
    ap.add_argument("--effort", default=ai.DEFAULT_EFFORT,
                    choices=["low", "medium", "high"])
    ap.add_argument("--workers", type=int, default=5,
                    help="Parallel so'rovlar soni")
    ap.add_argument("--dsn", default=os.environ.get("XT_DB_DSN"))
    args = ap.parse_args()

    if psycopg2 is None:
        sys.exit("XATO: pip install psycopg2-binary")
    if not args.dsn:
        sys.exit("XATO: DSN yo'q (XT_DB_DSN).")

    conn = psycopg2.connect(args.dsn)
    rows = fetch_candidates(conn, only_open=not args.all, limit=args.limit)
    print(f"[1/3] {len(rows)} ta nomzod tender.")

    # Kirish matnini qurib, keshni tekshiramiz
    todo: List[Dict[str, Any]] = []
    cached = 0
    for r in rows:
        text = ai.build_input(r)
        h = ai.content_hash(text)
        if not args.force and r.get("cached_hash") == h:
            cached += 1
            continue
        todo.append({"id": r["id"], "row": r, "text": text, "hash": h})

    print(f"[1/3] Keshdan: {cached} ta o'tkazib yuborildi. "
          f"Tahlil qilinadi: {len(todo)} ta.\n")

    if not todo:
        print("Hammasi allaqachon tahlil qilingan. Tayyor.")
        conn.close()
        return

    if args.dry_run:
        print("[2/3] --dry-run: AI CHAQIRILMADI. Namuna kirish matni:\n")
        s = todo[0]
        print(f"--- Tender #{s['id']} ---")
        print(s["text"][:1200])
        print(f"\n... (jami {len(s['text'])} belgi, ~{len(s['text'])//3} token)")
        print(f"\n{len(todo)} ta tender uchun taxminan "
              f"~{len(todo) * len(s['text']) // 3 // 1000}K kirish tokeni.")
        conn.close()
        return

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("XATO: ANTHROPIC_API_KEY o'rnatilmagan. .env ga qo'shing yoki "
                 "export qiling. (--dry-run kalitsiz ishlaydi.)")

    print(f"[2/3] Claude tahlili ({ai.MODEL}, effort={args.effort}, "
          f"{args.workers} parallel)...")
    ok = failed = tin = tout = 0

    def work(job: Dict[str, Any]) -> Dict[str, Any]:
        out = ai.analyze(job["row"], effort=args.effort)
        out["_job"] = job
        return out

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(work, j): j for j in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            job = futures[fut]
            try:
                out = fut.result()
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"  [{i}/{len(todo)}] #{job['id']} — XATO: {str(e)[:90]}")
                continue

            res = out["result"]
            tin += out["input_tokens"]; tout += out["output_tokens"]; ok += 1
            with conn.cursor() as cur:
                cur.execute(UPSERT_SQL, {
                    "tender_id": job["id"], "kind": ai.KIND,
                    "content_hash": job["hash"],
                    "result": json.dumps(res, ensure_ascii=False),
                    "model": out["model"],
                    "input_tokens": out["input_tokens"],
                    "output_tokens": out["output_tokens"],
                })
            conn.commit()
            print(f"  [{i}/{len(todo)}] #{job['id']} "
                  f"{res.get('category_tags')} — {res.get('summary_uz','')[:60]}")

    conn.close()
    # Opus 4.8 narxi: $5 / 1M kirish, $25 / 1M chiqish
    cost = tin / 1e6 * 5 + tout / 1e6 * 25
    print(f"\n[3/3] Tayyor. OK: {ok}, xato: {failed}")
    print(f"      Tokenlar: {tin:,} kirish + {tout:,} chiqish")
    print(f"      Taxminiy xarajat: ${cost:.2f}")


if __name__ == "__main__":
    main()
