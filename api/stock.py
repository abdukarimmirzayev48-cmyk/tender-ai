"""
OMBOR QOLDIG'INI TEKSHIRISH (TZ P0-6).

Qabul qilish mezonlari:
    * Har bir mos kelgan pozitsiya bo'yicha ombordagi qoldiq va so'ralgan
      miqdor uchun YETARLILIGI ko'rsatiladi
    * Yetishmayotgan pozitsiyalar alohida "yetishmayapti" ro'yxatida ajratiladi

DIZAYN
------
1. USTAMA, ALMASHTIRISH EMAS. Mavjud moslashtirish (`main._product_matches`,
   `POST /catalog/match`) TENDER darajasida ishlaydi: "shu tender katalogga
   mos keladimi". Bu modul esa POZITSIYA darajasida: "shu tenderning qaysi
   qatoriga qaysi mahsulotim mos va qoldig'im yetadimi". Shuning uchun
   kategoriya tarmog'i (tender darajasidagi kuchli signal) bu yerda
   ISHLATILMAYDI — u tenderning HAMMA pozitsiyasini mos deb belgilab
   qo'yardi. Moslik faqat NOM/KALIT SO'Z bo'yicha, `api.matching` ning
   alifbodan qat'i nazar ishlaydigan `_hits()` i orqali (nasos <-> Насос).

2. TAXMIN QILINMAYDI. `tender_item.amount_text` — MATN (" 660.00 шт",
   "3 720 порция"). Sonni ishonchli ajratib bo'lmasa, pozitsiya "noma'lum"
   deb belgilanadi va "yetishmayapti" ro'yxatiga TUSHMAYDI (soxta xavotir
   bermaymiz), lekin xulosada alohida sanaladi.

3. QOLDIQ BO'LINADI. Bitta mahsulot tenderning bir necha qatoriga mos kelsa,
   ombordagi qoldiq ULAR ORASIDA taqsimlanadi (ketma-ket ayirib boriladi).
   Aks holda 150 dona qoldiq bilan 3 ta 100 donalik qator ham "yetarli"
   ko'rinardi.

4. ESKIRGAN QOLDIQ. `catalog_product.stock_updated_at` STOCK_STALE_DAYS
   (default 14) kundan eski bo'lsa yoki umuman yuklanmagan bo'lsa — natija
   `preliminary: true` ("dastlabki") deb belgilanadi va ogohlantirish
   qaytariladi (TZ talabi).
"""
import os
import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from api import db, matching

# Qoldiq necha kundan keyin "eskirgan" hisoblanadi
STALE_DAYS = int(os.environ.get("STOCK_STALE_DAYS", "14"))

STATUS_LABELS = {
    "yetarli": "Yetarli",
    "yetishmaydi": "Yetishmayapti",
    "nomalum": "Noma’lum",
}

# ---------------------------------------------------------------------------
# 1. amount_text -> son
# ---------------------------------------------------------------------------
_SPACES = "    "   # NBSP, thin space, narrow NBSP


