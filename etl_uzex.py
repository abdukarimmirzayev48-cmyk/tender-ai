#!/usr/bin/env python3
"""
etender.uzex.uz  |  ADAPTER (2-manba)
=====================================
UzEx tenderlarini bizning UMUMIY sxemamizga o'giradi. Baza, backend API va
dashboard o'zgarmaydi — faqat shu transform qatlami qo'shiladi.

MANBA (autentifikatsiya KERAK EMAS — tekshirilgan):
    POST https://apietender.uzex.uz/api/common/TradeList   {TypeId, From, To, System_Id}
    GET  https://apietender.uzex.uz/api/common/GetTrade/{id}/0
    GET  https://apietender.uzex.uz/api/Libs/GetRegions
    Fayl: POST /api/common/DownloadFile?path=<urlencoded>   (GET ishlamaydi!)

MUHIM NUANCELAR (empirik aniqlangan):
  1. `budget_products`, `languages`, `contacts` — STRINGIFIED JSON, parse shart.
  2. Sahifalash — From/To OFFSET-DIAPAZON (page/size emas). From:1,To:20.
  3. `total_count` alohida maydon emas — har qatorning ichida takrorlanadi.
  4. Muddatlar turli birlikda: Delivery_Term=1 + Term_Period_Name='Год (лет)'.
     Biz KUNGA normalizatsiya qilamiz (bizning sxema kunlarda).
  5. Hudud ID umuman yo'q — faqat nom, turli alifboda. Shuning uchun
     viloyat darajasida ANIQ jadval bilan moslashtiramiz (pastda).
  6. UzEx'da "lot" tushunchasi yo'q — butun savdo = bitta lot (frontend /lot/{id}).
  7. TypeId savdo TURINI bildiradi va u `tender.type` ga o'giriladi (TYPE_BY_ID).
     Ilgari "tender" qattiq yozilgan edi — TypeId=1 yozuvlari ham noto'g'ri
     "tender" bo'lib qolar edi. Endi TypeId=1 -> 'selection' (xt-xarid'dagi
     ref_selection_public bilan bir xil atama).

Ishga tushirish:
    export XT_DB_DSN="dbname=xtxarid user=a1234 password=... host=localhost"
    python3 etl_uzex.py                # ochiq tenderlar (TypeId=2)
    python3 etl_uzex.py --type-id 1    # "Eng yaxshi takliflarni tanlash"
    python3 etl_uzex.py --limit 5 --dry-run
"""
import argparse
import json
import os
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

API           = "https://apietender.uzex.uz/api"
SOURCE        = "uzex"
UZEX_OFFSET   = 20_000_000_000   # global ID = source_id + shu ofset
PAGE          = 50
REQUEST_DELAY = 0.4
#: (ulanish, o'qish). Ilgari BITTA `TIMEOUT = 40` edi va u ikkalasiga
#: qo'llanardi: tushgan host uchun ham 40 sekund kutardik, holbuki
#: ulanish 8 sekundda ma'lum bo'ladi.
TIMEOUT       = ish.STANDART_TIMEOUT
HEADERS = {"Content-Type": "application/json",
           "User-Agent": "tender-aggregator/0.1 (research)"}

#: Vaqt byudjeti (sekund). Rejalashtiruvchi chegarasidan (45 daqiqa)
#: ANIQ KICHIK bo'lishi SHART: byudjet tugaganda skript checkpoint
#: yozib TOZA to'xtaydi, chegara tugaganda esa Windows uni O'LDIRADI
#: va checkpoint yozilmay qoladi.
STANDART_BYUDJET = 20 * 60

#: `GetTrade` ni o'tkazib yuborish uchun solishtiriladigan maydonlar.
#: TradeList da `updated_at` YO'Q (tekshirilgan), shuning uchun
#: o'zgarishni SHU maydonlar bo'yicha aniqlaymiz. Ular savdoning
#: mazmunini belgilaydi: nomi, muddati, narxi, sotuvchisi, hududi.
KUZATILADIGAN = ("name", "start_date", "end_date", "cost",
                 "seller_id", "region_name", "clarific_date")

#: Bitta seans — keep-alive va ulanish pooli. Ilgari modul darajasidagi
#: `requests.post/get` ishlatilardi, ya'ni HAR SO'ROVGA yangi TCP+TLS
#: qo'l berish (to'liq yurishda 623 ta ortiqcha handshake).
_SESSIYA: Optional[requests.Session] = None


def sessiya() -> requests.Session:
    global _SESSIYA
    if _SESSIYA is None:
        _SESSIYA = ish.sessiya_yarat(pool=4, sarlavhalar=HEADERS)
    return _SESSIYA

