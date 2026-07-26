#!/usr/bin/env python3
"""
etender.uzex.uz  |  ADAPTER (2-manba)
=====================================
UzEx tenderlarini bizning UMUMIY sxemamizga o'giradi. Baza, backend API va
dashboard o'zgarmaydi — faqat shu transform qatlami qo'shiladi.

MANBA (autentifikatsiya KERAK EMAS — tekshirilgan):
    POST https://apietender.uzex.uz/api/common/TradeList   {TypeId, From, To, System_Id}
    GET  https://apietender.uzex.uz/api/common/GetTrade/{id}/0
    GET  https://apietender.uzex.uz/api/Libs/GetRegions
    Fayl: POST /api/common/DownloadFile?path=<urlencoded>   (GET ishlamaydi!)

MUHIM NUANCELAR (empirik aniqlangan):
  1. `budget_products`, `languages`, `contacts` — STRINGIFIED JSON, parse shart.
  2. Sahifalash — From/To OFFSET-DIAPAZON (page/size emas). From:1,To:20.
  3. `total_count` alohida maydon emas — har qatorning ichida takrorlanadi.
  4. Muddatlar turli birlikda: Delivery_Term=1 + Term_Period_Name='Год (лет)'.
     Biz KUNGA normalizatsiya qilamiz (bizning sxema kunlarda).
  5. Hudud ID umuman yo'q — faqat nom, turli alifboda. Shuning uchun
     viloyat darajasida ANIQ jadval bilan moslashtiramiz (pastda).
  6. UzEx'da "lot" tushunchasi yo'q — butun savdo = bitta lot (frontend /lot/{id}).

Ishga tushirish:
    export XT_DB_DSN="dbname=xtxarid user=a1234 password=... host=localhost"
    python3 etl_uzex.py                # ochiq tenderlar (TypeId=2)
    python3 etl_uzex.py --type-id 1    # "Eng yaxshi takliflarni tanlash"
    python3 etl_uzex.py --limit 5 --dry-run
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
    psycopg2 = None

API           = "https://apietender.uzex.uz/api"
SOURCE        = "uzex"
UZEX_OFFSET   = 20_000_000_000   # global ID = source_id + shu ofset
PAGE          = 50
REQUEST_DELAY = 0.4
TIMEOUT       = 40
HEADERS = {"Content-Type": "application/json",
           "User-Agent": "tender-aggregator/0.1 (research)"}

# ---------------------------------------------------------------------------
# HUDUD MOSLASHTIRISH — UzEx viloyati -> bizdagi KANONIK dim_area kodi
# Ikkala platforma bir xil 14 viloyatni ishlatadi, shuning uchun ularni
# BIRLASHTIRAMIZ: "Toshkent viloyati" filtri ikkala manbadan ham chiqaradi.
# (ID farqi doim 32 ekanini payqadik, lekin arifmetikaga tayanmaymiz —
#  aniq jadval xavfsizroq.)
# ---------------------------------------------------------------------------
REGION_MAP: Dict[int, Tuple[str, str]] = {
    2:    ("33.34",   "Andijon viloyati"),
    242:  ("33.274",  "Buxoro viloyati"),
    487:  ("33.519",  "Jizzax viloyati"),
    679:  ("33.711",  "Qashqadaryo viloyati"),
    1008: ("33.1040", "Navoiy viloyati"),
    1150: ("33.1182", "Namangan viloyati"),
    1413: ("33.1445", "Samarqand viloyati"),
    1692: ("33.1724", "Surxondaryo viloyati"),
    1977: ("33.2009", "Sirdaryo viloyati"),
    2105: ("33.2137", "Toshkent shahri"),
    2120: ("33.2152", "Toshkent viloyati"),
    2434: ("33.2466", "Farg‘ona viloyati"),
    2858: ("33.2890", "Xorazm viloyati"),
    3049: ("33.3081", "Qoraqalpog‘iston Respublikasi"),
}

# Muddat birligini kunga o'girish
PERIOD_DAYS = {"дней": 1, "день": 1, "кун": 1, "kun": 1,
               "неделя": 7, "hafta": 7,
               "месяц": 30, "ой": 30, "oy": 30,
               "год (лет)": 365, "год": 365, "йил": 365, "yil": 365}


# ---------------------------------------------------------------------------
def post(path: str, body: dict) -> Any:
    r = requests.post(f"{API}{path}", json=body, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def get(path: str) -> Any:
    r = requests.get(f"{API}{path}", headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def jparse(v: Any) -> Any:
    """UzEx ba'zi maydonlarni JSON-STRING sifatida qaytaradi."""
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:  # noqa: BLE001
            return None
    return v


