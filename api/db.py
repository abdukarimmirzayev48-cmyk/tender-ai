"""
DB qatlami — PostgreSQL connection pool va query yordamchilari.

Dizayn:
  - .env dan XT_DB_DSN o'qiladi (ETL bilan bir xil o'zgaruvchi).
  - psycopg2 ThreadedConnectionPool ishlatamiz: FastAPI sync-endpointlarni
    threadpool'da ishlatadi, shuning uchun thread-safe pool kerak.
  - RealDictCursor — natijalar dict ko'rinishida (JSON'ga oson).
  - Pool lifespan'da (main.py) init/close qilinadi.
"""
import os
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

_pool: Optional[ThreadedConnectionPool] = None


class DBUnavailable(RuntimeError):
    """Baza mavjud emas yoki so'rov muvaffaqiyatsiz — API buni 503 ga aylantiradi."""


def init_pool() -> None:
    """Pool'ni yaratadi. main.py lifespan startup'da chaqiriladi."""
    global _pool
    if _pool is not None:
        return
    dsn = os.environ.get("XT_DB_DSN")
    if not dsn:
        raise RuntimeError(
            "XT_DB_DSN o'rnatilmagan. .env faylini yarating (.env.example dan nusxa)."
        )
    mn = int(os.environ.get("DB_POOL_MIN", "1"))
    mx = int(os.environ.get("DB_POOL_MAX", "8"))
    try:
        _pool = ThreadedConnectionPool(mn, mx, dsn=dsn, cursor_factory=RealDictCursor)
    except psycopg2.Error as e:
        raise DBUnavailable(f"Pool yaratib bo'lmadi: {e}") from e


def close_pool() -> None:
    """Pool'ni yopadi. lifespan shutdown'da chaqiriladi."""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


@contextmanager
def get_conn():
    """Pool'dan connection oladi va qaytaradi (context manager)."""
    if _pool is None:
        raise DBUnavailable("DB pool ishga tushmagan.")
    conn = None
    try:
        conn = _pool.getconn()
        yield conn
    finally:
        if conn is not None:
            _pool.putconn(conn)


def query(sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Ko'p qatorli SELECT — dict'lar ro'yxatini qaytaradi."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params or {})
                rows = cur.fetchall()
            conn.rollback()  # faqat o'qish — tranzaksiyani ochiq qoldirmaymiz
            return [dict(r) for r in rows]
    except psycopg2.Error as e:
        raise DBUnavailable(str(e)) from e


def query_one(sql: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Bitta qator (yoki None)."""
    rows = query(sql, params)
    return rows[0] if rows else None


def scalar(sql: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """Bitta qiymat (birinchi qator, birinchi ustun)."""
    row = query_one(sql, params)
    if not row:
        return None
    return next(iter(row.values()))


def execute_returning(sql: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """YOZISH (INSERT/UPDATE ... RETURNING) — commit qiladi. query() faqat o'qish
    uchun (u rollback qiladi), shuning uchun yozuvlar shu funksiyadan o'tishi SHART."""
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params or {})
                row = cur.fetchone()
            conn.commit()
            return dict(row) if row else None
        except psycopg2.Error as e:
            conn.rollback()
            raise DBUnavailable(str(e)) from e