# ---------------------------------------------------------------------------
# HUDUD MOSLASHTIRISH — UzEx viloyati -> bizdagi KANONIK dim_area kodi
# Ikkala platforma bir xil 14 viloyatni ishlatadi, shuning uchun ularni
# BIRLASHTIRAMIZ: "Toshkent viloyati" filtri ikkala manbadan ham chiqaradi.
# (ID farqi doim 32 ekanini payqadik, lekin arifmetikaga tayanmaymiz —
#  aniq jadval xavfsizroq.)
# ---------------------------------------------------------------------------
REGION_MAP: Dict[int, Tuple[str, str]] = {
    2:    ("33.34",   "Andijon viloyati"),
    242:  ("33.274",  "Buxoro viloyati"),
    487:  ("33.519",  "Jizzax viloyati"),
    679:  ("33.711",  "Qashqadaryo viloyati"),
    1008: ("33.1040", "Navoiy viloyati"),
    1150: ("33.1182", "Namangan viloyati"),
    1413: ("33.1445", "Samarqand viloyati"),
    1692: ("33.1724", "Surxondaryo viloyati"),
    1977: ("33.2009", "Sirdaryo viloyati"),
    2105: ("33.2137", "Toshkent shahri"),
    2120: ("33.2152", "Toshkent viloyati"),
    2434: ("33.2466", "Farg‘ona viloyati"),
    2858: ("33.2890", "Xorazm viloyati"),
    3049: ("33.3081", "Qoraqalpog‘iston Respublikasi"),
}

# UzEx ro'yxati hudud nomini uch xil ko'rinishda qaytaradi:
#   * o'zbekcha lotin (kamdan-kam),
#   * o'zbekcha kirill,
#   * detail ichida ruscha (`delivering_region_name`).
#
# Faqat `REGION_MAP` dagi lotincha nom bilan tenglashtirish 376 ta ochiq
# UzEx tenderining 374 tasini hududsiz qoldirgan. Aliaslar ID ga emas,
# bizning KANONIK `dim_area.area_id` yo'liga bog'langan: manba nomi
# o'zgarsa ham bazadagi ierarxiya bir xil qoladi.
REGION_ALIASES: Dict[str, Tuple[str, ...]] = {
    "33.34": (
        "Andijon viloyati", "Андижон вилояти", "Андижанская область",
    ),
    "33.274": (
        "Buxoro viloyati", "Бухоро вилояти", "Бухарская область",
    ),
    "33.519": (
        "Jizzax viloyati", "Жиззах вилояти", "Джизакская область",
    ),
    "33.711": (
        "Qashqadaryo viloyati", "Қашқадарё вилояти", "Кашкадарьинская область",
    ),
    "33.1040": (
        "Navoiy viloyati", "Навоий вилояти", "Навоийская область",
    ),
    "33.1182": (
        "Namangan viloyati", "Наманган вилояти", "Наманганская область",
    ),
    "33.1445": (
        "Samarqand viloyati", "Самарқанд вилояти", "Самаркандская область",
    ),
    "33.1724": (
        "Surxondaryo viloyati", "Сурхандарё вилояти", "Сурхандарьинская область",
    ),
    "33.2009": (
        "Sirdaryo viloyati", "Сирдарё вилояти", "Сырдарьинская область",
    ),
    "33.2137": (
        "Toshkent shahri", "Тошкент шаҳри", "город Ташкент", "Ташкент",
    ),
    "33.2152": (
        "Toshkent viloyati", "Тошкент вилояти", "Ташкентская область",
    ),
    "33.2466": (
        "Farg‘ona viloyati", "Farg'ona viloyati", "Фарғона вилояти", "Ферганская область",
    ),
    "33.2890": (
        "Xorazm viloyati", "Хоразм вилояти", "Хорезмская область",
    ),
    "33.3081": (
        "Qoraqalpog‘iston Respublikasi", "Qoraqalpog'iston Respublikasi",
        "Қорақалпоғистон Республикаси", "Республика Каракалпакстан",
    ),
}

# SAVDO TURI: UzEx TypeId -> bizning kanonik `tender.type` qiymati.
# xt-xarid ham xuddi shu atamalarni beradi ('tender' / 'selection'), shuning
# uchun ikkala platformada tur bo'yicha filtr bir xil ishlaydi.
TYPE_BY_ID: Dict[int, str] = {
    1: "selection",   # "Eng yaxshi takliflarni tanlash"
    2: "tender",      # klassik tender
}
DEFAULT_TYPE = "tender"   # noma'lum TypeId uchun xavfsiz zaxira

# Muddat birligini kunga o'girish — O'ZAK bo'yicha, aniq moslik bo'yicha EMAS.
#
# NEGA O'ZAK: manba birlik nomini KELISHIKDA qaytaradi. O'lchangan qiymatlar
# (2551 pozitsiya): "Дней", "Месяцев", "Год (лет)" — bosh kelishikdagi
# "день"/"месяц"/"год" HECH QACHON kelmaydi. Aniq moslikda "Месяцев" jadvaldan
# topilmay ×1 bo'lib qolardi va 12 oylik kafolat 12 KUN bo'lib saqlanardi
# (2551 pozitsiyaning 913 tasi — 36%).
#
# TARTIB MUHIM: uzunroq o'zak oldin tekshiriladi, aks holda qisqasi uni
# yutib yuborardi.
PERIOD_STEMS = (
    ("недел", 7), ("hafta", 7), ("apta", 7),
    ("месяц", 30), ("мес", 30), ("oy", 30), ("ой", 30), ("month", 30),
    ("год", 365), ("лет", 365), ("йил", 365), ("yil", 365), ("year", 365),
    ("дн", 1), ("ден", 1), ("кун", 1), ("kun", 1), ("day", 1),
)


def period_mult(period_name: Optional[str]) -> int:
    """Birlik nomi -> kunlar soni. Tanilmasa 1 (ya'ni qiymat kunda deb olinadi)."""
    s = (period_name or "").strip().lower()
    if not s:
        return 1
    for stem, days in PERIOD_STEMS:
        if s.startswith(stem):
            return days
    return 1


