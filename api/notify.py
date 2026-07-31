"""
BILDIRISHNOMA (TZ P0-10) — "yangi mos tender chiqdi" xabari
===========================================================
FOYDALANUVCHI HIKOYASI: "Broker-operator sifatida, men mosligi yuqori bo'lgan
tender paydo bo'lsa, bildirishnoma olishni xohlayman, tizimni doimiy
tekshirmaslik uchun."

IKKI KANAL, BITTA MANTIQ:
  EMAIL    — SMTP orqali (`send()`), sozlamaда `enabled`
  TELEGRAM — Bot API orqali (`send_telegram()`), sozlamaда `telegram_enabled`
Kanallar MUSTAQIL yoqiladi, lekin MOSLIK CHEGARASI (`min_score`), kuzatuv
oynasi va ballash ULARDA BIR XIL — nomzodlar bir marta hisoblanib, ikkala
kanalga tarqatiladi. Sabab: chegara ikki joyda saqlansa ular ertami-kechmi
bir-biridan uzoqlashadi va foydalanuvchi nega Telegram boshqa natija
berayotganini tushunmay qoladi.

QABUL QILISH MEZONLARI va ular qayerda bajarilgani:
  [x] SOATLIK KUZATISH TSIKLI DAVOMIDA keladi
      -> `find_candidates()` faqat OXIRGI ETL TSIKLIDAN keyin birinchi marta
         ko'rilgan (`tender.first_seen_at`) tenderlarni oladi. Skript
         `notify_new.py` ETL dan keyin (soatlik jadvalда) chaqiriladi.
  [x] TIZIMDAGI TENDER KARTOCHKASIGA HAVOLA
      -> `card_url()`: base_url + '/?tender=<id>'. Havola HAR UCH versiyada:
         email matni, email HTML (`render()`) va Telegram (`render_telegram()`).

BALL QAYERDAN OLINADI — YANGI MANTIQ YOZILMAGAN, mavjudi qayta ishlatilgan:
  1) KATALOG (api/main.py `_product_matches` + `/catalog/match` shkalasi):
         kategoriya mosligi = 100, faqat nom/kalit so'z mosligi = 70
  2) PROFIL (api/matching.py `score_tender`): 0–100
         kalit so'z 60 + hudud 20 + byudjet 15 + valyuta 5
  Yakuniy ball = IKKISINING KATTASI. Sabab: katalog bo'sh bo'lsa profil
  ishlaydi, profil bo'sh bo'lsa katalog ishlaydi — foydalanuvchi bittasini
  to'ldirsa ham bildirishnoma jonlanadi.

SIRLAR BAZADA EMAS: `.env` dagi `SMTP_PASSWORD` va `TELEGRAM_BOT_TOKEN`.
Ular yo'q bo'lsa `NotifyError`/`TelegramError` otiladi — JIMGINA O'TILMAYDI.
"""
import os
import re
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from html import escape
from typing import Any, Dict, List, Optional, Tuple

from api import db, matching, queries, telegram

# Xabar turi/kanali (notify_sent.kind). HAR KANAL O'Z JURNALINI yuritadi:
# aks holda email allaqachon "yuborilgan" deb belgilagan tenderlar keyinroq
# yoqilgan Telegramga hech qachon tushmasdi.
KIND_NEW_MATCH = "new_match"          # email
KIND_TG_PREFIX = "new_match_tg:"      # telegram — HAR OBUNACHI uchun alohida


def tg_kind(chat_id: str) -> str:
    """Telegram obunachisining jurnal kaliti.

    NEGA CHAT BO'YICHA: obunachi bittadan ko'p bo'lishi mumkin. Agar hammasi
    bitta 'new_match_tg' qatoriga tayansa, birinchi obunachiga yuborilgan
    tender qolganlariga HECH QACHON ketmasdi.
    """
    return f"{KIND_TG_PREFIX}{chat_id}"

# Bir xabarда nechta tender ko'rsatiladi (standart). Ko'pi "va yana N ta" bo'lib
# qisqaradi — pochta xabari o'qilmaydigan darajada uzun bo'lmasligi uchun.
DEFAULT_LIMIT = 20

# Nomzod tenderlar SQL chegarasi (main.py MATCH_CAP bilan bir xil g'oya:
# ballash Pythonда, LIMIT esa SQLда).
CANDIDATE_CAP = 3000

# ETL tsikli oynasi: bitta tsiklда bir necha manba ketma-ket yuriladi
# (xt-xarid, uzex...). Ular bir necha daqiqa ichida boshlanadi, shuning uchun
# "oxirgi tsikl" = eng oxirgi start atrofidagi SHU OYNAга tushgan yurishlar.
CYCLE_WINDOW = "30 minutes"

# etl_run bo'sh bo'lsa (ETL hali yurmagan) shu oynaга qaytamiz — soatlik tsikl.
FALLBACK_HOURS = 1


class NotifyError(RuntimeError):
    """Bildirishnoma yuborib bo'lmadi (sozlama/SMTP xatosi). API buni 400/503
    ga aylantiradi, skript esa aniq matn bilan to'xtaydi."""


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------
_NS_COLS = ("id, enabled, email, min_score, smtp_host, smtp_port, smtp_user, "
            "smtp_use_tls, from_email, base_url, telegram_enabled, "
            "telegram_chat_id, updated_at")

SETTINGS_GET_SQL = f"SELECT {_NS_COLS} FROM notify_settings WHERE id = 1"

# `schema_patch_notify_telegram.sql` qo'llanmagan bazada Telegram ustunlari yo'q.
# Ularsiz SELECT "column does not exist" bilan yiqilardi va MAVJUD EMAIL
# bildirishnomasi ham ishlamay qolardi — patch esa alohida qadamда qo'llanadi.
# Shuning uchun ustunlar borligi BIR MARTA tekshiriladi va yo'q bo'lsa modul
# eski ustunlar bilan ishlayveradi (Telegram bo'limi esa "patch kerak" deydi).
TG_COLS_SQL = """
SELECT count(*) = 2 AS ok FROM information_schema.columns
WHERE table_name = 'notify_settings'
  AND column_name IN ('telegram_enabled', 'telegram_chat_id')
"""

_LEGACY_COLS = ("id, enabled, email, min_score, smtp_host, smtp_port, smtp_user, "
                "smtp_use_tls, from_email, base_url, updated_at")

LEGACY_SETTINGS_GET_SQL = f"SELECT {_LEGACY_COLS} FROM notify_settings WHERE id = 1"

_tg_cols: Optional[bool] = None


def telegram_columns_ready() -> bool:
    """Telegram ustunlari bazadami. Natija keshlanadi — har so'rovда
    information_schema ni qidirmaslik uchun."""
    global _tg_cols
    if _tg_cols is None:
        try:
            _tg_cols = bool(db.scalar(TG_COLS_SQL))
        except db.DBUnavailable:
            return False          # baza yo'q — keshlamaymiz, keyin qayta uriniladi
    return _tg_cols


# ---------------------------------------------------------------------------
# Telegram obunachilari
# ---------------------------------------------------------------------------
# MODEL: botga /start bosgan (yoki bot qo'shilgan guruhда yozilgan) HAR BIR
# suhbat obunachi bo'ladi va xabar oladi. Sozlamalardagi bitta
# `telegram_chat_id` ENDI ISHLATILMAYDI (patch uni obunachiga ko'chirgan) —
# ustun faqat orqaga moslik uchun qolgan.
SUB_TABLE_SQL = """
SELECT count(*) = 1 AS ok FROM information_schema.tables
WHERE table_name = 'notify_telegram_subscriber'
"""

