#!/usr/bin/env python3
"""
ETL ORKESTRATORI (H bosqich) — barcha manbalarni yangilaydi + jurnal yozadi
===========================================================================
Cron/launchd/Task Scheduler shu skriptni chaqiradi. Har MANBA yurishi
`etl_run` jadvaliga yoziladi (sog'lik + yangi topilgan tenderlar soni).
Bu tufayli:
  - "oxirgi yangilanish qachon", "nechta yangi topildi" — o'lchanadigan
  - biror manba buzilsa (sayt o'zgardi/tushdi) — status='error' qoladi (jimgina
    o'tkazib yuborilmaydi, TZ NFT talabi)

first_seen_at (schema_patch_freshness.sql) UPSERT'da saqlanadi, shuning uchun
"biz birinchi qachon ko'rdik" aniq qoladi -> aniqlash-kechikishini o'lchaymiz.

QAMROV (nega bir manbada bir nechta qadam bor)
----------------------------------------------
Har platforma BIR EMAS, bir nechta ochiq reyestrni chop etadi. Faqat bittasini
yig'ish ochiq lotlarning katta qismini yo'qotadi:
  xt-xarid : ref_tender_public  +  ref_selection_public
  uzex     : TypeId=2 (tender)  +  TypeId=1 ("eng yaxshi taklifni tanlash")
Shuning uchun har platforma "guruh" bo'lib, ichida bir nechta qadam bor.

PARALLELIK QOIDASI (ongli qaror)
--------------------------------
  - GURUHLAR (platformalar) O'ZARO PARALLEL yuriladi — turli hostlar, bir-biriga
    xalaqit bermaydi. Umumiy vaqt = eng sekin platforma vaqti.
  - GURUH ICHIDA qadamlar KETMA-KET yuriladi — ular BITTA hostga uriladi va
    parallel yurgizish so'rov tezligini ikki barobar oshirib, manba
    rate-limitini hurmat qilmaslikka olib keladi.
  - `etl_run` guruh boshida bitta qator ochadi va guruh oxirida yopadi, ya'ni
    jurnalda har platforma uchun bitta yozuv qoladi (dashboard "Yangilangan"
    ko'rsatkichi shunga tayanadi) va `new` metrikasi ikki marta sanalmaydi.

Ishga tushirish:
    # DSN .env dan avtomatik o'qiladi (XT_DB_DSN)
    python run_etl.py                 # tez: barcha manbalar + kategoriyalar
    python run_etl.py --with-docs     # + hujjatlar (sekinroq)
    python run_etl.py --all-statuses  # ochiq emas, hammasi (qimmat)
    python run_etl.py --limit 3       # SINOV: har manbadan 3 yozuv
    python run_etl.py --sequential    # parallelsiz (nosozlikni izlashda)
"""
import argparse
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple

try:
    import psycopg2
except ImportError:
    psycopg2 = None

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv bo'lmasa ham muhit o'zgaruvchisi bilan ishlayveradi
    load_dotenv = None

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable  # o'sha venv python'i

# Chiqishni parallel oqimlarda aralashtirib yubormaslik uchun
_PRINT_LOCK = threading.Lock()


def emit(lines: List[str]) -> None:
    """Bir nechta qatorni ATOMAR chiqaradi (parallel guruhlar aralashmasin)."""
    with _PRINT_LOCK:
        for ln in lines:
            print(ln)
        sys.stdout.flush()


def db():
    return psycopg2.connect(os.environ["XT_DB_DSN"])


def platform_count(conn, platform: str, since=None) -> int:
    with conn.cursor() as cur:
        if since:
            cur.execute("SELECT count(*) FROM tender WHERE source_platform=%s "
                        "AND first_seen_at >= %s", (platform, since))
        else:
            cur.execute("SELECT count(*) FROM tender WHERE source_platform=%s", (platform,))
        return cur.fetchone()[0]