# ---------------------------------------------------------------------------
#: Qayta urinish hisoblagichi va to'xtash so'rovi `main()` da
#: o'rnatiladi. Modul darajasida turishi HTTP funksiyalarini
#: imzosini o'zgartirmasdan metrikaga ulash uchun.
_HISOB: Optional[Any] = None
_TOXTATGICH: Optional[ish.Toxtatgich] = None


def _qayta_urinish_hisobi() -> None:
    if _HISOB is not None:
        _HISOB.oldinga(retried=1)


def _toxtaymi() -> bool:
    return _TOXTATGICH.toxtaymi() if _TOXTATGICH is not None else False


def post(path: str, body: dict) -> Any:
    """POST + tasniflangan qayta urinish. 4xx da DARHOL yiqiladi."""
    def _ish():
        return ish.javob_json(
            sessiya().post(f"{API}{path}", json=body, timeout=TIMEOUT))
    return ish.qayta_urin(_ish, nom=f"POST {path}",
                          ogohlantir=lambda m: print(f"  ! {m}", file=sys.stderr),
                          hisob=_qayta_urinish_hisobi, toxtash=_toxtaymi)


def get(path: str) -> Any:
    """GET + tasniflangan qayta urinish."""
    def _ish():
        return ish.javob_json(sessiya().get(f"{API}{path}", timeout=TIMEOUT))
    return ish.qayta_urin(_ish, nom=f"GET {path}",
                          ogohlantir=lambda m: print(f"  ! {m}", file=sys.stderr),
                          hisob=_qayta_urinish_hisobi, toxtash=_toxtaymi)


def jparse(v: Any) -> Any:
    """UzEx ba'zi maydonlarni JSON-STRING sifatida qaytaradi."""
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:  # noqa: BLE001
            return None
    return v


def to_days(term: Any, period_name: Optional[str]) -> Optional[int]:
    """Muddatni kunga o'giradi: Guarantee_Term=1 + 'Год (лет)' -> 365 kun.

    DIQQAT — `Term_Period_Name` FAQAT KAFOLATGA tegishli, yetkazishga EMAS.
    UzEx pozitsiyasida bitta `Term_Period_Name` maydoni bor, lekin u ikkala
    muddatning birligi emas. O'lchangan dalil (2551 pozitsiya):

        Term_Period_Name | Delivery_Term xom | Guarantee_Term xom
        Дней             | median 30         | median 3
        Месяцев          | median 22         | median 12
        Год (лет)        | median 15         | median 1

    Delivery_Term medianasi uch guruhda ham bir xil darajada — ya'ni u
    DOIM KUNDA. Guarantee_Term esa guruhga qarab o'zgaradi (3 kun / 12 oy /
    1 yil) — birlik aynan unga tegishli.

    Shuning uchun yetkazish uchun bu funksiya `period_name=None` bilan
    chaqiriladi. Ilgari ikkalasiga ham bir xil birlik berilgan edi va
    "7 kun" -> "7 yil" (2555 kun) bo'lib ketardi: 2551 pozitsiyaning
    934 tasi (37%) shu sababdan buzilgan edi.
    """
    if term in (None, ""):
        return None
    try:
        n = float(term)
    except (TypeError, ValueError):
        return None
    return int(round(n * period_mult(period_name)))


def _region_key(name: Optional[str]) -> str:
    """Hudud nomini taqqoslash uchun yumshoq normalizatsiya qiladi."""
    return " ".join((name or "").replace("\xa0", " ").strip().casefold().split()) \
        .replace("`", "‘").replace("'", "‘").replace("ʻ", "‘")