_SUB_COLS = ("chat_id, title, chat_type, username, enabled, source, "
             "first_seen_at, last_seen_at")

SUBS_LIST_SQL = (f"SELECT {_SUB_COLS} FROM notify_telegram_subscriber "
                 "ORDER BY enabled DESC, last_seen_at DESC")

SUBS_ENABLED_SQL = ("SELECT chat_id, title FROM notify_telegram_subscriber "
                    "WHERE enabled ORDER BY first_seen_at")

# Ulash havolasi bilan tasdiqlangan suhbat -> obunachi.
#
# `enabled = TRUE` va `source = 'link'` QAYTA KELGANDA HAM qo'yiladi: havolani
# bosish — foydalanuvchining ANIQ harakati, ya'ni "menga xabar yuboring"
# degani. Shu sabab ilgari o'chirilgan (yoki eski usulda qo'shilgan) suhbat
# qayta ulanganда tiklanadi.
SUB_UPSERT_SQL = f"""
INSERT INTO notify_telegram_subscriber
    (chat_id, title, chat_type, username, enabled, source)
VALUES (%(chat_id)s, %(title)s, %(chat_type)s, %(username)s, TRUE, 'link')
ON CONFLICT (chat_id) DO UPDATE SET
    title = COALESCE(EXCLUDED.title, notify_telegram_subscriber.title),
    chat_type = COALESCE(EXCLUDED.chat_type, notify_telegram_subscriber.chat_type),
    username = COALESCE(EXCLUDED.username, notify_telegram_subscriber.username),
    enabled = TRUE,
    source = 'link',
    last_seen_at = now()
RETURNING {_SUB_COLS}, (xmax = 0) AS inserted
"""

SUB_SET_ENABLED_SQL = (f"UPDATE notify_telegram_subscriber SET enabled = %(enabled)s "
                       f"WHERE chat_id = %(chat_id)s RETURNING {_SUB_COLS}")

SUB_DELETE_SQL = ("DELETE FROM notify_telegram_subscriber WHERE chat_id = %(chat_id)s "
                  "RETURNING chat_id")

_sub_table: Optional[bool] = None


def subscribers_ready() -> bool:
    """`notify_telegram_subscriber` jadvali bazadami (patch qo'llanganmi)."""
    global _sub_table
    if _sub_table is None:
        try:
            _sub_table = bool(db.scalar(SUB_TABLE_SQL))
        except db.DBUnavailable:
            return False
    return _sub_table


def subscribers() -> List[Dict[str, Any]]:
    """Barcha obunachilar (o'chirilganlari ham — interfeys ularni ko'rsatadi)."""
    if not subscribers_ready() or not links_ready():
        return []
    rows = db.query(SUBS_LIST_SQL)
    for r in rows:
        for k in ("first_seen_at", "last_seen_at"):
            r[k] = r[k].isoformat() if r.get(k) else None
    return rows


def enabled_subscribers() -> List[Dict[str, Any]]:
    """Xabar ketadigan obunachilar."""
    if not subscribers_ready():
        return []
    return db.query(SUBS_ENABLED_SQL)


# ---------------------------------------------------------------------------
# Telegramni ULASH — bir martalik havola (deep link)
# ---------------------------------------------------------------------------
# OQIM:
#   1. Foydalanuvchi interfeysда "Telegramni ulash" ni bosadi.
#   2. Platforma bir martalik token yaratadi va havola beradi:
#          https://t.me/<bot_username>?start=<token>
#   3. Foydalanuvchi havolani bosadi -> Telegram botni ochadi -> "Start".
#      Telegram botga AYNAN `/start <token>` xabarini yuboradi.
#   4. `consume_links()` `getUpdates` dan o'sha tokenli xabarni topadi va
#      chatni obunachi qilib yozadi.
#
# NEGA TOKEN: tokensiz /start bosgan HAR QANDAY odam obunachi bo'lardi —
# botni topgan begona ham, bot tasodifan qo'shilgan guruh ham. Token esa
# "bu suhbat platformadagi foydalanuvchiga tegishli" degan YAGONA dalil.
LINK_TTL_MIN = 30
_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{16,64}")

LINK_CREATE_SQL = """
INSERT INTO notify_telegram_link (token, expires_at)
VALUES (%(token)s, now() + INTERVAL '%(ttl)s minutes')
RETURNING token, created_at, expires_at
"""

# Ochiq (ishlatilmagan, muddati o'tmagan) tokenlar
LINK_OPEN_SQL = ("SELECT token FROM notify_telegram_link "
                 "WHERE used_at IS NULL AND expires_at > now()")

LINK_USE_SQL = """
UPDATE notify_telegram_link SET chat_id = %(chat_id)s, used_at = now()
WHERE token = %(token)s AND used_at IS NULL AND expires_at > now()
RETURNING token, chat_id
"""

LINK_STATUS_SQL = ("SELECT token, chat_id, used_at, expires_at "
                   "FROM notify_telegram_link WHERE token = %(token)s")


def links_ready() -> bool:
    """Ulash jadvali bazadami."""
    try:
        return bool(db.scalar(
            "SELECT count(*) = 1 FROM information_schema.tables "
            "WHERE table_name = 'notify_telegram_link'"))
    except db.DBUnavailable:
        return False


def create_link() -> Dict[str, Any]:
    """Bir martalik ulash havolasini yaratadi.

    Bot username `getMe` dan olinadi — havola AYNAN shu botga ketishi kerak,
    aks holda foydalanuvchi boshqa botni ochib, hech narsa ishlamaydi.
    """
    if not links_ready():
        raise NotifyError(
            "Ulash jadvali yo'q. Ishga tushiring: "
            "psql ... -f schema_patch_notify_link.sql")
    try:
        bot = telegram.get_me()
    except telegram.TelegramError as e:
        raise NotifyError(str(e)) from e
    username = bot.get("username")
    if not username:
        raise NotifyError("Bot username aniqlanmadi — tokenni tekshiring.")

    token = secrets.token_urlsafe(18)      # ~24 belgi, [A-Za-z0-9_-]
    row = db.execute_returning(LINK_CREATE_SQL, {"token": token,
                                                 "ttl": LINK_TTL_MIN})
    return {
        "token": token,
        "url": f"https://t.me/{username}?start={token}",
        "bot": username,
        "expires_at": row["expires_at"].isoformat() if row else None,
        "ttl_minutes": LINK_TTL_MIN,
    }


def link_status(token: str) -> Dict[str, Any]:
    """Havola ishlatilganmi (interfeys shuni kutib turadi)."""
    row = db.query_one(LINK_STATUS_SQL, {"token": token})
    if not row:
        return {"found": False, "connected": False}
    return {
        "found": True,
        "connected": row["used_at"] is not None,
        "chat_id": row["chat_id"],
        "expired": row["used_at"] is None and row["expires_at"] < datetime.now(
            timezone.utc),
    }


