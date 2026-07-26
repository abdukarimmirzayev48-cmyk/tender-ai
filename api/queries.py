"""
SQL matnlari va dinamik filtr quruvchisi — bir joyda saqlanadi.

Xavfsizlik: barcha foydalanuvchi qiymatlari psycopg2 named-param (%(x)s) orqali
uzatiladi — SQL-injection yo'q. Faqat ORDER BY ustuni oq ro'yxat (whitelist)
bilan tekshiriladi, chunki ustun nomini parametrlashtirib bo'lmaydi.
"""
from typing import Any, Dict, List, Tuple

# Ro'yxat va bitta tender uchun umumiy SELECT boshi (JOIN'lar bilan).
# name_uz hozircha bo'sh — shuning uchun name_ru ni ham qaytaramiz, frontend tanlaydi.
_TENDER_SELECT = """
SELECT
    t.id, t.source_id, t.type, t.name, t.status,
    s.name_uz  AS status_name_uz,
    s.name_ru  AS status_name_ru,
    s.is_terminal,
    t.totalcost, t.currency,
    t.area_path, t.area_leaf_id,
    a.name_uz  AS region_name_uz,
    a.name_ru  AS region_name_ru,
    t.company_id, t.company_name,
    t.lot_count, t.good_count, t.part_count,
    t.publicated_at, t.close_at, t.starting_date, t.ends_at,
    t.remain_time, t.source_platform, t.fetched_at, t.first_seen_at,
    -- Mahsulot nomlari qisqacha ro'yxati (jadvalда ko'rsatish uchun, takrorsiz, 6 tagacha)
    ARRAY(SELECT DISTINCT tg.name FROM tender_good tg
          WHERE tg.tender_id = t.id AND tg.name IS NOT NULL
          ORDER BY tg.name LIMIT 6) AS goods_preview,
    COALESCE(td.doc_count, 0) AS doc_count,
    -- LOTLAR xulosasi: ko'p lotli tenderda asosiy ma'no LOT nomlarida.
    -- Ro'yxatda darhol ko'rsatish uchun (qo'shimcha so'rovsiz) shu yerda yig'amiz.
    (SELECT json_agg(l ORDER BY l.lot_id) FROM (
        SELECT tl.lot_id, tl.title, tl.total_sum_lot, tl.item_count,
               MAX(ti.delivery_period) AS delivery_period,
               MAX(ti.guarantee)       AS guarantee
        FROM tender_lot tl
        LEFT JOIN tender_item ti
               ON ti.tender_id = tl.tender_id AND ti.lot_id = tl.lot_id
        WHERE tl.tender_id = t.id
        GROUP BY tl.lot_id, tl.title, tl.total_sum_lot, tl.item_count
    ) l) AS lots_json
FROM tender t
LEFT JOIN dim_status   s  ON s.status_code = t.status AND s.domain = 'tender'
LEFT JOIN dim_area     a  ON a.area_id = t.area_leaf_id
LEFT JOIN tender_detail td ON td.tender_id = t.id
"""

# ORDER BY uchun ruxsat etilgan ustunlar (oq ro'yxat)
_SORT_WHITELIST = {
    "close_at": "t.close_at",
    "publicated_at": "t.publicated_at",
    "totalcost": "t.totalcost",
    "id": "t.id",
}
DEFAULT_SORT = "close_at"  # deadline yaqinlashayotgani yuqorida

# ---------------------------------------------------------------------------
# AI QIDIRUV MATNI — 5a tahlilining qidiriladigan qismlari bitta matnga.
#
# NEGA KERAK: tovar nomi "Моноблок" bo'lsa, "kompyuter" so'rovi uni hech qachon
# topmaydi — harflar mos kelmaydi. AI esa `keywords_uz` ga "kompyuter",
# `keywords_ru` ga "моноблок, МФУ, ноутбук" yozadi. Shu matnni qidiruvga
# qo'shsak, ikkala tomondan ham topiladi.
#
# Butun JSONB ni matn sifatida qidirmaymiz — u holda maydon NOMLARI
# ("summary_uz") ham qidiruvga tushib, soxta natija berardi. Faqat QIYMATLAR.
# ---------------------------------------------------------------------------
_AI_TEXT = """concat_ws(' ',
    ax.result->>'summary_uz',
    ax.result->>'supplier_profile',
    (SELECT string_agg(x, ' ') FROM jsonb_array_elements_text(
        COALESCE(ax.result->'keywords_uz', '[]'::jsonb)) x),
    (SELECT string_agg(x, ' ') FROM jsonb_array_elements_text(
        COALESCE(ax.result->'keywords_ru', '[]'::jsonb)) x),
    (SELECT string_agg(x, ' ') FROM jsonb_array_elements_text(
        COALESCE(ax.result->'category_tags', '[]'::jsonb)) x))"""


