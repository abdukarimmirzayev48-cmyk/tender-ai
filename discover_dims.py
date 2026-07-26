#!/usr/bin/env python3
"""
Kashfiyot: ref_status_tender va ref_area reestrlarining STRUKTURASINI ko'rsatadi.
Maqsad — bu reestrlar qanday maydonlar qaytarishini bilib, keyin ularni
dim_status / dim_area jadvallariga to'g'ri yuklovchi skript yozish.

Ishga tushirish:
    python3 discover_dims.py
"""
import json
import requests

API_URL = "https://api.xt-xarid.uz/rpc"
HEADERS = {"Content-Type": "application/json",
           "User-Agent": "xt-xarid-tender-aggregator/0.1 (research)"}


def call(ref, params_extra=None, rid=1):
    params = {"ref": ref, "op": "read", "limit": 100, "offset": 0}
    if params_extra:
        params.update(params_extra)
    payload = {"jsonrpc": "2.0", "id": rid, "method": "ref", "params": params}
    r = requests.post(API_URL, json=payload, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def unwrap(res):
    """Javobdan yozuvlar ro'yxatini ajratadi (turli shakllarни qo'llab-quvvatlaydi)."""
    result = res.get("result")
    if isinstance(result, dict) and "result" in result:
        return result["result"]
    if isinstance(result, list):
        return result
    if isinstance(result, dict) and "items" in result:
        return result["items"]
    return result


def show(ref, params_extra=None):
    print(f"\n{'='*60}\n  {ref}   params_extra={params_extra}\n{'='*60}")
    try:
        res = call(ref, params_extra)
    except Exception as e:
        print(f"  XATO: {e}")
        return
    recs = unwrap(res)
    if not isinstance(recs, list):
        print("  Kutilmagan javob shakli. Xom javob:")
        print(json.dumps(res, ensure_ascii=False, indent=2)[:1500])
        return
    print(f"  Yozuvlar soni: {len(recs)}")
    if recs:
        print(f"  Birinchi yozuv maydonlari: {list(recs[0].keys())}")
        print("  Birinchi 5 yozuv:")
        for r in recs[:5]:
            print("   ", json.dumps(r, ensure_ascii=False))


# 1) Status lug'ati
show("ref_status_tender")

# 2) Hudud — ildiz darajasi (parent_id bermaymiz — top level chiqishi kerak)
show("ref_area")

# 3) Hudud — Toshkent shahri ostidagi tumanlar (33 = ildiz deb taxmin qilamiz)
#    Agar parent_id boshqacha ishlasa, natijadan ko'rib tuzatamiz
show("ref_area", {"filters": {"parent_id": "33"}})