def parse_amount_text(raw: Any) -> Tuple[Optional[Decimal], Optional[str]]:
    """`tender_item.amount_text` dan so'ralgan MIQDORNI ajratadi.

    Qaytaradi: (miqdor, izoh). Ishonchsiz bo'lsa (None, sabab) — chaqiruvchi
    pozitsiyani "noma'lum" deb belgilaydi. HECH QACHON taxmin qilinmaydi.

    Bazadagi haqiqiy ko'rinishlar (tekshirilgan, 2113 pozitsiya):
        " 660.00 шт"      -> 660      (bosh probel, nuqta — kasr)
        "3 000.00 т"      -> 3000     (probel — mingliklar ajratgichi)
        "3 720 порция"    -> 3720
        "1 порция"        -> 1
        "1.00 усл. ед"    -> 1
    Qabul qilinmaydigan holatlar:
        ""/None/"-"       -> noma'lum (miqdor ko'rsatilmagan)
        "10-15 шт"        -> noma'lum (diapazon)
        "2 x 3 шт"        -> noma'lum (ko'paytma)
        "по требованию"   -> noma'lum (son yo'q)
    """
    if raw is None:
        return None, "miqdor ko‘rsatilmagan"
    if isinstance(raw, (int, float, Decimal)) and not isinstance(raw, bool):
        try:
            return Decimal(str(raw)), None
        except InvalidOperation:
            return None, "miqdorni o‘qib bo‘lmadi"

    s = unicodedata.normalize("NFKC", str(raw))
    for ch in _SPACES:
        s = s.replace(ch, " ")
    s = s.strip()
    if not s or s in {"-", "—", "–"}:
        return None, "miqdor ko‘rsatilmagan"

    m = re.match(r"^(\d[\d ]*(?:[.,]\d+)?)", s)
    if not m:
        return None, f"matnda son yo‘q: “{s[:40]}”"
    token = m.group(1)
    tail = s[m.end():]
    # Qolgan qismda yana son bo'lsa — diapazon/ko'paytma, qaysi biri ekani
    # noma'lum. "1.00 усл. ед" da ham raqam bor -> shuning uchun faqat
    # ALOHIDA turgan sonlarni tekshiramiz.
    if re.search(r"(?<![\w.])\d", tail):
        return None, f"bir nechta son (diapazon yoki ko‘paytma): “{s[:40]}”"

    token = token.strip()
    if " " in token:
        # Probel faqat TO'G'RI mingliklar guruhida ruxsat: 3 720, 1 000.00
        if not re.fullmatch(r"\d{1,3}( \d{3})+([.,]\d+)?", token):
            return None, f"sonni aniq ajratib bo‘lmadi: “{s[:40]}”"
        token = token.replace(" ", "")
    token = token.replace(",", ".")
    try:
        return Decimal(token), None
    except InvalidOperation:
        return None, f"sonni o‘qib bo‘lmadi: “{s[:40]}”"


# ---------------------------------------------------------------------------
# 2. O'lchov birliklari
# ---------------------------------------------------------------------------
# Bazadagi haqiqiy birliklar: шт, дона, dona, Штук, компл., компл, тўплам,
# набор, упак, упак., усл.ед, усл. ед, шартли бирлик, порция, порц., доз.,
# флакон, фл, кг, т, объект
_UNIT_CANON: Dict[str, str] = {}


def _reg(canon: str, *forms: str) -> None:
    for f in forms:
        _UNIT_CANON[f] = canon


_reg("dona", "шт", "штук", "шт-к", "дона", "dona", "pcs", "pc", "ta", "ед", "единица")
_reg("komplekt", "компл", "комплект", "тўплам", "туплам", "to'plam", "toplam",
     "набор", "set", "komplekt")
_reg("kg", "кг", "kg", "килограмм", "kilogramm")
_reg("t", "т", "t", "тонна", "tonna", "ton")
_reg("l", "л", "l", "литр", "litr")
_reg("m", "м", "m", "метр", "metr")
_reg("m2", "м2", "m2", "кв м", "kv m")
_reg("m3", "м3", "m3", "куб м", "kub m")
_reg("upak", "упак", "упаковка", "пачка", "quti", "коробка", "box", "pack", "paket")
_reg("shartli", "услед", "усл ед", "уе", "шартли бирлик", "шартли", "усл")
_reg("porsiya", "порция", "порц", "porsiya", "portsiya")
_reg("flakon", "флакон", "фл", "доз", "доза", "flakon")
_reg("obyekt", "объект", "obyekt", "obekt")


