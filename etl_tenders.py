#!/usr/bin/env python3
"""
xt-xarid.uz  |  ref_tender_public  ETL yig'uvchi skript
=======================================================
Vazifa: JSON-RPC endpointdan barcha (yoki filtrlangan) tenderlarni sahifalab
yig'ib, PostgreSQL bazasiga (xt_xarid_schema.sql sxemasi) yuklaydi.

Tadbirkorga mo'ljallangan: standart holatda faqat OCHIQ tenderlar ('open')
yig'iladi, chunki tadbirkorga ariza berish mumkin bo'lgan tenderlar kerak.
Butun bazani olish uchun --all-statuses bayrog'ini bering.

ISHGA TUSHIRISH (o'z muhitingizda — sandbox tarmog'i bu domenga chiqa olmaydi):
    pip install requests psycopg2-binary
    export XT_DB_DSN="dbname=xtxarid user=postgres password=... host=localhost"
    python3 etl_tenders.py                 # faqat ochiq tenderlar
    python3 etl_tenders.py --all-statuses  # barcha statuslar
    python3 etl_tenders.py --dry-run       # DBga yozmasdan, faqat yig'ib sanaydi

ESLATMA (odob-axloq):
    Bu rasmiy hujjatlashtirilmagan ichki API. Serverga bosim qilmaslik uchun
    so'rovlar orasida REQUEST_DELAY (s) kechikish qo'yilgan. Ommaviy chop
    etishdan oldin UzEx/mas'ul tashkilotdan rasmiy ruxsat so'rash tavsiya etiladi.
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    psycopg2 = None  # --dry-run uchun DB shart emas

# ---------------------------------------------------------------------------
# Konfiguratsiya
# ---------------------------------------------------------------------------
API_URL        = "https://api.xt-xarid.uz/rpc"
REF_NAME       = "ref_tender_public"
PAGE_LIMIT     = 51          # aniqlangan standart limit
REQUEST_DELAY  = 1.0         # so'rovlar orasi (sekund) — rate-limit hurmati
MAX_RETRIES    = 4           # bitta sahifa uchun qayta urinishlar
RETRY_BACKOFF  = 2.0         # eksponensial kutish koeffitsienti
TIMEOUT        = 30          # so'rov timeouti (sekund)
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    # Foydalanuvchi agentini halol ko'rsatamiz
    "User-Agent": "xt-xarid-tender-aggregator/0.1 (research; contact: you@example.com)",
}


# ---------------------------------------------------------------------------
# RPC qatlami
# ---------------------------------------------------------------------------
def rpc_call(session: requests.Session, params: Dict[str, Any], req_id: int = 1) -> Any:
    """Bitta JSON-RPC 'ref' chaqiruvi, retry + backoff bilan."""
    payload = {"jsonrpc": "2.0", "id": req_id, "method": "ref", "params": params}
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.post(API_URL, json=payload, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data and data["error"]:
                raise RuntimeError(f"RPC error: {data['error']}")
            return data.get("result")
        except Exception as e:  # noqa: BLE001 — tarmoq/JSON xatolarini keng ushlaymiz
            last_err = e
            wait = RETRY_BACKOFF ** attempt
            print(f"  ! urinish {attempt}/{MAX_RETRIES} muvaffaqiyatsiz ({e}); "
                  f"{wait:.0f}s kutamiz...", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"{MAX_RETRIES} urinishdan keyin ham muvaffaqiyatsiz: {last_err}")


def fetch_all_tenders(statuses: Optional[List[str]]) -> List[Dict[str, Any]]:
    """
    ref_tender_public ni limit+offset bilan sahifalab, to'liq yig'adi.
    Bo'sh sahifa (result==[]) kelguncha davom etadi.
    """
    session = requests.Session()
    filters: Dict[str, Any] = {}
    if statuses:
        filters["status"] = statuses  # qiymatlar massiv ko'rinishida

    all_records: List[Dict[str, Any]] = []
    offset = 0
    page = 0
    while True:
        page += 1
        params = {
            "ref": REF_NAME, "op": "read",
            "limit": PAGE_LIMIT, "offset": offset,
            "filters": filters,
            # fields bermaymiz → API barcha maydonlarni qaytaradi
        }
        result = rpc_call(session, params, req_id=page)

        # Javob shakli {"result": [...]} yoki to'g'ridan-to'g'ri [...] bo'lishi mumkin
        if isinstance(result, dict) and "result" in result:
            batch = result["result"]
        elif isinstance(result, list):
            batch = result
        else:
            batch = result.get("items") if isinstance(result, dict) else []
            batch = batch or []

        got = len(batch)
        all_records.extend(batch)
        print(f"  sahifa {page}: offset={offset}, olindi={got}, "
              f"jami={len(all_records)}")

        if got < PAGE_LIMIT:      # oxirgi (to'liq bo'lmagan yoki bo'sh) sahifa
            break
        offset += PAGE_LIMIT
        time.sleep(REQUEST_DELAY)

    return all_records


# ---------------------------------------------------------------------------
# Transform — RPC yozuvini jadval qatorlariga ajratadi (namunada tasdiqlangan)
# ---------------------------------------------------------------------------
def transform(rec: Dict[str, Any]) -> Tuple[dict, List[dict], List[dict], Dict[str, dict]]:
    meta = rec.get("meta") or {}
    area = rec.get("area") or ""
    # MUHIM: dim_area.area_id TO'LIQ nuqtali yo'lni saqlaydi ('33.2137.2138.2140'),
    # oxirgi segment ('2140') EMAS. Shuning uchun FK (area_leaf_id → dim_area.area_id)
    # mos kelishi uchun bu yerga ham to'liq yo'lni beramiz (leaf tugun IDsi = yo'l).
    area_leaf = area or None

    tender_row = {
        # Ko'p-platforma sxemasi: xt-xarid ofsetsi 0, ya'ni global id = manba id.
        "id": rec["id"], "source_id": rec["id"], "source_platform": "xt-xarid",
        "type": rec.get("type"), "name": rec.get("name"),
        "status": rec.get("status"), "totalcost": rec.get("totalcost"),
        "currency": rec.get("currency"), "lang": rec.get("lang"),
        "is_new_multilot": rec.get("is_new_multilot"),
        "lot_count": rec.get("lot_count"), "good_count": rec.get("good_count"),
        "part_count": rec.get("part_count"),
        "participants_of_joint_purchase": rec.get("participants_of_joint_purchase"),
        "green": rec.get("green"),
        "area_path": area or None, "area_leaf_id": area_leaf,
        "company_id": rec.get("company_id"),
        "company_name": (rec.get("company_name") or "").strip() or None,
        "contract_num": rec.get("contract_num"),
        "contract_number": rec.get("contract_number"),
        "contract_id": rec.get("contract_id"),
        "created_at": rec.get("created_at"), "inserted_at": rec.get("inserted_at"),
        "publicated_at": rec.get("publicated_at"), "starting_date": rec.get("starting_date"),
        "agree_at": rec.get("agree_at"), "close_at": rec.get("close_at"),
        "ends_at": rec.get("ends_at"),
        "close_docs_objections_at": rec.get("close_docs_objections_at"),
        "docs_objections_remain_time": rec.get("docs_objections_remain_time"),
        "remain_time": rec.get("remain_time"),
        "raw_json": json.dumps(rec, ensure_ascii=False),
    }

    lot_rows = [
        {"tender_id": rec["id"], "lot_id": l["lot_id"],
         "item_count": l.get("item_count"), "total_sum_lot": l.get("total_sum_lot")}
        for l in meta.get("lots", [])
    ]

    good_rows: List[dict] = []
    categories: Dict[str, dict] = {}
    for g in meta.get("good_maps", []):
        cat = g.get("category")
        cat_uid = None
        if cat:
            cat_uid = cat.get("uid")
            categories[cat_uid] = {
                "category_uid": cat_uid, "code": cat.get("code"),
                "title_ru": cat.get("title"), "title_uz": None,
            }
        good_rows.append({
            "tender_id": rec["id"], "lot_id": g.get("lot_id"),
            "good_code": g.get("id"), "name": g.get("name"), "unit": g.get("unit"),
            "amount": g.get("amount"), "price": g.get("price"),
            "totalcost_item": g.get("totalcost_item"), "category_uid": cat_uid,
        })

    return tender_row, lot_rows, good_rows, categories


# ---------------------------------------------------------------------------
# Load — PostgreSQL ga UPSERT (idempotent: qayta ishga tushirsa dublikat bo'lmaydi)
# ---------------------------------------------------------------------------
TENDER_COLS = [
    "id","source_id","source_platform",
    "type","name","status","totalcost","currency","lang","is_new_multilot",
    "lot_count","good_count","part_count","participants_of_joint_purchase","green",
    "area_path","area_leaf_id","company_id","company_name","contract_num",
    "contract_number","contract_id","created_at","inserted_at","publicated_at",
    "starting_date","agree_at","close_at","ends_at","close_docs_objections_at",
    "docs_objections_remain_time","remain_time","raw_json",
]

def dedupe_by_key(rows: List[dict], key_cols: Tuple[str, ...], label: str) -> List[dict]:
    """PK bo'yicha takrorlarni olib tashlaydi (OXIRGISINI saqlaydi).

    Manba API bir tenderning bir lotida bir xil good_code'ni bir necha marta
    qaytarishi mumkin — bu PK'ni buzadi. Jimgina yo'qotmaymiz: nechta tashlangani
    log qilinadi, to'liq yozuv esa tender.raw_json da saqlanib qoladi.
    """
    seen: Dict[tuple, dict] = {}
    for r in rows:
        seen[tuple(r[c] for c in key_cols)] = r  # keyingisi avvalgisini bosadi
    dropped = len(rows) - len(seen)
    if dropped:
        print(f"  ! {label}: {dropped} ta takror qator dedup qilindi "
              f"(PK={'+'.join(key_cols)}; raw_json da saqlanib qoldi)")
    return list(seen.values())


def load_to_db(dsn: str, tenders, lots, goods, categories) -> None:
    # Yuklashdan oldin PK bo'yicha dedup — manba ma'lumotidagi takrorlar
    lots  = dedupe_by_key(lots,  ("tender_id", "lot_id"), "tender_lot")
    goods = dedupe_by_key(goods, ("tender_id", "lot_id", "good_code"), "tender_good")

    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            # 1) categories (FK bog'liqligi uchun avval)
            if categories:
                execute_values(cur,
                    """INSERT INTO dim_category (category_uid, code, title_ru, title_uz)
                       VALUES %s
                       ON CONFLICT (category_uid) DO UPDATE
                       SET code=EXCLUDED.code, title_ru=EXCLUDED.title_ru""",
                    [(c["category_uid"], c["code"], c["title_ru"], c["title_uz"])
                     for c in categories.values()])

            # 2) tenders
            execute_values(cur,
                f"""INSERT INTO tender ({",".join(TENDER_COLS)})
                    VALUES %s
                    ON CONFLICT (id) DO UPDATE SET
                    {",".join(f"{c}=EXCLUDED.{c}" for c in TENDER_COLS if c != "id")},
                    fetched_at = now()""",
                [tuple(t[c] for c in TENDER_COLS) for t in tenders])

            # 3) lots (avval eski lotlarni tozalab, qayta yozamiz — struktura o'zgarishi mumkin)
            tid_list = tuple({t["id"] for t in tenders}) or (None,)
            cur.execute("DELETE FROM tender_lot WHERE tender_id IN %s", (tid_list,))
            if lots:
                execute_values(cur,
                    """INSERT INTO tender_lot (tender_id, lot_id, item_count, total_sum_lot)
                       VALUES %s""",
                    [(l["tender_id"], l["lot_id"], l["item_count"], l["total_sum_lot"])
                     for l in lots])

            # 4) goods
            cur.execute("DELETE FROM tender_good WHERE tender_id IN %s", (tid_list,))
            if goods:
                execute_values(cur,
                    """INSERT INTO tender_good
                       (tender_id, lot_id, good_code, name, unit, amount, price,
                        totalcost_item, category_uid)
                       VALUES %s""",
                    [(g["tender_id"], g["lot_id"], g["good_code"], g["name"], g["unit"],
                      g["amount"], g["price"], g["totalcost_item"], g["category_uid"])
                     for g in goods])

        conn.commit()
        print("  ✓ DBga muvaffaqiyatli yuklandi (commit).")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="xt-xarid.uz tenderlarini yig'uvchi ETL")
    ap.add_argument("--all-statuses", action="store_true",
                    help="Barcha statuslar (standart: faqat 'open')")
    ap.add_argument("--dry-run", action="store_true",
                    help="DBga yozmasdan, faqat yig'ib sanaydi")
    ap.add_argument("--dsn", default=os.environ.get("XT_DB_DSN"),
                    help="PostgreSQL DSN (yoki XT_DB_DSN muhit o'zgaruvchisi)")
    args = ap.parse_args()

    statuses = None if args.all_statuses else ["open"]
    label = "BARCHA statuslar" if args.all_statuses else "faqat 'open' (ochiq)"
    print(f"[1/3] Yig'ish boshlandi — {label}")

    records = fetch_all_tenders(statuses)
    print(f"[1/3] Jami {len(records)} ta tender yig'ildi.\n")

    print("[2/3] Transform...")
    all_t, all_l, all_g, all_c = [], [], [], {}
    for rec in records:
        t, l, g, c = transform(rec)
        all_t.append(t); all_l.extend(l); all_g.extend(g); all_c.update(c)
    print(f"[2/3] {len(all_t)} tender, {len(all_l)} lot, {len(all_g)} tovar, "
          f"{len(all_c)} kategoriya.\n")

    if args.dry_run:
        print("[3/3] --dry-run: DBga yozilmadi. Namuna (birinchi tender):")
        if all_t:
            preview = {k: all_t[0][k] for k in
                       ["id","name","status","currency","totalcost","area_leaf_id","company_name"]}
            print("   ", json.dumps(preview, ensure_ascii=False, indent=2))
        return

    if not args.dsn:
        sys.exit("XATO: DSN berilmagan. --dsn yoki XT_DB_DSN o'rnating (yoki --dry-run).")
    if psycopg2 is None:
        sys.exit("XATO: psycopg2 o'rnatilmagan. `pip install psycopg2-binary`.")

    print("[3/3] DBga yuklash...")
    load_to_db(args.dsn, all_t, all_l, all_g, all_c)
    print("\nTayyor.")


if __name__ == "__main__":
    main()