def consume_links() -> Dict[str, Any]:
    """`getUpdates` dan TOKENLI xabarlarni topib, chatni obunachi qiladi.

    IKKI JOYDAN chaqiriladi: bildirishnoma tsiklidan (soatiga bir marta) va
    interfeysdagi "ulanishni tekshirish" so'rovidan — foydalanuvchi havolani
    bosgach bir necha soniyada natijani ko'rsin.

    TOKENSIZ /start E'TIBORGA OLINMAYDI — aynan shu narsa begona odamning
    obunachi bo'lib qolishini to'xtatadi.
    """
    if not subscribers_ready() or not links_ready():
        raise NotifyError(
            "Obunachilar/ulash jadvali yo'q. Ishga tushiring: "
            "psql ... -f schema_patch_notify_subscribers.sql va "
            "psql ... -f schema_patch_notify_link.sql")
    try:
        chats = telegram.discover_chats()
    except telegram.TelegramError as e:
        raise NotifyError(str(e)) from e

    open_tokens = {r["token"] for r in db.query(LINK_OPEN_SQL)}
    if not open_tokens:
        return {"seen": len(chats), "added": 0, "added_chats": []}

    added: List[str] = []
    for c in chats:
        # Xabar matnidan token qidiramiz. "/start <token>" ham, tokenning
        # o'zi qo'lда yozilgani ham qabul qilinadi (guruhда qulay).
        found = None
        for text in c.get("texts") or []:
            for cand in _TOKEN_RE.findall(text):
                if cand in open_tokens:
                    found = cand
                    break
            if found:
                break
        if not found:
            continue

        # Tokenni BAND qilamiz — SQL sharti (`used_at IS NULL`) tufayli
        # ikki marta ishlatib bo'lmaydi.
        used = db.execute_returning(LINK_USE_SQL, {"token": found,
                                                   "chat_id": c["chat_id"]})
        if not used:
            continue
        open_tokens.discard(found)
        row = db.execute_returning(SUB_UPSERT_SQL, {
            "chat_id": c["chat_id"], "title": c.get("title"),
            "chat_type": c.get("type"), "username": c.get("username"),
        })
        if row:
            added.append(c["chat_id"])
    return {"seen": len(chats), "added": len(added), "added_chats": added}


# Eski nom — `run()` va sinovlar shu nomni ishlatadi.
sync_subscribers = consume_links

# Bitta faol yozuv — bor bo'lsa yangilanadi (schema patch uni yaratib qo'ygan,
# lekin patch qo'llanmaган bazaда ham ishlashi uchun INSERT ... ON CONFLICT).
SETTINGS_UPSERT_SQL = f"""
INSERT INTO notify_settings (
    id, enabled, email, min_score, smtp_host, smtp_port, smtp_user,
    smtp_use_tls, from_email, base_url, telegram_enabled, telegram_chat_id,
    updated_at)
VALUES (1, %(enabled)s, %(email)s, %(min_score)s, %(smtp_host)s, %(smtp_port)s,
        %(smtp_user)s, %(smtp_use_tls)s, %(from_email)s, %(base_url)s,
        %(telegram_enabled)s, %(telegram_chat_id)s, now())
ON CONFLICT (id) DO UPDATE SET
    enabled=EXCLUDED.enabled, email=EXCLUDED.email, min_score=EXCLUDED.min_score,
    smtp_host=EXCLUDED.smtp_host, smtp_port=EXCLUDED.smtp_port,
    smtp_user=EXCLUDED.smtp_user, smtp_use_tls=EXCLUDED.smtp_use_tls,
    from_email=EXCLUDED.from_email, base_url=EXCLUDED.base_url,
    telegram_enabled=EXCLUDED.telegram_enabled,
    telegram_chat_id=EXCLUDED.telegram_chat_id, updated_at=now()
RETURNING {_NS_COLS}
"""

# Telegram ustunlari yo'q bazada ishlatiladigan variant (patchgacha).
LEGACY_SETTINGS_UPSERT_SQL = f"""
INSERT INTO notify_settings (
    id, enabled, email, min_score, smtp_host, smtp_port, smtp_user,
    smtp_use_tls, from_email, base_url, updated_at)
VALUES (1, %(enabled)s, %(email)s, %(min_score)s, %(smtp_host)s, %(smtp_port)s,
        %(smtp_user)s, %(smtp_use_tls)s, %(from_email)s, %(base_url)s, now())
ON CONFLICT (id) DO UPDATE SET
    enabled=EXCLUDED.enabled, email=EXCLUDED.email, min_score=EXCLUDED.min_score,
    smtp_host=EXCLUDED.smtp_host, smtp_port=EXCLUDED.smtp_port,
    smtp_user=EXCLUDED.smtp_user, smtp_use_tls=EXCLUDED.smtp_use_tls,
    from_email=EXCLUDED.from_email, base_url=EXCLUDED.base_url, updated_at=now()
RETURNING {_LEGACY_COLS}
"""

# Profil emaili — sozlamada email bo'sh bo'lsa zaxira manba.
PROFILE_EMAIL_SQL = ("SELECT email FROM company_profile "
                     "WHERE email IS NOT NULL AND email <> '' "
                     "ORDER BY updated_at DESC LIMIT 1")

# Oxirgi ETL TSIKLI boshlangan payt. Bitta tsiklда bir necha manba yuriladi,
# shuning uchun eng oxirgi startdan CYCLE_WINDOW oldingi yurishlar ham
# SHU tsiklga tegishli hisoblanadi.
LAST_CYCLE_SQL = f"""
SELECT min(started_at) AS since
FROM etl_run
WHERE started_at >= (SELECT max(started_at) FROM etl_run) - INTERVAL '{CYCLE_WINDOW}'
"""

# Allaqachon xabar ketgan tenderlar (takrorlanmasin)
SENT_IDS_SQL = "SELECT tender_id FROM notify_sent WHERE kind = %(kind)s"

# PK (tender_id, kind) -> ikkinchi marta yozilmaydi, ya'ni ikkinchi marta
# xabar ham ketmaydi.
MARK_SENT_SQL = """
INSERT INTO notify_sent (tender_id, kind, email, score)
VALUES (%(tender_id)s, %(kind)s, %(email)s, %(score)s)
ON CONFLICT (tender_id, kind) DO NOTHING
RETURNING tender_id
"""

# Katalog mahsulotlari (moslik uchun) — queries.CATALOG_LIST_SQL bilan bir xil
# manba, takror yozmaymiz.
CATALOG_SQL = queries.CATALOG_LIST_SQL
PROFILE_SQL = queries.PROFILE_GET_SQL


# ---------------------------------------------------------------------------
# SMTP — PLATFORMA sozlamasi, foydalanuvchiniki EMAS
# ---------------------------------------------------------------------------
# Foydalanuvchidan pochta serveri so'ralmaydi: u faqat O'Z EMAILINI yozadi,
# xabarni platformaning o'zi yuboradi. Server rekvizitlari `.env` da —
# `notify_settings` dagi smtp_* ustunlari ESKIRDI va endi o'qilmaydi.
#
# Sabab: host/port/STARTTLS/login — operatorning infratuzilma detali. Uni
# interfeysга chiqarish foydalanuvchiga o'zi javob bera olmaydigan savol
# berish demakdir; bundan tashqari har foydalanuvchi o'z pochta serverini
# kiritsa, xabarlar turli manzillardan kelib, spamга tushardi.
def smtp_config() -> Dict[str, Any]:
    """Platformaning SMTP rekvizitlari (.env). Parol qaytmaydi — faqat bor/yo'q."""
    return {
        "host": (os.environ.get("SMTP_HOST") or "").strip(),
        "port": int(os.environ.get("SMTP_PORT") or 587),
        "user": (os.environ.get("SMTP_USER") or "").strip(),
        "password": os.environ.get("SMTP_PASSWORD") or "",
        "from_email": (os.environ.get("SMTP_FROM")
                       or os.environ.get("SMTP_USER") or "").strip(),
        # 465 portда `send()` o'zi SMTP_SSL ga o'tadi, bu bayroq STARTTLS uchun.
        "use_tls": (os.environ.get("SMTP_TLS") or "1").strip().lower()
                   not in ("0", "false", "no"),
    }