def run_script(script: str, extra_args: List[str]) -> Tuple[bool, Optional[str], float, List[str]]:
    """Bitta ETL skriptini bola-jarayon sifatida yurgizadi.

    Qaytadi: (ok, xato_matni, sekund, chiqish_qatorlari)

    MUHIM (Windows): bola-jarayon chiqishi UTF-8 deb dekodlanadi va
    PYTHONIOENCODING=utf-8 bola muhitiga beriladi. Aks holda kirill matnда
    UnicodeDecodeError chiqib, BOLA CHIQISHI BUTUNLAY YO'QOLADI — ya'ni xato
    jimgina o'tib ketishi mumkin edi.
    """
    out: List[str] = [f"--- {script} {' '.join(extra_args)} ---"]
    t0 = time.time()
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        res = subprocess.run([PY, os.path.join(HERE, script), *extra_args],
                             cwd=HERE, env=env,
                             capture_output=True, text=True,
                             encoding="utf-8", errors="replace",
                             timeout=3600)
        ok = res.returncode == 0
        tail = "\n".join((res.stdout or "").strip().splitlines()[-4:])
        if tail:
            out.extend(f"    {ln}" for ln in tail.splitlines())
        err = None if ok else (res.stderr or res.stdout or "")[-500:]
    except subprocess.TimeoutExpired:
        ok, err = False, "timeout (1 soat)"
    except Exception as e:  # noqa: BLE001
        ok, err = False, str(e)[:500]

    dt = time.time() - t0
    if not ok:
        out.append(f"    !! XATO: {(err or '').strip()[:300]}")
    out.append(f"  [{'OK' if ok else 'XATO'}] {script} — {dt:.0f}s")
    return ok, err, dt, out


def run_group(platform: str, steps: List[Tuple[str, List[str]]],
              log: bool = True) -> bool:
    """Bitta platformaning barcha qadamlarini KETMA-KET yurgizadi va butun
    guruh uchun BITTA `etl_run` yozuvini ochadi/yopadi.

    Bir host = bir guruh: guruh ichida ketma-ketlik manba rate-limitini
    hurmat qiladi, guruhlar esa tashqarida parallel yuriladi.
    """
    conn = db() if log else None
    run_id = started = None
    if conn is not None:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO etl_run (source_platform, status) VALUES (%s,'running') "
                        "RETURNING id, started_at", (platform,))
            run_id, started = cur.fetchone()
        conn.commit()

    # Har qadam TUGAGACH atomar chiqariladi (butun guruhni kutmasdan) — uzex
    # qadami ~10 daqiqa yurishi mumkin, jonli qayta aloqa yo'qolmasin.
    emit([f"\n===== {platform}: {len(steps)} qadam ====="])
    all_ok = True
    errors: List[str] = []
    t0 = time.time()
    for script, extra in steps:
        ok, err, _dt, out = run_script(script, extra)
        emit([f"[{platform}] " + ln for ln in out])
        if not ok:
            all_ok = False
            errors.append(f"{script} {' '.join(extra)}: {(err or '').strip()[:200]}")
    dt = time.time() - t0

    lines: List[str] = []
    if conn is not None:
        found = platform_count(conn, platform)
        new = platform_count(conn, platform, since=started) if started else None
        with conn.cursor() as cur:
            cur.execute("UPDATE etl_run SET finished_at=now(), status=%s, found=%s, "
                        "new=%s, error=%s WHERE id=%s",
                        ("ok" if all_ok else "error", found, new,
                         "\n".join(errors)[:2000] or None, run_id))
        conn.commit()
        lines.append(f"  => {platform}: [{'OK' if all_ok else 'XATO'}] {dt:.0f}s | "
                     f"jami {found}, yangi {new}")
    else:
        lines.append(f"  => {platform}: [{'OK' if all_ok else 'XATO'}] {dt:.0f}s")
    if conn is not None:
        conn.close()

    emit(lines)
    return all_ok


def build_groups(args) -> List[Tuple[str, List[Tuple[str, List[str]]]]]:
    """Platforma -> ketma-ket qadamlar ro'yxati."""
    status_args = ["--all-statuses"] if args.all_statuses else []
    limit_args = ["--limit", str(args.limit)] if args.limit else []

    xt_steps: List[Tuple[str, List[str]]] = [
        # Ikkala ochiq reyestr ham kerak — bittasi ochiq lotlarning katta
        # qismini yo'qotadi (ID fazolari kesishmaydi, tekshirilgan).
        ("etl_tenders.py", ["--ref", "ref_tender_public", *status_args, *limit_args]),
        ("etl_tenders.py", ["--ref", "ref_selection_public", *status_args, *limit_args]),
    ]
    if args.with_docs:
        # Hujjatlar ham xt-xarid hostiga uriladi -> shu guruh ichida, ketma-ket
        xt_steps.append(("etl_details.py", []))

    uzex_steps: List[Tuple[str, List[str]]] = [
        ("etl_uzex.py", ["--type-id", "2", *limit_args]),
        ("etl_uzex.py", ["--type-id", "1", *limit_args]),
    ]
    return [("xt-xarid", xt_steps), ("uzex", uzex_steps)]


