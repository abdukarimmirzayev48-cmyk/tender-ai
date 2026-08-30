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

import etl_ishonch as ish

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    psycopg2 = None

URPC_URL      = "https://api.xt-xarid.uz/urpc"
REQUEST_DELAY = 0.8      # serverga bosim qilmaslik uchun
MAX_RETRIES   = 3
RETRY_BACKOFF = 2.0
#: (ulanish, o'qish) — ilgari bitta `40` edi va ikkalasiga qo'llanardi.
TIMEOUT       = (8.0, 40.0)
SIYOSAT = ish.Siyosat(urinishlar=MAX_RETRIES, asos=1.0, koeff=RETRY_BACKOFF,
                      max_kutish=45.0, jitter=0.25)

#: Vaqt byudjeti — bu qadam eng uzun (har tender uchun alohida so'rov).
STANDART_BYUDJET = 20 * 60

#: Kelishilgan chiqish kodlari (`run_etl.py` shularga qarab status qo'yadi).
CHIQISH_TUGADI = 0
CHIQISH_QISMAN = 7
CHIQISH_BAND   = 8
CHIQISH_XATO   = 1

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


#: Metrika hisoblagichi va to'xtash so'rovi — `main()` da o'rnatiladi.
_HISOB: Optional[Any] = None
_TOXTATGICH: Optional[ish.Toxtatgich] = None


def get_proc(session: requests.Session, proc_id: Any) -> Optional[dict]:
    """Bitta tenderning to'liq tafsilotini oladi. Xato bo'lsa None.

    `None` = "shu YOZUV olinmadi" va u BUTUN yurishni to'xtatmaydi.
    Qayta urinish TASNIFLANGAN: 404 darhol tashlanadi, 503 kutib
    qayta urinilyapti.
    """
    payload = {"id": 1, "jsonrpc": "2.0", "method": "get_proc",
               "params": {"proc_id": str(proc_id)}}

    def _ish():
        body = ish.javob_json(
            session.post(URPC_URL, json=payload, headers=headers(proc_id),
                         timeout=TIMEOUT))
        if isinstance(body, dict) and body.get("error"):
            # RPC xatosi HTTP 200 bilan keladi — MAZMUNIY xato,
            # qayta urinish tuzatmaydi.
            raise ish.ManbaXato(f"RPC xato: {str(body['error'])[:120]}",
                                qayta_urinsa=False)
        return body.get("result") if isinstance(body, dict) else None

    try:
        return ish.qayta_urin(
            _ish, siyosat=SIYOSAT, nom=f"get_proc #{proc_id}",
            ogohlantir=lambda m: print(f"    ! {m}", file=sys.stderr),
            hisob=(lambda: _HISOB.oldinga(retried=1)) if _HISOB else None,
            toxtash=(lambda: _TOXTATGICH.toxtaymi()) if _TOXTATGICH else None)
    except ish.ManbaXato as e:
        print(f"    ! #{proc_id} olinmadi: {e}", file=sys.stderr)
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
        d["file_ref"] = d["file_id"]
    return detail, docs


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
DETAIL_COLS = ["tender_id", "anno", "method_marks", "company_details", "director",
               "close_time", "proc_lang", "offer_period", "doc_count", "raw_json"]