def build_tender_filters(
    status: str = None,
    region: str = None,
    currency: str = None,
    source: str = None,
    q: str = None,
    category: str = None,
) -> Tuple[str, Dict[str, Any]]:
    """WHERE bo'lagini va parametrlarni quradi (bo'sh filtrlar tashlab yuboriladi)."""
    clauses: List[str] = []
    params: Dict[str, Any] = {}

    if status:
        clauses.append("t.status = %(status)s")
        params["status"] = status
    if region:
        # Ierarxik PREFIX moslashuvi: dim_area.area_id to'liq nuqtali yo'l
        # ('33.2137' = viloyat, '33.2137.2138.2140' = leaf). Viloyat tanlansa,
        # ostidagi barcha tumanlar/leaflar ham chiqadi.
        #   region = '33.2137'  ->  '33.2137' va '33.2137.%' mos keladi
        # (%% — psycopg2 uchun literal foiz belgisi)
        clauses.append("(t.area_path = %(region)s OR t.area_path LIKE %(region)s || '.%%')")
        params["region"] = region
    if currency:
        clauses.append("t.currency = %(currency)s")
        params["currency"] = currency
    if source:
        clauses.append("t.source_platform = %(source)s")
        params["source"] = source
    if category:
        # Parent tanlansa ichkilar ham kiradi: 'qurilish' -> 'qurilish' va
        # 'qurilish/%'. Ichki tanlansa aynan o'zi.
        clauses.append(
            "EXISTS (SELECT 1 FROM tender_category tc WHERE tc.tender_id = t.id "
            "        AND (tc.code = %(category)s OR tc.code LIKE %(category)s || '/%%'))")
        params["category"] = category
    if q:
        # name, company_name yoki tovar nomi bo'yicha qidiruv (katta-kichik farqsiz).
        # MUHIM: baza `C` locale bilan yaratilgan — oddiy ILIKE kirill harflarni
        # katta-kichik qila olmaydi. Shuning uchun har ustunga COLLATE "unicode"
        # (ICU) qo'yamiz — kirillcha ham to'g'ri ishlaydi, locale'ga bog'liq emas.
        clauses.append(
            '(t.name COLLATE "unicode" ILIKE %(q)s '
            'OR t.company_name COLLATE "unicode" ILIKE %(q)s '
            "OR EXISTS (SELECT 1 FROM tender_good g "
            '           WHERE g.tender_id = t.id AND g.name COLLATE "unicode" ILIKE %(q)s)'
            # AI kalit so'zlari bo'yicha ham qidiramiz — shu bilan "kompyuter"
            # so'rovi "Моноблок" tenderini topadi (AI sinonimlarni yozib qo'ygan).
            # Tahlil qilinmagan tenderlarда bu shart oddiygina FALSE bo'ladi.
            " OR EXISTS (SELECT 1 FROM ai_analysis ax "
            "            WHERE ax.tender_id = t.id AND ax.kind = 'summary_v1' "
            f'              AND {_AI_TEXT} COLLATE "unicode" ILIKE %(q)s))'
        )
        params["q"] = f"%{q}%"

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def build_order_by(sort: str) -> str:
    """`sort` yoki `-sort` (minus = kamayish) ni xavfsiz ORDER BY ga aylantiradi."""
    desc = sort.startswith("-")
    key = sort[1:] if desc else sort
    col = _SORT_WHITELIST.get(key, _SORT_WHITELIST[DEFAULT_SORT])
    direction = "DESC" if desc else "ASC"
    # Deadline saralashda NULL'lar oxirida bo'lsin (to'ldirilmagan sanalar pastda)
    return f"ORDER BY {col} {direction} NULLS LAST, t.id DESC"


def tenders_sql(where: str, order_by: str) -> str:
    return f"{_TENDER_SELECT}\n{where}\n{order_by}\nLIMIT %(limit)s OFFSET %(offset)s"


