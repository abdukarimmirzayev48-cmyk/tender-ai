#!/usr/bin/env python3
"""
Yordamchi: xt-xarid.uz tenderlarining STATUS bo'yicha taqsimotini ko'rsatadi.
Tadbirkor uchun qaysi statuslar "faol" (ariza berса bo'ladigan) ekanini
aniqlashga yordam beradi.

Ishga tushirish:
    python3 status_counts.py
"""
import time
import requests
from collections import Counter

API_URL   = "https://api.xt-xarid.uz/rpc"
REF_NAME  = "ref_tender_public"
LIMIT     = 51
DELAY     = 1.0
HEADERS   = {"Content-Type": "application/json",
             "User-Agent": "xt-xarid-tender-aggregator/0.1 (research)"}


def fetch_all():
    session = requests.Session()
    records, offset, page = [], 0, 0
    while True:
        page += 1
        payload = {"jsonrpc": "2.0", "id": page, "method": "ref",
                   "params": {"ref": REF_NAME, "op": "read",
                              "limit": LIMIT, "offset": offset, "filters": {}}}
        r = session.post(API_URL, json=payload, headers=HEADERS, timeout=30)
        r.raise_for_status()
        res = r.json().get("result")
        batch = res["result"] if isinstance(res, dict) and "result" in res else res
        batch = batch or []
        records.extend(batch)
        if len(batch) < LIMIT:
            break
        offset += LIMIT
        time.sleep(DELAY)
    return records


def main():
    recs = fetch_all()
    print(f"Jami: {len(recs)} tender\n")

    # 1) Status taqsimoti
    status_ct = Counter(r.get("status") for r in recs)
    print("=== STATUS bo'yicha taqsimot ===")
    for st, n in status_ct.most_common():
        print(f"  {st:<20} {n:>4}")

    # 2) Valyuta taqsimoti (dashboard normalizatsiyasi uchun muhim)
    cur_ct = Counter(r.get("currency") for r in recs)
    print("\n=== VALYUTA bo'yicha ===")
    for c, n in cur_ct.most_common():
        print(f"  {c:<6} {n:>4}")

    # 3) Har status uchun sana maydonlari to'ldirilganmi — "faollik" belgisi
    #    (ends_at bor = deadline bor = ehtimol hali faol)
    print("\n=== STATUS × (ends_at bormi) ===")
    st_ends = Counter()
    for r in recs:
        has_ends = "bor" if r.get("ends_at") else "yo'q"
        st_ends[(r.get("status"), has_ends)] += 1
    for (st, he), n in sorted(st_ends.items()):
        print(f"  {st:<20} ends_at={he:<4} {n:>4}")


if __name__ == "__main__":
    main()