def to_days(term: Any, period_name: Optional[str]) -> Optional[int]:
    """Delivery_Term=1 + 'Год (лет)' -> 365 kun."""
    if term in (None, ""):
        return None
    try:
        n = float(term)
    except (TypeError, ValueError):
        return None
    mult = PERIOD_DAYS.get((period_name or "").strip().lower(), 1)
    return int(round(n * mult))


def region_for(name: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Viloyat nomi -> (area_path, area_leaf_id) kanonik kodda."""
    if not name:
        return None, None
    key = name.strip().lower().replace("`", "‘").replace("'", "‘")
    for _uid, (code, uz) in REGION_MAP.items():
        if uz.strip().lower().replace("`", "‘").replace("'", "‘") == key:
            return code, code
    return None, None


# ---------------------------------------------------------------------------
# Yig'ish
# ---------------------------------------------------------------------------
def fetch_list(type_id: int) -> List[dict]:
    """TradeList — From/To offset-diapazon bilan sahifalaydi."""
    out: List[dict] = []
    frm = 1
    while True:
        batch = post("/common/TradeList",
                     {"TypeId": type_id, "From": frm, "To": frm + PAGE - 1,
                      "System_Id": 0})
        if not batch:
            break
        out.extend(batch)
        total = batch[0].get("total_count") or 0
        print(f"  sahifa {frm}-{frm + PAGE - 1}: {len(batch)} ta "
              f"(jami {len(out)}/{total})")
        if len(out) >= total or len(batch) < PAGE:
            break
        frm += PAGE
        time.sleep(REQUEST_DELAY)
    return out


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------
def scan_documents(detail: dict, tender_id: int) -> List[dict]:
    """Fayl guruhlarini UMUMIY tarzda topadi: '<prefiks>_path' + _name/_ext/_sizes.
    Nom bo'yicha qattiq yozmaymiz — yangi guruh qo'shilsa ham o'zi topiladi."""
    docs = []
    for key, val in detail.items():
        if not key.endswith("_path") or not val:
            continue
        pref = key[:-5]
        ext = (detail.get(f"{pref}_ext") or "").lower() or None
        size = detail.get(f"{pref}_sizes")
        docs.append({
            "tender_id": tender_id,
            "file_ref": str(val),          # UzEx'da kalit = yo'l (uuid yo'q)
            "file_id": None,
            "file_path": str(val),
            "name": detail.get(f"{pref}_name") or str(val).rsplit("/", 1)[-1],
            "size_bytes": int(size) if size else None,
            "content_type": None,
            "file_type": ext,
            "field_key": pref,
            "field_path": key,
            "source_platform": SOURCE,
        })
    return docs


def transform(row: dict, detail: dict) -> dict:
    src_id = int(row["id"])
    tid = UZEX_OFFSET + src_id
    area_path, area_leaf = region_for(row.get("region_name"))

    bp = jparse(detail.get("budget_products")) or []

    tender = {
        "id": tid, "source_id": src_id, "source_platform": SOURCE,
        "type": "tender",
        "name": row.get("name") or detail.get("display_no"),
        "status": "open",                       # TradeList faqat faollarni beradi
        "totalcost": detail.get("start_cost") or row.get("cost"),
        "currency": row.get("currency_codeabc"),
        "lang": None,
        "area_path": area_path, "area_leaf_id": area_leaf,
        "company_id": row.get("seller_id"),
        "company_name": (row.get("seller_name") or detail.get("customer_name") or "").strip() or None,
        "publicated_at": row.get("start_date"),
        "close_at": row.get("end_date"),
        "created_at": row.get("start_date"),
        "lot_count": 1,                         # UzEx: butun savdo = 1 lot
        "good_count": len(bp),
        "raw_json": json.dumps({"list": row, "detail": detail}, ensure_ascii=False),
    }

    # Bitta lot — sarlavhasi tender nomi
    lot = {"tender_id": tid, "lot_id": 1, "title": row.get("name"),
           "item_count": len(bp),
           "total_sum_lot": detail.get("start_cost") or row.get("cost")}

    goods, items = [], []
    for p in bp:
        code = p.get("Product_Code") or str(p.get("Product_Id"))
        unit = None
        for pr in (p.get("Js_Properties") or []):
            if "измерения" in str(pr.get("Property_Name", "")).lower():
                unit = pr.get("User_Value")
        goods.append({
            "tender_id": tid, "lot_id": 1, "good_code": code,
            "name": p.get("Product_Name"), "unit": unit,
            "amount": p.get("Quantity"), "price": p.get("Price"),
            "totalcost_item": p.get("Cost"), "category_uid": None,
        })
        items.append({
            "tender_id": tid, "lot_id": 1, "item_id": str(p.get("Id")),
            "product_code": code, "name": p.get("Product_Name"), "unit": unit,
            "amount_text": f"{p.get('Quantity')} {unit or ''}".strip(),
            "price_text": str(p.get("Price")),
            "totalcost_text": str(p.get("Cost")),
            "delivery_period": to_days(p.get("Delivery_Term"), p.get("Term_Period_Name")),
            "guarantee": to_days(p.get("Guarantee_Term"), p.get("Term_Period_Name")),
            "prod_year": None,
            "country_of_origin": None,
            "delivery_address": detail.get("delivering_region_name"),
            "spec": p.get("Description"),
            "properties": json.dumps(p.get("Js_Properties") or [], ensure_ascii=False),
            "raw_json": json.dumps(p, ensure_ascii=False),
        })

    docs = scan_documents(detail, tid)
    contacts = jparse(detail.get("contacts")) or []
    det = {
        "tender_id": tid,
        "anno": detail.get("description"),
        "method_marks": detail.get("valuation_name"),
        "company_details": detail.get("customer_name"),
        "director": (contacts[0].get("Fullname") if contacts else None),
        "close_time": detail.get("end_date"),
        "proc_lang": None,
        "offer_period": str(detail.get("term_online_days") or "") or None,
        "doc_count": len(docs),
        "raw_json": json.dumps(detail, ensure_ascii=False),
    }
    return {"tender": tender, "lot": lot, "goods": goods,
            "items": items, "docs": docs, "detail": det}


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
T_COLS = ["id", "source_id", "source_platform", "type", "name", "status",
          "totalcost", "currency", "lang", "area_path", "area_leaf_id",
          "company_id", "company_name", "publicated_at", "close_at",
          "created_at", "lot_count", "good_count", "raw_json"]
D_COLS = ["tender_id", "anno", "method_marks", "company_details", "director",
          "close_time", "proc_lang", "offer_period", "doc_count", "raw_json"]
DOC_COLS = ["tender_id", "file_ref", "file_id", "file_path", "name",
            "size_bytes", "content_type", "file_type", "field_key",
            "field_path", "source_platform"]
I_COLS = ["tender_id", "lot_id", "item_id", "product_code", "name", "unit",
          "amount_text", "price_text", "totalcost_text", "delivery_period",
          "guarantee", "prod_year", "country_of_origin", "delivery_address",
          "spec", "properties", "raw_json"]


def save(conn, rec: dict) -> None:
    t = rec["tender"]
    tid = t["id"]
    with conn.cursor() as cur:
        cur.execute(
            f"""INSERT INTO tender ({",".join(T_COLS)})
                VALUES ({",".join("%s" for _ in T_COLS)})
                ON CONFLICT (id) DO UPDATE SET
                {",".join(f"{c}=EXCLUDED.{c}" for c in T_COLS if c != "id")},
                fetched_at=now()""",
            [t[c] for c in T_COLS])

        cur.execute("DELETE FROM tender_good WHERE tender_id=%s", (tid,))
        cur.execute("DELETE FROM tender_item WHERE tender_id=%s", (tid,))
        cur.execute("DELETE FROM tender_lot  WHERE tender_id=%s", (tid,))
        l = rec["lot"]
        cur.execute("""INSERT INTO tender_lot (tender_id, lot_id, title, item_count, total_sum_lot)
                       VALUES (%s,%s,%s,%s,%s)""",
                    (l["tender_id"], l["lot_id"], l["title"], l["item_count"],
                     l["total_sum_lot"]))
        if rec["goods"]:
            execute_values(cur,
                """INSERT INTO tender_good (tender_id, lot_id, good_code, name, unit,
                   amount, price, totalcost_item, category_uid) VALUES %s
                   ON CONFLICT DO NOTHING""",
                [(g["tender_id"], g["lot_id"], g["good_code"], g["name"], g["unit"],
                  g["amount"], g["price"], g["totalcost_item"], g["category_uid"])
                 for g in rec["goods"]])
        if rec["items"]:
            execute_values(cur,
                f"INSERT INTO tender_item ({','.join(I_COLS)}) VALUES %s "
                "ON CONFLICT DO NOTHING",
                [tuple(i[c] for c in I_COLS) for i in rec["items"]])

        cur.execute(
            f"""INSERT INTO tender_detail ({",".join(D_COLS)})
                VALUES ({",".join("%s" for _ in D_COLS)})
                ON CONFLICT (tender_id) DO UPDATE SET
                {",".join(f"{c}=EXCLUDED.{c}" for c in D_COLS if c != "tender_id")},
                fetched_at=now()""",
            [rec["detail"][c] for c in D_COLS])

        cur.execute("DELETE FROM tender_document WHERE tender_id=%s", (tid,))
        if rec["docs"]:
            execute_values(cur,
                f"INSERT INTO tender_document ({','.join(DOC_COLS)}) VALUES %s",
                [tuple(d[c] for c in DOC_COLS) for d in rec["docs"]])
    conn.commit()


def sync_region_names(conn) -> None:
    """BONUS: UzEx lotincha o'zbekcha nomlarni beradi — dim_area.name_uz ni
    to'ldiramiz (u shu paytgacha bo'sh edi)."""
    with conn.cursor() as cur:
        for _uid, (code, uz) in REGION_MAP.items():
            cur.execute("UPDATE dim_area SET name_uz=%s WHERE area_id=%s AND name_uz IS NULL",
                        (uz, code))
    conn.commit()


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="etender.uzex.uz adapteri")
    ap.add_argument("--type-id", type=int, default=2,
                    help="2=Tender (default), 1=Eng yaxshi takliflarni tanlash")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--dsn", default=os.environ.get("XT_DB_DSN"))
    args = ap.parse_args()

    print(f"[1/3] TradeList (TypeId={args.type_id}) yig'ilyapti...")
    rows = fetch_list(args.type_id)
    if args.limit:
        rows = rows[:args.limit]
    print(f"[1/3] {len(rows)} ta savdo.\n")

    if not args.dry_run:
        if not args.dsn:
            sys.exit("XATO: DSN yo'q.")
        if psycopg2 is None:
            sys.exit("XATO: pip install psycopg2-binary")
        conn = psycopg2.connect(args.dsn)
        sync_region_names(conn)
    else:
        conn = None

    print("[2/3] Tafsilotlar (GetTrade) va transform...")
    ok = failed = ndocs = nitems = 0
    for i, row in enumerate(rows, 1):
        try:
            detail = get(f"/common/GetTrade/{row['id']}/0")
            rec = transform(row, detail)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  [{i}/{len(rows)}] #{row['id']} — XATO: {str(e)[:70]}")
            time.sleep(REQUEST_DELAY)
            continue

        ndocs += len(rec["docs"]); nitems += len(rec["items"]); ok += 1
        print(f"  [{i}/{len(rows)}] #{row['id']} -> {rec['tender']['id']} | "
              f"{len(rec['items'])} pozitsiya, {len(rec['docs'])} hujjat | "
              f"{(rec['tender']['name'] or '')[:40]}")

        if conn:
            try:
                save(conn, rec)
            except Exception as e:  # noqa: BLE001
                conn.rollback(); failed += 1
                print(f"    ! DB xato: {str(e)[:110]}", file=sys.stderr)
        time.sleep(REQUEST_DELAY)

    if conn:
        conn.close()
    print(f"\n[3/3] Tayyor. OK: {ok}, xato: {failed}, "
          f"pozitsiya: {nitems}, hujjat: {ndocs}")


if __name__ == "__main__":
    main()
