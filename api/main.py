"""
xt-xarid tender aggregator — Backend API (3-bosqich)
====================================================
O'z bazamizdan (PostgreSQL 'xtxarid') dashboardga ma'lumot beruvchi API.
Manba API'ga to'g'ridan-to'g'ri ulanmaydi (arxitektura tamoyili).

Ishga tushirish:
    cp .env.example .env          # va parolni to'ldiring
    .venv/bin/pip install -r requirements-api.txt
    .venv/bin/uvicorn api.main:app --reload --port 8000
    # Swagger (sinov uchun): http://localhost:8000/docs

Endpointlar:
    GET /tenders            — filtrlanadigan ro'yxat (X-Total-Count header bilan)
    GET /tenders/{id}       — bitta tender + lotlar + tovarlar
    GET /stats             — dashboard umumiy ko'rsatkichlari
    GET /regions           — hudud dropdown
    GET /statuses          — status dropdown
    GET /health            — sog'liq tekshiruvi
"""
import os
import re
from contextlib import asynccontextmanager
from typing import List, Optional
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel

load_dotenv()  # .env ni import paytida yuklaymiz (pool DSN'ni ko'rishi uchun)

from api import ai, db, matching, queries  # noqa: E402  (load_dotenv dan keyin bo'lishi shart)


# ---------------------------------------------------------------------------
# So'rov modellari (aqlli moslashtirish)
# ---------------------------------------------------------------------------
class ProfileIn(BaseModel):
    name: Optional[str] = None
    keywords: List[str] = []
    regions: List[str] = []
    currency: Optional[str] = None
    min_cost: Optional[float] = None
    max_cost: Optional[float] = None


class SavedSearchIn(BaseModel):
    name: str
    keywords: List[str] = []
    categories: List[str] = []      # B bosqich (kategoriya) uchun tayyor
    regions: List[str] = []
    currency: Optional[str] = None
    min_cost: Optional[float] = None
    max_cost: Optional[float] = None
    notify: bool = True


class CatalogItemIn(BaseModel):
    name: str
    category_code: Optional[str] = None
    keywords: List[str] = []
    unit: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    notify: bool = True


class CatalogMatchIn(BaseModel):
    region: Optional[str] = None
    currency: Optional[str] = None
    limit: int = 20
    offset: int = 0


class MatchIn(BaseModel):
    profile: ProfileIn
    # Qattiq filtrlar (profildan ALOHIDA — profil faqat skorlaydi, filtrlamaydi)
    status: Optional[str] = "open"
    region: Optional[str] = None
    currency: Optional[str] = None
    q: Optional[str] = None
    category: Optional[str] = None
    limit: int = 20
    offset: int = 0


# ---------------------------------------------------------------------------
# Lifespan — pool init/close
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_pool()
    yield
    db.close_pool()


app = FastAPI(
    title="xt-xarid Tender Aggregator API",
    version="0.1.0",
    description="O'zbekiston davlat xaridlari agregatori — backend API (3-bosqich).",
    lifespan=lifespan,
)

# CORS — .env dagi CORS_ORIGINS bo'sh bo'lmasa yoqiladi (frontend ulanganда)
_cors = os.environ.get("CORS_ORIGINS", "").strip()
if _cors:
    from fastapi.middleware.cors import CORSMiddleware

    origins = ["*"] if _cors == "*" else [o.strip() for o in _cors.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET"],
        allow_headers=["*"],
    )


# DB mavjud emasligini 503 ga aylantiramiz
@app.exception_handler(db.DBUnavailable)
async def _db_unavailable_handler(request, exc: db.DBUnavailable):
    return JSONResponse(
        status_code=503,
        content={"error": "database_unavailable", "detail": str(exc)},
    )