def smtp_ready() -> bool:
    """Platforma email yubora oladimi (interfeys shuni ko'rsatadi)."""
    c = smtp_config()
    return bool(c["host"] and c["from_email"] and (c["password"] or not c["user"]))


# ---------------------------------------------------------------------------
# Sozlamalar
# ---------------------------------------------------------------------------
def get_settings() -> Dict[str, Any]:
    """Faol sozlamalar. Yozuv yo'q bo'lsa standart qiymatlar qaytadi
    (frontend forma bo'sh bazada ham ochilsin)."""
    ready = telegram_columns_ready()
    row = db.query_one(SETTINGS_GET_SQL if ready else LEGACY_SETTINGS_GET_SQL)
    st: Dict[str, Any] = dict(row) if row else {
        "id": 1, "enabled": False, "email": None, "min_score": 70,
        "smtp_host": None, "smtp_port": 587, "smtp_user": None,
        "smtp_use_tls": True, "from_email": None,
        "base_url": "http://localhost:5173",
        "telegram_enabled": False, "telegram_chat_id": None,
        "updated_at": None,
    }
    st["updated_at"] = st["updated_at"].isoformat() if st.get("updated_at") else None
    # Patchgacha bo'lgan bazada bu kalitlar SELECT dan kelmaydi — interfeys
    # `undefined` ni ko'rmasligi uchun aniq standart qiymat qo'yamiz.
    st.setdefault("telegram_enabled", False)
    st.setdefault("telegram_chat_id", None)
    # Sirlar HECH QACHON javobga qo'shilmaydi — faqat "sozlanganmi" belgisi.
    # SMTP endi PLATFORMA sozlamasi (.env) — interfeys faqat "platforma email
    # yubora oladimi" degan bitta belgini ko'radi, rekvizitlarni emas.
    st["smtp_ready"] = smtp_ready()
    st["smtp_from"] = smtp_config()["from_email"] or None
    st["telegram_token_set"] = telegram.token_set()
    # False bo'lsa: `schema_patch_notify_telegram.sql` hali qo'llanmagan.
    st["telegram_ready"] = ready
    # False bo'lsa: `schema_patch_notify_subscribers.sql` hali qo'llanmagan.
    st["subscribers_ready"] = subscribers_ready()
    # Sozlamada email bo'sh bo'lsa profildan olinadi — foydalanuvchi qayerga
    # ketishini interfeysда ko'rsin.
    st["effective_email"] = st.get("email") or _profile_email()
    return st


def save_settings(data: Dict[str, Any]) -> Dict[str, Any]:
    """Sozlamalarni saqlaydi (bitta faol yozuv).

    `data` — FAQAT o'zgartirilgan maydonlar (endpoint `exclude_unset` beradi).
    Yo'q maydon joriy qiymatida qoladi: ilgari har PUT to'liq almashtirardi va
    `{"enabled": false}` yuborish SMTP sozlamasini ham o'chirib yuborardi.
    """
    cur = get_settings()

    def take(key, default=None):
        return data[key] if key in data else cur.get(key, default)

    params = {
        "enabled": bool(take("enabled", False)),
        "email": (take("email") or None),
        "min_score": _clamp_score(take("min_score", 70)),
        "smtp_host": (take("smtp_host") or None),
        "smtp_port": int(take("smtp_port") or 587),
        "smtp_user": (take("smtp_user") or None),
        "smtp_use_tls": bool(take("smtp_use_tls", True)),
        "from_email": (take("from_email") or None),
        "base_url": (take("base_url") or "http://localhost:5173").rstrip("/"),
        "telegram_enabled": bool(take("telegram_enabled", False)),
        "telegram_chat_id": (str(take("telegram_chat_id") or "").strip() or None),
    }
    # Yoqilgan bildirishnoma manzilsiz — eng yomon holat: foydalanuvchi "yoqdim"
    # deb o'ylaydi, xabar esa hech qayerga ketmaydi. Buni JIM qoldirmaymiz.
    if params["enabled"] and not (params["email"] or _profile_email()):
        raise NotifyError(
            "Bildirishnomani yoqish uchun email manzili kerak "
            "(shu yerda yoki kompaniya profilida).")
    # Telegram uchun chat ID TALAB QILINMAYDI: obunachilar botga /start
    # bosganda o'zi qo'shiladi. Yoqish uchun faqat token kerak — obunachi
    # hali bo'lmasa ham kanal yoqilgan turaveradi va birinchi /start dan
    # keyin ishlay boshlaydi.
    if params["telegram_enabled"] and not telegram.token_set():
        raise NotifyError(
            "Telegram bot tokeni serverда yo'q. .env fayliga "
            "TELEGRAM_BOT_TOKEN=... qo'shing va API'ni qayta ishga tushiring.")

    if telegram_columns_ready():
        db.execute_returning(SETTINGS_UPSERT_SQL, params)
    else:
        # Patch qo'llanmagan — Telegram maydonlarini saqlab bo'lmaydi. Buni
        # JIMGINA tashlab ketmaymiz: foydalanuvchi yoqmoqchi bo'lsa aytamiz.
        if params["telegram_enabled"] or params["telegram_chat_id"]:
            raise NotifyError(
                "Telegram sozlamalari uchun baza patchi qo'llanmagan. "
                "Ishga tushiring: psql ... -f schema_patch_notify_telegram.sql")
        db.execute_returning(LEGACY_SETTINGS_UPSERT_SQL, params)
    return get_settings()


def _clamp_score(v: Any) -> int:
    """Chegarani 0–100 oralig'ida ushlaydi (CHECK cheklovi bilan bir xil)."""
    try:
        n = int(v)
    except (TypeError, ValueError):
        return 70
    return max(0, min(100, n))


def _profile_email() -> Optional[str]:
    """company_profile.email — FAQAT O'QIYMIZ (u jadval boshqa modulniki)."""
    return db.scalar(PROFILE_EMAIL_SQL)


def recipient(st: Dict[str, Any]) -> str:
    """Qabul qiluvchi manzil. Yo'q bo'lsa — aniq xato."""
    to = (st.get("email") or "").strip() or (_profile_email() or "").strip()
    if not to:
        raise NotifyError(
            "Qabul qiluvchi email yo'q. Sozlamalarда email kiriting yoki "
            "kompaniya profilining email maydonini to'ldiring.")
    return to


# ---------------------------------------------------------------------------
# Nomzodlarni topish va ballash
# ---------------------------------------------------------------------------
def last_cycle_since() -> datetime:
    """Oxirgi ETL tsikli boshlangan payt — "yangi tender" shundan keyin
    BIRINCHI MARTA ko'rilgani (`first_seen_at`) hisoblanadi.

    etl_run bo'sh bo'lsa (ETL hali yurmagan) — oxirgi FALLBACK_HOURS soat.
    """
    since = db.scalar(LAST_CYCLE_SQL)
    if since:
        return since
    return datetime.now(timezone.utc) - timedelta(hours=FALLBACK_HOURS)