def norm_unit(u: Optional[str]) -> Optional[str]:
    """Birlikni kanonik ko'rinishga keltiradi. Noma'lum bo'lsa tozalangan
    matn qaytadi (shunda bir xil yozilganlar baribir tenglashadi)."""
    if not u:
        return None
    t = unicodedata.normalize("NFKC", str(u)).strip().lower()
    t = t.replace("ў", "у").replace("қ", "к").replace("ҳ", "х").replace("ғ", "г")
    t = re.sub(r"[.\-_/]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return _UNIT_CANON.get(t) or _UNIT_CANON.get(t.replace(" ", "")) or (t or None)


# ---------------------------------------------------------------------------
# 3. SQL
# ---------------------------------------------------------------------------
_ITEMS_SQL = """
SELECT lot_id, item_id, product_code, name, unit, amount_text, spec, properties
FROM tender_item
WHERE tender_id = %(id)s
ORDER BY lot_id, item_id, name
"""

# Zaxira manba: 262/342 tenderда `tender_item` bor, `tender_good` esa
# HAMMASIDA — va u yerda `amount` allaqachon NUMERIC. Pozitsiya tafsiloti
# yuklanmagan tenderlar uchun shu ishlatiladi (natijada `source` ko'rsatiladi).
_GOODS_SQL = """
SELECT lot_id, good_code AS item_id, NULL::text AS product_code, name, unit,
       amount, NULL::text AS spec, NULL::jsonb AS properties
FROM tender_good
WHERE tender_id = %(id)s
ORDER BY lot_id, good_code
"""

_PRODUCTS_SQL = """
SELECT id, name, keywords, unit, stock_qty, stock_unit, stock_updated_at,
       cost_price, price, currency
FROM catalog_product
ORDER BY id
"""

_TENDER_SQL = "SELECT id, name FROM tender WHERE id = %(id)s"


# ---------------------------------------------------------------------------
# 4. Pozitsiya <-> katalog moslashtirish
# ---------------------------------------------------------------------------
def match_product(position: Dict[str, Any], products: List[Dict[str, Any]]
                  ) -> Optional[Dict[str, Any]]:
    """Pozitsiyaga eng mos katalog bandi (yoki None).

    `main._product_matches` ning NOM shoxchasi bilan bir xil mantiq
    (`matching._hits` — alifbodan qat'i nazar). Bir nechtasi mos kelsa ENG
    UZUN atama g'olib: "kompyuter sichqonchasi" "kompyuter" dan aniqroq.
    """
    blob = matching._norm(" ".join(filter(None, [
        position.get("name"), position.get("spec"),
    ])))
    if not blob:
        return None
    best: Optional[Dict[str, Any]] = None
    best_len = 0
    for p in products:
        terms = [p["name"]] + list(p.get("keywords") or [])
        for t in terms:
            if t and matching._hits(t, blob) and len(t) > best_len:
                best, best_len = p, len(t)
    return best


# ---------------------------------------------------------------------------
# 5. Asosiy tekshiruv
# ---------------------------------------------------------------------------
def _f(v: Any) -> Optional[float]:
    return float(v) if v is not None else None


def _age_days(ts: Optional[datetime]) -> Optional[int]:
    if ts is None:
        return None
    now = datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max(0, (now - ts).days)


def check_tender_stock(tender_id: int) -> Optional[Dict[str, Any]]:
    """Tender pozitsiyalarini katalog qoldig'iga solishtiradi.

    None qaytsa — bunday tender yo'q (chaqiruvchi 404 beradi).
    """
    tender = db.query_one(_TENDER_SQL, {"id": tender_id})
    if not tender:
        return None

    rows = db.query(_ITEMS_SQL, {"id": tender_id})
    source = "tender_item"
    if not rows:
        rows = db.query(_GOODS_SQL, {"id": tender_id})
        source = "tender_good"

    products = db.query(_PRODUCTS_SQL)

    return build_check(tender, rows, products, source=source)


def build_check(tender: Dict[str, Any], rows: List[Dict[str, Any]],
                products: List[Dict[str, Any]], *, source: str = "tender_item"
                ) -> Dict[str, Any]:
    """Sof hisob-kitob qismi (bazadan ajratilgan — sinovda to'g'ridan-to'g'ri
    chaqirsa bo'ladi)."""
    # Mahsulot bo'yicha qolgan qoldiq — qatorlar orasida taqsimlanadi
    pool: Dict[int, Optional[Decimal]] = {
        p["id"]: (Decimal(str(p["stock_qty"])) if p["stock_qty"] is not None else None)
        for p in products
    }

    items: List[Dict[str, Any]] = []
    shortages: List[Dict[str, Any]] = []
    unmatched: List[Dict[str, Any]] = []
    used_products: Dict[int, Dict[str, Any]] = {}

    for r in rows:
        # `tender_good` da miqdor NUMERIC, `tender_item` da MATN
        raw_amount = r.get("amount_text") if "amount_text" in r else r.get("amount")
        required, note = parse_amount_text(raw_amount)

        base = {
            "lot_id": r.get("lot_id"),
            "item_id": r.get("item_id"),
            "name": r.get("name"),
            "unit": r.get("unit"),
            "amount_text": None if raw_amount is None else str(raw_amount),
            "required_qty": _f(required),
            "qty_note": note,
        }

        product = match_product(r, products)
        if not product:
            unmatched.append({**base, "reason": "Katalogda mos mahsulot yo‘q."})
            continue

        used_products[product["id"]] = product
        available = pool.get(product["id"])

        t_unit = norm_unit(r.get("unit"))
        c_unit = norm_unit(product.get("stock_unit") or product.get("unit"))
        unit_ok = True
        unit_note = None
        if t_unit and c_unit and t_unit != c_unit:
            unit_ok = False
            unit_note = (f"O‘lchov birligi mos emas: tenderda “{r.get('unit')}”, "
                         f"omborda “{product.get('stock_unit') or product.get('unit')}”.")
        elif not c_unit:
            unit_note = "Ombor o‘lchov birligi ko‘rsatilmagan — solishtiruv taxminiy."

        # --- Holat ---
        if available is None:
            status = "nomalum"
            reason = "Ombor qoldig‘i kiritilmagan."
            shortfall = None
        elif required is None:
            status = "nomalum"
            reason = f"So‘ralgan miqdor aniqlanmadi ({note})."
            shortfall = None
        elif not unit_ok:
            status = "nomalum"
            reason = unit_note
            shortfall = None
        elif available >= required:
            status = "yetarli"
            reason = None
            shortfall = None
            pool[product["id"]] = available - required   # zaxiradan ayiramiz
        else:
            status = "yetishmaydi"
            shortfall = required - available
            reason = (f"{_fmt(shortfall)} {r.get('unit') or ''}".strip()
                      + " yetishmayapti.")
            pool[product["id"]] = Decimal(0)

        item = {
            **base,
            "product": {
                "id": product["id"],
                "name": product["name"],
                "unit": product.get("unit"),
                "stock_unit": product.get("stock_unit"),
                "stock_qty": _f(product.get("stock_qty")),
                "stock_updated_at": (product["stock_updated_at"].isoformat()
                                     if product.get("stock_updated_at") else None),
                "stock_age_days": _age_days(product.get("stock_updated_at")),
                "cost_price": _f(product.get("cost_price")),
            },
            "available_qty": _f(available),          # SHU qator uchun qolgan qoldiq
            "shortfall_qty": _f(shortfall),
            "unit_match": unit_ok,
            "unit_note": unit_note,
            "status": status,
            "status_label": STATUS_LABELS[status],
            "reason": reason,
        }
        items.append(item)
        if status == "yetishmaydi":
            shortages.append(item)

    # --- Qoldiq yangiligi (TZ: eskirgan bo'lsa "dastlabki" deb belgilanadi) ---
    stamps = [p["stock_updated_at"] for p in used_products.values()
              if p.get("stock_updated_at")]
    have_stock = any(p.get("stock_qty") is not None for p in used_products.values())
    oldest = min(stamps) if stamps else None
    age = _age_days(oldest)
    stale = age is not None and age > STALE_DAYS
    loaded = bool(stamps) and have_stock

    if not have_stock:
        warning = ("Ombor qoldiqlari yuklanmagan — solishtiruv DASTLABKI. "
                   "Katalogni Excel/CSV dan import qiling.")
    elif not loaded:
        warning = ("Qoldiq qachon yangilangani noma’lum — solishtiruv DASTLABKI.")
    elif stale:
        warning = (f"Ombor qoldiqlari {age} kun oldin yangilangan "
                   f"({STALE_DAYS} kundan eski) — solishtiruv DASTLABKI.")
    else:
        warning = None

    counts = {"yetarli": 0, "yetishmaydi": 0, "nomalum": 0}
    for it in items:
        counts[it["status"]] += 1

    return {
        "tender_id": tender["id"],
        "tender_name": tender.get("name"),
        "source": source,
        "stock": {
            "loaded": loaded,
            "updated_at": oldest.isoformat() if oldest else None,
            "age_days": age,
            "stale": stale,
            "stale_after_days": STALE_DAYS,
            "products_used": len(used_products),
            "warning": warning,
        },
        # TZ: qoldiq yuklanmagan yoki eskirgan bo'lsa solishtiruv "dastlabki"
        "preliminary": (not loaded) or stale,
        "summary": {
            "positions": len(rows),
            "matched": len(items),
            "unmatched": len(unmatched),
            "ok": counts["yetarli"],
            "short": counts["yetishmaydi"],
            "unknown": counts["nomalum"],
        },
        "items": items,
        # P0-6: yetishmayotganlar ALOHIDA ro'yxat
        "shortages": shortages,
        "unmatched": unmatched,
    }


def _fmt(d: Optional[Decimal]) -> str:
    """3120.000 -> "3120", 12.500 -> "12.5" (xabarlarda chiroyli ko'rinsin)."""
    if d is None:
        return "—"
    q = d.normalize()
    s = format(q, "f")
    return s.rstrip("0").rstrip(".") if "." in s else s