def tenders_count_sql(where: str) -> str:
    return f"SELECT count(*) AS n FROM tender t\n{where}"


def tender_by_id_sql() -> str:
    return f"{_TENDER_SELECT}\nWHERE t.id = %(id)s"


TENDER_LOTS_SQL = """
SELECT lot_id, title, item_count, total_sum_lot
FROM tender_lot
WHERE tender_id = %(id)s
ORDER BY lot_id
"""

# Pozitsiya tafsiloti — yetkazib berish sharti, kafolat, texnik xarakteristika
TENDER_ITEMS_SQL = """
SELECT lot_id, item_id, product_code, name, unit, amount_text,
       price_text, totalcost_text, delivery_period, guarantee, prod_year,
       country_of_origin, delivery_address, spec, properties
FROM tender_item
WHERE tender_id = %(id)s
ORDER BY lot_id, name
"""

# --- Tender tafsiloti (get_proc dan ajratilgan maydonlar) ---
TENDER_DETAIL_SQL = """
SELECT anno, method_marks, company_details, director,
       close_time, proc_lang, offer_period, doc_count
FROM tender_detail
WHERE tender_id = %(id)s
"""

# --- Tenderga biriktirilgan hujjatlar (texnik topshiriq, xarid hujjatlari...) ---
TENDER_DOCUMENTS_SQL = """
SELECT file_ref, file_id, file_path, name, size_bytes, content_type,
       file_type, field_key, source_platform
FROM tender_document
WHERE tender_id = %(id)s
ORDER BY field_key, name
"""

# AI tahlili (5a) — o'zbekcha xulosa + kanonik kategoriya teglari
AI_ANALYSIS_SQL = """
SELECT result, model, created_at
FROM ai_analysis
WHERE tender_id = %(id)s AND kind = %(kind)s
"""

# Bitta hujjat (yuklab olish proksisi uchun)
DOCUMENT_BY_REF_SQL = """
SELECT file_id, file_path, name, content_type, file_type, source_platform
FROM tender_document
WHERE tender_id = %(id)s AND file_ref = %(ref)s
"""

TENDER_GOODS_SQL = """
SELECT g.lot_id, g.good_code, g.name, g.unit, g.amount, g.price,
       g.totalcost_item, g.category_uid,
       c.code AS category_code, c.title_ru AS category_title_ru
FROM tender_good g
LEFT JOIN dim_category c ON c.category_uid = g.category_uid
WHERE g.tender_id = %(id)s
ORDER BY g.lot_id, g.good_code
"""

# --- /stats ---
STATS_OPEN_COUNT_SQL = "SELECT count(*) AS n FROM tender WHERE status = %(status)s"

STATS_BY_CURRENCY_SQL = """
SELECT currency, count(*) AS tender_count, COALESCE(SUM(totalcost), 0) AS total_value
FROM tender
WHERE status = %(status)s
GROUP BY currency
ORDER BY currency
"""

STATS_BY_REGION_SQL = """
SELECT a.area_id,
       COALESCE(a.name_uz, a.name_ru) AS name,
       count(*) AS tender_count
FROM tender t
LEFT JOIN dim_area a ON a.area_id = t.area_leaf_id
WHERE t.status = %(status)s
GROUP BY a.area_id, COALESCE(a.name_uz, a.name_ru)
ORDER BY tender_count DESC
"""

# --- /regions ---
REGIONS_SQL = """
SELECT area_id, COALESCE(name_uz, name_ru) AS name,
       name_ru, name_uz, level, parent_id, has_children
FROM dim_area
{where}
ORDER BY level, name
"""

