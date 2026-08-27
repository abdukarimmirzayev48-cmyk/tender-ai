"""
OMBOR QOLDIG'I — ERP dan (faqat o'qish).

QAROR (`tender erp/docs/erp_arxitektura_3.md` 4.3 va 6.1): qoldiqning
EGASI — ERP. U yerda harakatlar jurnali bor (`erp.stock_move`), qoldiq esa
shundan hisoblanadi. Bu yerdagi `catalog_product.stock_qty` — Excel
importidan qolgan SURAT va u endi HAQIQAT MANBAI EMAS.

"A1" yo'li tanlangan: biz ERP dan O'QIYMIZ, ERP esa bizning ustunimizga
YOZMAYDI. Shu tufayli `public.*` ga yozmaslik qoidasi buzilmaydi.

NEGA HTTP EMAS: `erp_status.py` dagi bilan bir xil sabab — ikkalasi bitta
bazada va ERP `erp.v_stock_balance` VIEW ini shartnoma sifatida beradi.
Biz `erp.stock_move` jadvaliga emas, shu view ga bog'lanamiz: ERP ichida
ustun o'zgarsa view moslashtiriladi va bu fayl o'zgarmaydi.

ERP O'RNATILMAGAN bo'lsa `ready()` False qaytaradi va chaqiruvchi eski
xatti-harakatiga qaytadi (import qoldig'i). Ombor ishga tushmagan
o'rnatmalarda hech narsa buzilmaydi.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from api import db

READY_SQL = """
SELECT 1 AS x FROM information_schema.views
WHERE table_schema = 'erp' AND table_name = 'v_stock_balance'
"""

# `available` = qty - rezerv. Tender-AI ning savoli "YETADIMI?" —
# unga javob beradigan son shu: boshqa tenderga ajratilgan tovarni
# ikkinchi marta hisoblab bo'lmaydi.
BALANCES_SQL = """
SELECT product_id, qty, reserved, available, unit, updated_at
FROM erp.v_stock_balance
"""

#: Omborda umuman harakat bormi. Bo'sh jurnal "hamma qoldiq nol" degani
#: EMAS — "ombor hali ishga tushmagan" degani.
ANY_MOVE_SQL = "SELECT 1 AS x FROM erp.stock_move LIMIT 1"

_READY: bool = False


def ready() -> bool:
    global _READY
    if _READY:
        return True
    _READY = bool(db.query_one(READY_SQL))
    return _READY


def balances() -> Dict[int, Dict[str, Any]]:
    """`{product_id: {qty, reserved, available, unit, updated_at}}`.

    ERP o'rnatilmagan bo'lsa bo'sh lug'at."""
    if not ready():
        return {}
    return {r["product_id"]: {"qty": r["qty"], "reserved": r["reserved"],
                              "available": r["available"], "unit": r["unit"],
                              "updated_at": r["updated_at"]}
            for r in db.query(BALANCES_SQL)}


def in_use() -> bool:
    """Ombor ISHGA TUSHGANMI (hech bo'lmasa bitta harakat bormi).

    NEGA ALOHIDA SAVOL: sxema patchi qo'llangani bilan ombor to'ldirilgan
    bo'lmaydi. Bo'sh jurnalni "hamma qoldiq nol" deb o'qisak, patch
    qo'llangan kuniyoq butun katalogdagi qoldiq YO'QOLIB ko'rinardi va
    hech kim sababini tushunmasdi.

    Shuning uchun qoida: jurnal bo'sh ekan — eski surat (Excel importi)
    ishlaydi; birinchi harakat kiritilgach EGA butunlay ERP bo'ladi.
    Ikki haqiqat manbai bir vaqtda YASHAMAYDI."""
    return ready() and bool(db.query_one(ANY_MOVE_SQL))


def apply_to_products(products: list, *, bal: Optional[Dict[int, Dict[str, Any]]] = None
                      ) -> str:
    """Katalog qatorlaridagi qoldiqni ERP hisobiga ALMASHTIRADI.

    Qaytaradi: qoldiq QAYERDAN kelgani — 'erp' yoki 'import'. Chaqiruvchi
    buni javobga qo'shadi, chunki foydalanuvchi raqamning manbaini bilishi
    kerak: "14 kundan eski import" va "bugungi ombor jurnali" bir xil
    ishonchga ega emas.

    ERP EGALIK QILGANDA (jurnalda harakat bor) undagi qaydi YO'Q mahsulot
    `stock_qty = None` bo'ladi — import qiymati QOLDIRILMAYDI. Aks holda
    bitta ro'yxatda ikki xil haqiqat aralashib ketardi: ayrimi jurnaldan,
    ayrimi eski Exceldan. `None` esa "ERP da qoldiq kiritilmagan" degani
    va cheklist buni "noma'lum" deb ko'rsatadi — bu rost javob.
    """
    if not in_use():
        return "import"
    bal = balances() if bal is None else bal
    for p in products:
        b = bal.get(p.get("id"))
        # `stock_qty` ga MAVJUD miqdor yoziladi (jismoniy qoldiq emas):
        # boshqa tenderga ajratilgan tovar bizga yetmaydi.
        p["stock_qty"] = b["available"] if b else None
        # Jismoniy qoldiq va rezerv ham beriladi — interfeys "10 dona bor,
        # 8 tasi band" deb tushuntira olsin.
        p["stock_physical"] = b["qty"] if b else None
        p["stock_reserved"] = b["reserved"] if b else None
        if b and b.get("unit"):
            p["stock_unit"] = b["unit"]
        p["stock_updated_at"] = b["updated_at"] if b else None
    return "erp"