def limit_args_for(args) -> List[str]:
    """Post-qadamlarga `--limit` ni uzatadi (sinov yurishlarini qisqartirish)."""
    return ["--limit", str(args.limit)] if args.limit else []


def main() -> None:
    ap = argparse.ArgumentParser(description="ETL orkestratori (H bosqich)")
    ap.add_argument("--with-docs", action="store_true", help="Hujjatlarni ham (sekinroq)")
    ap.add_argument("--all-statuses", action="store_true", help="Barcha statuslar (qimmat)")
    ap.add_argument("--limit", type=int,
                    help="SINOV: har manbadan faqat N yozuv (to'liq yurish o'rniga)")
    ap.add_argument("--sequential", action="store_true",
                    help="Platformalarni parallel emas, ketma-ket yurgiz")
    ap.add_argument("--skip-categorize", action="store_true",
                    help="Kategoriyalash post-qadamini o'tkazib yubor")
    ap.add_argument("--skip-notify", action="store_true",
                    help="Bildirishnoma (email/Telegram) post-qadamini o'tkazib yubor")
    args = ap.parse_args()

    # .env dan XT_DB_DSN — Windows'da muhit o'zgaruvchisi odatda o'rnatilmagan
    # (uni faqat bash wrapper run_etl.sh berardi). Bu qator bo'lmasa har
    # yurish "XATO: XT_DB_DSN o'rnatilmagan" bilan tugardi.
    if load_dotenv is not None:
        load_dotenv(os.path.join(HERE, ".env"))

    if psycopg2 is None:
        sys.exit("XATO: pip install psycopg2-binary")
    if not os.environ.get("XT_DB_DSN"):
        sys.exit("XATO: XT_DB_DSN o'rnatilmagan (.env yoki muhit o'zgaruvchisi).")

    groups = build_groups(args)
    mode = "ketma-ket" if args.sequential else "parallel"
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ETL orkestratori boshlandi "
          f"({len(groups)} platforma, {mode})")
    sys.stdout.flush()

    if args.sequential:
        results = [run_group(p, steps) for p, steps in groups]
    else:
        with ThreadPoolExecutor(max_workers=len(groups)) as pool:
            results = list(pool.map(lambda g: run_group(g[0], g[1]), groups))

    # Kategoriyalash — barcha manbalar tugagach (yangi tenderlarni belgilaydi).
    # Tender qo'shmaydi, shuning uchun etl_run'ga loglanmaydi.
    if not args.skip_categorize:
        _ok, _err, _dt, out = run_script("etl_categorize.py", [])
        emit(["\n===== post: kategoriyalash =====", *out])

    # Hujjat matnini ajratish (TZ P0-2) — faqat --with-docs bilan, chunki har
    # faylni manbadan yuklab olish kerak. Hujjatlarning O'ZI etl_details.py da
    # yig'iladi, bu qadam ularning MATNINI chiqaradi.
    if args.with_docs:
        _ok, _err, _dt, out = run_script("etl_doc_text.py", limit_args_for(args))
        emit(["\n===== post: hujjat matni =====", *out])

    # Bildirishnoma (TZ P0-10) — "soatlik kuzatish tsikli davomida keladi".
    # Skript YOQILGAN kanallarga yuboradi: email (SMTP) va/yoki Telegram.
    # Ikkalasi ham o'chirilgan bo'lsa hech narsa qilmaydi, xato bermaydi.
    if not args.skip_notify:
        _ok, _err, _dt, out = run_script("notify_new.py", [])
        emit(["\n===== post: bildirishnoma =====", *out])

    ok = all(results)
    summary = "hammasi muvaffaqiyatli" if ok else "ba'zi manbalarda xato (etl_run'ni ko'ring)"
    print(f"\n[{time.strftime('%H:%M:%S')}] Tugadi. {summary}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