def region_for(*names: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Lotin/kirill/rus nomlaridan kanonik viloyat kodini topadi.

    Birinchi nom odatda TradeList'dan; u bo'sh bo'lsa detail ichidagi
    `delivering_region_name` zaxira bo'ladi.
    """
    keys = {_region_key(name) for name in names if _region_key(name)}
    for code, aliases in REGION_ALIASES.items():
        if any(_region_key(alias) in keys for alias in aliases):
            return code, code
    return None, None


# ---------------------------------------------------------------------------
# Yig'ish
# ---------------------------------------------------------------------------
def fetch_list(type_id: int) -> List[dict]:
    """TradeList — From/To offset-diapazon bilan sahifalaydi.

    NATIJA `id` BO'YICHA TAKRORSIZ. Manba OFFSET bilan sahifalaydi va
    ro'yxatni yangisi birinchi tartibida beradi: sahifalar orasida
    yangi savdo e'lon qilinsa chegaradagi yozuv KEYINGI sahifada YANA
    keladi. `etl_tenders.py` da aynan shu takror butun yurishni
    `CardinalityViolation` bilan yiqitgan edi — bu yerda ham
    oldini olamiz.
    """
    out: List[dict] = []
    frm = 1
    while True:
        batch = post("/common/TradeList",
                     {"TypeId": type_id, "From": frm, "To": frm + PAGE - 1,
                      "System_Id": 0})
        if not batch:
            break
        out.extend(batch)
        total = batch[0].get("total_count") or 0
        print(f"  sahifa {frm}-{frm + PAGE - 1}: {len(batch)} ta "
              f"(jami {len(out)}/{total})")
        if len(out) >= total or len(batch) < PAGE:
            break
        if _toxtaymi():
            print("  ! to'xtash so'raldi — sahifalash uzildi", file=sys.stderr)
            break
        frm += PAGE
        time.sleep(REQUEST_DELAY)

    takrorsiz: Dict[Any, dict] = {}
    for r in out:
        takrorsiz[r.get("id")] = r
    tashlandi = len(out) - len(takrorsiz)
    if tashlandi:
        print(f"  ! sahifalash takrori: {tashlandi} ta yozuv bir necha "
              f"sahifada kelgan (id bo'yicha birlashtirildi)")
    return list(takrorsiz.values())


def saqlangan_listlar(conn, idlar: List[int]) -> Dict[int, Dict[str, Any]]:
    """Bizda saqlangan `raw_json->'list'` qatorlarini o'qiydi.

    INKREMENTALNING VA TIKLASHNING ASOSI. `raw_json` da manbadan
    kelgan TO'LIQ list-qatori saqlanadi (`transform()` shunday yozadi),
    shuning uchun uni yangisi bilan solishtirib `GetTrade` chaqirish
    kerakmi-yo'qmi hal qilamiz.
    """
    if conn is None or not idlar:
        return {}
    natija: Dict[int, Dict[str, Any]] = {}
    with conn.cursor() as cur:
        cur.execute("SELECT id, raw_json FROM tender WHERE id = ANY(%s)", (idlar,))
        for tid, xom in cur.fetchall():
            natija[int(tid)] = ish.json_yukla(xom).get("list") or {}
    return natija


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------
def scan_documents(detail: dict, tender_id: int) -> List[dict]:
    """Fayl guruhlarini UMUMIY tarzda topadi: '<prefiks>_path' + _name/_ext/_sizes.
    Nom bo'yicha qattiq yozmaymiz — yangi guruh qo'shilsa ham o'zi topiladi."""
    docs = []
    for key, val in detail.items():
        if not key.endswith("_path") or not val:
            continue
        pref = key[:-5]
        ext = (detail.get(f"{pref}_ext") or "").lower() or None
        size = detail.get(f"{pref}_sizes")
        docs.append({
            "tender_id": tender_id,
            "file_ref": str(val),          # UzEx'da kalit = yo'l (uuid yo'q)
            "file_id": None,
            "file_path": str(val),
            "name": detail.get(f"{pref}_name") or str(val).rsplit("/", 1)[-1],
            "size_bytes": int(size) if size else None,
            "content_type": None,
            "file_type": ext,
            "field_key": pref,
            "field_path": key,
            "source_platform": SOURCE,
        })
    return docs


def transform(row: dict, detail: dict, type_id: int = 2) -> dict:
    src_id = int(row["id"])
    tid = UZEX_OFFSET + src_id
    area_path, area_leaf = region_for(
        row.get("region_name"), detail.get("delivering_region_name"))

    bp = jparse(detail.get("budget_products")) or []

    tender = {
        "id": tid, "source_id": src_id, "source_platform": SOURCE,
        # Tur TypeId dan olinadi (ilgari "tender" qattiq yozilgan edi)
        "type": TYPE_BY_ID.get(type_id, DEFAULT_TYPE),
        "name": row.get("name") or detail.get("display_no"),
        "status": "open",                       # TradeList faqat faollarni beradi
        "totalcost": detail.get("start_cost") or row.get("cost"),
        "currency": row.get("currency_codeabc"),
        "lang": None,
        "area_path": area_path, "area_leaf_id": area_leaf,
        "buyer_org_id": row.get("seller_id"),   # UzEx: sotuvchi = buyurtmachi
        "company_name": (row.get("seller_name") or detail.get("customer_name") or "").strip() or None,
        "publicated_at": row.get("start_date"),
        "close_at": row.get("end_date"),
        "created_at": row.get("start_date"),
        "lot_count": 1,                         # UzEx: butun savdo = 1 lot
        "good_count": len(bp),
        "raw_json": json.dumps({"list": row, "detail": detail}, ensure_ascii=False),
    }

    # Bitta lot — sarlavhasi tender nomi
    lot = {"tender_id": tid, "lot_id": 1, "title": row.get("name"),
           "item_count": len(bp),
           "total_sum_lot": detail.get("start_cost") or row.get("cost")}

    goods, items = [], []
    for p in bp:
        code = p.get("Product_Code") or str(p.get("Product_Id"))
        unit = None
        for pr in (p.get("Js_Properties") or []):
            if "измерения" in str(pr.get("Property_Name", "")).lower():
                unit = pr.get("User_Value")
        goods.append({
            "tender_id": tid, "lot_id": 1, "good_code": code,
            "name": p.get("Product_Name"), "unit": unit,
            "amount": p.get("Quantity"), "price": p.get("Price"),
            "totalcost_item": p.get("Cost"), "category_uid": None,
        })
        items.append({
            "tender_id": tid, "lot_id": 1, "item_id": str(p.get("Id")),
            "product_code": code, "name": p.get("Product_Name"), "unit": unit,
            "amount_text": f"{p.get('Quantity')} {unit or ''}".strip(),
            "price_text": str(p.get("Price")),
            "totalcost_text": str(p.get("Cost")),
            # Yetkazish DOIM kunda — birlik berilmaydi (izohga qarang).
            "delivery_period": to_days(p.get("Delivery_Term"), None),
            # Kafolat — `Term_Period_Name` aynan shu maydonning birligi.
            "guarantee": to_days(p.get("Guarantee_Term"), p.get("Term_Period_Name")),
            "prod_year": None,
            "country_of_origin": None,
            "delivery_address": detail.get("delivering_region_name"),
            "spec": p.get("Description"),
            "properties": json.dumps(p.get("Js_Properties") or [], ensure_ascii=False),
            "raw_json": json.dumps(p, ensure_ascii=False),
        })

    docs = scan_documents(detail, tid)
    contacts = jparse(detail.get("contacts")) or []
    det = {
        "tender_id": tid,
        "anno": detail.get("description"),
        "method_marks": detail.get("valuation_name"),
        "company_details": detail.get("customer_name"),
        "director": (contacts[0].get("Fullname") if contacts else None),
        "close_time": detail.get("end_date"),
        "proc_lang": None,
        "offer_period": str(detail.get("term_online_days") or "") or None,
        "doc_count": len(docs),
        "raw_json": json.dumps(detail, ensure_ascii=False),
    }
    return {"tender": tender, "lot": lot, "goods": goods,
            "items": items, "docs": docs, "detail": det}


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
T_COLS = ["id", "source_id", "source_platform", "type", "name", "status",
          "totalcost", "currency", "lang", "area_path", "area_leaf_id",
          "buyer_org_id", "company_name", "publicated_at", "close_at",
          "created_at", "lot_count", "good_count", "raw_json"]
D_COLS = ["tender_id", "anno", "method_marks", "company_details", "director",
          "close_time", "proc_lang", "offer_period", "doc_count", "raw_json"]
DOC_COLS = ["tender_id", "file_ref", "file_id", "file_path", "name",
            "size_bytes", "content_type", "file_type", "field_key",
            "field_path", "source_platform"]
I_COLS = ["tender_id", "lot_id", "item_id", "product_code", "name", "unit",
          "amount_text", "price_text", "totalcost_text", "delivery_period",
          "guarantee", "prod_year", "country_of_origin", "delivery_address",
          "spec", "properties", "raw_json"]


def save(conn, rec: dict) -> None:
    t = rec["tender"]
    tid = t["id"]
    with conn.cursor() as cur:
        cur.execute(
            f"""INSERT INTO tender ({",".join(T_COLS)})
                VALUES ({",".join("%s" for _ in T_COLS)})
                ON CONFLICT (id) DO UPDATE SET
                {",".join(f"{c}=EXCLUDED.{c}" for c in T_COLS if c != "id")},
                fetched_at=now()""",
            [t[c] for c in T_COLS])

        cur.execute("DELETE FROM tender_good WHERE tender_id=%s", (tid,))
        cur.execute("DELETE FROM tender_item WHERE tender_id=%s", (tid,))
        cur.execute("DELETE FROM tender_lot  WHERE tender_id=%s", (tid,))
        l = rec["lot"]
        cur.execute("""INSERT INTO tender_lot (tender_id, lot_id, title, item_count, total_sum_lot)
                       VALUES (%s,%s,%s,%s,%s)""",
                    (l["tender_id"], l["lot_id"], l["title"], l["item_count"],
                     l["total_sum_lot"]))
        if rec["goods"]:
            execute_values(cur,
                """INSERT INTO tender_good (tender_id, lot_id, good_code, name, unit,
                   amount, price, totalcost_item, category_uid) VALUES %s
                   ON CONFLICT DO NOTHING""",
                [(g["tender_id"], g["lot_id"], g["good_code"], g["name"], g["unit"],
                  g["amount"], g["price"], g["totalcost_item"], g["category_uid"])
                 for g in rec["goods"]])
        if rec["items"]:
            execute_values(cur,
                f"INSERT INTO tender_item ({','.join(I_COLS)}) VALUES %s "
                "ON CONFLICT DO NOTHING",
                [tuple(i[c] for c in I_COLS) for i in rec["items"]])

        cur.execute(
            f"""INSERT INTO tender_detail ({",".join(D_COLS)})
                VALUES ({",".join("%s" for _ in D_COLS)})
                ON CONFLICT (tender_id) DO UPDATE SET
                {",".join(f"{c}=EXCLUDED.{c}" for c in D_COLS if c != "tender_id")},
                fetched_at=now()""",
            [rec["detail"][c] for c in D_COLS])

        # PK = (tender_id, file_ref). UzEx da `file_ref` — fayl YO'LI va
        # ikki xil maydon guruhi (`anno_path`, `proc_path`) BIR XIL yo'lni
        # ko'rsatishi mumkin. Ilgari bunday tender `duplicate key` bilan
        # yiqilardi va butun yozuv saqlanmasdi. Endi takror olib
        # tashlanadi — yo'qolgan narsa yo'q, chunki qator AYNI bir xil.
        docs = {d["file_ref"]: d for d in rec["docs"]}
        if len(docs) != len(rec["docs"]):
            print(f"    ! #{tid}: {len(rec['docs']) - len(docs)} ta takror "
                  f"hujjat yo'li birlashtirildi", file=sys.stderr)

        # DELETE + INSERT EMAS — UPSERT.
        #
        # O'LCHANGAN NUQSON (2026-08-30): ilgari bu yerda
        # `DELETE FROM tender_document WHERE tender_id=%s` turardi.
        # Ikki oqibati bor edi:
        #
        #   1. Manba faylni ro'yxatdan chiqarsa (yoki `file_ref`
        #      o'zgarsa) metadata qatori YO'QOLARDI, lekin
        #      `tender_document_text` (FK yo'q) QOLARDI. Natijada
        #      MUVAFFAQIYATLI AJRATILGAN matn hech qanday JOIN da
        #      ko'rinmasdi — o'lchangan: 392 yetim qator, 391 tasi `ok`.
        #
        #   2. Qayta ishlash HOLATI (`holat`, vaqt belgilari, urinish
        #      soni) HAR SOATLIK ETL YURISHIDA o'chib ketardi.
        #
        # Endi qator SAQLANADI va manbada yo'q bo'lgani ALOHIDA
        # belgilanadi (`manbadan_yoqoldi`) — o'chirilmaydi.
        if docs:
            execute_values(cur,
                f"INSERT INTO tender_document ({','.join(DOC_COLS)}) VALUES %s "
                "ON CONFLICT (tender_id, file_ref) DO UPDATE SET "
                + ",".join(f"{c}=EXCLUDED.{c}" for c in DOC_COLS
                           if c not in ("tender_id", "file_ref"))
                + ", fetched_at = now()"
                # Manbaga QAYTGAN hujjat yana navbatga tushadi.
                + ", manbadan_yoqoldi_at = NULL"
                + ", holat = CASE WHEN tender_document.holat = 'manbadan_yoqoldi' "
                  "              THEN 'navbatda' ELSE tender_document.holat END",
                [tuple(d[c] for c in DOC_COLS) for d in docs.values()])

        # Manbada BOSHQA YO'Q hujjatlar — O'CHIRILMAYDI, BELGILANADI.
        # `discovered_at`, `holat` va ajratilgan matn saqlanib qoladi.
        cur.execute(
            "UPDATE tender_document SET holat='manbadan_yoqoldi', "
            "       manbadan_yoqoldi_at = COALESCE(manbadan_yoqoldi_at, now()) "
            "WHERE tender_id = %s AND holat <> 'manbadan_yoqoldi' "
            "  AND NOT (file_ref = ANY(%s))",
            (tid, list(docs.keys()) or [""]))
    conn.commit()


def sync_region_names(conn) -> None:
    """BONUS: UzEx lotincha o'zbekcha nomlarni beradi — dim_area.name_uz ni
    to'ldiramiz (u shu paytgacha bo'sh edi)."""
    with conn.cursor() as cur:
        for _uid, (code, uz) in REGION_MAP.items():
            cur.execute("UPDATE dim_area SET name_uz=%s WHERE area_id=%s AND name_uz IS NULL",
                        (uz, code))
    conn.commit()


def backfill_regions(conn) -> Tuple[int, int]:
    """Eski UzEx yozuvlarining hududini saqlangan xom javobdan tiklaydi.

    Adapterdagi aliaslar tuzatilishidan oldin yozilgan tenderlar qayta ETL
    qilinmaguncha NULL bo'lib qolmasligi uchun. Faqat hududi bo'sh UzEx
    yozuvlariga tegadi; qo'lda yoki boshqa manbadan kelgan qiymatni
    almashtirmaydi. Natija: (tekshirilgan, yangilangan).
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, raw_json
            FROM tender
            WHERE source_platform = %s
              AND (area_path IS NULL OR area_leaf_id IS NULL)
        """, (SOURCE,))
        rows = cur.fetchall()

    updates = []
    for tender_id, raw in rows:
        try:
            payload = json.loads(raw) if isinstance(raw, str) else (raw or {})
            list_row = payload.get("list") or {}
            detail = payload.get("detail") or {}
            area_path, area_leaf = region_for(
                list_row.get("region_name"),
                detail.get("delivering_region_name"),
            )
        except (TypeError, ValueError, AttributeError):
            continue
        if area_path:
            updates.append((area_path, area_leaf, tender_id))

    if updates:
        with conn.cursor() as cur:
            cur.executemany("""
                UPDATE tender
                SET area_path = %s, area_leaf_id = %s
                WHERE id = %s AND source_platform = 'uzex'
                  AND (area_path IS NULL OR area_leaf_id IS NULL)
            """, updates)
    conn.commit()
    return len(rows), len(updates)


