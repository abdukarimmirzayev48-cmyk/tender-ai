#!/usr/bin/env python3
"""
xt-xarid.uz  |  TENDER TAFSILOTI va HUJJATLARI ETL
==================================================
Har bir tender uchun `get_proc` chaqiruvini qilib, tafsilotni va unga
biriktirilgan FAYLLARNI (texnik topshiriq, xarid hujjatlari, shartnoma
namunasi) yig'adi.

MANBA (autentifikatsiyasiz ishlaydi — tekshirilgan):
    POST https://api.xt-xarid.uz/urpc
    {"id":1,"jsonrpc":"2.0","method":"get_proc","params":{"proc_id":"8062765"}}
    Sarlavhalar: X-DBRPC-Language, x-idempotency-key, x-url-on

MUHIM ARXITEKTURA QARORI — FAYLLARNI QANDAY TOPAMIZ:
    Fayllar QATTIQ maydon nomida turmaydi. Bitta tenderda ular
    anno_file, proform_file, proc_custom2, proc_custom4, proc_custom6 ...
    kabi TARQOQ maydonlarda edi (11 ta fayldan faqat 3 tasi anno_file'da).
    Shuning uchun maydon NOMI bo'yicha emas, STRUKTURA bo'yicha skanerlaymiz:
        {"id": "<uuid>", "meta": {"size": ..., "content_type": ...}}
    ko'rinishidagi HAR QANDAY obyekt = fayl. Shunda yangi tenderda fayl
    kutilmagan maydonда bo'lsa ham topiladi.

Ishga tushirish:
    export XT_DB_DSN="dbname=xtxarid user=a1234 password=... host=localhost"
    python3 etl_details.py                 # bazadagi BARCHA tenderlar
    python3 etl_details.py --only-open     # faqat ochiq tenderlar (tez)
    python3 etl_details.py --limit 5 --dry-run
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
REQUEST_DELAY = 0.8      # serverga bosim qilmaslik uchun
MAX_RETRIES   = 3
RETRY_BACKOFF = 2.0
TIMEOUT       = 40

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)


# ---------------------------------------------------------------------------
# RPC qatlami
# ---------------------------------------------------------------------------
def headers(proc_id: Any) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-DBRPC-Language": "ru",
        # har chaqiruvda yangi tasodifiy kalit (API shuni kutadi)
        "x-idempotency-key": str(random.randint(10**9, 10**10)),
        "x-url-on": f"https://xt-xarid.uz/procedure/{proc_id}/core",
        "User-Agent": "xt-xarid-tender-aggregator/0.1 (research)",
    }


def get_proc(session: requests.Session, proc_id: Any) -> Optional[dict]:
    """Bitta tenderning to'liq tafsilotini oladi. Xato bo'lsa None."""
    payload = {"id": 1, "jsonrpc": "2.0", "method": "get_proc",
               "params": {"proc_id": str(proc_id)}}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.post(URPC_URL, json=payload, headers=headers(proc_id),
                             timeout=TIMEOUT)
            r.raise_for_status()
            body = r.json()
            if body.get("error"):
                print(f"    ! RPC xato: {str(body['error'])[:90]}", file=sys.stderr)
                return None
            return body.get("result")
        except Exception as e:  # noqa: BLE001
            if attempt == MAX_RETRIES:
                print(f"    ! {MAX_RETRIES} urinishdan keyin muvaffaqiyatsiz: {e}",
                      file=sys.stderr)
                return None
            time.sleep(RETRY_BACKOFF ** attempt)
    return None


# ---------------------------------------------------------------------------
# UMUMIY FAYL SKANERI — maydon nomiga bog'liq emas
# ---------------------------------------------------------------------------
def looks_like_file(node: Any) -> bool:
    """{id:<uuid>, meta:{...}} => fayl obyekti."""
    return (
        isinstance(node, dict)
        and isinstance(node.get("id"), str)
        and UUID_RE.match(node["id"]) is not None
        and isinstance(node.get("meta"), dict)
    )


def scan_files(fields: dict) -> List[dict]:
    """fields ichidagi barcha fayl obyektlarini rekursiv topadi."""
    found: List[dict] = []

    def walk(node: Any, path: str, top: Optional[str]) -> None:
        if looks_like_file(node):
            meta = node.get("meta") or {}
            name = node.get("name") or meta.get("name") or ""
            # Toza tur: fayl nomining kengaytmasi ('docx'), chunki meta.type
            # ba'zan uzun MIME-subtype bo'ladi ('vnd.openxmlformats-...').
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else None
            found.append({
                "file_id": node["id"],
                "name": name or None,
                "size_bytes": meta.get("size"),
                "content_type": meta.get("content_type"),
                "file_type": (ext or meta.get("type") or None),
                "field_key": top,
                "field_path": path,
            })
            return
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}", top or k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]", top)

    walk(fields, "fields", None)

    # Bir fayl bir necha maydonda uchrasa — bir marta saqlaymiz
    uniq: Dict[str, dict] = {}
    for f in found:
        uniq.setdefault(f["file_id"], f)
    return list(uniq.values())


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------
def fval(fields: dict, key: str) -> Optional[str]:
    """fields[key].value ni xavfsiz oladi (bo'sh bo'lsa None)."""
    v = fields.get(key)
    if isinstance(v, dict):
        v = v.get("value")
    if v in (None, "", [], {}):
        return None
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def transform(tender_id: int, result: dict) -> Tuple[dict, List[dict]]:
    fields = result.get("fields") or {}
    docs = scan_files(fields)
    detail = {
        "tender_id": tender_id,
        "anno": fval(fields, "anno"),
        "method_marks": fval(fields, "method_marks"),
        "company_details": fval(fields, "company_details"),
        "director": fval(fields, "director"),
        "close_time": fval(fields, "close_time"),
        "proc_lang": fval(fields, "lang"),
        "offer_period": fval(fields, "offer_period"),
        "doc_count": len(docs),
        "raw_json": json.dumps(result, ensure_ascii=False),
    }
    for d in docs:
        d["tender_id"] = tender_id
    return detail, docs


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
DETAIL_COLS = ["tender_id", "anno", "method_marks", "company_details", "director",
               "close_time", "proc_lang", "offer_period", "doc_count", "raw_json"]
DOC_COLS = ["tender_id", "file_id", "name", "size_bytes", "content_type",
            "file_type", "field_key", "field_path"]


def save(conn, detail: dict, docs: List[dict]) -> None:
    """Bitta tenderni yozadi (idempotent). Har tenderdan keyin commit —
    uzun yurish yarmida uzilsa ham yig'ilgan ma'lumot saqlanib qoladi."""
    with conn.cursor() as cur:
        cur.execute(
            f"""INSERT INTO tender_detail ({",".join(DETAIL_COLS)})
                VALUES ({",".join("%s" for _ in DETAIL_COLS)})
                ON CONFLICT (tender_id) DO UPDATE SET
                {",".join(f"{c}=EXCLUDED.{c}" for c in DETAIL_COLS if c != "tender_id")},
                fetched_at = now()""",
            [detail[c] for c in DETAIL_COLS])

        # Hujjatlarni qayta yozamiz (manbada o'zgargan/olib tashlangan bo'lishi mumkin)
        cur.execute("DELETE FROM tender_document WHERE tender_id = %s",
                    (detail["tender_id"],))
        if docs:
            execute_values(cur,
                f"INSERT INTO tender_document ({','.join(DOC_COLS)}) VALUES %s",
                [tuple(d[c] for c in DOC_COLS) for d in docs])
    conn.commit()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Tender tafsiloti va hujjatlari ETL")
    ap.add_argument("--only-open", action="store_true",
                    help="Faqat ochiq tenderlar (standart: barchasi)")
    ap.add_argument("--limit", type=int, help="Nechta tender (sinov uchun)")
    ap.add_argument("--dry-run", action="store_true", help="DBga yozmaydi")
    ap.add_argument("--dsn", default=os.environ.get("XT_DB_DSN"))
    args = ap.parse_args()

    if not args.dsn:
        sys.exit("XATO: DSN yo'q. --dsn yoki XT_DB_DSN o'rnating.")
    if psycopg2 is None:
        sys.exit("XATO: pip install psycopg2-binary")

    # Qaysi tenderlarni yig'amiz
    conn = psycopg2.connect(args.dsn)
    with conn.cursor() as cur:
        sql = "SELECT id FROM tender"
        if args.only_open:
            sql += " WHERE status = 'open'"
        sql += " ORDER BY close_at DESC NULLS LAST"
        if args.limit:
            sql += f" LIMIT {int(args.limit)}"
        cur.execute(sql)
        ids = [r[0] for r in cur.fetchall()]

    label = "faqat ochiq" if args.only_open else "barcha"
    print(f"[1/2] {len(ids)} ta tender ({label}) uchun tafsilot yig'iladi...")
    print(f"      Taxminiy vaqt: ~{len(ids) * REQUEST_DELAY / 60:.1f} daqiqa\n")

    session = requests.Session()
    ok = failed = total_docs = 0

    for i, tid in enumerate(ids, 1):
        result = get_proc(session, tid)
        if not result:
            failed += 1
            print(f"  [{i}/{len(ids)}] #{tid} — TAFSILOT OLINMADI")
            time.sleep(REQUEST_DELAY)
            continue

        detail, docs = transform(tid, result)
        total_docs += len(docs)
        ok += 1
        mark = f"{len(docs)} hujjat" if docs else "hujjatsiz"
        print(f"  [{i}/{len(ids)}] #{tid} — {mark}")

        if not args.dry_run:
            try:
                save(conn, detail, docs)
            except Exception as e:  # noqa: BLE001
                conn.rollback()
                print(f"    ! DB xato: {e}", file=sys.stderr)
                failed += 1

        time.sleep(REQUEST_DELAY)

    conn.close()
    print(f"\n[2/2] Tayyor. Muvaffaqiyatli: {ok}, xato: {failed}, "
          f"jami hujjat: {total_docs}")
    if args.dry_run:
        print("      (--dry-run — DBga yozilmadi)")


if __name__ == "__main__":
    main()