# --- /match nomzodlari ---
# Tenderlarni skorlash uchun: har tenderning barcha tovar nomlarini bitta
# 'goods_blob' matnга jamlab olamiz (kalit so'z qidirish uchun). GROUP BY —
# t.id PK + agregatsiyasiz dim ustunlar.
def match_candidates_sql(where: str, cap: int) -> str:
    return f"""
SELECT
    t.id, t.source_id, t.type, t.name, t.status,
    s.name_uz AS status_name_uz, s.name_ru AS status_name_ru, s.is_terminal,
    t.totalcost, t.currency, t.area_path, t.area_leaf_id,
    a.name_uz AS region_name_uz, a.name_ru AS region_name_ru,
    COALESCE(a.name_uz, a.name_ru) AS region_name,
    t.company_id, t.company_name,
    t.lot_count, t.good_count, t.publicated_at, t.close_at,
    t.remain_time, t.source_platform,
    -- Kalit so'z qidiriladigan matn: tovar nomlari + AI sinonimlari.
    -- AI qismi tufayli profilda "kompyuter" bo'lsa, "Моноблок" tenderi ham
    -- moslik ball oladi. Tahlil qilinmagan tenderда bu qism bo'sh qoladi.
    COALESCE(string_agg(DISTINCT g.name, ' '), '') || ' ' ||
    COALESCE((SELECT {_AI_TEXT} FROM ai_analysis ax
              WHERE ax.tender_id = t.id AND ax.kind = 'summary_v1'), '')
        AS goods_blob,
    -- Katalog moslik uchun: shu tenderning kategoriya kodlari
    ARRAY(SELECT code FROM tender_category tc WHERE tc.tender_id = t.id) AS category_codes,
    ARRAY(SELECT DISTINCT tg.name FROM tender_good tg
          WHERE tg.tender_id = t.id AND tg.name IS NOT NULL
          ORDER BY tg.name LIMIT 6) AS goods_preview
FROM tender t
LEFT JOIN dim_status s ON s.status_code = t.status AND s.domain = 'tender'
LEFT JOIN dim_area   a ON a.area_id = t.area_leaf_id
LEFT JOIN tender_good g ON g.tender_id = t.id
{where}
GROUP BY t.id, s.name_uz, s.name_ru, s.is_terminal, a.name_uz, a.name_ru
-- TARTIB MUHIM: ballash PYTHONда, LIMIT esa SHU YERDA bo'ladi. Ya'ni cap
-- ishga tushsa, ro'yxat OXIRIDAGI tenderlar umuman ballanmaydi.
-- Shuning uchun eng HARAKATGA YAROQLILARI birinchi turishi shart:
--   1) ochiq tenderlar, 2) muddati o'tmaganlar, 3) deadline yaqinlari.
-- (Ilgari `close_at ASC` edi — bu muddati o'tganlarni oldinga chiqarib,
--  aynan ochiq tenderlarni cap tashqarisida qoldirardi.)
ORDER BY
    (t.status = 'open') DESC,
    (t.close_at >= now()) DESC NULLS LAST,
    t.close_at ASC NULLS LAST
LIMIT {int(cap)}
"""


# --- profil (CRUD, bitta faol profil) ---
PROFILE_GET_SQL = """
SELECT id, name, keywords, regions, currency, min_cost, max_cost, updated_at
FROM company_profile
ORDER BY updated_at DESC
LIMIT 1
"""

# Bitta faol profil: bor bo'lsa yangilaymiz, yo'q bo'lsa qo'shamiz
PROFILE_UPSERT_SQL = """
INSERT INTO company_profile (id, name, keywords, regions, currency, min_cost, max_cost, updated_at)
VALUES (
    COALESCE((SELECT id FROM company_profile ORDER BY updated_at DESC LIMIT 1), 1),
    %(name)s, %(keywords)s, %(regions)s, %(currency)s, %(min_cost)s, %(max_cost)s, now()
)
ON CONFLICT (id) DO UPDATE SET
    name=EXCLUDED.name, keywords=EXCLUDED.keywords, regions=EXCLUDED.regions,
    currency=EXCLUDED.currency, min_cost=EXCLUDED.min_cost, max_cost=EXCLUDED.max_cost,
    updated_at=now()
RETURNING id, name, keywords, regions, currency, min_cost, max_cost, updated_at
"""


# ---------------------------------------------------------------------------
# SAQLANGAN QIDIRUVLAR (A bosqich)
# ---------------------------------------------------------------------------
_SS_COLS = ("id, name, keywords, categories, regions, currency, "
            "min_cost, max_cost, notify, last_seen_at, created_at, updated_at")

SEARCHES_LIST_SQL = f"SELECT {_SS_COLS} FROM saved_search ORDER BY created_at"

SEARCH_GET_SQL = f"SELECT {_SS_COLS} FROM saved_search WHERE id = %(id)s"

SEARCH_INSERT_SQL = f"""
INSERT INTO saved_search (name, keywords, categories, regions, currency, min_cost, max_cost, notify)
VALUES (%(name)s, %(keywords)s, %(categories)s, %(regions)s, %(currency)s,
        %(min_cost)s, %(max_cost)s, %(notify)s)
RETURNING {_SS_COLS}
"""

