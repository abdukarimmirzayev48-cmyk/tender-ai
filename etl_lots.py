#!/usr/bin/env python3
"""
xt-xarid.uz  |  LOT NOMLARI va POZITSIYA TAFSILOTI ETL
======================================================
Har tender uchun `get_lots` (lot nomlari) va har lot uchun `get_items`
(yetkazib berish muddati, kafolat, texnik xarakteristikalar) yig'adi.

NEGA MUHIM:
    Ko'p lotli tender nomi foydasiz ("Многолотовая процедура"), lekin lot
    nomlari aniq ("Оборудование лазерной резки металлов 6,12,30 кВт").
    Yetkazuvchi aynan LOT darajasida qaror qabul qiladi.

Ishga tushirish:
    export XT_DB_DSN="dbname=xtxarid user=a1234 password=... host=localhost"
    python3 etl_lots.py                # barcha tenderlar
    python3 etl_lots.py --only-open
    python3 etl_lots.py --limit 3 --dry-run
"""
import argparse
import json
import os
import random
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    psycopg2 = None

URPC_URL      = "https://api.xt-xarid.uz/urpc"
REQUEST_DELAY = 0.5
MAX_RETRIES   = 3
RETRY_BACKOFF = 2.0
TIMEOUT       = 40
ITEMS_PAGE    = 101


def headers(proc_id: Any) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-DBRPC-Language": "ru",
        "x-idempotency-key": str(random.randint(10**9, 10**10)),
        "x-url-on": f"https://xt-xarid.uz/procedure/{proc_id}/core",
        "User-Agent": "xt-xarid-tender-aggregator/0.1 (research)",
    }


def urpc(session: requests.Session, method: str, params: dict,
         proc_id: Any) -> Optional[Any]:
    payload = {"id": 1, "jsonrpc": "2.0", "method": method, "params": params}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.post(URPC_URL, json=payload, headers=headers(proc_id),
                             timeout=TIMEOUT)
            r.raise_for_status()
            body = r.json()
            if body.get("error"):
                return None
            return body.get("result")
        except Exception:  # noqa: BLE001
            if attempt == MAX_RETRIES:
                return None
            time.sleep(RETRY_BACKOFF ** attempt)
    return None


# ---------------------------------------------------------------------------
# Yordamchilar
# ---------------------------------------------------------------------------
def fv(fields: dict, key: str) -> Any:
    """fields[key].value (bo'sh bo'lsa None)."""
    v = fields.get(key)
    if isinstance(v, dict):
        v = v.get("value")
    return None if v in (None, "", [], {}) else v