# ---------------------------------------------------------------------------
# Javob shakllantiruvchi yordamchilar
# ---------------------------------------------------------------------------
def _shape_tender(r: dict) -> dict:
    """Xom qatorni toza, ichma-ich (nested) JSON obyektiga aylantiradi."""
    return {
        "id": r["id"],
        # Manbadagi asl ID — rasmiy sahifa havolasini qurish uchun
        # (bizning id global: source_id + platforma ofseti)
        "source_id": r.get("source_id"),
        "type": r["type"],
        "name": r["name"],
        "status": r["status"],
        "status_name": r.get("status_name_uz") or r.get("status_name_ru"),
        "status_name_ru": r.get("status_name_ru"),
        "status_name_uz": r.get("status_name_uz"),
        "is_terminal": r.get("is_terminal"),
        "totalcost": _num(r.get("totalcost")),
        "currency": r.get("currency"),
        "region": {
            "id": r.get("area_leaf_id"),
            "name": r.get("region_name_uz") or r.get("region_name_ru"),
            "name_ru": r.get("region_name_ru"),
            "name_uz": r.get("region_name_uz"),
            "path": r.get("area_path"),
        },
        "company": {"id": r.get("company_id"), "name": r.get("company_name")},
        "lot_count": r.get("lot_count"),
        "good_count": r.get("good_count"),
        "goods_preview": r.get("goods_preview") or [],
        "doc_count": r.get("doc_count") or 0,
        # Lotlar xulosasi — ro'yxatда qatorni ochib ko'rish uchun
        "lots_summary": [
            {
                "lot_id": l.get("lot_id"),
                "title": l.get("title"),
                "total_sum_lot": _num(l.get("total_sum_lot")),
                "item_count": l.get("item_count"),
                "delivery_period": l.get("delivery_period"),
                "guarantee": l.get("guarantee"),
            }
            for l in (r.get("lots_json") or [])
        ],
        "part_count": r.get("part_count"),
        "publicated_at": _iso(r.get("publicated_at")),
        "close_at": _iso(r.get("close_at")),
        "starting_date": _iso(r.get("starting_date")),
        "ends_at": _iso(r.get("ends_at")),
        "remain_time": r.get("remain_time"),
        "source_platform": r.get("source_platform"),
        "fetched_at": _iso(r.get("fetched_at")),
        "first_seen_at": _iso(r.get("first_seen_at")),
    }


# Fayl yuklab olish manzili.
#   xt-xarid — to'g'ridan-to'g'ri GET (brauzer o'zi yuklab oladi, trafik bizdan o'tmaydi)
#   uzex     — manba POST talab qiladi, brauzer havolasi esa GET yuboradi,
#              shuning uchun BIZNING proksi orqali o'tadi (pastdagi endpoint).
_FILE_URL = {"xt-xarid": "https://api.xt-xarid.uz/file/{file_id}"}

# To'g'ridan-to'g'ri GET bilan yuklab olinadigan manbalar: fayl yo'li shu bazaga
# ulanadi (proksi shart emas — brauzer o'zi oladi, trafik bizdan o'tmaydi).
# Hozircha bo'sh (kelajakdagi shunday manbalar uchun mexanizm qoldirildi).
_FILE_DIRECT: dict = {}

# POST talab qiluvchi manbalar — proksi orqali o'tadi (brauzer havolasi GET
# yuboradi, manba esa POST kutadi).
_POST_DOWNLOAD = {
    "uzex": "https://apietender.uzex.uz/api/common/DownloadFile",
}
# Ba'zi manbalar oddiy skript User-Agent'ini rad etadi — brauzernikini beramiz.
_BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
               "AppleWebKit/537.36 (KHTML, like Gecko) "
               "Chrome/120.0.0.0 Safari/537.36")

# Moslashtirish uchun nomzodlar chegarasi. Ballash Pythonда bo'lgani uchun
# bu SQL LIMIT — undan tashqaridagilar UMUMAN ballanmaydi. Hozirgi baza ~900
# yozuv, shuning uchun chegara undan yuqori. Cap ishga tushsa javobда
# `truncated: true` qaytadi.
MATCH_CAP = 3000

