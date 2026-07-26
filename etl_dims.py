#!/usr/bin/env python3
"""
xt-xarid.uz  |  dim_status + dim_area to'ldiruvchi ETL
======================================================
Yordamchi reestrlarni (dimension jadvallar) yuklaydi. Ular kamdan-kam
o'zgargani uchun bu skriptni kuniga bir marta (yoki hatto haftada bir)
ishga tushirish yetarli.

MUHIM ARXITEKTURA NUANCE:
  - ref_status_tender  →  o'z alohida metodi ('ref_status_tender'), params={scope:public}
  - ref_area           →  o'z alohida metodi ('ref_area'), params={parent_id, limit, offset}
  Bular universal 'ref' metodidan FARQ qiladi (u ref_tender_public uchun).
  ref_area IERARXIK: parent_id orqali daraja tanlanadi, has_children=true bo'lsa
  quyi darajaga (tuman) tushamiz.

Ishga tushirish:
    export XT_DB_DSN="dbname=xtxarid user=a1234 host=localhost"
    python3 etl_dims.py                 # bazaga yuklaydi
    python3 etl_dims.py --dry-run       # DBsiz, faqat ko'rsatadi
"""
import argparse
import os
import sys
import time
from typing import Any, Dict, List, Optional

import requests

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    psycopg2 = None

API_URL = "https://api.xt-xarid.uz/rpc"
DELAY   = 0.5
HEADERS = {"Content-Type": "application/json",
           "User-Agent": "xt-xarid-tender-aggregator/0.1 (research)"}

# Tugallangan / bekor qilingan statuslar — dashboardda "faol emas" filtri uchun
TERMINAL_STATUSES = {"close", "cancel", "not_realized"}

# Hudud rekursiya xavfsizligi
AREA_ROOT = "33"          # respublika ildizi (aniqlangan)
MAX_DEPTH = 3             # 0=respublika, 1=viloyat, 2=tuman
PAGE_LIMIT = 51


def rpc(method: str, params: Dict[str, Any], rid: int = 1) -> Any:
    payload = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
    r = requests.post(API_URL, json=payload, headers=HEADERS, timeout=30)
    r.raise_for_status()
    body = r.json()
    if body.get("error"):
        raise RuntimeError(f"RPC error ({method}): {body['error']}")
    res = body.get("result")
    # yozuvlar ro'yxatini ajratamiz
    if isinstance(res, dict) and "result" in res:
        return res["result"]
    return res if isinstance(res, list) else (res or [])


# ---------------------------------------------------------------------------
# STATUS — o'z metodi orqali
# ---------------------------------------------------------------------------
def fetch_statuses() -> List[dict]:
    recs = rpc("ref_status_tender", {"scope": "public"})
    rows = []
    for r in recs:
        rows.append({
            "status_code": r["code"],
            "domain": "tender",
            "status_id": r["id"],
            "name_ru": r["name"],
            "name_uz": None,
            "is_terminal": r["code"] in TERMINAL_STATUSES,
        })
    return rows


# ---------------------------------------------------------------------------
# AREA — rekursiv (has_children bo'yicha quyi darajaga tushamiz)
# ---------------------------------------------------------------------------
def fetch_area_level(parent_id: str) -> List[dict]:
    """Bitta ota tugun ostidagi barcha bolalarni (sahifalab) qaytaradi."""
    out, offset = [], 0
    while True:
        batch = rpc("ref_area", {"parent_id": parent_id,
                                 "limit": PAGE_LIMIT, "offset": offset})
        out.extend(batch)
        if len(batch) < PAGE_LIMIT:
            break
        offset += PAGE_LIMIT
        time.sleep(DELAY)
    return out


def fetch_all_areas() -> List[dict]:
    """Butun ierarxiyani ildizdan rekursiv yig'adi."""
    rows: List[dict] = []
    seen = set()

    def walk(parent_id: str, depth: int):
        if depth > MAX_DEPTH:
            return
        children = fetch_area_level(parent_id)
        for c in children:
            fid = c["id"]
            if fid in seen:
                continue
            seen.add(fid)
            rows.append({
                "area_id": fid,
                "parent_id": c.get("parent_id"),
                "name_ru": c["name"],
                "name_uz": None,
                "level": fid.count("."),
                "has_children": c.get("has_children", False),
                "full_path": fid,
            })
            if c.get("has_children"):
                time.sleep(DELAY)
                walk(fid, depth + 1)

    # Ildiz tugunning o'zini ham qo'shamiz
    rows.append({"area_id": AREA_ROOT, "parent_id": None, "name_ru": "Respublika",
                 "name_uz": "Respublika", "level": 0, "has_children": True,
                 "full_path": AREA_ROOT})
    seen.add(AREA_ROOT)
    walk(AREA_ROOT, 1)
    return rows


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
def load(dsn: str, statuses: List[dict], areas: List[dict]) -> None:
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            # dim_status
            execute_values(cur,
                """INSERT INTO dim_status
                   (status_code, domain, status_id, name_ru, name_uz, is_terminal)
                   VALUES %s
                   ON CONFLICT (status_code, domain) DO UPDATE SET
                   status_id=EXCLUDED.status_id, name_ru=EXCLUDED.name_ru,
                   is_terminal=EXCLUDED.is_terminal""",
                [(s["status_code"], s["domain"], s["status_id"],
                  s["name_ru"], s["name_uz"], s["is_terminal"]) for s in statuses])

            # dim_area — parent avval kelishi uchun level bo'yicha saralaymiz
            areas_sorted = sorted(areas, key=lambda a: a["level"])
            execute_values(cur,
                """INSERT INTO dim_area
                   (area_id, parent_id, name_ru, name_uz, level, has_children, full_path)
                   VALUES %s
                   ON CONFLICT (area_id) DO UPDATE SET
                   parent_id=EXCLUDED.parent_id, name_ru=EXCLUDED.name_ru,
                   level=EXCLUDED.level, has_children=EXCLUDED.has_children,
                   full_path=EXCLUDED.full_path""",
                [(a["area_id"], a["parent_id"], a["name_ru"], a["name_uz"],
                  a["level"], a["has_children"], a["full_path"]) for a in areas_sorted])
        conn.commit()
        print("  ✓ dim_status va dim_area yuklandi (commit).")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--dsn", default=os.environ.get("XT_DB_DSN"))
    args = ap.parse_args()

    print("[1/2] Statuslar yig'ilyapti...")
    statuses = fetch_statuses()
    print(f"      {len(statuses)} status. Namuna: "
          f"{[(s['status_code'], s['name_ru'], s['is_terminal']) for s in statuses[:4]]}")

    print("[2/2] Hududlar yig'ilyapti (rekursiv)...")
    areas = fetch_all_areas()
    by_level = {}
    for a in areas:
        by_level[a["level"]] = by_level.get(a["level"], 0) + 1
    print(f"      {len(areas)} hudud. Darajalar bo'yicha: {by_level}")

    if args.dry_run:
        print("\n--dry-run: DBga yozilmadi. Namuna hududlar:")
        for a in areas[:6]:
            print("   ", a["area_id"], a["name_ru"], f"(level {a['level']})")
        return

    if not args.dsn:
        sys.exit("XATO: DSN yo'q. --dsn yoki XT_DB_DSN o'rnating.")
    if psycopg2 is None:
        sys.exit("XATO: pip install psycopg2-binary")

    print("\nDBga yuklash...")
    load(args.dsn, statuses, areas)
    print("Tayyor.")


if __name__ == "__main__":
    main()