DOC_COLS = ["tender_id", "file_id", "file_ref", "name", "size_bytes", "content_type",
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

        # PK = (tender_id, file_ref). `scan_files()` STRUKTURA bo'yicha
        # skanerlaydi, ya'ni bitta fayl obyekti IKKI xil maydonda
        # uchrasa ikki marta qaytadi. Ilgari bunday tender
        # `duplicate key` bilan yiqilar va TAFSILOTI UMUMAN
        # saqlanmasdi. Takror = AYNI bir xil qator, ya'ni yo'qoladigan
        # narsa yo'q.
        uniq = {d["file_ref"]: d for d in docs}
        if len(uniq) != len(docs):
            print(f"    ! #{detail['tender_id']}: {len(docs) - len(uniq)} ta "
                  f"takror hujjat havolasi birlashtirildi", file=sys.stderr)

        # DELETE + INSERT EMAS — UPSERT. Sabab `etl_uzex.save()` dagi
        # bilan bir xil: o'chirish qayta ishlash HOLATINI va ajratilgan
        # matn bilan bog'lanishni yo'qotardi (o'lchangan: 392 yetim
        # matn qatori).
        if uniq:
            execute_values(cur,
                f"INSERT INTO tender_document ({','.join(DOC_COLS)}) VALUES %s "
                "ON CONFLICT (tender_id, file_ref) DO UPDATE SET "
                + ",".join(f"{c}=EXCLUDED.{c}" for c in DOC_COLS
                           if c not in ("tender_id", "file_ref"))
                + ", fetched_at = now()"
                + ", manbadan_yoqoldi_at = NULL"
                + ", holat = CASE WHEN tender_document.holat = 'manbadan_yoqoldi' "
                  "              THEN 'navbatda' ELSE tender_document.holat END",
                [tuple(d[c] for c in DOC_COLS) for d in uniq.values()])

        # Manbada BOSHQA YO'Q — o'chirilmaydi, BELGILANADI.
        cur.execute(
            "UPDATE tender_document SET holat='manbadan_yoqoldi', "
            "       manbadan_yoqoldi_at = COALESCE(manbadan_yoqoldi_at, now()) "
            "WHERE tender_id = %s AND holat <> 'manbadan_yoqoldi' "
            "  AND NOT (file_ref = ANY(%s))",
            (detail["tender_id"], list(uniq.keys()) or [""]))
    conn.commit()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    ish.chiqishni_sozla()
    ap = argparse.ArgumentParser(description="Tender tafsiloti va hujjatlari ETL")
    ap.add_argument("--only-open", action="store_true",
                    help="Faqat ochiq tenderlar (standart: barchasi)")
    ap.add_argument("--limit", type=int, help="Nechta tender (sinov uchun)")
    ap.add_argument("--dry-run", action="store_true", help="DBga yozmaydi")
    ap.add_argument("--dsn", default=os.environ.get("XT_DB_DSN"))
    ap.add_argument("--max-seconds", type=float, default=STANDART_BYUDJET,
                    help="Vaqt byudjeti. Tugaganda checkpoint yozib TOZA "
                         "to'xtaydi (0 = cheksiz)")
    ap.add_argument("--no-checkpoint", action="store_true",
                    help="Checkpoint o'qilmaydi/yozilmaydi (sinov uchun)")
    args = ap.parse_args()

    if not args.dsn:
        sys.exit("XATO: DSN yo'q. --dsn yoki XT_DB_DSN o'rnating.")
    if psycopg2 is None:
        sys.exit("XATO: pip install psycopg2-binary")

    global _HISOB, _TOXTATGICH
    _TOXTATGICH = ish.Toxtatgich(args.max_seconds or None)
    _TOXTATGICH.signallarni_ulash()
    yozuvchi = ish.BazaYozuvchi(args.dsn)
    yurish = ish.Yurish(yozuvchi)
    _HISOB = yurish
    oqim = "details:" + ("open" if args.only_open else "all")
    kp = ish.Checkpoint(yozuvchi, "xt-xarid", oqim,
                        faol=not (args.no_checkpoint or args.dry_run))

    # Qaysi tenderlarni yig'amiz
    conn = psycopg2.connect(args.dsn)
    with conn.cursor() as cur:
        sql = "SELECT id FROM tender WHERE source_platform = 'xt-xarid'"
        if args.only_open:
            sql += " AND status = 'open'"
        sql += " ORDER BY close_at DESC NULLS LAST"
        if args.limit:
            sql += f" LIMIT {int(args.limit)}"
        cur.execute(sql)
        ids = [r[0] for r in cur.fetchall()]

    label = "faqat ochiq" if args.only_open else "barcha"
    print(f"[1/2] {len(ids)} ta tender ({label}) uchun tafsilot yig'iladi...")
    print(f"      Taxminiy vaqt: ~{len(ids) * REQUEST_DELAY / 60:.1f} daqiqa")

    # --- CHECKPOINT: qayerdan davom etamiz? ---------------------------
    # `ish_kaliti` ID ro'yxatining barmoq izi. Ro'yxat o'zgargan bo'lsa
    # (yangi tender qo'shilgan) kursor YAROQSIZ deb belgilanadi va
    # noldan boshlanadi — noto'g'ri joydan davom etib oradagi tenderni
    # JIMGINA tashlab ketishdan ko'ra shu yaxshi.
    kalit = ish.ish_kaliti(ids)
    boshlanish = kp.boshla(len(ids), kalit) if ids else 0
    if boshlanish:
        yurish.oldinga(resumed=boshlanish)
        print(f"      CHECKPOINT: {boshlanish}/{len(ids)} dan davom etamiz "
              f"(oldingi yurish uzilgan).")
    byudjet = _TOXTATGICH.qolgan()
    if byudjet:
        print(f"      Byudjet: {byudjet:.0f}s")
    print()

    # Keep-alive: bu qadam har tenderga alohida so'rov qiladi, ya'ni
    # ulanishni qayta ishlatish eng ko'p shu yerda foyda beradi.
    session = ish.sessiya_yarat(pool=2)
    ok = failed = total_docs = 0
    sabab, chiqish = "tugadi", CHIQISH_TUGADI

    i = boshlanish
    while i < len(ids):
        if _TOXTATGICH.toxtaymi():
            sabab = _TOXTATGICH.sabab or "toxtatildi"
            chiqish = CHIQISH_QISMAN
            print(f"\n[!] TO'XTASH ({sabab}): {i}/{len(ids)} da to'xtadik, "
                  f"checkpoint yozildi. Keyingi yurish shu yerdan davom etadi.")
            break

        tid = ids[i]
        i += 1
        result = get_proc(session, tid)
        if not result:
            failed += 1
            yurish.oldinga(processed=1, failed=1)
            print(f"  [{i}/{len(ids)}] #{tid} — TAFSILOT OLINMADI")
            kp.siljit(i)
            time.sleep(REQUEST_DELAY)
            continue

        # BITTA BUZUQ YOZUV BUTUN PAKETNI YIQITMAYDI.
        try:
            detail, docs = transform(tid, result)
        except Exception as e:                              # noqa: BLE001
            failed += 1
            yurish.oldinga(processed=1, failed=1)
            print(f"  [{i}/{len(ids)}] #{tid} — BUZUQ YOZUV: "
                  f"{type(e).__name__}: {str(e)[:70]}", file=sys.stderr)
            kp.siljit(i)
            time.sleep(REQUEST_DELAY)
            continue

        yozildi = True
        if not args.dry_run:
            try:
                save(conn, detail, docs)
            except Exception as e:  # noqa: BLE001
                conn.rollback()
                print(f"    ! #{tid} DB xato: {str(e)[:120]}", file=sys.stderr)
                failed += 1
                yozildi = False
                yurish.oldinga(processed=1, failed=1)

        if yozildi:
            total_docs += len(docs)
            ok += 1
            yurish.oldinga(processed=1, succeeded=1)
            mark = f"{len(docs)} hujjat" if docs else "hujjatsiz"
            print(f"  [{i}/{len(ids)}] #{tid} — {mark}")

        kp.siljit(i, oxirgi_id=tid if yozildi else None)
        yurish.puls()
        time.sleep(REQUEST_DELAY)
    else:
        kp.tugat()

    conn.close()
    yurish.checkpoint_yoz(dict(kp.holat.dict(), oqim=oqim))
    yurish.sabab_yoz(sabab)
    print(f"\n[2/2] {sabab.upper()}. Muvaffaqiyatli: {ok}, xato: {failed}, "
          f"jami hujjat: {total_docs}")
    print(f"      Metrika: {yurish.xulosa()}")
    if args.dry_run:
        print("      (--dry-run — DBga yozilmadi)")
    yozuvchi.yop()
    if failed and chiqish == CHIQISH_TUGADI:
        chiqish = CHIQISH_QISMAN
    sys.exit(chiqish)


if __name__ == "__main__":
    main()