# Hujjat qaysi bo'limdan kelgani — o'qiladigan nom
_FIELD_LABELS = {
    "anno_file": "Tender asos-hujjatlari",
    "proform_file": "Shartnoma namunasi",
    "start_price_file": "Texnik topshiriq / boshlang‘ich narx",
    "load_pdf": "PDF ilova",
}


def _doc_label(field_key: Optional[str]) -> str:
    if not field_key:
        return "Boshqa hujjatlar"
    if field_key in _FIELD_LABELS:
        return _FIELD_LABELS[field_key]
    m = re.match(r"proc_custom(\d+)", field_key)
    if m:
        return f"Qo‘shimcha ma'lumot №{m.group(1)}"
    return field_key


def _shape_document(r: dict, tender_id: Optional[int] = None) -> dict:
    platform = r.get("source_platform") or "xt-xarid"
    ref = r.get("file_ref")
    if platform == "xt-xarid" and r.get("file_id"):
        url = _FILE_URL["xt-xarid"].format(file_id=r["file_id"])
    elif platform in _FILE_DIRECT and r.get("file_path"):
        # To'g'ridan-to'g'ri GET — fayl yo'li ('/storage/...') bazaga ulanadi
        url = _FILE_DIRECT[platform] + r["file_path"]
    else:
        # Proksi orqali (uzex va kelajakdagi POST-talab qiluvchi manbalar)
        url = f"/documents/{tender_id}/download?ref={quote(str(ref), safe='')}"
    return {
        "file_ref": ref,
        "file_id": str(r["file_id"]) if r.get("file_id") else None,
        "name": r.get("name"),
        "size_bytes": r.get("size_bytes"),
        "content_type": r.get("content_type"),
        "file_type": r.get("file_type"),
        "section": _doc_label(r.get("field_key")),
        "download_url": url,
    }


def _num(v):
    """Decimal -> float (JSON uchun). None o'zgarmaydi."""
    return float(v) if v is not None else None


def _iso(v):
    """datetime -> ISO string. None o'zgarmaydi."""
    return v.isoformat() if v is not None else None


# ---------------------------------------------------------------------------
# Endpointlar
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    """Baza ulanishini tekshiradi."""
    db.scalar("SELECT 1")
    return {"status": "ok"}