# ---------------------------------------------------------------------------
#: Chiqish kodlari — ota-jarayon (`run_etl.py`) shularga qarab
#: `etl_run.status` ni qo'yadi. ATAYLAB 0/1 dan boshqa:
#:   0  to'liq tugadi
#:   7  QISMAN tugadi (vaqt byudjeti / to'xtash so'rovi) — checkpoint bor
#:   8  BAND (boshqa yurish shu oqimni olib turibdi yoki backoff oynasi)
#:   1  haqiqiy xato
CHIQISH_TUGADI  = 0
CHIQISH_QISMAN  = 7
CHIQISH_BAND    = 8
CHIQISH_XATO    = 1


def main() -> None:
    ish.chiqishni_sozla()
    global _HISOB, _TOXTATGICH

    ap = argparse.ArgumentParser(description="etender.uzex.uz adapteri")
    ap.add_argument("--type-id", type=int, default=2,
                    help="2=Tender (default), 1=Eng yaxshi takliflarni tanlash")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--dsn", default=os.environ.get("XT_DB_DSN"))
    ap.add_argument("--max-seconds", type=float, default=STANDART_BYUDJET,
                    help="Vaqt byudjeti. Tugaganda checkpoint yozib TOZA "
                         "to'xtaydi (0 = cheksiz)")
    ap.add_argument("--full", action="store_true",
                    help="Inkrementalni o'chiradi: o'zgarmagan savdolar ham "
                         "qayta olinadi (haftalik to'liq yangilash uchun)")
    ap.add_argument("--no-checkpoint", action="store_true",
                    help="Checkpoint o'qilmaydi/yozilmaydi (sinov uchun)")
    args = ap.parse_args()

    oqim = f"type={args.type_id}"
    ttype = TYPE_BY_ID.get(args.type_id, DEFAULT_TYPE)

    _TOXTATGICH = ish.Toxtatgich(args.max_seconds or None)
    _TOXTATGICH.signallarni_ulash()

    yozuvchi = ish.BazaYozuvchi(args.dsn)
    yurish = ish.Yurish(yozuvchi)
    _HISOB = yurish
    kp_faol = not (args.no_checkpoint or args.dry_run)
    kp = ish.Checkpoint(yozuvchi, SOURCE, oqim, faol=kp_faol)
    sabab = "tugadi"
    chiqish = CHIQISH_TUGADI

    # --- USTMA-UST YURISHDAN HIMOYA -----------------------------------
    # Qulf OQIM darajasida: TypeId=1 va TypeId=2 bir vaqtda yurishi
    # MUMKIN emas edi (bir host), lekin ular ketma-ket chaqiriladi.
    # Bu yerdagi qulf BOSHQA VAZIFA (RAG) yoki qo'lda yurgizishdan
    # himoya qiladi — Task Scheduler ning IgnoreNew si vazifalar
    # ORASIDA ishlamaydi.
    qulf = ish.Qulf(f"etl:{SOURCE}", args.dsn) if not args.dry_run else None
    if qulf is not None and not qulf.ol():
        print(f"[BAND] {SOURCE} allaqachon yig'ilmoqda — bu yurish "
              f"o'tkazib yuborildi (manbaga ikki barobar so'rov yubormaymiz).")
        yurish.sabab_yoz("band")
        yozuvchi.yop()
        sys.exit(CHIQISH_BAND)

    try:
        # --- MANBA BACKOFF OYNASI -------------------------------------
        band, nega = kp.band_mi()
        if band:
            print(f"[BAND] {oqim}: {nega}. Yurish o'tkazib yuborildi.")
            yurish.sabab_yoz("band")
            sys.exit(CHIQISH_BAND)

        print(f"[1/3] TradeList (TypeId={args.type_id} -> type='{ttype}') yig'ilyapti...")
        try:
            rows = fetch_list(args.type_id)
        except ish.ManbaXato as e:
            # RO'YXAT OLINMASA ish yo'q. Bu OQIM darajasidagi xato:
            # keyingi urinish vaqtini yozamiz va CHIQAMIZ.
            kutish = ish.STANDART_SIYOSAT.kutish(1)
            kp.xato_yoz(f"TradeList: {e}", kutish)
            print(f"[XATO] TradeList olinmadi: {e}", file=sys.stderr)
            yurish.sabab_yoz("manba_xato")
            sys.exit(CHIQISH_XATO)

        if args.limit:
            rows = rows[:args.limit]
        print(f"[1/3] {len(rows)} ta savdo.\n")

        conn = None
        if not args.dry_run:
            if not args.dsn:
                sys.exit("XATO: DSN yo'q.")
            if psycopg2 is None:
                sys.exit("XATO: pip install psycopg2-binary")
            conn = psycopg2.connect(args.dsn)
            sync_region_names(conn)
            checked, filled = backfill_regions(conn)
            if checked:
                print(f"[i] Eski UzEx hududlari: {filled}/{checked} ta tiklandi.")

        # --- INKREMENTAL: nimani olish KERAK? -------------------------
        #
        # BU BIR VAQTNING O'ZIDA TIKLASH MEXANIZMI HAM. Oldingi yurishda
        # saqlangan savdo `raw_json->'list'` da o'z qatorini saqlaydi;
        # u manbadagi qator bilan bir xil bo'lsa `GetTrade` chaqirilmaydi.
        # Ya'ni uzilgan yurish keyingi safar TABIIY ravishda qolgan
        # joydan davom etadi — indeksga tayanmasdan, ro'yxat qayta
        # tartiblansa ham to'g'ri.
        eski = {}
        if conn is not None and not args.full:
            eski = saqlangan_listlar(conn, [UZEX_OFFSET + int(r["id"]) for r in rows])

        ish_royxati: List[dict] = []
        otkazildi = 0
        for r in rows:
            if args.full or ish.ozgardimi(eski.get(UZEX_OFFSET + int(r["id"])),
                                          r, KUZATILADIGAN):
                ish_royxati.append(r)
            else:
                otkazildi += 1
        if otkazildi:
            yurish.oldinga(processed=otkazildi, skipped=otkazildi)
            print(f"[i] {otkazildi} ta savdo o'zgarmagan — GetTrade "
                  f"chaqirilmaydi ({otkazildi}/{len(rows)}).")

        # --- CHECKPOINT: qayerdan davom etamiz? -----------------------
        kalit = ish.ish_kaliti(r["id"] for r in ish_royxati)
        # `boshla()` HAR DOIM chaqiriladi, ish ro'yxati bo'sh bo'lsa ham:
        # oqim jurnalda RO'YXATDAN O'TSIN. Aks holda "hech qachon
        # yurmagan oqim" va "yurib, qiladigan ishi bo'lmagan oqim"
        # bir xil ko'rinardi — ikkalasi ham bo'sh jadval.
        boshlanish = kp.boshla(len(ish_royxati), kalit)
        if boshlanish:
            yurish.oldinga(resumed=boshlanish)
            print(f"[i] CHECKPOINT: {boshlanish}/{len(ish_royxati)} "
                  f"dan davom etamiz (oldingi yurish uzilgan).")

        byudjet = _TOXTATGICH.qolgan()
        print(f"[2/3] Tafsilotlar (GetTrade): {len(ish_royxati)} ta olinadi"
              + (f", byudjet {byudjet:.0f}s" if byudjet else "") + "...")

        ok = failed = ndocs = nitems = 0
        jami = len(ish_royxati)
        i = boshlanish
        while i < jami:
            if _TOXTATGICH.toxtaymi():
                sabab = _TOXTATGICH.sabab or "toxtatildi"
                chiqish = CHIQISH_QISMAN
                print(f"\n[!] TO'XTASH ({sabab}): {i}/{jami} da to'xtadik, "
                      f"checkpoint yozildi. Keyingi yurish shu yerdan davom etadi.")
                break

            row = ish_royxati[i]
            i += 1
            src_id = row.get("id")

            # BITTA YOZUV BUTUN PAKETNI YIQITMAYDI. Manba xatosi ham,
            # transform xatosi ham, baza xatosi ham SHU YOZUVDA qoladi.
            try:
                detail = get(f"/common/GetTrade/{src_id}/0")
                rec = transform(row, detail, args.type_id)
            except ish.ManbaXato as e:
                failed += 1
                yurish.oldinga(processed=1, failed=1)
                print(f"  [{i}/{jami}] #{src_id} — MANBA XATO: {str(e)[:80]}")
                kp.siljit(i, majburan=False)
                time.sleep(REQUEST_DELAY)
                continue
            except Exception as e:                           # noqa: BLE001
                # Transform xatosi (kutilmagan maydon shakli). Yozuv
                # tashlanadi, yurish DAVOM ETADI.
                failed += 1
                yurish.oldinga(processed=1, failed=1)
                print(f"  [{i}/{jami}] #{src_id} — BUZUQ YOZUV: "
                      f"{type(e).__name__}: {str(e)[:70]}", file=sys.stderr)
                kp.siljit(i, majburan=False)
                time.sleep(REQUEST_DELAY)
                continue

            yozildi = True
            if conn:
                try:
                    save(conn, rec)
                except Exception as e:                       # noqa: BLE001
                    conn.rollback()
                    yozildi = False
                    failed += 1
                    yurish.oldinga(processed=1, failed=1)
                    print(f"    ! #{src_id} DB xato: {str(e)[:110]}", file=sys.stderr)

            if yozildi:
                ndocs += len(rec["docs"]); nitems += len(rec["items"]); ok += 1
                yurish.oldinga(processed=1, succeeded=1)
                print(f"  [{i}/{jami}] #{src_id} -> {rec['tender']['id']} | "
                      f"{len(rec['items'])} pozitsiya, {len(rec['docs'])} hujjat | "
                      f"{(rec['tender']['name'] or '')[:40]}")

            # Checkpoint FAQAT muvaffaqiyatli yozuvdan keyin `oxirgi_id`
            # ni yangilaydi: "oxirgi muvaffaqiyatli tashqi ID" aynan
            # shuni anglatishi kerak.
            kp.siljit(i, oxirgi_id=src_id if yozildi else None)
            yurish.puls()
            time.sleep(REQUEST_DELAY)
        else:
            # Halqa to'liq aylandi — oqim tugadi.
            kp.tugat()

        if conn:
            conn.close()

        yurish.checkpoint_yoz(dict(kp.holat.dict(), oqim=oqim))
        yurish.sabab_yoz(sabab)
        print(f"\n[3/3] {sabab.upper()}. OK: {ok}, xato: {failed}, "
              f"o'tkazildi: {otkazildi}, pozitsiya: {nitems}, hujjat: {ndocs}")
        print(f"      Metrika: {yurish.xulosa()}")
        if yozuvchi.baza_xatolari:
            print(f"      [!] metrika bazasiga {len(yozuvchi.baza_xatolari)} ta "
                  f"yozuv bajarilmadi: {yozuvchi.baza_xatolari[-1]}", file=sys.stderr)

        # Yozuvlar YIQILGAN bo'lsa yurish "tugadi" deb ko'rsatilmaydi.
        # Jimgina o'tkazib yuborish shu loyihada takroriy nuqson.
        if failed and chiqish == CHIQISH_TUGADI:
            print(f"      [!] {failed} ta yozuv yiqildi — chiqish kodi QISMAN.")
            chiqish = CHIQISH_QISMAN
    finally:
        if qulf is not None:
            qulf.qoyver()
        yozuvchi.yop()

    sys.exit(chiqish)


if __name__ == "__main__":
    main()
