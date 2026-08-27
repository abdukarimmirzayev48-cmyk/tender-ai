# Integratsiya — ERP 1-BOSQICH: "Ishga olish" + Opportunity pipeline

Bu hujjatdagi kod **UMUMIY fayllarga tegmasdan** yoziladigan mustaqil
fayllarni va umumiy fayllarga **aynan ko'chiriladigan** ulash qatorlarini
beradi. Uslub — `compliance.md` / `pricing.md` bilan bir xil.

Mustaqil fayllar (ERP agenti yaratadi):

| Fayl | Vazifasi |
|---|---|
| `schema_patch_erp_1.sql` | `erp` sxemasi + 4 jadval (idempotent) |
| `api/erp/__init__.py` | bo'sh |
| `api/erp/opportunity.py` | snapshot, CRUD, status o'tish, SQL matnlari |
| `api/erp/stats.py` | rahbar hisoboti SQL + shakllantirish |
| `frontend/src/components/erp/TakeTenderDialog.jsx` | "Ishga olish" formasi |
| `frontend/src/components/erp/OpportunityBoard.jsx` | Kanban |
| `frontend/src/components/erp/OpportunityTable.jsx` | jadval |
| `frontend/src/components/erp/OpportunityCard.jsx` | karta (drawer) |
| `frontend/src/components/erp/OpportunityStats.jsx` | rahbar paneli |
| `frontend/src/components/erp/OpportunitiesPage.jsx` | bo'lim sahifasi (board/table/stats almashtirgich) |
| `frontend/src/styles/erp.css` | uslublar (komponentlar o'zi import qiladi) |
| `_tests/erp_test.py` | sinov (TestClient, bazani tozalaydi) |

Yangi kutubxona **kerak emas**. AI chaqiruvi **yo'q**. `public.*` ga **yozilmaydi**.

> **Moslash kerak bo'lgan joy — bitta:** `opportunity.py` dagi
> `TENDER_SNAPSHOT_SQL`. Unda `tender` jadvalining buyurtmachi/muddat/hudud
> ustun nomlari `queries.py` dagi haqiqiy nomlarga moslanadi (pastda belgilangan).

---

## 0. Baza — `schema_patch_erp_1.sql`

```sql
-- ERP 1-bosqich. Idempotent: qayta ishga tushirish xavfsiz.
-- public.* ga tegmaydi. erp.opportunity.tender_id -> public.tender.id
-- ATAYLAB FK'siz (etl qayta yozadi / manba o'chirishi mumkin; karta qolishi kerak).
CREATE SCHEMA IF NOT EXISTS erp;

CREATE TABLE IF NOT EXISTS erp.broker (
    id          SERIAL PRIMARY KEY,
    full_name   TEXT NOT NULL,
    email       TEXT,
    phone       TEXT,
    active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2-bosqichda passport ustunlari shu jadvalga qo'shiladi (INN, manzil, ...)
CREATE TABLE IF NOT EXISTS erp.client_company (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.opportunity (
    id                SERIAL PRIMARY KEY,
    tender_id         BIGINT NOT NULL,
    -- snapshot (ishga olingan paytdagi holat; keyin tender o'zgarsa ham qoladi)
    source_platform   TEXT,
    tender_ref        TEXT,          -- "tender № / lot №" ko'rinishida
    customer_name     TEXT,
    title             TEXT,
    start_price       NUMERIC,
    currency          TEXT,
    deadline_at       TIMESTAMPTZ,
    region_name       TEXT,
    source_url        TEXT,
    -- xodim kiritadi
    broker_id         INT REFERENCES erp.broker(id),
    client_id         INT REFERENCES erp.client_company(id),
    priority          TEXT NOT NULL DEFAULT 'medium'
                      CHECK (priority IN ('low','medium','high')),
    win_probability   SMALLINT CHECK (win_probability BETWEEN 0 AND 100),
    note              TEXT,
    next_task         TEXT,
    next_task_at      DATE,
    -- holat
    status            TEXT NOT NULL DEFAULT 'new'
                      CHECK (status IN ('new','reviewing','sent_to_client','confirmed',
                                        'preparing','submitted','won','lost','rejected')),
    status_changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at         TIMESTAMPTZ,
    created_by        TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- bir tender -> bir mijoz uchun bitta karta. client_id NULL bo'lsa
    -- UNIQUE ishlamaydi, shuning uchun pastda qisman indeks ham bor.
    UNIQUE (tender_id, client_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS opportunity_tender_noclient_uq
    ON erp.opportunity (tender_id) WHERE client_id IS NULL;
CREATE INDEX IF NOT EXISTS opportunity_status_idx   ON erp.opportunity (status);
CREATE INDEX IF NOT EXISTS opportunity_broker_idx   ON erp.opportunity (broker_id);
CREATE INDEX IF NOT EXISTS opportunity_deadline_idx ON erp.opportunity (deadline_at);

CREATE TABLE IF NOT EXISTS erp.opportunity_history (
    id              SERIAL PRIMARY KEY,
    opportunity_id  INT NOT NULL REFERENCES erp.opportunity(id) ON DELETE CASCADE,
    from_status     TEXT,
    to_status       TEXT NOT NULL,
    changed_by      TEXT,
    note            TEXT,
    changed_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS opp_history_opp_idx ON erp.opportunity_history (opportunity_id);
```

Qo'llash:

```
psql "dbname=xtxarid user=postgres host=localhost" -f schema_patch_erp_1.sql
```

---

## 1. `api/erp/opportunity.py` — mantiq va SQL

```python
"""ERP 1-bosqich: tenderni "ishga olish" va opportunity pipeline.

Chegara: public.* faqat O'QILADI (TENDER_SNAPSHOT_SQL). api.main, api.compliance
va boshqalar bu modulni import QILMAYDI — bog'liqlik bir tomonlama.
"""
from __future__ import annotations

from typing import Optional

from api import db

STATUSES = [
    ("new",            "Yangi"),
    ("reviewing",      "Ko‘rib chiqilmoqda"),
    ("sent_to_client", "Mijozga yuborildi"),
    ("confirmed",      "Qatnashish tasdiqlandi"),
    ("preparing",      "Taklif tayyorlanmoqda"),
    ("submitted",      "Topshirildi"),
    ("won",            "Yutildi"),
    ("lost",           "Yutqazildi"),
    ("rejected",       "Rad etildi"),
]
STATUS_LABEL = dict(STATUSES)
FINAL = {"won", "lost", "rejected"}
PRIORITIES = {"low": "Past", "medium": "O‘rta", "high": "Yuqori"}

# frontend/src/format.js dagi havola quruvchi bilan BIR XIL bo'lishi shart.
# Server tomonda kerak: snapshot'da source_url saqlanadi.
SOURCE_URL = {
    "xt-xarid": "https://xt-xarid.uz/procedure/{id}/core",
    "uzex":     "https://etender.uzex.uz/lot/{id}",
}


class ErpError(Exception):
    """Foydalanuvchi tuzata oladigan xato -> main.py da 400/404/409."""
    def __init__(self, msg, code=400, **extra):
        super().__init__(msg)
        self.code = code
        self.extra = extra


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------
# !!! MOSLASH: customer/deadline/region ustun nomlarini api/queries.py dagi
# TENDER_SQL ga qarab to'g'rilang. Quyidagi nomlar TAXMIN.
TENDER_SNAPSHOT_SQL = """
SELECT t.id, t.source_platform, t.name AS title,
       t.customer_name,                 -- <- moslang
       t.totalcost AS start_price, t.currency,
       t.deadline_at,                   -- <- moslang (masalan t.end_date)
       t.region_name                    -- <- moslang (masalan r.name_uz JOIN bilan)
FROM tender t
WHERE t.id = %(id)s
"""

_OPP_COLS = """
o.id, o.tender_id, o.source_platform, o.tender_ref, o.customer_name, o.title,
o.start_price, o.currency, o.deadline_at, o.region_name, o.source_url,
o.broker_id, b.full_name AS broker_name,
o.client_id, c.name AS client_name,
o.priority, o.win_probability, o.note, o.next_task, o.next_task_at,
o.status, o.status_changed_at, o.closed_at, o.created_by, o.created_at, o.updated_at
"""
_OPP_FROM = """
FROM erp.opportunity o
LEFT JOIN erp.broker b ON b.id = o.broker_id
LEFT JOIN erp.client_company c ON c.id = o.client_id
"""

OPP_LIST_SQL = f"""
SELECT {_OPP_COLS} {_OPP_FROM}
WHERE (%(status)s::text IS NULL OR o.status = %(status)s)
  AND (%(broker_id)s::int IS NULL OR o.broker_id = %(broker_id)s)
  AND (%(client_id)s::int IS NULL OR o.client_id = %(client_id)s)
  AND (%(q)s::text IS NULL OR o.title ILIKE '%%' || %(q)s || '%%'
                           OR o.customer_name ILIKE '%%' || %(q)s || '%%')
  AND (%(open_only)s::bool IS NOT TRUE OR o.status NOT IN ('won','lost','rejected'))
ORDER BY o.deadline_at NULLS LAST, o.id
"""
OPP_GET_SQL = f"SELECT {_OPP_COLS} {_OPP_FROM} WHERE o.id = %(id)s"
OPP_BY_TENDER_SQL = f"SELECT {_OPP_COLS} {_OPP_FROM} WHERE o.tender_id = %(tender_id)s ORDER BY o.id"

OPP_INSERT_SQL = """
INSERT INTO erp.opportunity (
    tender_id, source_platform, tender_ref, customer_name, title, start_price,
    currency, deadline_at, region_name, source_url,
    broker_id, client_id, priority, win_probability, note, next_task, next_task_at,
    created_by)
VALUES (%(tender_id)s, %(source_platform)s, %(tender_ref)s, %(customer_name)s,
        %(title)s, %(start_price)s, %(currency)s, %(deadline_at)s, %(region_name)s,
        %(source_url)s,
        %(broker_id)s, %(client_id)s, %(priority)s, %(win_probability)s, %(note)s,
        %(next_task)s, %(next_task_at)s, %(created_by)s)
RETURNING id
"""

# Faqat XODIM maydonlari tahrirlanadi; snapshot va status bu yerdan o'zgarmaydi.
OPP_UPDATE_SQL = """
UPDATE erp.opportunity SET
    broker_id=%(broker_id)s, client_id=%(client_id)s, priority=%(priority)s,
    win_probability=%(win_probability)s, note=%(note)s,
    next_task=%(next_task)s, next_task_at=%(next_task_at)s, updated_at=now()
WHERE id = %(id)s
RETURNING id
"""

OPP_STATUS_SQL = """
UPDATE erp.opportunity SET
    status=%(status)s, status_changed_at=now(), updated_at=now(),
    closed_at = CASE WHEN %(status)s IN ('won','lost','rejected') THEN now() ELSE NULL END
WHERE id = %(id)s
RETURNING id, status
"""

HISTORY_INSERT_SQL = """
INSERT INTO erp.opportunity_history (opportunity_id, from_status, to_status, changed_by, note)
VALUES (%(opportunity_id)s, %(from_status)s, %(to_status)s, %(changed_by)s, %(note)s)
RETURNING id
"""
HISTORY_LIST_SQL = """
SELECT id, from_status, to_status, changed_by, note, changed_at
FROM erp.opportunity_history WHERE opportunity_id = %(id)s ORDER BY changed_at, id
"""

BROKERS_SQL = "SELECT id, full_name, email, phone, active FROM erp.broker ORDER BY active DESC, full_name"
BROKER_INSERT_SQL = ("INSERT INTO erp.broker (full_name, email, phone) "
                     "VALUES (%(full_name)s, %(email)s, %(phone)s) RETURNING id, full_name, email, phone, active")
CLIENTS_SQL = "SELECT id, name, active FROM erp.client_company ORDER BY active DESC, name"
CLIENT_INSERT_SQL = "INSERT INTO erp.client_company (name) VALUES (%(name)s) RETURNING id, name, active"


# ---------------------------------------------------------------------------
# Shakllantirish
# ---------------------------------------------------------------------------
def _iso(v):
    return v.isoformat() if v is not None else None


def _num(v):
    return None if v is None else float(v)


def shape(r: dict) -> dict:
    return {
        "id": r["id"], "tender_id": r["tender_id"],
        "tender": {
            "source_platform": r["source_platform"], "tender_ref": r["tender_ref"],
            "customer_name": r["customer_name"], "title": r["title"],
            "start_price": _num(r["start_price"]), "currency": r["currency"],
            "deadline_at": _iso(r["deadline_at"]), "region_name": r["region_name"],
            "source_url": r["source_url"],
        },
        "broker": ({"id": r["broker_id"], "name": r["broker_name"]} if r["broker_id"] else None),
        "client": ({"id": r["client_id"], "name": r["client_name"]} if r["client_id"] else None),
        "priority": r["priority"], "priority_label": PRIORITIES.get(r["priority"]),
        "win_probability": r["win_probability"],
        "note": r["note"], "next_task": r["next_task"], "next_task_at": _iso(r["next_task_at"]),
        "status": r["status"], "status_label": STATUS_LABEL.get(r["status"]),
        "is_final": r["status"] in FINAL,
        "status_changed_at": _iso(r["status_changed_at"]), "closed_at": _iso(r["closed_at"]),
        "created_by": r["created_by"], "created_at": _iso(r["created_at"]),
        "updated_at": _iso(r["updated_at"]),
    }


# ---------------------------------------------------------------------------
# Amallar
# ---------------------------------------------------------------------------
def _tender_snapshot(tender_id: int) -> dict:
    """Tenderdan 9 maydon. Keyin ERP ajratilsa — shu BITTA funksiya HTTP
    chaqiruvga almashadi, boshqa joy tender bazasiga tegmaydi."""
    t = db.query_one(TENDER_SNAPSHOT_SQL, {"id": tender_id})
    if not t:
        raise ErpError("Tender topilmadi.", 404)
    url_tpl = SOURCE_URL.get(t["source_platform"] or "")
    return {
        "tender_id": t["id"],
        "source_platform": t["source_platform"],
        "tender_ref": str(t["id"]),          # lot raqami bo'lsa "id / lot" qiling
        "customer_name": t.get("customer_name"),
        "title": t.get("title"),
        "start_price": t.get("start_price"),
        "currency": t.get("currency"),
        "deadline_at": t.get("deadline_at"),
        "region_name": t.get("region_name"),
        "source_url": url_tpl.format(id=t["id"]) if url_tpl else None,
    }


def list_(status=None, broker_id=None, client_id=None, q=None, open_only=False):
    rows = db.query(OPP_LIST_SQL, {"status": status, "broker_id": broker_id,
                                   "client_id": client_id, "q": q or None,
                                   "open_only": open_only})
    return [shape(r) for r in rows]


def get(opp_id: int) -> dict:
    r = db.query_one(OPP_GET_SQL, {"id": opp_id})
    if not r:
        raise ErpError("Karta topilmadi.", 404)
    out = shape(r)
    out["history"] = [
        {"id": h["id"], "from_status": h["from_status"], "to_status": h["to_status"],
         "to_label": STATUS_LABEL.get(h["to_status"]), "changed_by": h["changed_by"],
         "note": h["note"], "changed_at": _iso(h["changed_at"])}
        for h in db.query(HISTORY_LIST_SQL, {"id": opp_id})]
    return out


def by_tender(tender_id: int) -> list:
    """TenderDrawer uchun: shu tender ishga olinganmi, qaysi mijozlar uchun."""
    return [shape(r) for r in db.query(OPP_BY_TENDER_SQL, {"tender_id": tender_id})]


def take(tender_id: int, data: dict) -> dict:
    """"Ishga olish". data: broker_id, client_id, priority, win_probability,
    note, next_task, next_task_at, created_by."""
    if data.get("priority") not in PRIORITIES:
        raise ErpError("Ustuvorlik: low | medium | high.")
    # Takror: bir tender + bir mijoz
    for ex in by_tender(tender_id):
        if (ex["client"] or {}).get("id") == data.get("client_id"):
            raise ErpError("Bu tender shu mijoz uchun allaqachon ishga olingan.",
                           409, opportunity_id=ex["id"])
    snap = _tender_snapshot(tender_id)
    params = {**snap, **{k: data.get(k) for k in (
        "broker_id", "client_id", "priority", "win_probability",
        "note", "next_task", "next_task_at", "created_by")}}
    row = db.execute_returning(OPP_INSERT_SQL, params)
    db.execute_returning(HISTORY_INSERT_SQL, {
        "opportunity_id": row["id"], "from_status": None, "to_status": "new",
        "changed_by": data.get("created_by"), "note": "Ishga olindi"})
    return get(row["id"])


def update(opp_id: int, data: dict) -> dict:
    if data.get("priority") not in PRIORITIES:
        raise ErpError("Ustuvorlik: low | medium | high.")
    row = db.execute_returning(OPP_UPDATE_SQL, {**data, "id": opp_id})
    if not row:
        raise ErpError("Karta topilmadi.", 404)
    return get(opp_id)


def set_status(opp_id: int, status: str, changed_by: Optional[str], note: Optional[str]) -> dict:
    if status not in STATUS_LABEL:
        raise ErpError("Noma'lum status.")
    cur = db.query_one(OPP_GET_SQL, {"id": opp_id})
    if not cur:
        raise ErpError("Karta topilmadi.", 404)
    if cur["status"] == status:
        return get(opp_id)
    # Yakuniydan qaytish — faqat izoh bilan (tarixda sabab qolishi kerak)
    if cur["status"] in FINAL and status not in FINAL and not (note or "").strip():
        raise ErpError("Yakuniy statusdan qaytarish uchun izoh majburiy.")
    db.execute_returning(OPP_STATUS_SQL, {"id": opp_id, "status": status})
    db.execute_returning(HISTORY_INSERT_SQL, {
        "opportunity_id": opp_id, "from_status": cur["status"], "to_status": status,
        "changed_by": changed_by, "note": note})
    return get(opp_id)


def brokers():
    return db.query(BROKERS_SQL)


def add_broker(full_name: str, email=None, phone=None):
    if not (full_name or "").strip():
        raise ErpError("Ism bo'sh.")
    return db.execute_returning(BROKER_INSERT_SQL,
                                {"full_name": full_name.strip(), "email": email, "phone": phone})


def clients():
    return db.query(CLIENTS_SQL)


def add_client(name: str):
    if not (name or "").strip():
        raise ErpError("Nom bo'sh.")
    return db.execute_returning(CLIENT_INSERT_SQL, {"name": name.strip()})
```

---

## 2. `api/erp/stats.py` — rahbar hisoboti

```python
"""Rahbar paneli. Hisob BAZADA (GROUP BY), frontendda emas."""
from api import db
from api.erp.opportunity import STATUS_LABEL, _num, _iso

BY_STATUS_SQL = """
SELECT status, count(*) AS n, coalesce(sum(start_price),0) AS total
FROM erp.opportunity GROUP BY status
"""
BY_BROKER_SQL = """
SELECT b.id, b.full_name, count(o.id) AS n,
       count(o.id) FILTER (WHERE o.status NOT IN ('won','lost','rejected')) AS open_n,
       count(o.id) FILTER (WHERE o.status = 'won') AS won_n,
       count(o.id) FILTER (WHERE o.status = 'lost') AS lost_n
FROM erp.broker b LEFT JOIN erp.opportunity o ON o.broker_id = b.id
GROUP BY b.id, b.full_name ORDER BY n DESC, b.full_name
"""
BY_CLIENT_SQL = """
SELECT c.id, c.name, count(o.id) AS n,
       count(o.id) FILTER (WHERE o.status = 'won') AS won_n,
       coalesce(sum(o.start_price) FILTER (WHERE o.status = 'won'),0) AS won_total
FROM erp.client_company c LEFT JOIN erp.opportunity o ON o.client_id = c.id
GROUP BY c.id, c.name ORDER BY n DESC, c.name
"""
UPCOMING_SQL = """
SELECT o.id, o.title, o.deadline_at, o.status, b.full_name AS broker_name, c.name AS client_name
FROM erp.opportunity o
LEFT JOIN erp.broker b ON b.id = o.broker_id
LEFT JOIN erp.client_company c ON c.id = o.client_id
WHERE o.status NOT IN ('won','lost','rejected')
  AND o.deadline_at IS NOT NULL
  AND o.deadline_at <= now() + (%(days)s || ' days')::interval
ORDER BY o.deadline_at
"""
MONTHLY_SQL = """
SELECT to_char(date_trunc('month', closed_at), 'YYYY-MM') AS month,
       count(*) FILTER (WHERE status='won') AS won,
       count(*) FILTER (WHERE status='lost') AS lost,
       count(*) FILTER (WHERE status='rejected') AS rejected
FROM erp.opportunity WHERE closed_at IS NOT NULL
GROUP BY 1 ORDER BY 1 DESC LIMIT 12
"""


def build(days: int = 7) -> dict:
    by_status = {r["status"]: {"n": r["n"], "total": _num(r["total"])}
                 for r in db.query(BY_STATUS_SQL)}
    statuses = [{"code": code, "label": label,
                 "n": by_status.get(code, {}).get("n", 0),
                 "total": by_status.get(code, {}).get("total", 0.0)}
                for code, label in STATUS_LABEL.items()]
    total = sum(s["n"] for s in statuses)
    won = by_status.get("won", {}).get("n", 0)
    lost = by_status.get("lost", {}).get("n", 0)
    return {
        "total": total,
        "open": sum(s["n"] for s in statuses if s["code"] not in ("won", "lost", "rejected")),
        "submitted": by_status.get("submitted", {}).get("n", 0),
        "won": won, "lost": lost,
        "rejected": by_status.get("rejected", {}).get("n", 0),
        "win_rate": (round(100 * won / (won + lost)) if (won + lost) else None),
        "by_status": statuses,
        "by_broker": db.query(BY_BROKER_SQL),
        "by_client": [{**r, "won_total": _num(r["won_total"])} for r in db.query(BY_CLIENT_SQL)],
        "upcoming": [{**r, "deadline_at": _iso(r["deadline_at"]),
                      "status_label": STATUS_LABEL.get(r["status"])}
                     for r in db.query(UPCOMING_SQL, {"days": str(days)})],
        "monthly": db.query(MONTHLY_SQL),
        "upcoming_days": days,
    }
```

---

## 3. `api/main.py` — ulash

### 3.1. Import (36-qatordagi `from api import ...` dan keyin, alohida qator)

```python
from api.erp import opportunity as erp_opp, stats as erp_stats  # noqa: E402
```

(ERP alohida paket — umumiy import qatoriga qo'shilmaydi, parallel agentlar
o'sha qatorni o'zgartiradi.)

### 3.2. So'rov modellari (`...In` modellari yoniga)

```python
class OpportunityIn(BaseModel):
    """Xodim kiritadigan maydonlar. Snapshot serverda tenderdan olinadi."""
    broker_id: Optional[int] = None
    client_id: Optional[int] = None
    priority: str = "medium"              # low | medium | high
    win_probability: Optional[int] = None # 0..100
    note: Optional[str] = None
    next_task: Optional[str] = None
    next_task_at: Optional[date] = None
    created_by: Optional[str] = None      # auth yo'q: tanlangan broker nomi


class OpportunityStatusIn(BaseModel):
    status: str
    changed_by: Optional[str] = None
    note: Optional[str] = None            # yakuniydan qaytishda MAJBURIY


class BrokerIn(BaseModel):
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None


class ClientCompanyIn(BaseModel):
    name: str
```

`date` importi (`compliance.md` 2-bo'limda ham kerak edi): `from datetime import date`.

### 3.3. Endpointlar (fayl oxiriga — `/match` va narx hisobi bloklaridan keyin)

```python
# ---------------------------------------------------------------------------
# ERP 1-BOSQICH — "Ishga olish" + Opportunity pipeline. Mantiq api/erp/ da.
# public.* faqat o'qiladi. AI yo'q.
# ---------------------------------------------------------------------------
def _erp(fn, *a, **kw):
    """ErpError -> HTTP kodi (400/404/409); 409 da mavjud karta id si ham qaytadi."""
    try:
        return fn(*a, **kw)
    except erp_opp.ErpError as e:
        detail = {"message": str(e), **e.extra} if e.extra else str(e)
        raise HTTPException(status_code=e.code, detail=detail)


@app.get("/erp/meta")
def erp_meta():
    """Statuslar va ustuvorliklar — Kanban ustunlari va formalar shundan."""
    return {"statuses": [{"code": c, "label": l, "final": c in erp_opp.FINAL}
                         for c, l in erp_opp.STATUSES],
            "priorities": [{"code": c, "label": l} for c, l in erp_opp.PRIORITIES.items()]}


@app.get("/erp/opportunities")
def erp_list(status: Optional[str] = None, broker_id: Optional[int] = None,
             client_id: Optional[int] = None, q: Optional[str] = None,
             open_only: bool = False):
    return erp_opp.list_(status, broker_id, client_id, q, open_only)


@app.get("/erp/opportunities/{opp_id}")
def erp_get(opp_id: int):
    return _erp(erp_opp.get, opp_id)


@app.put("/erp/opportunities/{opp_id}")
def erp_update(opp_id: int, body: OpportunityIn):
    return _erp(erp_opp.update, opp_id, body.model_dump(exclude={"created_by"}))


@app.patch("/erp/opportunities/{opp_id}/status")
def erp_status(opp_id: int, body: OpportunityStatusIn):
    return _erp(erp_opp.set_status, opp_id, body.status, body.changed_by, body.note)


@app.get("/tenders/{tender_id}/opportunities")
def tender_opportunities(tender_id: int):
    """Tender paneli uchun: ishga olinganmi (qaysi mijozlar uchun)."""
    return erp_opp.by_tender(tender_id)


@app.post("/tenders/{tender_id}/take", status_code=201)
def tender_take(tender_id: int, body: OpportunityIn):
    """"ISHGA OLISH" — tender ro'yxatdan ichki kartaga aylanadi."""
    return _erp(erp_opp.take, tender_id, body.model_dump())


@app.get("/erp/brokers")
def erp_brokers():
    return erp_opp.brokers()


@app.post("/erp/brokers", status_code=201)
def erp_add_broker(b: BrokerIn):
    return _erp(erp_opp.add_broker, b.full_name, b.email, b.phone)


@app.get("/erp/clients")
def erp_clients():
    return erp_opp.clients()


@app.post("/erp/clients", status_code=201)
def erp_add_client(c: ClientCompanyIn):
    return _erp(erp_opp.add_client, c.name)


@app.get("/erp/stats")
def erp_stats_view(days: int = Query(7, ge=1, le=90)):
    """Rahbar paneli: qancha ishga olingan / topshirilgan / yutilgan /
    yutqazilgan / rad etilgan; broker va mijoz bo'yicha; yaqin deadline'lar."""
    return erp_stats.build(days)
```

> Marshrut to'qnashuvi yo'q: `/tenders/{id}/take` va
> `/tenders/{id}/opportunities` — mavjud `/tenders/{id}/compliance`,
> `/pricing`, `/stock-check` bilan bir qatorda, boshqa nom.

### Javob shakli — `GET /erp/opportunities/{id}`

```jsonc
{
  "id": 12, "tender_id": 7886728,
  "tender": { "source_platform": "xt-xarid", "tender_ref": "7886728",
              "customer_name": "AGROBANK ATB", "title": "Server infratuzilmasi xaridi",
              "start_price": 17128200000, "currency": "UZS",
              "deadline_at": "2026-07-31T18:51:00+05:00", "region_name": "Toshkent shahri",
              "source_url": "https://xt-xarid.uz/procedure/7886728/core" },
  "broker": { "id": 2, "name": "A. Karimov" },
  "client": { "id": 5, "name": "Alfa Trade MChJ" },
  "priority": "high", "priority_label": "Yuqori", "win_probability": 60,
  "note": "...", "next_task": "Mijozga KP yuborish", "next_task_at": "2026-07-25",
  "status": "sent_to_client", "status_label": "Mijozga yuborildi", "is_final": false,
  "status_changed_at": "...", "closed_at": null,
  "history": [ { "from_status": null, "to_status": "new", "changed_by": "A. Karimov",
                 "note": "Ishga olindi", "changed_at": "..." }, "..." ]
}
```

---

## 4. `frontend/src/api.js` — chaqiruvlar

`api` obyektiga (oxiriga) qo'shiladi:

```js
  // ERP 1-bosqich — "Ishga olish" + opportunity pipeline
  erpMeta: () => request('GET', '/erp/meta'),
  erpOpportunities: (params) => request('GET', '/erp/opportunities', { params }),
  erpOpportunity: (id) => request('GET', `/erp/opportunities/${id}`),
  erpUpdateOpportunity: (id, body) => request('PUT', `/erp/opportunities/${id}`, { body }),
  erpSetStatus: (id, body) => request('PATCH', `/erp/opportunities/${id}/status`, { body }),
  tenderOpportunities: (tenderId) => request('GET', `/tenders/${tenderId}/opportunities`),
  takeTender: (tenderId, body) => request('POST', `/tenders/${tenderId}/take`, { body }),
  erpBrokers: () => request('GET', '/erp/brokers'),
  erpAddBroker: (body) => request('POST', '/erp/brokers', { body }),
  erpClients: () => request('GET', '/erp/clients'),
  erpAddClient: (body) => request('POST', '/erp/clients', { body }),
  erpStats: (params) => request('GET', '/erp/stats', { params }),
```

> `request()` `PATCH` ni qo'llab-quvvatlamasa (faqat GET/POST/PUT/DELETE
> bo'lsa) — `erpSetStatus` uchun `PUT` ishlatib, `main.py` da ham
> `@app.put(...)` qiling. Ikkalasi ham bir joyda o'zgaradi.

---

## 5. `frontend/src/components/TenderDrawer.jsx` — "Ishga olish" tugmasi

**5.1.** Import (`GoNoGo` yoniga):

```jsx
import TakeTenderDialog from './erp/TakeTenderDialog.jsx'
```

**5.2.** Imzoga `onOpenOpportunity` qo'shiladi:

```jsx
export default function TenderDrawer({ id, match, onClose, onOpenDocuments, onOpenOpportunity }) {
```

**5.3.** Sarlavha yonida (tender nomi chiqqan blokdan keyin):

```jsx
            {/* ERP — "Ishga olish": tender ichki opportunity kartasiga aylanadi.
                Komponent o'zi /tenders/{id}/opportunities ni so'rab, ishga
                olingan bo'lsa nishon + "Kartaga o'tish", bo'lmasa tugma ko'rsatadi. */}
            <TakeTenderDialog tenderId={t.id} onOpenOpportunity={onOpenOpportunity} />
```

`onOpenOpportunity` ixtiyoriy: berilmasa "Kartaga o'tish" havolasi ko'rinmaydi.

### `TakeTenderDialog.jsx` — xatti-harakati

- Yuklanganda `api.tenderOpportunities(tenderId)`.
- Natija bo'sh → **"Ishga olish"** tugmasi → forma (modal): broker (dropdown +
  "+ yangi"), mijoz (dropdown + "+ yangi"), ustuvorlik (3 tugma), yutish
  ehtimoli (0–100 slayder, ixtiyoriy), izoh, keyingi vazifa + sanasi.
  `created_by` = tanlangan brokerning nomi.
- `api.takeTender(...)` → 201 → nishon `Ishga olingan · Yangi · <broker> · <mijoz>`
  + "Kartaga o'tish" + "Yana bir mijoz uchun ishga olish".
- 409 → forma ichida: "Bu mijoz uchun allaqachon ishga olingan" + mavjud
  kartaga havola (`detail.opportunity_id`).

---

## 6. `frontend/src/components/Sidebar.jsx` — yangi bo'lim

`NAV` massiviga (`catalog`/`documents` dan keyin):

```js
  { key: 'opportunities', icon: 'briefcase', label: 'Ishdagi tenderlar' },
```

`briefcase` ikoni `Icon.jsx` da bo'lmasa — mavjud `clip` yoki `list`
ishlating; yangi ikon qo'shish umumiy faylga tegadi, shart emas.

---

## 7. `frontend/src/App.jsx` — sahifani ulash

**7.1.** Import:

```jsx
import OpportunitiesPage from './components/erp/OpportunitiesPage.jsx'
```

**7.2.** Holat (`docFocus` yoniga):

```jsx
  // Tender panelidan kartaga o'tilganda qaysi opportunity ochilsin
  const [oppFocus, setOppFocus] = useState(null)
```

**7.3.** O'tish funksiyasi (`openDocuments` dan keyin):

```jsx
  function openOpportunity(oppId) {
    setOppFocus(oppId || null)
    setSelected(null)
    setView('opportunities'); setOffset(0)
  }
```

**7.4.** Sahifa (`{view === 'documents' && ...}` yoniga):

```jsx
        {view === 'opportunities' && (
          <OpportunitiesPage focusId={oppFocus}
                             onOpenTender={(tenderId) => setSelected({ id: tenderId })} />
        )}
```

`onOpenTender` — kartadan asl tender paneliga qaytish (Go/No-Go, moslik
ballini ko'rish uchun).

**7.5.** Drawer'ga uzatish:

```jsx
        <TenderDrawer id={selected.id} match={selected.match}
                      onClose={...}
                      onOpenDocuments={openDocuments}
                      onOpenOpportunity={openOpportunity} />
```

---

## 8. `OpportunitiesPage.jsx` — tuzilma

```
[ Kanban | Jadval | Hisobot ]   filtr: broker ▾  mijoz ▾  status ▾  [qidiruv]  ☐ faqat ochiq
```

- **Kanban** (`OpportunityBoard.jsx`): 9 ustun `GET /erp/meta` dan; karta:
  nom, mijoz, broker, deadline (rangli: <3 kun qizil, <7 sariq), summa,
  ustuvorlik nishoni. Drag-and-drop → `api.erpSetStatus(id, {status,
  changed_by})`. Yakuniy ustunga tashlanganda — tasdiqlash; yakuniydan
  chiqarishda — izoh so'raladi (400 bo'lsa forma qayta ochiladi).
  Kutubxona shart emas: HTML5 `draggable` + `onDrop` yetarli.
- **Jadval** (`OpportunityTable.jsx`): Tender · Mijoz · Mas'ul · Deadline ·
  Summa · Status; ustun sarlavhasi bosilsa saralash (mijoz tomonda);
  qator bosilsa karta.
- **Karta** (`OpportunityCard.jsx`, drawer): chap — snapshot (o'zgarmas,
  "Manbada ochish" havolasi, "Tender panelini ochish"); o'ng — xodim
  maydonlari (tahrir → `api.erpUpdateOpportunity`), status tanlagich,
  tarix. Pastda tablar: **Hujjatlar** (`tender_document` ro'yxati —
  mavjud `api.tender(id)` javobidan), **Cheklist** (`<CompliancePanel
  tenderId={tender_id} />`), **Narx hisobi** (`<PricingPanel tender={t} />`),
  **Ombor** (`<StockCheck tenderId={tender_id} />`). Tablar faqat
  ochilganda yuklanadi.
- **Hisobot** (`OpportunityStats.jsx`): `api.erpStats({days: 7})` —
  yuqorida 6 ta raqam (jami / ochiq / topshirilgan / yutilgan / yutqazilgan /
  rad etilgan + yutish foizi), status bo'yicha gorizontal chiziqlar,
  broker jadvali, mijoz jadvali, "7 kun ichidagi deadline'lar" ro'yxati.
  Grafik kutubxonasi kerak emas — CSS chiziqlar.

`focusId` berilsa sahifa ochilishi bilan o'sha karta drawer'da ochiladi.

---

## 9. Sinov — `_tests/erp_test.py`

```
.venv/Scripts/python.exe _tests/erp_test.py
```

`fastapi.testclient.TestClient`, uvicorn ishga tushirilmaydi. Tekshiriladi:

1. `GET /erp/meta` — 9 status, 3 ustuvorlik, yakuniylar belgilangan.
2. Broker va mijoz qo'shish (`ZZTEST ` prefiksi bilan).
3. Bazadagi **haqiqiy** tenderni ishga olish → 201, snapshot 9 maydon
   to'lgan, `status=new`, tarixda 1 yozuv.
4. O'sha tender + o'sha mijoz → **409**, `detail.opportunity_id` mavjud.
5. O'sha tender + boshqa mijoz → 201 (ikkinchi karta).
6. Mavjud bo'lmagan tender → 404.
7. `priority='xxx'` → 400.
8. Status: `new → reviewing → submitted → won` — har qadam tarixga;
   `won → preparing` izohsiz → 400; izoh bilan → 200, `closed_at` null.
9. `PUT` xodim maydonlarini o'zgartiradi, snapshot va status **o'zgarmaydi**.
10. Filtrlar: `status`, `broker_id`, `client_id`, `q`, `open_only`.
11. `GET /erp/stats` — sonlar mos.
12. **Chegara sinovi:** sinov boshida va oxirida `public.tender`,
    `public.tender_document`, `public.company_profile`, `public.catalog_product`
    qator soni va `max(updated_at)` bir xil — ERP `public.*` ga yozmagan.
13. `finally`: `erp.opportunity_history` → `erp.opportunity` → `erp.broker`
    → `erp.client_company` dan `ZZTEST` yozuvlari o'chiriladi, tekshiriladi.

---

## 10. Nima QILINMAYDI (ongli chegara)

- Opportunity **o'chirilmaydi** — `rejected` + izoh.
- Status **ketma-ketligi majburlanmaydi** (ochiq ↔ ochiq erkin).
- Auth yo'q: `created_by`/`changed_by` — tanlangan broker nomi (matn).
- Fayl yuklash yo'q; hujjatlar — tenderniki, jonli.
- Bildirishnoma yo'q (3-bosqich).
- Snapshot tender bilan qayta **sinxronlanmaydi** (2-bosqichda "tenderda
  yangilanish bor" belgisi qo'shilishi mumkin — snapshot o'zgarmaydi).
- `queries.py`, `compliance.py`, `pricing.py`, `stock.py` **o'zgarmaydi**.
