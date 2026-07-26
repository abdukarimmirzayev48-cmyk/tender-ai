#!/usr/bin/env python3
"""
ETL ORKESTRATORI (H bosqich) — barcha manbalarni yangilaydi + jurnal yozadi
===========================================================================
Cron/launchd shu skriptni chaqiradi. Har manba yurishi `etl_run` jadvaliga
yoziladi (sog'lik + yangi topilgan tenderlar soni). Bu tufayli:
  - "oxirgi yangilanish qachon", "nechta yangi topildi" — o'lchanadigan
  - biror manba buzilsa (sayt o'zgardi/tushdi) — status='error' qoladi (jimgina
    o'tkazib yuborilmaydi, TZ NFT talabi)

first_seen_at (schema_patch_freshness.sql) UPSERT'да saqlanadi, shuning uchun
"biz birinchi qachon ko'rdik" aniq qoladi -> aniqlash-kechikishini o'lchaymiz.

Ishga tushirish:
    export XT_DB_DSN="dbname=xtxarid user=a1234 password=... host=localhost"
    python3 run_etl.py                 # tez: tenderlar + kategoriyalar
    python3 run_etl.py --with-docs      # + hujjatlar (sekinroq)
    python3 run_etl.py --all-statuses   # ochiq emas, hammasi (qimmat)
"""
import argparse
import os
import subprocess
import sys
import time
from typing import List, Optional

try:
    import psycopg2
except ImportError:
    psycopg2 = None

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable  # o'sha venv python'i


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


def run_step(platform: str, script: str, extra_args: List[str],
             log_platform: Optional[str]) -> bool:
    """Bitta ETL skriptini yurgizadi. log_platform berilsa etl_run'ga yozadi.
    Qaytadi: muvaffaqiyatli (True/False)."""
    conn = db()
    run_id = None
    started = None
    if log_platform:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO etl_run (source_platform, status) VALUES (%s,'running') "
                        "RETURNING id, started_at", (log_platform,))
            run_id, started = cur.fetchone()
        conn.commit()

    print(f"\n--- {platform}: {script} {' '.join(extra_args)} ---")
    t0 = time.time()
    try:
        res = subprocess.run([PY, os.path.join(HERE, script), *extra_args],
                             cwd=HERE, env=os.environ.copy(),
                             capture_output=True, text=True, timeout=3600)
        ok = res.returncode == 0
        # Oxirgi bir necha qatorni ko'rsatamiz
        tail = "\n".join((res.stdout or "").strip().splitlines()[-4:])
        if tail:
            print(tail)
        err = None if ok else (res.stderr or res.stdout or "")[-500:]
    except subprocess.TimeoutExpired:
        ok, err = False, "timeout (1 soat)"
    except Exception as e:  # noqa: BLE001
        ok, err = False, str(e)[:500]

    dt = time.time() - t0
    if log_platform and run_id:
        found = platform_count(conn, log_platform)
        new = platform_count(conn, log_platform, since=started) if started else None
        with conn.cursor() as cur:
            cur.execute("UPDATE etl_run SET finished_at=now(), status=%s, found=%s, "
                        "new=%s, error=%s WHERE id=%s",
                        ("ok" if ok else "error", found, new, err, run_id))
        conn.commit()
        print(f"  [{'OK' if ok else 'XATO'}] {dt:.0f}s | jami {found}, yangi {new}")
    else:
        print(f"  [{'OK' if ok else 'XATO'}] {dt:.0f}s")
    conn.close()
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description="ETL orkestratori (H bosqich)")
    ap.add_argument("--with-docs", action="store_true", help="Hujjatlarni ham (sekinroq)")
    ap.add_argument("--all-statuses", action="store_true", help="Barcha statuslar (qimmat)")
    args = ap.parse_args()

    if psycopg2 is None:
        sys.exit("XATO: pip install psycopg2-binary")
    if not os.environ.get("XT_DB_DSN"):
        sys.exit("XATO: XT_DB_DSN o'rnatilmagan.")

    status_args = ["--all-statuses"] if args.all_statuses else []
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ETL orkestratori boshlandi")

    results = []
    # 1) Manba tenderlari (etl_run'ga loglanadi)
    results.append(run_step("xt-xarid", "etl_tenders.py", status_args, "xt-xarid"))
    results.append(run_step("uzex", "etl_uzex.py", [], "uzex"))

    # 2) Hujjatlar (ixtiyoriy, sekinroq) — tender qo'shmaydi, loglanmaydi
    if args.with_docs:
        run_step("xt-xarid-docs", "etl_details.py", [], None)

    # 3) Kategoriyalash (yangi tenderlarни belgilaydi) — post-qadam
    run_step("categorize", "etl_categorize.py", [], None)

    ok = all(results)
    summary = "hammasi muvaffaqiyatli" if ok else "ba'zi manbalarda xato (etl_run'ni ko'ring)"
    print(f"\n[{time.strftime('%H:%M:%S')}] Tugadi. {summary}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