SEARCH_UPDATE_SQL = f"""
UPDATE saved_search SET
    name=%(name)s, keywords=%(keywords)s, categories=%(categories)s,
    regions=%(regions)s, currency=%(currency)s,
    min_cost=%(min_cost)s, max_cost=%(max_cost)s, notify=%(notify)s,
    updated_at=now()
WHERE id=%(id)s
RETURNING {_SS_COLS}
"""

SEARCH_DELETE_SQL = "DELETE FROM saved_search WHERE id=%(id)s RETURNING id"

# Qidiruvni "ko'rildi" deb belgilash (yangi-mos belgisi tozalanadi — C bosqich)
SEARCH_SEEN_SQL = "UPDATE saved_search SET last_seen_at=now() WHERE id=%(id)s RETURNING id"


# --- /categories (B bosqich) — daraxt + OCHIQ tenderlar soni ---
# Parent soni ichkilarни ham qamrab oladi (roll-up). Bir tender bir necha
# kategoriyada bo'lishi mumkin, shuning uchun sonlar yig'indisi jamiga teng emas.
CATEGORIES_SQL = """
SELECT c.code, c.parent, c.name_uz, c.sort_order,
       (SELECT count(DISTINCT tc.tender_id)
          FROM tender_category tc
          JOIN tender t ON t.id = tc.tender_id
         WHERE t.status = 'open'
           AND (tc.code = c.code OR tc.code LIKE c.code || '/%%')) AS cnt
FROM dim_category_uz c
ORDER BY c.sort_order
"""

# ---------------------------------------------------------------------------
# MAHSULOT KATALOGI (REJA.md P0-4/5)
# ---------------------------------------------------------------------------
_CP_COLS = ("id, name, category_code, keywords, unit, price, currency, "
            "notify, created_at, updated_at")

CATALOG_LIST_SQL = f"SELECT {_CP_COLS} FROM catalog_product ORDER BY created_at"

CATALOG_INSERT_SQL = f"""
INSERT INTO catalog_product (name, category_code, keywords, unit, price, currency, notify)
VALUES (%(name)s, %(category_code)s, %(keywords)s, %(unit)s, %(price)s, %(currency)s, %(notify)s)
RETURNING {_CP_COLS}
"""

CATALOG_UPDATE_SQL = f"""
UPDATE catalog_product SET
    name=%(name)s, category_code=%(category_code)s, keywords=%(keywords)s,
    unit=%(unit)s, price=%(price)s, currency=%(currency)s, notify=%(notify)s,
    updated_at=now()
WHERE id=%(id)s
RETURNING {_CP_COLS}
"""

CATALOG_DELETE_SQL = "DELETE FROM catalog_product WHERE id=%(id)s RETURNING id"

CATALOG_STATE_GET_SQL = "SELECT last_seen_at FROM catalog_state WHERE id=1"
CATALOG_SEEN_SQL = "UPDATE catalog_state SET last_seen_at=now() WHERE id=1 RETURNING last_seen_at"

# --- /freshness (H bosqich) — ma'lumot yangiligi + ETL sog'ligi ---
# Har platforma uchun ENG SO'NGGI yurish.
FRESHNESS_SQL = """
SELECT DISTINCT ON (source_platform)
       source_platform, status, found, new, started_at, finished_at,
       EXTRACT(EPOCH FROM (now() - finished_at))::bigint AS age_sec
FROM etl_run
ORDER BY source_platform, started_at DESC
"""

# Aniqlash-kechikishi statistikasi (e'londan biz topgunga qadar), ochiq tenderlar
DETECTION_STATS_SQL = """
SELECT
    count(*) FILTER (WHERE publicated_at IS NOT NULL) AS n,
    percentile_cont(0.5) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (first_seen_at - publicated_at))/3600) AS median_hours,
    count(*) FILTER (
        WHERE publicated_at IS NOT NULL
          AND first_seen_at - publicated_at <= interval '1 hour') AS within_1h
FROM tender
WHERE status = 'open' AND first_seen_at >= publicated_at
"""

# --- /statuses ---
STATUSES_SQL = """
SELECT status_code, COALESCE(name_uz, name_ru) AS name,
       name_ru, name_uz, is_terminal, status_id
FROM dim_status
WHERE domain = 'tender'
ORDER BY status_id NULLS LAST, status_code
"""