@app.get("/tenders")
def list_tenders(
    response: Response,
    status: Optional[str] = Query("open", description="Status kodi. Barchasi uchun bo'sh bering (?status=)."),
    region: Optional[str] = Query(None, description="Hudud kodi (istalgan daraja — leaf/viloyat/respublika)."),
    currency: Optional[str] = Query(None, description="Valyuta: UZS yoki USD."),
    source: Optional[str] = Query(None, description="Manba platforma (masalan xt-xarid)."),
    q: Optional[str] = Query(None, description="Qidiruv: tender nomi, buyurtmachi yoki tovar nomi."),
    category: Optional[str] = Query(None, description="Kategoriya kodi (parent tanlansa ichkilar ham kiradi)."),
    sort: str = Query(queries.DEFAULT_SORT, description="Saralash: close_at | publicated_at | totalcost | id. Kamayish uchun oldiga '-'."),
    limit: int = Query(51, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Ochiq (yoki filtrlangan) tenderlar ro'yxati. Umumiy soni X-Total-Count header'da."""
    status_val = status or None  # bo'sh string -> filtr yo'q
    where, params = queries.build_tender_filters(
        status=status_val, region=region, currency=currency, source=source,
        q=q, category=category,
    )
    order_by = queries.build_order_by(sort)

    total = db.scalar(queries.tenders_count_sql(where), params) or 0

    params_page = {**params, "limit": limit, "offset": offset}
    rows = db.query(queries.tenders_sql(where, order_by), params_page)

    response.headers["X-Total-Count"] = str(total)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_shape_tender(r) for r in rows],
    }


@app.get("/tenders/{tender_id}")
def get_tender(tender_id: int):
    """Bitta tender to'liq — lotlar va har lotda tovarlar bilan."""
    row = db.query_one(queries.tender_by_id_sql(), {"id": tender_id})
    if not row:
        raise HTTPException(status_code=404, detail=f"Tender {tender_id} topilmadi.")

    tender = _shape_tender(row)

    lots = db.query(queries.TENDER_LOTS_SQL, {"id": tender_id})
    goods = db.query(queries.TENDER_GOODS_SQL, {"id": tender_id})

    # Tovarlarni lot bo'yicha guruhlaymiz
    goods_by_lot: dict = {}
    for g in goods:
        goods_by_lot.setdefault(g["lot_id"], []).append({
            "good_code": g["good_code"],
            "name": g["name"],
            "unit": g["unit"],
            "amount": _num(g["amount"]),
            "price": _num(g["price"]),
            "totalcost_item": _num(g["totalcost_item"]),
            "category": (
                {"uid": str(g["category_uid"]), "code": g["category_code"],
                 "title_ru": g["category_title_ru"]}
                if g.get("category_uid") else None
            ),
        })

    # Pozitsiya tafsilotlari (get_items dan) — yetkazish/kafolat/xarakteristika
    items = db.query(queries.TENDER_ITEMS_SQL, {"id": tender_id})
    items_by_lot: dict = {}
    for it in items:
        items_by_lot.setdefault(it["lot_id"], []).append({
            "item_id": it["item_id"],
            "product_code": it["product_code"],
            "name": it["name"],
            "unit": it["unit"],
            "amount_text": it["amount_text"],
            "price_text": it["price_text"],
            "totalcost_text": it["totalcost_text"],
            "delivery_period": it["delivery_period"],
            "guarantee": it["guarantee"],
            "prod_year": it["prod_year"],
            "country_of_origin": it["country_of_origin"],
            "delivery_address": it["delivery_address"],
            "spec": it["spec"],
            "properties": it["properties"] or [],
        })

    tender["lots"] = [
        {
            "lot_id": l["lot_id"],
            "title": l.get("title"),
            "item_count": l["item_count"],
            "total_sum_lot": _num(l["total_sum_lot"]),
            "goods": goods_by_lot.get(l["lot_id"], []),
            "items": items_by_lot.get(l["lot_id"], []),
        }
        for l in lots
    ]

    # Tafsilot (get_proc dan): baholash usuli, rekvizitlar, izoh...
    det = db.query_one(queries.TENDER_DETAIL_SQL, {"id": tender_id})
    tender["detail"] = {
        "anno": det.get("anno"),
        "method_marks": det.get("method_marks"),
        "company_details": det.get("company_details"),
        "director": det.get("director"),
        "close_time": det.get("close_time"),
        "proc_lang": det.get("proc_lang"),
        "offer_period": det.get("offer_period"),
    } if det else None

    # AI TAHLILI (5a) — bo'lsa qo'shamiz, bo'lmasa null (majburiy emas)
    ai_row = db.query_one(queries.AI_ANALYSIS_SQL,
                          {"id": tender_id, "kind": ai.KIND})
    tender["ai"] = ({**ai_row["result"],
                     "model": ai_row.get("model"),
                     "generated_at": _iso(ai_row.get("created_at"))}
                    if ai_row else None)

    # HUJJATLAR — bo'limlar bo'yicha guruhlangan (texnik topshiriq, xarid hujjati...)
    docs = [_shape_document(r, tender_id) for r in
            db.query(queries.TENDER_DOCUMENTS_SQL, {"id": tender_id})]
    tender["documents"] = docs
    tender["doc_count"] = len(docs)

    groups: dict = {}
    for d in docs:
        groups.setdefault(d["section"], []).append(d)
    tender["document_sections"] = [
        {"section": k, "files": v} for k, v in groups.items()
    ]
    return tender


@app.get("/tenders/{tender_id}/documents")
def tender_documents(tender_id: int):
    """Faqat hujjatlar ro'yxati (yuklab olish havolalari bilan)."""
    rows = db.query(queries.TENDER_DOCUMENTS_SQL, {"id": tender_id})
    return [_shape_document(r, tender_id) for r in rows]


@app.get("/documents/{tender_id}/download")
def download_document(tender_id: int, ref: str):
    """Fayl yuklab olish proksisi.

    NEGA KERAK: UzEx fayl endpointi faqat POST qabul qiladi (GET -> 405),
    brauzerdagi <a href> esa GET yuboradi. Shuning uchun POST'ni biz qilamiz
    va oqimni (stream) foydalanuvchiga uzatamiz — fayl xotiraga to'liq
    yuklanmaydi (16 MB li arxivlar ham bor).
    """
    row = db.query_one(queries.DOCUMENT_BY_REF_SQL, {"id": tender_id, "ref": ref})
    if not row:
        raise HTTPException(status_code=404, detail="Hujjat topilmadi.")

    platform = row.get("source_platform") or "xt-xarid"
    if platform == "xt-xarid" and row.get("file_id"):
        return RedirectResponse(_FILE_URL["xt-xarid"].format(file_id=row["file_id"]))

    upstream = _POST_DOWNLOAD.get(platform)
    if upstream:
        try:
            up = requests.post(upstream, params={"path": row["file_path"]},
                               headers={"User-Agent": _BROWSER_UA},
                               stream=True, timeout=60)
            up.raise_for_status()
        except requests.RequestException as e:
            raise HTTPException(status_code=502,
                                detail=f"Manbadan olinmadi: {e}") from e
        name = row.get("name") or "document"
        return StreamingResponse(
            up.iter_content(chunk_size=65536),
            media_type=up.headers.get("Content-Type", "application/octet-stream"),
            headers={"Content-Disposition":
                     f'attachment; filename="{quote(name)}"'},
        )

    raise HTTPException(status_code=501,
                        detail=f"'{platform}' uchun yuklab olish qo'llab-quvvatlanmaydi.")


@app.get("/stats")
def stats(status: str = Query("open", description="Qaysi status bo'yicha statistika (default open).")):
    """Dashboard umumiy ko'rsatkichlari. Valyutalar ALOHIDA (UZS/USD aralashtirilmaydi)."""
    p = {"status": status}
    open_count = db.scalar(queries.STATS_OPEN_COUNT_SQL, p) or 0

    by_currency = [
        {"currency": r["currency"],
         "tender_count": r["tender_count"],
         "total_value": _num(r["total_value"])}
        for r in db.query(queries.STATS_BY_CURRENCY_SQL, p)
    ]

    by_region = [
        {"area_id": r["area_id"], "name": r["name"], "tender_count": r["tender_count"]}
        for r in db.query(queries.STATS_BY_REGION_SQL, p)
    ]

    return {
        "status": status,
        "count": open_count,
        "by_currency": by_currency,
        "by_region": by_region,
    }


@app.get("/regions")
def regions(parent_id: Optional[str] = Query(None, description="Faqat shu ota tugun bolalari (kaskad dropdown uchun).")):
    """Hudud dropdown ma'lumotlari. parent_id berilsa faqat bolalari qaytadi."""
    if parent_id:
        where = "WHERE parent_id = %(parent_id)s"
        params = {"parent_id": parent_id}
    else:
        where, params = "", {}
    return db.query(queries.REGIONS_SQL.format(where=where), params)


@app.get("/statuses")
def statuses():
    """Status dropdown ma'lumotlari (domain='tender')."""
    return db.query(queries.STATUSES_SQL)


@app.get("/freshness")
def freshness():
    """Ma'lumot yangiligi + ETL sog'ligi (H bosqich).
    Dashboard 'oxirgi yangilanish' ko'rsatkichi va aniqlash-kechikishi uchun."""
    runs = db.query(queries.FRESHNESS_SQL)
    platforms = [{
        "source_platform": r["source_platform"],
        "status": r["status"],
        "found": r["found"], "new": r["new"],
        "finished_at": _iso(r["finished_at"]),
        "age_sec": r["age_sec"],
    } for r in runs]

    # Umumiy yangilik = eng eski (eng kam yangilangan) manba
    ages = [p["age_sec"] for p in platforms if p["age_sec"] is not None]
    overall_age = max(ages) if ages else None
    any_error = any(p["status"] == "error" for p in platforms)

    det = db.query_one(queries.DETECTION_STATS_SQL) or {}
    n = det.get("n") or 0
    detection = {
        "sample": n,
        "median_hours": round(float(det["median_hours"]), 1) if det.get("median_hours") is not None else None,
        "within_1h_pct": round(100 * det["within_1h"] / n) if n else None,
    }
    return {
        "overall_age_sec": overall_age,
        "any_error": any_error,
        "platforms": platforms,
        "detection": detection,
    }


@app.get("/categories")
def categories():
    """Kategoriya daraxti (2 daraja) + har birida ochiq tenderlar soni.
    Parent tugunда `children` massivi; son ichkilarни ham qamrab oladi."""
    rows = db.query(queries.CATEGORIES_SQL)
    by_code = {r["code"]: {"code": r["code"], "name": r["name_uz"],
                           "count": r["cnt"], "children": []} for r in rows}
    tree = []
    for r in rows:
        node = by_code[r["code"]]
        if r["parent"] and r["parent"] in by_code:
            by_code[r["parent"]]["children"].append(node)
        else:
            tree.append(node)
    return tree


# ---------------------------------------------------------------------------
# Aqlli moslashtirish (deterministik — kelajakda AI bilan almashtiriladi)
# ---------------------------------------------------------------------------
def _shape_profile(r: Optional[dict]) -> Optional[dict]:
    if not r:
        return None
    return {
        "id": r["id"],
        "name": r["name"],
        "keywords": r["keywords"] or [],
        "regions": r["regions"] or [],
        "currency": r["currency"],
        "min_cost": _num(r["min_cost"]),
        "max_cost": _num(r["max_cost"]),
        "updated_at": _iso(r["updated_at"]),
    }


# ---------------------------------------------------------------------------
# SAQLANGAN QIDIRUVLAR (A bosqich)
# ---------------------------------------------------------------------------
def _shape_search(r: dict) -> dict:
    return {
        "id": r["id"], "name": r["name"],
        "keywords": r["keywords"] or [],
        "categories": r["categories"] or [],
        "regions": r["regions"] or [],
        "currency": r["currency"],
        "min_cost": _num(r["min_cost"]), "max_cost": _num(r["max_cost"]),
        "notify": r["notify"],
        "last_seen_at": _iso(r["last_seen_at"]),
        "created_at": _iso(r["created_at"]),
    }


def _search_to_profile(r: dict) -> dict:
    """Saqlangan qidiruvni matching profiliga o'giradi (skorlash uchun)."""
    return {"keywords": r["keywords"] or [], "regions": r["regions"] or [],
            "currency": r["currency"], "min_cost": _num(r["min_cost"]),
            "max_cost": _num(r["max_cost"])}


def _count_matches(candidates: list, prof: dict) -> int:
    """Qidiruvga mos ochiq tenderlar soni. Kalit so'z bo'lsa — kamida bittasi
    mos kelganlar; bo'lmasa — hudud/byudjet biror ball berganlar."""
    has_kw = bool(prof.get("keywords"))
    n = 0
    for c in candidates:
        m = matching.score_tender(c, prof)
        if (m["matched_keywords"] if has_kw else m["score"] > 0):
            n += 1
    return n


@app.get("/searches")
def list_searches():
    """Barcha saqlangan qidiruvlar + har birida mos ochiq tenderlar soni."""
    rows = db.query(queries.SEARCHES_LIST_SQL)
    if not rows:
        return []
    # Nomzodlarni BIR MARTA olamiz, keyin har qidiruv bo'yicha skorlaymiz
    where, params = queries.build_tender_filters(status="open")
    cand = db.query(queries.match_candidates_sql(where, cap=MATCH_CAP), params)
    return [{**_shape_search(r),
             "match_count": _count_matches(cand, _search_to_profile(r))}
            for r in rows]


@app.post("/searches", status_code=201)
def create_search(s: SavedSearchIn):
    row = db.execute_returning(queries.SEARCH_INSERT_SQL, s.model_dump())
    return _shape_search(row)


@app.put("/searches/{search_id}")
def update_search(search_id: int, s: SavedSearchIn):
    row = db.execute_returning(queries.SEARCH_UPDATE_SQL,
                               {**s.model_dump(), "id": search_id})
    if not row:
        raise HTTPException(status_code=404, detail="Qidiruv topilmadi.")
    return _shape_search(row)


@app.delete("/searches/{search_id}", status_code=204)
def delete_search(search_id: int):
    row = db.execute_returning(queries.SEARCH_DELETE_SQL, {"id": search_id})
    if not row:
        raise HTTPException(status_code=404, detail="Qidiruv topilmadi.")
    return None


# ---------------------------------------------------------------------------
# MAHSULOT KATALOGI (REJA.md P0-4/5) — mijoz sotadigan mahsulot/xizmatlar
# ---------------------------------------------------------------------------
def _shape_product(r: dict) -> dict:
    return {
        "id": r["id"], "name": r["name"],
        "category_code": r["category_code"], "keywords": r["keywords"] or [],
        "unit": r["unit"], "price": _num(r["price"]), "currency": r["currency"],
        "notify": r["notify"], "created_at": _iso(r["created_at"]),
    }


def _product_matches(cand: dict, product: dict) -> Optional[str]:
    """Tender mahsulotga mos keladimi? -> 'category' | 'name' | None.
    Kategoriya kuchli signal (roll-up: parent tanlansa ichkilar ham),
    nom/kalit so'z esa qo'shimcha."""
    cat = product.get("category_code")
    if cat:
        for code in (cand.get("category_codes") or []):
            if code == cat or code.startswith(cat + "/"):
                return "category"
    terms = [product["name"]] + (product.get("keywords") or [])
    blob = matching._norm(f"{cand.get('name') or ''} {cand.get('goods_blob') or ''}")
    for t in terms:
        if t and matching._norm(t) in blob:
            return "name"
    return None


def _catalog_candidates(region=None, currency=None):
    """Ochiq nomzod tenderlar (katalog moslik uchun bir marta olinadi)."""
    where, params = queries.build_tender_filters(
        status="open", region=region, currency=currency)
    return db.query(queries.match_candidates_sql(where, cap=MATCH_CAP), params)


@app.get("/catalog")
def list_catalog():
    """Katalog mahsulotlari + har birida mos ochiq tenderlar soni."""
    prods = db.query(queries.CATALOG_LIST_SQL)
    if not prods:
        return []
    cand = _catalog_candidates()
    out = []
    for p in prods:
        cnt = sum(1 for c in cand if _product_matches(c, p))
        out.append({**_shape_product(p), "match_count": cnt})
    return out


@app.post("/catalog", status_code=201)
def create_product(p: CatalogItemIn):
    row = db.execute_returning(queries.CATALOG_INSERT_SQL, p.model_dump())
    return _shape_product(row)


@app.put("/catalog/{product_id}")
def update_product(product_id: int, p: CatalogItemIn):
    row = db.execute_returning(queries.CATALOG_UPDATE_SQL,
                               {**p.model_dump(), "id": product_id})
    if not row:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi.")
    return _shape_product(row)


@app.delete("/catalog/{product_id}", status_code=204)
def delete_product(product_id: int):
    row = db.execute_returning(queries.CATALOG_DELETE_SQL, {"id": product_id})
    if not row:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi.")
    return None


@app.post("/catalog/match")
def catalog_match(body: CatalogMatchIn):
    """Katalogga mos ochiq tenderlar. Kategoriya = asosiy relevantlik,
    nom = qo'shimcha. Har tenderда qaysi mahsulot(lar) mos kelgani ko'rsatiladi."""
    prods = db.query(queries.CATALOG_LIST_SQL)
    cand = _catalog_candidates(region=body.region, currency=body.currency)

    matched = []
    for c in cand:
        hits = [(p, _product_matches(c, p)) for p in prods]
        hits = [(p, how) for p, how in hits if how]
        if not hits:
            continue
        item = _shape_tender(c)
        item["catalog"] = {
            "score": 100 if any(how == "category" for _, how in hits) else 70,
            "products": [p["name"] for p, _ in hits][:5],
            "by": "category" if any(how == "category" for _, how in hits) else "name",
        }
        matched.append(item)

    # Kategoriya mosligi yuqori, keyin deadline yaqin
    matched.sort(key=lambda it: (-it["catalog"]["score"], it["close_at"] or "9999"))
    total = len(matched)
    page = matched[body.offset: body.offset + body.limit]
    return {"total": total, "limit": body.limit, "offset": body.offset, "items": page}


@app.get("/catalog/new-count")
def catalog_new_count():
    """Xabarnoma belgisi: katalogga mos VA oxirgi ko'rilgandan keyin e'lon
    qilingan ochiq tenderlar soni (ilova-ichi 'N yangi')."""
    prods = db.query(queries.CATALOG_LIST_SQL)
    if not prods:
        return {"new": 0, "total": 0}
    last_seen = db.scalar(queries.CATALOG_STATE_GET_SQL)
    cand = _catalog_candidates()
    total = new = 0
    for c in cand:
        if not any(_product_matches(c, p) for p in prods):
            continue
        total += 1
        pub = c.get("publicated_at")
        if last_seen and pub and pub > last_seen:
            new += 1
    return {"new": new, "total": total}


@app.post("/catalog/seen", status_code=204)
def catalog_seen():
    """Katalog moslarini 'ko'rildi' deb belgilaydi (yangi-belgisi tozalanadi)."""
    db.execute_returning(queries.CATALOG_SEEN_SQL)
    return None


@app.get("/profile")
def get_profile():
    """Faol kompaniya profili (yo'q bo'lsa null)."""
    return _shape_profile(db.query_one(queries.PROFILE_GET_SQL))


@app.put("/profile")
def put_profile(p: ProfileIn):
    """Profilni saqlaydi (bitta faol profil — bor bo'lsa yangilanadi)."""
    row = db.execute_returning(queries.PROFILE_UPSERT_SQL, {
        "name": p.name,
        "keywords": p.keywords,
        "regions": p.regions,
        "currency": p.currency,
        "min_cost": p.min_cost,
        "max_cost": p.max_cost,
    })
    return _shape_profile(row)


@app.post("/match")
def match(body: MatchIn):
    """Profilга qarab tenderlarни ballab tartiblaydi.

    Filtrlar (status/region/currency/q) QATTIQ — nomzodlarни cheklaydi.
    Profil esa faqat SKORLAYDI (tartiblaydi), filtrlamaydi.
    """
    where, params = queries.build_tender_filters(
        status=body.status or None, region=body.region,
        currency=body.currency, q=body.q, category=body.category,
    )
    rows = db.query(queries.match_candidates_sql(where, cap=MATCH_CAP), params)

    profile = body.profile.model_dump()
    scored = []
    for r in rows:
        m = matching.score_tender(r, profile)
        item = _shape_tender(r)
        item["match"] = m
        scored.append(item)

    # Ball bo'yicha kamayish tartibida; teng bo'lsa deadline yaqin birinchi
    scored.sort(key=lambda it: (-it["match"]["score"], it["close_at"] or "9999"))

    total = len(scored)
    page = scored[body.offset: body.offset + body.limit]
    return {
        "total": total, "limit": body.limit, "offset": body.offset,
        # Cap ishga tushgan bo'lsa buni YASHIRMAYMIZ — foydalanuvchi ba'zi
        # tenderlar umuman ballanmaganini bilishi kerak (jimgina kesish yo'q).
        "truncated": len(rows) >= MATCH_CAP,
        "candidate_cap": MATCH_CAP,
        "items": page,
    }
