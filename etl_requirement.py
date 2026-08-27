#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""J3 — talablarni ajratish (`tender_requirement`).

HOZIRGI HOLAT: faqat `source='api'` — reyestr pozitsiyalari.
MODEL CHAQIRILMAYDI, PUL SARFLANMAYDI.

Hujjatdan ajratish (`source='document'`, Opus 5 + Batch API) keyingi
qadam; jadval, `ON CONFLICT` mantiqi va yurish jurnali o'sha-o'sha
qoladi — faqat manba qo'shiladi.

Ishlatish:
    python etl_requirement.py --company 2                # ochiq tenderlar
    python etl_requirement.py --company 2 --limit 50
    python etl_requirement.py --company 2 --count-only   # sanaydi, yozmaydi
    python etl_requirement.py --company 2 --tender-id 8438603
    python etl_requirement.py --company 2 --force        # ajratilganini ham
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from api import db, requirement as R


def main() -> int:
    if load_dotenv:
        load_dotenv(os.path.join(HERE, ".env"))

    ap = argparse.ArgumentParser(description="Tender talablarini ajratish (J3)")
    ap.add_argument("--company", type=int, required=True,
                    help="Kompaniya id (qamrov kompaniyaga bog'liq)")
    ap.add_argument("--tender-id", type=int, help="Faqat shu tender")
    ap.add_argument("--limit", type=int, default=1000,
                    help="Nechta tender (standart 1000)")
    ap.add_argument("--count-only", action="store_true",
                    help="Faqat SANAYDI — bazaga yozmaydi")
    ap.add_argument("--force", action="store_true",
                    help="Allaqachon ajratilganlarni ham qayta yozadi")
    ap.add_argument("--method", choices=["reyestr", "naqsh"],
                    default="reyestr",
                    help="reyestr — tender_good pozitsiyalari; "
                         "naqsh — hujjatdan REGEX bilan. Ikkalasi ham BEPUL. "
                         "LLM (`llm`) alohida yurgiziladi va PUL SARFLAYDI")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if not os.environ.get("XT_DB_DSN"):
        sys.exit("XATO: XT_DB_DSN o'rnatilmagan (.env ni tekshiring).")

    db.init_pool()
    try:
        if not db.scalar("SELECT to_regclass('public.tender_requirement')"):
            sys.exit("XATO: jadval yo'q. Avval qo'llang:\n"
                     "  psql -d xtxarid -f schema_patch_requirement.sql")

        cid = args.company
        if not db.scalar("SELECT 1 FROM company_account WHERE id=%(c)s",
                         {"c": cid}):
            sys.exit(f"XATO: company_account da id={cid} yo'q.")

        if args.tender_id:
            nishon = [{"id": args.tender_id, "name": None, "close_at": None}]
        elif args.force:
            nishon = db.query("""
                SELECT id, name, close_at FROM tender
                WHERE close_at IS NULL OR close_at > now()
                ORDER BY close_at NULLS LAST LIMIT %(l)s""",
                {"l": args.limit})
        else:
            nishon = R.pending(cid, args.limit, method=args.method)

        print(f"[1/2] Kompaniya {cid}: {len(nishon)} ta tender "
              f"({'hammasi' if args.force else 'ajratilmaganlari'}), "
              f"usul={args.method}")
        if args.count_only:
            n_poz = db.scalar("""
                SELECT count(*) FROM tender_good g
                WHERE g.tender_id = ANY(%(ids)s)""",
                {"ids": [t["id"] for t in nishon]}) or 0
            print(f"      Taxminiy talab: {n_poz:,} ta pozitsiya")
            print("\n      (--count-only — bazaga yozilmadi)")
            return 0

        t0, jami, xato = time.time(), 0, 0
        for i, t in enumerate(nishon, 1):
            try:
                if args.method == "naqsh":
                    from api import requirement_naqsh
                    r = requirement_naqsh.extract(t["id"], cid)
                else:
                    r = R.from_api(t["id"], cid)
                jami += r["n"]
            except Exception as e:                          # noqa: BLE001
                # BITTA tender butun yurishni to'xtatmasin — sabab
                # jurnalga yoziladi va keyin ko'rish mumkin.
                xato += 1
                R._run_yoz(cid, t["id"], args.method, "failed", 0, None,
                           None, error=str(e)[:400])
                if not args.quiet:
                    print(f"  [{i}/{len(nishon)}] #{t['id']} XATO: {str(e)[:70]}")
                continue
            if not args.quiet and (i % 50 == 0 or i == len(nishon)):
                print(f"      {i}/{len(nishon)} — {jami:,} talab")

        dt = time.time() - t0
        print(f"\n[2/2] Tayyor. {jami:,} talab, {len(nishon)} tender, "
              f"{dt:.0f} s. Xato: {xato}")
        korish = db.scalar("SELECT count(*) FROM v_requirement_review")
        if korish:
            print(f"      Ko'rib chiqish kerak: {korish} ta "
                  "(v_requirement_review)")
        return 1 if xato else 0
    finally:
        db.close_pool()


if __name__ == "__main__":
    raise SystemExit(main())