def sent_ids(kind: str = KIND_NEW_MATCH) -> set:
    """Shu KANALDA allaqachon xabar ketgan tender id lari.

    Kanal bo'yicha ajratilgan (`kind`) — email 'new_match', Telegram
    'new_match_tg'. Shu sabab Telegram keyinroq yoqilsa, u o'zi ko'rmagan
    tenderlarni oladi va email jurnaliga bog'lanib qolmaydi.
    """
    return {r["tender_id"] for r in db.query(SENT_IDS_SQL, {"kind": kind})}


def _fetch_candidates(since: datetime) -> List[Dict[str, Any]]:
    """`since` dan keyin birinchi marta ko'rilgan OCHIQ va muddati o'tmagan
    tenderlar (ballash uchun goods_blob/kategoriya kodlari bilan)."""
    where, params = queries.build_tender_filters(status="open")
    # build_tender_filters `first_seen_at` ni bilmaydi (u qidiruv filtri emas,
    # kuzatuv maydoni) — shuning uchun shartni shu yerda qo'shamiz.
    where += (" AND t.first_seen_at >= %(since)s"
              " AND (t.close_at IS NULL OR t.close_at > now())")
    params["since"] = since
    return db.query(queries.match_candidates_sql(where, cap=CANDIDATE_CAP), params)


