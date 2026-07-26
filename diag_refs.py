#!/usr/bin/env python3
"""
Diagnostika: ref_status / ref_area uchun QAYSI nom va parametr shakli ishlashini topadi.
500 xato bergani uchun turli variantlarni sinab ko'ramiz.

Ishga tushirish:
    python3 diag_refs.py
"""
import json
import requests

API_URL = "https://api.xt-xarid.uz/rpc"
HEADERS = {"Content-Type": "application/json",
           "User-Agent": "xt-xarid-tender-aggregator/0.1 (research)"}


def try_call(label, params):
    payload = {"jsonrpc": "2.0", "id": 1, "method": "ref", "params": params}
    try:
        r = requests.post(API_URL, json=payload, headers=HEADERS, timeout=30)
        status = r.status_code
        if status == 200:
            body = r.json()
            # Xatoni RPC ichida ham tekshiramiz
            if "error" in body and body["error"]:
                print(f"  [{status}] {label}  →  RPC error: {json.dumps(body['error'], ensure_ascii=False)[:120]}")
                return
            res = body.get("result")
            # yozuvlar sonini aniqlashga urinamiz
            recs = res
            if isinstance(res, dict) and "result" in res:
                recs = res["result"]
            n = len(recs) if isinstance(recs, list) else "?"
            print(f"  [200] ✓ ISHLADI  {label}  →  {n} yozuv")
            if isinstance(recs, list) and recs:
                print(f"         maydonlar: {list(recs[0].keys())}")
                print(f"         namuna:    {json.dumps(recs[0], ensure_ascii=False)[:200]}")
        else:
            # xato matnidan ipucha izlaymiz
            print(f"  [{status}] {label}  →  {r.text[:120]}")
    except Exception as e:
        print(f"  [ERR] {label}  →  {e}")


print("=== 1) Status reestri — nom variantlari (minimal params) ===")
for ref in ["ref_status_tender", "ref_status", "ref_tender_status",
            "ref_status_tenders", "ref_statuses", "status_tender"]:
    try_call(ref, {"ref": ref, "op": "read"})

print("\n=== 2) Status — turli param shakllari (ref_status_tender) ===")
try_call("faqat ref+op",        {"ref": "ref_status_tender", "op": "read"})
try_call("+ limit",             {"ref": "ref_status_tender", "op": "read", "limit": 100})
try_call("+ limit+offset",      {"ref": "ref_status_tender", "op": "read", "limit": 100, "offset": 0})
try_call("+ filters bo'sh",     {"ref": "ref_status_tender", "op": "read", "limit": 100, "offset": 0, "filters": {}})

print("\n=== 3) Hudud reestri — nom variantlari ===")
for ref in ["ref_area", "ref_areas", "ref_region", "ref_regions",
            "ref_area_public", "area", "ref_soato"]:
    try_call(ref, {"ref": ref, "op": "read"})

print("\n=== 4) Hudud — parent_id turli joyda ===")
try_call("filters.parent_id str", {"ref": "ref_area", "op": "read", "filters": {"parent_id": "33"}})
try_call("filters.parent_id int", {"ref": "ref_area", "op": "read", "filters": {"parent_id": 33}})
try_call("params.parent_id",      {"ref": "ref_area", "op": "read", "parent_id": "33"})
try_call("params.parent_id null", {"ref": "ref_area", "op": "read", "parent_id": None})
try_call("filters.parent_id null",{"ref": "ref_area", "op": "read", "filters": {"parent_id": None}})
