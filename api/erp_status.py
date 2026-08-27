"""
ERP HOLATI — "shu tender ishga olinganmi?"

Bu tender-ai ning ERP ga YAGONA murojaati va u FAQAT O'QISH.

NEGA BOR: tender panelidagi `ErpLink` bloki foydalanuvchiga "bu tender
allaqachon ishga olingan, mas'ul — Karimov" deb aytadi. Ma'lumot ERP niki
(odamlar ham, kartalar ham u yerda).

NEGA HTTP EMAS: ilgari buni BRAUZER so'rardi — `ErpLink` to'g'ridan-to'g'ri
ERP backendiga borardi. Shuning uchun ERP ning o'sha endpointi OCHIQ
qolishga majbur edi: brauzer server-server kalitini ushlab turolmaydi
(kalit JS to'plamiga tushib qolardi). Endi so'rovni SERVER qiladi va ERP
endpointi yopildi.

NEGA `erp.opportunity` EMAS, `erp.v_tender_status`: bu ATAYLAB SHARTNOMA.
Biz ERP ning jadval ustunlariga emas, u kafolatlagan view ga bog'lanamiz.
ERP ichida ustun nomi o'zgarsa yoki jadval bo'linsa — view moslashtiriladi
va bu fayl o'zgarmaydi. View ERP tomonida yaratiladi:
`tender erp/schema_patch_erp_7.sql`.

CHEGARA SIMMETRIK:
    ERP        `public.*` dan O'QIYDI (tender snapshoti), YOZMAYDI.
    Tender-AI  `erp.v_tender_status` dan O'QIYDI, YOZMAYDI.
Ikkala loyihaning sinovi ham har yurishda buni tekshiradi.

ERP O'RNATILMAGAN bo'lsa (view yo'q) — bu XATO EMAS: `ready()` False
qaytaradi, endpoint bo'sh ro'yxat beradi va interfeys blokni umuman
ko'rsatmaydi. Tender paneli ERP tufayli buzilmasligi kerak.
"""
from __future__ import annotations

from typing import Any, Dict, List

from api import db

VIEW_SQL = """
SELECT opportunity_id, tender_id, status, status_label, priority,
       broker_name, client_name, created_at, updated_at
FROM erp.v_tender_status
WHERE tender_id = %(tender_id)s
ORDER BY opportunity_id
"""

READY_SQL = """
SELECT 1 AS x FROM information_schema.views
WHERE table_schema = 'erp' AND table_name = 'v_tender_status'
"""

#: Bir marta tekshiriladi: view paydo bo'lgach o'chib qolmaydi va har
#: so'rovda `information_schema` ga bormaymiz.
_READY: bool = False


def ready() -> bool:
    global _READY
    if _READY:
        return True
    _READY = bool(db.query_one(READY_SQL))
    return _READY


def _iso(v):
    return v.isoformat() if v is not None else None


def for_tender(tender_id: int) -> List[Dict[str, Any]]:
    """Shu tender bo'yicha ERP kartalari. ERP yo'q bo'lsa — bo'sh ro'yxat."""
    if not ready():
        return []
    return [{
        "opportunity_id": r["opportunity_id"],
        "status": r["status"],
        "status_label": r["status_label"],
        "priority": r["priority"],
        "broker_name": r["broker_name"],
        "client_name": r["client_name"],
        "created_at": _iso(r["created_at"]),
    } for r in db.query(VIEW_SQL, {"tender_id": tender_id})]