def score_candidate(cand: Dict[str, Any], products: List[Dict[str, Any]],
                    profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Bitta tenderning moslik balli. YANGI MANTIQ YO'Q — mavjud ikki manba:

      katalog: api/main.py `_product_matches` (kategoriya=100, nom=70)
      profil : api/matching.py `score_tender` (0–100)

    Yakuniy ball = kattasi. `by` — ball qaysi manbadan kelgani (xabarда
    "nega bu tender?" degan savolga javob bo'ladi).
    """
    # Kech import — AYLANMA IMPORTNI oldini oladi: api/main.py bu modulni
    # o'z endpointlari uchun import qiladi, shuning uchun modul darajasida
    # `from api.main import ...` yozib bo'lmaydi. Chaqiruv paytida main
    # allaqachon to'liq yuklangan bo'ladi.
    from api.main import _product_matches

    cat_score = 0
    matched_products: List[str] = []
    by_category = False
    for p in products:
        how = _product_matches(cand, p)
        if not how:
            continue
        matched_products.append(p["name"])
        if how == "category":
            by_category = True
    if matched_products:
        # /catalog/match bilan AYNAN bir xil shkala
        cat_score = 100 if by_category else 70

    prof = matching.score_tender(cand, profile) if profile else None
    prof_score = int(prof["score"]) if prof else 0

    if cat_score >= prof_score:
        score, by = cat_score, ("katalog" if cat_score else None)
        reasons = ([f"Katalogingizga mos: {', '.join(matched_products[:5])}"
                    + (" (kategoriya bo'yicha)" if by_category else " (nom bo'yicha)")]
                   if matched_products else [])
    else:
        score, by = prof_score, "profil"
        reasons = (prof or {}).get("reasons", [])

    return {"score": score, "by": by, "reasons": reasons,
            "products": matched_products}


def find_candidates(min_score: Optional[int] = None,
                    since: Optional[datetime] = None,
                    limit: int = DEFAULT_LIMIT,
                    include_sent: bool = False,
                    kind: str = KIND_NEW_MATCH) -> List[Dict[str, Any]]:
    """Xabar yuborilishi kerak bo'lgan tenderlar (ball bo'yicha kamayish
    tartibida).

    min_score      — chegara (None bo'lsa sozlamalardan olinadi)
    since          — shu paytdan keyin BIRINCHI MARTA ko'rilganlar
                     (None bo'lsa oxirgi ETL tsikli)
    include_sent   — True bo'lsa `notify_sent` dagilar ham qaytadi (--force)
    """
    st = get_settings()
    threshold = _clamp_score(min_score if min_score is not None else st["min_score"])
    since = since or last_cycle_since()

    products = db.query(CATALOG_SQL)
    # Faqat "xabar yoqilgan" mahsulotlar (catalog_product.notify)
    products = [p for p in products if p.get("notify", True)]
    profile = db.query_one(PROFILE_SQL)

    already = set() if include_sent else sent_ids(kind)

    out: List[Dict[str, Any]] = []
    for c in _fetch_candidates(since):
        if c["id"] in already:
            continue
        s = score_candidate(c, products, profile)
        if s["score"] < threshold:
            continue
        out.append({
            "id": c["id"],
            "name": c.get("name"),
            "company_name": c.get("company_name"),
            "totalcost": c.get("totalcost"),
            "currency": c.get("currency"),
            "region_name": c.get("region_name"),
            "close_at": c.get("close_at"),
            "publicated_at": c.get("publicated_at"),
            "source_platform": c.get("source_platform"),
            **s,
        })

    out.sort(key=lambda t: (-t["score"], t["close_at"] or datetime.max.replace(
        tzinfo=timezone.utc)))
    return out[:limit] if limit else out


# ---------------------------------------------------------------------------
# Xabar matni
# ---------------------------------------------------------------------------
def card_url(base_url: Optional[str], tender_id: int) -> str:
    """TZ TALABI: tizimdagi tender KARTOCHKASIGA havola.
    Frontend `?tender=<id>` parametrini o'qib drawer'ni ochadi."""
    base = (base_url or "http://localhost:5173").rstrip("/")
    return f"{base}/?tender={tender_id}"


def _money(v: Any, currency: Optional[str]) -> str:
    """1234567.0 -> '1 234 567 UZS'. Bo'sh bo'lsa '—'."""
    if v is None:
        return "—"
    try:
        s = f"{float(v):,.0f}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"
    return f"{s} {currency or ''}".strip()


def _dt(v: Any) -> str:
    """datetime -> '28.07.2026 18:00'. Bo'sh bo'lsa '—'."""
    if not v:
        return "—"
    if isinstance(v, str):
        return v
    return v.strftime("%d.%m.%Y %H:%M")


def subject(tenders: List[Dict[str, Any]], threshold: int) -> str:
    n = len(tenders)
    if n == 1:
        return f"Tender AI: 1 ta yangi mos tender ({tenders[0]['score']} ball)"
    return f"Tender AI: {n} ta yangi mos tender (chegara {threshold} ball)"


def render(tenders: List[Dict[str, Any]], base_url: Optional[str] = None,
           threshold: int = 70) -> Tuple[str, str, str]:
    """O'zbekcha xabar. Qaytadi: (mavzu, matn, html).

    HAR TENDER UCHUN: nomi, buyurtmachi, summa, muddat, moslik balli va
    TIZIMDAGI KARTOCHKAGA HAVOLA (TZ talabi — ikkala versiyada ham bor).
    """
    subj = subject(tenders, threshold)

    # --- oddiy matn (HTML ni o'qiy olmaydigan mijozlar uchun) ---
    lines = [
        "Tender AI — yangi mos tenderlar",
        "=" * 40,
        f"Moslik chegarasi: {threshold} ball. Topildi: {len(tenders)} ta.",
        "",
    ]
    for i, t in enumerate(tenders, 1):
        lines += [
            f"{i}. {t.get('name') or '(nomsiz)'}",
            f"   Moslik: {t['score']} ball" +
            (f" ({t['by']} bo'yicha)" if t.get("by") else ""),
            f"   Buyurtmachi: {t.get('company_name') or '—'}",
            f"   Summa: {_money(t.get('totalcost'), t.get('currency'))}",
            f"   Muddat: {_dt(t.get('close_at'))}",
            f"   Hudud: {t.get('region_name') or '—'}",
        ]
        for r in (t.get("reasons") or [])[:3]:
            lines.append(f"   • {r}")
        # HAVOLA — TZ qabul qilish mezoni
        lines += [f"   Kartochka: {card_url(base_url, t['id'])}", ""]
    lines += [
        "-" * 40,
        "Bu xabar Tender AI tizimidan avtomatik yuborildi.",
        "Chegarani o'zgartirish yoki o'chirish: Akkaunt > Bildirishnoma.",
    ]
    text = "\n".join(lines)

    # --- HTML (pochta mijozlari uchun: inline uslub, jadvalsiz) ---
    # MATN tugunlarida `quote=False`: apostrof (o'zbekcha matnда har qadamda
    # uchraydi) `&#x27;` ga aylanib xabarni o'qib bo'lmas qilib qo'yardi.
    # ATRIBUTLARDA (href) esa to'liq escape saqlanadi.
    def _esc(v: Any) -> str:
        return escape(str(v), quote=False)

    rows = []
    for t in tenders:
        url = card_url(base_url, t["id"])
        reasons_html = "".join(
            f"<div style='color:#7a8397;font-size:12px'>• {_esc(r)}</div>"
            for r in (t.get("reasons") or [])[:3])
        rows.append(f"""
      <tr><td style="padding:14px 0;border-bottom:1px solid #e6e9f0">
        <div style="margin-bottom:6px">
          <span style="display:inline-block;background:#edf1fa;color:#2b5cc4;
            font-weight:700;font-size:12px;padding:2px 8px;border-radius:10px">
            {t['score']} ball{_esc(' · ' + t['by']) if t.get('by') else ''}</span>
        </div>
        <a href="{escape(url)}" style="color:#1a2233;font-weight:600;
          font-size:15px;text-decoration:none">{_esc(t.get('name') or '(nomsiz)')}</a>
        <div style="color:#7a8397;font-size:13px;margin-top:4px">
          {_esc(t.get('company_name') or '—')}</div>
        <div style="color:#1a2233;font-size:13px;margin-top:4px">
          Summa: <b>{_esc(_money(t.get('totalcost'), t.get('currency')))}</b>
          &nbsp;·&nbsp; Muddat: <b>{_esc(_dt(t.get('close_at')))}</b>
          &nbsp;·&nbsp; {_esc(t.get('region_name') or '—')}</div>
        {reasons_html}
        <div style="margin-top:8px">
          <a href="{escape(url)}" style="display:inline-block;background:#2b5cc4;
            color:#ffffff;font-size:13px;font-weight:600;padding:7px 14px;
            border-radius:8px;text-decoration:none">Tender kartochkasini ochish</a>
        </div>
      </td></tr>""")

    html = f"""<!DOCTYPE html>
<html lang="uz"><head><meta charset="utf-8"><title>{_esc(subj)}</title></head>
<body style="margin:0;padding:24px;background:#f6f7fb;
  font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;color:#1a2233">
  <table role="presentation" cellpadding="0" cellspacing="0" width="100%"
    style="max-width:640px;margin:0 auto;background:#ffffff;border:1px solid #e6e9f0;
    border-radius:12px;padding:20px 24px">
    <tr><td>
      <div style="font-size:18px;font-weight:700">Yangi mos tenderlar</div>
      <div style="color:#7a8397;font-size:13px;margin-top:2px">
        Moslik chegarasi: {threshold} ball · Topildi: {len(tenders)} ta</div>
    </td></tr>
    {''.join(rows)}
    <tr><td style="padding-top:16px;color:#7a8397;font-size:12px">
      Bu xabar Tender AI tizimidan avtomatik yuborildi.<br>
      Chegarani o‘zgartirish yoki o‘chirish: Akkaunt &gt; Bildirishnoma.
    </td></tr>
  </table>
</body></html>"""

    return subj, text, html


# ---------------------------------------------------------------------------
# Telegram xabari
# ---------------------------------------------------------------------------
# Ball darajasini bir qarashda ko'rsatadigan belgi. Telegramда rang yo'q,
# shuning uchun ustuvorlik EMOJI bilan beriladi (email dagi rangli "ball"
# yorlig'ining o'rnini bosadi).
def _score_mark(score: int) -> str:
    if score >= 100:
        return "🟢"
    if score >= 85:
        return "🔵"
    return "⚪️"


def telegram_block(t: Dict[str, Any], base_url: Optional[str]) -> str:
    """Bitta tender uchun Telegram HTML bloki.

    HTML ichida FAQAT Telegram qo'llab-quvvatlaydigan teglar: <b>, <a>, <i>.
    Matn `telegram.esc()` dan o'tadi (& < >), apostrof esa TEGILMAYDI —
    o'zbekcha matnда u har qadamda uchraydi.
    """
    esc = telegram.esc
    url = card_url(base_url, t["id"])
    by = f" · {esc(t['by'])}" if t.get("by") else ""
    lines = [
        f"{_score_mark(int(t['score']))} <b>{t['score']} ball</b>{by}",
        # TZ QABUL MEZONI: tizimdagi kartochkaga havola. Tender nomining o'zi
        # havola — Telegramда eng qulay ko'rinish.
        f"<b><a href=\"{esc(url)}\">{esc(t.get('name') or '(nomsiz)')}</a></b>",
        f"🏢 {esc(t.get('company_name') or '—')}",
        f"💰 {esc(_money(t.get('totalcost'), t.get('currency')))}"
        f"   ⏳ {esc(_dt(t.get('close_at')))}",
        f"📍 {esc(t.get('region_name') or '—')}",
    ]
    for r in (t.get("reasons") or [])[:3]:
        lines.append(f"<i>• {esc(r)}</i>")
    return "\n".join(lines)


def render_telegram(tenders: List[Dict[str, Any]],
                    base_url: Optional[str] = None,
                    threshold: int = 70) -> Tuple[str, List[str], str]:
    """Telegram xabari qismlari: (sarlavha, tender bloklari, izoh).

    Bo'lib yuborishni `telegram.send_blocks()` bajaradi — bitta xabar 4096
    belgidan oshsa, KESIM BLOK CHEGARASIDAN o'tadi (tender o'rtasidan emas).
    """
    head = (f"<b>Tender AI — {len(tenders)} ta yangi mos tender</b>\n"
            f"<i>Moslik chegarasi: {threshold} ball</i>")
    blocks = [telegram_block(t, base_url) for t in tenders]
    foot = "<i>Sozlamalar: Akkaunt → Bildirishnoma</i>"
    return head, blocks, foot


def require_subscribers() -> List[Dict[str, Any]]:
    """Xabar ketadigan obunachilar. Bitta ham bo'lmasa — ANIQ xato."""
    subs = enabled_subscribers()
    if not subs:
        raise NotifyError(
            "Telegram ulanmagan. Akkaunt → Bildirishnoma bo'limida "
            "\"Telegramni ulash\" tugmasini bosing va ochilgan havola orqali "
            "botga /start yuboring.")
    return subs


def send_telegram(chat_id: str, tenders: List[Dict[str, Any]],
                  base_url: Optional[str], threshold: int) -> int:
    """BITTA obunachiga yuboradi. Qaytadi: yuborilgan xabarlar soni.

    `telegram.TelegramError` -> `NotifyError` ga o'raladi: chaqiruvchi (API,
    skript, sinovlar) bitta xato turini ushlasa yetadi — email bilan bir xil.
    """
    head, blocks, foot = render_telegram(tenders, base_url, threshold)
    try:
        return telegram.send_blocks(chat_id, head, blocks, foot)
    except telegram.TelegramError as e:
        raise NotifyError(str(e)) from e


# ---------------------------------------------------------------------------
# Yuborish
# ---------------------------------------------------------------------------
def check_smtp(st: Optional[Dict[str, Any]] = None) -> None:
    """Platforma email yubora oladimi — YO'Q bo'lsa ANIQ xato.

    Yuborishdan OLDIN chaqiriladi, shuning uchun yarim-yuborilgan holat yo'q.
    Xato matni FOYDALANUVCHIGA emas, OPERATORGA qaratilgan: bu server
    sozlamasi, foydalanuvchi uni tuzata olmaydi.
    """
    del st          # eski imzo bilan moslik uchun (sozlama endi .env dan)
    c = smtp_config()
    if not c["host"]:
        raise NotifyError(
            "Platformaning pochta serveri sozlanmagan. Serverdagi .env ga "
            "qo'shing: SMTP_HOST=..., SMTP_FROM=... (va kerak bo'lsa "
            "SMTP_USER / SMTP_PASSWORD), so'ng API'ni qayta ishga tushiring.")
    if c["user"] and not c["password"]:
        raise NotifyError(
            "SMTP paroli topilmadi. Uni .env fayliga qo'shing: "
            "SMTP_PASSWORD=... (keyin API/skriptni qayta ishga tushiring).")
    if not c["from_email"]:
        raise NotifyError(
            "Jo'natuvchi manzil yo'q. .env ga SMTP_FROM=... qo'shing.")


def send(st: Dict[str, Any], to: str, subj: str, text: str, html: str) -> None:
    """Xabarni PLATFORMANING SMTP serveri orqali yuboradi
    (STARTTLS; 465 portда SMTP_SSL).

    `st` faqat imzo mosligi uchun — rekvizitlar `.env` dan olinadi.
    Sozlama/parol yo'q bo'lsa `NotifyError`. SMTP xatolari ham `NotifyError`
    ga o'raladi — chaqiruvchi bitta turdagi xatoni ushlasa yetadi.
    """
    check_smtp()
    c = smtp_config()

    msg = EmailMessage()
    msg["Subject"] = subj
    msg["From"] = c["from_email"]
    msg["To"] = to
    # Tartib MUHIM: avval oddiy matn, keyin HTML alternativasi
    # (RFC 2046 — oxirgi qism eng "boy" versiya hisoblanadi).
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    host, port, user, pw = c["host"], c["port"], c["user"], c["password"]
    st_use_tls = c["use_tls"]

    try:
        if port == 465:
            # Implicit TLS — starttls() chaqirilmaydi
            srv = smtplib.SMTP_SSL(host, port, timeout=30,
                                   context=ssl.create_default_context())
        else:
            srv = smtplib.SMTP(host, port, timeout=30)
        with srv:
            srv.ehlo()
            if port != 465 and st_use_tls:
                srv.starttls(context=ssl.create_default_context())
                srv.ehlo()
            if user:
                srv.login(user, pw or "")
            srv.send_message(msg)
    except NotifyError:
        raise
    except (smtplib.SMTPException, OSError) as e:
        raise NotifyError(f"SMTP xatosi ({host}:{port}): {e}") from e


def mark_sent(tender_id: int, email: str, score: int,
              kind: str = KIND_NEW_MATCH) -> None:
    """Jurnalga yozadi. Takroriy yozuv ON CONFLICT bilan e'tiborsiz qoladi —
    ya'ni bir tender haqida ikkinchi marta xabar ketmaydi."""
    db.execute_returning(MARK_SENT_SQL, {
        "tender_id": tender_id, "kind": kind, "email": email, "score": score})


def _sample(st: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Sinov xabari uchun SOXTA tender — ikkala kanal bir xil namunani
    ishlatsin (ko'rinishlar farqi faqat formatда bo'lsin)."""
    return [{
        "id": 0, "name": "Sinov xabari — Tender AI sozlamalari ishlayapti",
        "company_name": "Tender AI", "totalcost": 100000000, "currency": "UZS",
        "region_name": "Toshkent shahri", "close_at": None,
        "score": st["min_score"], "by": "sinov",
        "reasons": ["Bu sinov xabari — haqiqiy tender emas."], "products": [],
    }]


def send_test(st: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """EMAIL sinov xabari — sozlamalar to'g'riligini tekshirish uchun.
    Haqiqiy tenderlar bilan bog'liq emas, `notify_sent` ga YOZMAYDI."""
    st = st or get_settings()
    to = recipient(st)
    subj, text, html = render(_sample(st), st.get("base_url"), st["min_score"])
    send(st, to, "[SINOV] " + subj, text, html)
    return {"sent": True, "to": to}


def send_telegram_test(st: Optional[Dict[str, Any]] = None,
                       chat_id: Optional[str] = None) -> Dict[str, Any]:
    """TELEGRAM sinov xabari. `notify_sent` ga YOZMAYDI.

    `chat_id` berilsa — faqat o'sha obunachiga (interfeysdagi bitta qatorni
    sinash uchun). Berilmasa — BARCHA yoqilgan obunachilarga, ya'ni haqiqiy
    yuborish qanday ketishini aynan takrorlaydi.

    `telegram_enabled` TEKSHIRILMAYDI — sinov aynan "yoqishdan oldin
    ishlayaptimi?" degan savolga javob beradi.
    """
    st = st or get_settings()
    targets = ([{"chat_id": chat_id, "title": None}] if chat_id
               else require_subscribers())

    head, blocks, foot = render_telegram(_sample(st), st.get("base_url"),
                                         st["min_score"])
    head = "🧪 <b>[SINOV]</b> " + head

    sent: List[str] = []
    errors: List[Dict[str, str]] = []
    for sub in targets:
        try:
            telegram.send_blocks(str(sub["chat_id"]), head, blocks, foot)
            sent.append(str(sub["chat_id"]))
        except telegram.TelegramError as e:
            errors.append({"chat_id": str(sub["chat_id"]), "error": str(e)})

    # HAMMASI yiqilsa — bu xato, jimgina "yuborildi" demaymiz.
    if not sent:
        raise NotifyError(errors[0]["error"] if errors
                          else "Telegram obunachisi yo'q.")
    try:
        bot = telegram.get_me()
    except telegram.TelegramError:
        bot = {}
    return {"sent": True, "chats": sent, "errors": errors,
            "bot": bot.get("username")}


# ---------------------------------------------------------------------------
# Asosiy tsikl (notify_new.py va kelajakdagi jadval shu funksiyani chaqiradi)
# ---------------------------------------------------------------------------
def run(min_score: Optional[int] = None, limit: int = DEFAULT_LIMIT,
        dry_run: bool = False, force: bool = False,
        since_hours: Optional[float] = None) -> Dict[str, Any]:
    """Bitta bildirishnoma tsikli. Qaytadi: natija xulosasi (skript chop etadi).

    dry_run — HECH NARSA yuborilmaydi va BAZAGA YOZILMAYDI (faqat ko'rsatadi)
    force   — `notify_sent` dagilar ham qayta yuboriladi

    IKKI KANAL: nomzodlar BIR MARTA hisoblanadi (ballash qimmat — katalog va
    profil bo'yicha har tender uchun), so'ng har kanal O'Z JURNALI (`kind`)
    bo'yicha filtrlanadi. Shu sabab Telegram keyinroq yoqilsa u email
    "yuborilgan" deb belgilagan tenderlarga bog'lanib qolmaydi.

    TELEGRAM — HAR OBUNACHI ALOHIDA: jurnal `new_match_tg:<chat_id>` bo'yicha
    yuritiladi, ya'ni keyinroq /start bosgan odam o'zi ko'rmagan tenderlarni
    oladi va boshqalarga yuborilgani unga to'sqinlik qilmaydi.

    KANALLAR BIR-BIRINI YIQITMAYDI: Telegram xatosi email yuborilishini
    bekor qilmaydi va aksincha. Bitta obunachi yiqilsa (bot bloklangan)
    qolganlariga baribir ketadi. Har xato natijada qaytadi — jimgina
    yutilmaydi.
    """
    st = get_settings()
    threshold = _clamp_score(min_score if min_score is not None else st["min_score"])
    since = (datetime.now(timezone.utc) - timedelta(hours=since_hours)
             if since_hours else last_cycle_since())

    # OBUNACHILARNI YANGILASH — yuborishdan OLDIN. Shu sabab oxirgi tsikldan
    # keyin /start bosgan odam AYNAN SHU yurishda xabar oladi, keyingisini
    # kutmaydi. Xato bo'lsa (tarmoq/token) tsikl to'xtamaydi: mavjud
    # obunachilarga baribir yuboriladi.
    # Kutayotgan ULASH HAVOLALARI — yuborishdan OLDIN. Shu sabab havolani
    # endigina bosgan foydalanuvchi AYNAN SHU yurishда xabar oladi.
    sync_error: Optional[str] = None
    if st.get("telegram_enabled") and not dry_run:
        try:
            consume_links()
        except NotifyError as e:
            sync_error = str(e)

    # limit=0 — CHEKLOVSIZ ro'yxat: cheklov har kanalда, O'Z jurnali bo'yicha
    # filtrlangandan KEYIN qo'llanadi. Aks holda email allaqachon ko'rgan
    # tenderlar Telegramning limitini yeb qo'yardi.
    all_cands = find_candidates(min_score=threshold, since=since, limit=0,
                                include_sent=True)

    def for_channel(kind: str) -> List[Dict[str, Any]]:
        seen = set() if force else sent_ids(kind)
        out = [t for t in all_cands if t["id"] not in seen]
        return out[:limit] if limit else out

    tenders = for_channel(KIND_NEW_MATCH)          # email
    subs = enabled_subscribers() if st.get("telegram_enabled") else []
    # Har obunachi uchun O'Z ro'yxati (kim nimani ko'rmagan bo'lsa — o'sha)
    per_sub = [(s, for_channel(tg_kind(s["chat_id"]))) for s in subs]
    tg_total = sum(len(x) for _, x in per_sub)

    tg: Dict[str, Any] = {
        "enabled": bool(st.get("telegram_enabled")),
        "subscribers": len(subs),
        "found": tg_total, "sent": 0, "messages": 0,
        "tenders": per_sub[0][1] if per_sub else [],
        "chats": [], "errors": [], "error": sync_error, "message": None,
    }
    result: Dict[str, Any] = {
        "enabled": st["enabled"], "min_score": threshold,
        "since": since.isoformat(), "found": len(tenders),
        "sent": 0, "dry_run": dry_run, "to": None,
        "tenders": tenders, "telegram": tg, "message": None,
        "error": None,
    }

    if not tenders and not tg_total:
        result["message"] = "Chegaradan yuqori yangi tender topilmadi."
        tg["message"] = result["message"]
        return result

    if tenders:
        subj, text, html = render(tenders, st.get("base_url"), threshold)
        result["subject"] = subj
        result["text"] = text
        result["html"] = html

    if dry_run:
        # DIQQAT: bu shoxда na SMTP, na Telegram, na INSERT bo'ladi.
        result["message"] = "--dry-run: xabar yuborilmadi, bazaga yozilmadi."
        tg["message"] = result["message"]
        return result

    parts: List[str] = []

    # --- EMAIL -------------------------------------------------------------
    if not st["enabled"]:
        parts.append("Email o'chirilgan (enabled=false) — yuborilmadi.")
    elif not tenders:
        parts.append("Email: yangi tender yo'q (hammasi allaqachon yuborilgan).")
    else:
        try:
            to = recipient(st)
            result["to"] = to
            send(st, to, subj, text, html)
            for t in tenders:
                mark_sent(t["id"], to, t["score"], kind=KIND_NEW_MATCH)
            result["sent"] = len(tenders)
            parts.append(f"Email: {len(tenders)} ta tender yuborildi ({to}).")
        except NotifyError as e:
            # Telegram baribir urinib ko'rsin — kanallar mustaqil.
            result["error"] = str(e)
            parts.append(f"Email XATO: {e}")

    # --- TELEGRAM: HAR OBUNACHIGA ALOHIDA -----------------------------------
    # Bitta obunachi yiqilsa (bot bloklangan, guruhdan chiqarilgan) qolganlari
    # xabar olishi SHART — shuning uchun har biri o'z `try` ida.
    if not tg["enabled"]:
        tg["message"] = "Telegram o'chirilgan (telegram_enabled=false)."
    elif not subs:
        tg["message"] = ("Telegram: obunachi yo'q — botga /start yozilmagan.")
    elif not tg_total:
        tg["message"] = "Telegram: yangi tender yo'q (allaqachon yuborilgan)."
    else:
        for sub, items in per_sub:
            if not items:
                continue
            chat_id = str(sub["chat_id"])
            try:
                n = send_telegram(chat_id, items, st.get("base_url"), threshold)
                for t in items:
                    # `email` ustuniga chat ID yoziladi — jurnal "qayerga ketdi"
                    # degan savolga javob bersin (ustun nomi tarixiy).
                    mark_sent(t["id"], f"tg:{chat_id}", t["score"],
                              kind=tg_kind(chat_id))
                tg["sent"] += len(items)
                tg["messages"] += n
                tg["chats"].append(chat_id)
            except NotifyError as e:
                tg["errors"].append({"chat_id": chat_id, "error": str(e)})

        if tg["errors"] and not tg["chats"]:
            tg["error"] = tg["errors"][0]["error"]
            tg["message"] = f"Telegram XATO: {tg['error']}"
        else:
            tg["message"] = (f"Telegram: {tg['sent']} ta tender "
                             f"{len(tg['chats'])} ta obunachiga yuborildi "
                             f"({tg['messages']} ta xabar).")
            if tg["errors"]:
                bad = ", ".join(x["chat_id"] for x in tg["errors"])
                tg["error"] = tg["errors"][0]["error"]
                tg["message"] += f" XATO ({bad}): {tg['error']}"
    parts.append(tg["message"])

    result["message"] = " ".join(p for p in parts if p)
    return result