def as_text(v: Any) -> Optional[str]:
    if v is None:
        return None
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def as_int(v: Any) -> Optional[int]:
    """'150', 150, ' 150 kun' -> 150."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    m = re.search(r"-?\d+", str(v))
    return int(m.group()) if m else None


def transform_items(tender_id: int, lot_id: int,
                    items: List[dict]) -> List[dict]:
    rows = []
    for it in items or []:
        f = it.get("fields") or {}
        prod = fv(f, "product") or fv(f, "product_commercial") or {}
        if isinstance(prod, str):
            try:
                prod = json.loads(prod)
            except Exception:  # noqa: BLE001
                prod = {}
        rows.append({
            "tender_id": tender_id,
            "lot_id": lot_id,
            "item_id": str(it.get("item_id") or it.get("id")),
            "product_code": (prod or {}).get("id"),
            "name": (prod or {}).get("name"),
            "unit": as_text(fv(f, "unit_clone")),
            "amount_text": as_text(fv(f, "amount_clone")),
            "price_text": as_text(fv(f, "price")),
            "totalcost_text": as_text(fv(f, "totalcost_item")),
            "delivery_period": as_int(fv(f, "item_delivery_period")),
            "guarantee": as_int(fv(f, "guarantee")),
            "prod_year": as_int(fv(f, "prod_year")),
            "country_of_origin": as_text(fv(f, "country_of_origin")),
            "delivery_address": as_text(fv(f, "address")),
            "spec": as_text(fv(f, "spec")),
            "properties": json.dumps(fv(f, "product_properties") or [],
                                     ensure_ascii=False),
            "raw_json": json.dumps(it, ensure_ascii=False),
        })
    return rows


ITEM_COLS = ["tender_id", "lot_id", "item_id", "product_code", "name", "unit",
             "amount_text", "price_text", "totalcost_text", "delivery_period",
             "guarantee", "prod_year", "country_of_origin", "delivery_address",
             "spec", "properties", "raw_json"]


def save(conn, tender_id: int, lot_titles: Dict[int, str],
         items: List[dict]) -> None:
    with conn.cursor() as cur:
        # Lot nomlarini yozamiz (lot allaqachon tender_lot da bor)
        for lid, title in lot_titles.items():
            cur.execute(
                "UPDATE tender_lot SET title=%s WHERE tender_id=%s AND lot_id=%s",
                (title, tender_id, lid))

        cur.execute("DELETE FROM tender_item WHERE tender_id=%s", (tender_id,))
        if items:
            execute_values(cur,
                f"INSERT INTO tender_item ({','.join(ITEM_COLS)}) VALUES %s",
                [tuple(r[c] for c in ITEM_COLS) for r in items])
    conn.commit()


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Lot nomlari va pozitsiya tafsiloti ETL")
    ap.add_argument("--only-open", action="store_true")
    ap.add_argument("--skip-done", action="store_true",
                    help="Allaqachon yig'ilgan tenderlarni o'tkazib yuborish "
                         "(uzilgan yurishni davom ettirish uchun)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--dsn", default=os.environ.get("XT_DB_DSN"))
    args = ap.parse_args()

    if not args.dsn:
        sys.exit("XATO: DSN yo'q.")
    if psycopg2 is None:
        sys.exit("XATO: pip install psycopg2-binary")

    conn = psycopg2.connect(args.dsn)
    with conn.cursor() as cur:
        where = []
        if args.only_open:
            where.append("status='open'")
        if args.skip_done:
            where.append("id NOT IN (SELECT DISTINCT tender_id FROM tender_item)")
        sql = "SELECT id FROM tender"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY close_at DESC NULLS LAST"
        if args.limit:
            sql += f" LIMIT {int(args.limit)}"
        cur.execute(sql)
        ids = [r[0] for r in cur.fetchall()]

    print(f"[1/2] {len(ids)} ta tender uchun lot nomlari va pozitsiyalar...\n")
    session = requests.Session()
    ok = failed = n_lots = n_items = 0

    for i, tid in enumerate(ids, 1):
        res = urpc(session, "get_lots", {"proc_id": str(tid)}, tid)
        time.sleep(REQUEST_DELAY)
        if not res or not isinstance(res, dict):
            failed += 1
            print(f"  [{i}/{len(ids)}] #{tid} — lotlar olinmadi")
            continue

        titles: Dict[int, str] = {}
        all_items: List[dict] = []
        for lot in res.get("lots") or []:
            try:
                lid = int(lot.get("id"))
            except (TypeError, ValueError):
                continue
            f = lot.get("fields") or {}
            t = fv(f, "title")
            if t:
                titles[lid] = as_text(t)

            items = urpc(session, "get_items",
                         {"limit": ITEMS_PAGE, "offset": 0,
                          "proc_id": tid, "lot_id": lid}, tid)
            time.sleep(REQUEST_DELAY)
            if items:
                all_items.extend(transform_items(tid, lid, items))

        n_lots += len(titles)
        n_items += len(all_items)
        ok += 1
        first = next(iter(titles.values()), None)
        print(f"  [{i}/{len(ids)}] #{tid} — {len(titles)} lot, "
              f"{len(all_items)} pozitsiya" + (f" | {first[:45]}" if first else ""))

        if not args.dry_run:
            try:
                save(conn, tid, titles, all_items)
            except Exception as e:  # noqa: BLE001
                conn.rollback()
                print(f"    ! DB xato: {e}", file=sys.stderr)
                failed += 1

    conn.close()
    print(f"\n[2/2] Tayyor. OK: {ok}, xato: {failed}, "
          f"lot nomi: {n_lots}, pozitsiya: {n_items}")


if __name__ == "__main__":
    main()
