"""
BILDIRISHNOMA (TZ P0-10) — "yangi mos tender chiqdi" xabari
===========================================================
FOYDALANUVCHI HIKOYASI: "Broker-operator sifatida, men mosligi yuqori bo'lgan
tender paydo bo'lsa, bildirishnoma olishni xohlayman, tizimni doimiy
tekshirmaslik uchun."

XABAR TILI — PLATFORMA TILI. Foydalanuvchi interfeysда qaysi tilni tanlagan
bo'lsa (uz/ru/en), xabar ham SHU TILDA ketadi: mavzu, maydon nomlari, moslik
sabablari, summa va sana formati. Til `notify_settings.lang` da saqlanadi —
brauzerда emas: xabarni SERVER yuboradi (ETL dan keyin, foydalanuvchi ilovani
ochmagan bo'lsa ham), ya'ni u tanlovni bazadan bilishi kerak. Matnlar
`api/i18n.py` lug'atида; bu yerда birorta ham qotirilgan matn yo'q.

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
import logging
import os
import re
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from html import escape
from typing import Any, Dict, List, Optional, Tuple

from api import (db, i18n, matching, ommaviy_url, queries, telegram,
                 translit)

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


#: Modul jurnali. Tuzilmali chiqish `api/jurnal.py` da sozlanadi;
#: bu yerda oddiy nom yetarli.
log = logging.getLogger("api.notify")


class NotifyError(RuntimeError):
    """Bildirishnoma yuborib bo'lmadi (sozlama/SMTP xatosi). API buni 400/503
    ga aylantiradi, skript esa aniq matn bilan to'xtaydi."""


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------
# USTUNLAR IKKI GURUHGA bo'linadi:
#   ASOSIY   — `schema_patch_notify.sql` bilan kelgan, HAR DOIM bor
#   QO'SHIMCHA — keyingi patchlar qo'shgan (Telegram, til)
# Qo'shimcha patch alohida qadamда qo'llanadi, ya'ni u qo'llanmagan baza ham
# bo'lishi mumkin. Ularni SELECT ga so'zsiz qo'shsak "column does not exist"
# bilan MAVJUD EMAIL bildirishnomasi ham ishlamay qolardi. Shuning uchun
# ustunlar borligi bir marta tekshiriladi va SQL o'sha topilgan ustunlardan
# QURILADI (avval har patch uchun alohida "legacy" SQL nusxasi yozilardi —
# uchinchi ustun qo'shilganда bu yo'l ikki barobar nusxaga aylanardi).
_FIXED_COLS = ["id", "enabled", "email", "min_score", "smtp_host", "smtp_port",
               "smtp_user", "smtp_use_tls", "from_email", "base_url"]

# qo'shimcha guruh -> (ustunlar, "tayyormi" bayrog'i nomi)
_TG_COLS = ["telegram_enabled", "telegram_chat_id"]
_LANG_COLS = ["lang"]

COLS_EXIST_SQL = """
SELECT count(*) AS n FROM information_schema.columns
WHERE table_name = 'notify_settings' AND column_name = ANY(%(cols)s)
"""

_col_cache: Dict[str, bool] = {}


def _cols_ready(cols: List[str]) -> bool:
    """Ustunlar bazadami. Natija keshlanadi — har so'rovда
    information_schema ni qidirmaslik uchun."""
    key = ",".join(cols)
    if key not in _col_cache:
        try:
            _col_cache[key] = int(db.scalar(COLS_EXIST_SQL,
                                            {"cols": cols}) or 0) == len(cols)
        except db.DBUnavailable:
            return False          # baza yo'q — keshlamaymiz, keyin qayta uriniladi
    return _col_cache[key]


def telegram_columns_ready() -> bool:
    """`schema_patch_notify_telegram.sql` qo'llanganmi."""
    return _cols_ready(_TG_COLS)


def lang_column_ready() -> bool:
    """`schema_patch_notify_lang.sql` qo'llanganmi.

    Yo'q bo'lsa til SAQLANMAYDI va xabar standart tilда (o'zbekcha) ketadi —
    bu holat interfeysга `lang_ready: false` bo'lib qaytadi, ya'ni jimgina
    "til o'zgardi" deb ko'rsatilmaydi.
    """
    return _cols_ready(_LANG_COLS)


def _settings_cols() -> List[str]:
    """Bazada HAQIQATDA bor sozlama ustunlari."""
    cols = list(_FIXED_COLS)
    if telegram_columns_ready():
        cols += _TG_COLS
    if lang_column_ready():
        cols += _LANG_COLS
    return cols + ["updated_at"]


def _cid(company_id: Optional[int] = None) -> int:
    """Amal QAYSI kompaniya nomidan bajarilyapti (J1.6).

    Bu modul ikki xil chaqiriladi:
      * interfeysdan — endpoint sessiyadagi `company_id` ni uzatadi;
      * SESSIYASIZ — bildirishnoma tsikli ETL dan keyin yuradi, sinovlar
        ham to'g'ridan-to'g'ri chaqiradi.

    Ikkinchi holatda kompaniya TAXMIN QILINMAYDI: `auth.sole_company_id()`
    yagona faol hisobni qaytaradi va bir nechta bo'lsa ANIQ xato beradi.
    """
    if company_id is not None:
        return int(company_id)
    from api import auth
    return auth.sole_company_id()


def settings_get_sql() -> str:
    """Sozlamalar HAR KOMPANIYAGA bitta yozuv (J1.6).

    Ilgari `WHERE id = 1` edi — singleton `schema_patch_multitenant.sql`
    da sindirilgan. Yangi kompaniyada yozuv BO'LMASLIGI mumkin;
    `get_settings()` bunda standart qiymatlarni qaytaradi."""
    return (f"SELECT {', '.join(_settings_cols())} FROM notify_settings "
            "WHERE company_id = %(company_id)s")


def settings_upsert_sql() -> str:
    """Bitta faol yozuv (id=1) — bor bo'lsa yangilanadi.

    Schema patch uni yaratib qo'ygan, lekin patch qo'llanmaган bazада ham
    ishlashi uchun INSERT ... ON CONFLICT.
    """
    # `id` va `updated_at` alohida beriladi (biri qattiq 1, ikkinchisi now())
    ins = [c for c in _settings_cols() if c not in ("id", "updated_at")]
    values = ", ".join(f"%({c})s" for c in ins)
    sets = ", ".join(f"{c}=EXCLUDED.{c}" for c in ins)
    # `id` ketma-ketlikdan keladi (patch DEFAULT qo'ygan); kalit —
    # `company_id` (uq_notify_settings_company).
    return (
        f"INSERT INTO notify_settings (company_id, {', '.join(ins)}, updated_at)\n"
        f"VALUES (%(company_id)s, {values}, now())\n"
        f"ON CONFLICT (company_id) DO UPDATE SET {sets}, updated_at=now()\n"
        f"RETURNING {', '.join(_settings_cols())}"
    )


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

# OBUNACHILAR — ijarachiga bog'liq (J1.6): PK (company_id, chat_id).
SUBS_LIST_SQL = (f"SELECT {_SUB_COLS} FROM notify_telegram_subscriber "
                 "WHERE company_id = %(company_id)s "
                 "ORDER BY enabled DESC, last_seen_at DESC")

SUBS_ENABLED_SQL = ("SELECT chat_id, title FROM notify_telegram_subscriber "
                    "WHERE enabled AND company_id = %(company_id)s "
                    "ORDER BY first_seen_at")

# Ulash havolasi bilan tasdiqlangan suhbat -> obunachi.
#
# `enabled = TRUE` va `source = 'link'` QAYTA KELGANDA HAM qo'yiladi: havolani
# bosish — foydalanuvchining ANIQ harakati, ya'ni "menga xabar yuboring"
# degani. Shu sabab ilgari o'chirilgan (yoki eski usulda qo'shilgan) suhbat
# qayta ulanganда tiklanadi.
SUB_UPSERT_SQL = f"""
INSERT INTO notify_telegram_subscriber
    (chat_id, company_id, title, chat_type, username, enabled, source)
VALUES (%(chat_id)s, %(company_id)s, %(title)s, %(chat_type)s, %(username)s,
        TRUE, 'link')
-- PK (company_id, chat_id) — J1 dan keyin. `company_id` INSERT da
-- ko'rsatilmaydi: ustunda DEFAULT bor (schema_patch_multitenant.sql).
-- J1.7 tugagach bu yerga aniq qiymat uzatiladi.
ON CONFLICT (company_id, chat_id) DO UPDATE SET
    title = COALESCE(EXCLUDED.title, notify_telegram_subscriber.title),
    chat_type = COALESCE(EXCLUDED.chat_type, notify_telegram_subscriber.chat_type),
    username = COALESCE(EXCLUDED.username, notify_telegram_subscriber.username),
    enabled = TRUE,
    source = 'link',
    last_seen_at = now()
RETURNING {_SUB_COLS}, (xmax = 0) AS inserted
"""

SUB_SET_ENABLED_SQL = (f"UPDATE notify_telegram_subscriber SET enabled = %(enabled)s "
                       "WHERE chat_id = %(chat_id)s "
                       "AND company_id = %(company_id)s "
                       f"RETURNING {_SUB_COLS}")

SUB_DELETE_SQL = ("DELETE FROM notify_telegram_subscriber WHERE chat_id = %(chat_id)s "
                  "AND company_id = %(company_id)s RETURNING chat_id")

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


def subscribers(company_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Barcha obunachilar (o'chirilganlari ham — interfeys ularni ko'rsatadi)."""
    if not subscribers_ready() or not links_ready():
        return []
    rows = db.query(SUBS_LIST_SQL, {"company_id": _cid(company_id)})
    for r in rows:
        for k in ("first_seen_at", "last_seen_at"):
            r[k] = r[k].isoformat() if r.get(k) else None
    return rows


def enabled_subscribers(company_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Xabar ketadigan obunachilar."""
    if not subscribers_ready():
        return []
    return db.query(SUBS_ENABLED_SQL, {"company_id": _cid(company_id)})


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
INSERT INTO notify_telegram_link (token, company_id, expires_at)
VALUES (%(token)s, %(company_id)s, now() + INTERVAL '%(ttl)s minutes')
RETURNING token, created_at, expires_at
"""

# Ochiq (ishlatilmagan, muddati o'tmagan) tokenlar
# ULASH HAVOLASI — kompaniyaga bog'liq (J1.6): token BOSHQA kompaniyaning
# obunachisiga aylanmasligi kerak.
LINK_OPEN_SQL = ("SELECT token, company_id FROM notify_telegram_link "
                 "WHERE used_at IS NULL AND expires_at > now()")

LINK_USE_SQL = """
UPDATE notify_telegram_link SET chat_id = %(chat_id)s, used_at = now()
WHERE token = %(token)s AND used_at IS NULL AND expires_at > now()
RETURNING token, chat_id, company_id
"""

LINK_STATUS_SQL = ("SELECT token, chat_id, used_at, expires_at "
                   "FROM notify_telegram_link "
                   "WHERE token = %(token)s AND company_id = %(company_id)s")


def links_ready() -> bool:
    """Ulash jadvali bazadami."""
    try:
        return bool(db.scalar(
            "SELECT count(*) = 1 FROM information_schema.tables "
            "WHERE table_name = 'notify_telegram_link'"))
    except db.DBUnavailable:
        return False


def create_link(company_id: Optional[int] = None) -> Dict[str, Any]:
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
    row = db.execute_returning(LINK_CREATE_SQL, {"company_id": _cid(company_id),
                                                 "token": token,
                                                 "ttl": LINK_TTL_MIN})
    return {
        "token": token,
        "url": f"https://t.me/{username}?start={token}",
        "bot": username,
        "expires_at": row["expires_at"].isoformat() if row else None,
        "ttl_minutes": LINK_TTL_MIN,
    }


def link_status(token: str, company_id: Optional[int] = None) -> Dict[str, Any]:
    """Havola ishlatilganmi (interfeys shuni kutib turadi)."""
    row = db.query_one(LINK_STATUS_SQL, {"token": token,
                                         "company_id": _cid(company_id)})
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

    # Bot GLOBAL — barcha kompaniyalarning ochiq tokenlari o'qiladi. Qaysi
    # kompaniyaga obuna bo'lish esa TOKENDAN aniqlanadi (LINK_USE_SQL).
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
        # `company_id` TOKENDAN (LINK_USE_SQL qaytaradi) — parametrdan
        # emas: havolani qaysi kompaniya yaratgan bo'lsa, obunachi ham
        # o'shaniki bo'ladi.
        row = db.execute_returning(SUB_UPSERT_SQL, {
            "chat_id": c["chat_id"], "company_id": used["company_id"],
            "title": c.get("title"),
            "chat_type": c.get("type"), "username": c.get("username"),
        })
        if row:
            added.append(c["chat_id"])
    return {"seen": len(chats), "added": len(added), "added_chats": added}


# Eski nom — `run()` va sinovlar shu nomni ishlatadi.
sync_subscribers = consume_links

# Profil emaili — sozlamada email bo'sh bo'lsa zaxira manba.
PROFILE_EMAIL_SQL = ("SELECT email FROM company_profile "
                     "WHERE company_id = %(company_id)s "
                     "AND email IS NOT NULL AND email <> '' "
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
SENT_IDS_SQL = ("SELECT tender_id FROM notify_sent "
                "WHERE kind = %(kind)s AND company_id = %(company_id)s")

# PK (tender_id, kind, company_id) -> bir tender haqida HAR KOMPANIYAGA
# bir marta xabar ketadi. `company_id` DEFAULT dan keladi (J1.7 gacha).
MARK_SENT_SQL = """
INSERT INTO notify_sent (tender_id, kind, company_id, email, score)
VALUES (%(tender_id)s, %(kind)s, %(company_id)s, %(email)s, %(score)s)
ON CONFLICT (tender_id, kind, company_id) DO NOTHING
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
def get_settings(company_id: Optional[int] = None) -> Dict[str, Any]:
    """Faol sozlamalar. Yozuv yo'q bo'lsa standart qiymatlar qaytadi
    (frontend forma bo'sh bazada ham ochilsin)."""
    ready = telegram_columns_ready()
    # BIR MARTA hal qilamiz va HAMMA joyga uzatamiz. Ilgari `_cid()`
    # shu yerda chaqirilar, lekin `_profile_email()` ARGUMENTSIZ
    # qolardi va u `sole_company_id()` ga tushib, ikkinchi faol
    # kompaniya paydo bo'lishi bilan 500 berardi.
    cid = _cid(company_id)
    row = db.query_one(settings_get_sql(), {"company_id": cid})
    st: Dict[str, Any] = dict(row) if row else {
        "id": 1, "enabled": False, "email": None, "min_score": 70,
        "smtp_host": None, "smtp_port": 587, "smtp_user": None,
        "smtp_use_tls": True, "from_email": None,
        # Muhitdan (`APP_PUBLIC_URL`) — mahalliy manzil qattiq
        # yozilmaydi. Sabab `api/ommaviy_url.py` ustidagi izohda.
        "base_url": ommaviy_url.bazaviy_url(None),
        "telegram_enabled": False, "telegram_chat_id": None,
        "lang": i18n.DEFAULT_LANG, "updated_at": None,
    }
    st["updated_at"] = st["updated_at"].isoformat() if st.get("updated_at") else None
    # Patchgacha bo'lgan bazada bu kalitlar SELECT dan kelmaydi — interfeys
    # `undefined` ni ko'rmasligi uchun aniq standart qiymat qo'yamiz.
    st.setdefault("telegram_enabled", False)
    st.setdefault("telegram_chat_id", None)
    # XABAR TILI. Bazadagi qiymat buzilgan/eski bo'lsa ham yaroqli kod qaytadi.
    st["lang"] = i18n.norm_lang(st.get("lang"))
    # False bo'lsa: `schema_patch_notify_lang.sql` hali qo'llanmagan — til
    # saqlanmaydi va xabar o'zbekcha ketaveradi (interfeys buni aytadi).
    st["lang_ready"] = lang_column_ready()
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
    st["effective_email"] = st.get("email") or _profile_email(cid)
    return st


def _base_url_saqlash(data: Dict[str, Any],
                      joriy: Optional[str]) -> str:
    """Saqlanadigan `base_url`. ANIQ berilgan qiymat TEKSHIRILADI.

    IKKI HOLAT ATAYLAB AJRATILGAN:

      ANIQ BERILGAN (`"base_url" in data`) — foydalanuvchi shakl
      orqali yozdi. `dev` dan boshqa muhitda mahalliy manzil
      RAD ETILADI: uni jimgina muhitdagi qiymatga almashtirish
      "saqladim" deb ko'rsatib, boshqa narsani saqlash bo'lardi.

      BERILMAGAN — PUT faqat boshqa maydonni o'zgartiryapti
      (`exclude_unset`). Bunda bazadagi eski mahalliy qiymat
      muhitdagi bilan JIMGINA tuzatiladi (ogohlantirish bilan):
      aks holda eski ijarachi yozuvi tufayli hech qanday
      sozlamani saqlab bo'lmay qolardi.
    """
    aniq = "base_url" in data
    xom = data["base_url"] if aniq else joriy
    if aniq:
        try:
            ommaviy_url.bazani_tekshir((xom or "").strip().rstrip("/"))
        except ommaviy_url.OmmaviyUrlXato as e:
            raise NotifyError(str(e)) from e
    return ommaviy_url.bazaviy_url(xom)


def save_settings(data: Dict[str, Any],
                  company_id: Optional[int] = None) -> Dict[str, Any]:
    """Sozlamalarni saqlaydi (bitta faol yozuv).

    `data` — FAQAT o'zgartirilgan maydonlar (endpoint `exclude_unset` beradi).
    Yo'q maydon joriy qiymatida qoladi: ilgari har PUT to'liq almashtirardi va
    `{"enabled": false}` yuborish SMTP sozlamasini ham o'chirib yuborardi.
    """
    company_id = _cid(company_id)
    cur = get_settings(company_id)

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
        "base_url": _base_url_saqlash(data, cur.get("base_url")),
        "telegram_enabled": bool(take("telegram_enabled", False)),
        "telegram_chat_id": (str(take("telegram_chat_id") or "").strip() or None),
        # Xabar tili — interfeys tili bilan bir xil (frontend uni tanlanganда
        # yuboradi). Noma'lum qiymat o'zbekchaga tushadi, xato bermaydi:
        # til — yumshoq afzallik, uni deb sozlamani saqlab bo'lmay qolmasin.
        "lang": i18n.norm_lang(take("lang", i18n.DEFAULT_LANG)),
    }
    # Yoqilgan bildirishnoma manzilsiz — eng yomon holat: foydalanuvchi "yoqdim"
    # deb o'ylaydi, xabar esa hech qayerga ketmaydi. Buni JIM qoldirmaymiz.
    # `company_id` UZATILADI: busiz `sole_company_id()` ga tushardi va
    # ikkinchi faol hisob paydo bo'lishi bilan sozlamani SAQLAB
    # BO'LMAY qolardi (`get_settings` dagi bilan bir xil xato).
    if params["enabled"] and not (params["email"]
                                  or _profile_email(company_id)):
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

    # Patch qo'llanmagan — Telegram maydonlarini saqlab bo'lmaydi. Buni
    # JIMGINA tashlab ketmaymiz: foydalanuvchi yoqmoqchi bo'lsa aytamiz.
    if not telegram_columns_ready() and (params["telegram_enabled"]
                                         or params["telegram_chat_id"]):
        raise NotifyError(
            "Telegram sozlamalari uchun baza patchi qo'llanmagan. "
            "Ishga tushiring: psql ... -f schema_patch_notify_telegram.sql")

    # SQL faqat MAVJUD ustunlardan quriladi, shuning uchun ortiqcha kalitlar
    # (masalan patch qo'llanmagan bazada `lang`) parametrlardan chiqariladi.
    cols = set(_settings_cols())
    db.execute_returning(
        settings_upsert_sql(),
        {**{k: v for k, v in params.items() if k in cols},
         "company_id": company_id})
    return get_settings(company_id)


def _clamp_score(v: Any) -> int:
    """Chegarani 0–100 oralig'ida ushlaydi (CHECK cheklovi bilan bir xil)."""
    try:
        n = int(v)
    except (TypeError, ValueError):
        return 70
    return max(0, min(100, n))


def _profile_email(company_id: Optional[int] = None) -> Optional[str]:
    """company_profile.email — FAQAT O'QIYMIZ (u jadval boshqa modulniki).

    J1.6: profil KOMPANIYAGA bog'landi. `company_id` berilmasa sessiyasiz
    chaqiruv (bildirishnoma tsikli, sinov) — yagona faol hisob olinadi.
    NAVBAT 5 da `notify_settings` ham bog'langach, bu yer har kompaniya
    bo'ylab aylanishning ichiga tushadi."""
    if company_id is None:
        from api import auth
        company_id = auth.sole_company_id()
    return db.scalar(PROFILE_EMAIL_SQL, {"company_id": company_id})


def recipient(st: Dict[str, Any],
              company_id: Optional[int] = None) -> str:
    """Qabul qiluvchi manzil. Yo'q bo'lsa — aniq xato.

    `company_id` MAJBURIY ma'noda: berilmasa `_profile_email()`
    `sole_company_id()` ga tushadi va bir nechta faol kompaniya
    bo'lsa xato beradi. Chaqiruvchilarda kompaniya ALLAQACHON
    ma'lum — uni uzatish shart.
    """
    to = ((st.get("email") or "").strip()
          or (_profile_email(company_id) or "").strip())
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


def sent_ids(kind: str = KIND_NEW_MATCH,
             company_id: Optional[int] = None) -> set:
    """Shu KANALDA allaqachon xabar ketgan tender id lari.

    Kanal bo'yicha ajratilgan (`kind`) — email 'new_match', Telegram
    'new_match_tg'. Shu sabab Telegram keyinroq yoqilsa, u o'zi ko'rmagan
    tenderlarni oladi va email jurnaliga bog'lanib qolmaydi.
    """
    return {r["tender_id"] for r in db.query(
        SENT_IDS_SQL, {"kind": kind, "company_id": _cid(company_id)})}


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


#: Matn atamasining eng katta uzunligi — `queries.MAX_TERM_LEN` bilan
#: bir xil sabab: undan uzunlari SKU artikullari va ular tender
#: pozitsiyasida uchramaydi.
ATAMA_MAX_LEN = 25


def katalog_indeks(products: List[Dict[str, Any]],
                   db_mos: bool = True) -> Dict[str, Any]:
    """Katalogdan BIR MARTA quriladigan moslashtirish indeksi.

    NEGA KERAK (o'lchangan, 1797 qatorli real katalog):
        har nomzod uchun 1797 mahsulotni aylanish -> 10 nomzod = 67 s,
        528 nomzod = 59 DAQIQA. Soatlik ETL ning bildirishnoma qadami
        tugamasdi va keyingi yurish uni o'ldirardi.

    Indeks nomzoddan MUSTAQIL, shuning uchun bir marta quriladi:
        `kod`   -> [(prefiks, mahsulot_nomi)]      tasdiqlangan kodlar
        `atama` -> [(atama, mahsulot_nomi, variantlar)]  kodsizlar uchun

    Variantlar OLDINDAN hisoblanadi — `translit.variants()` qimmat va
    u har nomzod uchun qayta hisoblanardi.
    """
    kod: List[Tuple[str, str]] = []
    korilgan_kod = set()
    for p in products:
        for k in (p.get("codes") or []):
            if k and k not in korilgan_kod:
                korilgan_kod.add(k)
                kod.append((k, p.get("name") or ""))

    # ATAMALAR — `queries.catalog_terms()` dan, YAGONA MANBA.
    # Bu yerda o'z qoidasini yozmaymiz: ilgari shunday qilingandi va
    # indeks 1325 atamaga shishib ketgandi (SKU nomlari kirgani uchun).
    juft, kesilgan = queries.catalog_terms(products)
    atama = [(t, nom, translit.variants(t)) for t, nom in juft]

    # MATN MOSLIGI SQL DA — `/catalog/match` bilan AYNAN bir usul.
    #
    # Ilgari bu yerda har nomzod uchun 400 atama Python siklida
    # tekshirilardi: 528 nomzod x 400 atama x 3 regex = 630 ming amal,
    # ya'ni bir yurish ~51 s. Endi Postgres bir so'rovda mos
    # tenderlarni qaytaradi (~0.3 s) va `score_candidate` faqat
    # to'plamga tegishlilikni tekshiradi.
    #
    # Ikki joyda ikki xil amalga oshirish bo'lmasin — bu loyihada
    # aynan shu sabab bilan atama qoidasi ikkiga bo'linib ketgandi.
    matn_mos: Optional[Dict[int, str]] = None
    if db_mos and atama:
        matn_mos = {}
        tsql, tpar = queries.build_catalog_text_match([t for t, _n, _v in atama])
        if tsql:
            for r in db.query(tsql, tpar):
                matn_mos.setdefault(r["tender_id"], r["pozitsiya"])

    return {"kod": kod, "atama": atama, "kesilgan": kesilgan,
            # `None` -> SQL to'plami YO'Q, `score_candidate` matnni
            # o'zi tekshiradi. Bu sintetik nomzod uchun kerak (sinovlar
            # bazada bo'lmagan tender yasaydi) — u holda to'plamga
            # tegishlilik HAR DOIM yolg'on chiqardi va moslik jimgina
            # yo'qolardi.
            "matn_mos": matn_mos}


def score_candidate(cand: Dict[str, Any], products: List[Dict[str, Any]],
                    profile: Optional[Dict[str, Any]],
                    indeks: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Bitta tenderning moslik balli. YANGI MANTIQ YO'Q — mavjud ikki manba:

      katalog: api/main.py `_product_matches` (kod=100, nom=60)
      profil : api/matching.py `score_tender` (0–100)

    SHKALA O'ZGARDI (2026-08). Ilgari `kategoriya=100` edi va bu eng
    katta soxta-moslik manbai bo'lgan: bitta keng kategoriyali mahsulot
    butun bo'limni "100 ball" qilardi (o'lchangan: 206 moslikning 131
    tasi shu yo'ldan; "Andijon GES transformatorini ta'mirlash"
    tibbiy muzlatgich sotuvchiga 100 ball bilan borardi). Kategoriya
    endi moslik dalili EMAS — `api/matching.product_matches()` ga qarang.

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
    by_code = False

    # INDEKS BERILMAGAN -> bu yakka chaqiruv (sinov yoki ad-hoc).
    # SQL to'plamini qurmaymiz: nomzod bazada bo'lmasligi mumkin.
    ix = indeks if indeks is not None else katalog_indeks(products, db_mos=False)

    # --- KOD (birlamchi) ---
    for gc in (cand.get("good_codes") or []):
        for pref, nom in ix["kod"]:
            if gc and gc.startswith(pref):
                by_code = True
                if nom not in matched_products:
                    matched_products.append(nom)

    # --- NOM (faqat kodsiz mahsulotlar uchun) ---
    #
    # SQL allaqachon MOS TENDERLARNI aniqlab bergan (`matn_mos`), shuning
    # uchun bu yerda faqat tegishlilik tekshiriladi. Mahsulot nomini esa
    # atama bo'yicha topamiz — natija kichik, sikl arzon.
    mm = ix.get("matn_mos")
    matn_nomzod = (cand.get("id") in mm) if mm is not None else True
    if not by_code and matn_nomzod:
        blob = matching._norm(
            f"{cand.get('name') or ''} {cand.get('goods_blob') or ''} "
            f"{(mm or {}).get(cand.get('id')) or ''}")
        for _term, nom, variants in ix["atama"]:
            if matching.hits_variants(variants, blob):
                if nom not in matched_products:
                    matched_products.append(nom)
                if len(matched_products) >= 5:
                    break
        if not matched_products and mm is not None and cand.get("id") in mm:
            # SQL topgan, atama esa qaytadan topmadi — ehtimol
            # `goods_blob` cap ga tushgan. Moslikni YO'QOTMAYMIZ,
            # lekin mahsulot nomini TAXMIN QILMAYMIZ: mos kelgan
            # POZITSIYA nomi ko'rsatiladi.
            matched_products.append(mm[cand["id"]])
    if matched_products:
        # /catalog/match bilan AYNAN bir xil shkala (kod=100, nom=60).
        # Ikki joyda ikki shkala bo'lmasin: bildirishnoma va ekran bir
        # xil tenderni turlicha ballasa, foydalanuvchi qaysisiga
        # ishonishni bilmaydi.
        cat_score = 100 if by_code else 60

    prof = matching.score_tender(cand, profile) if profile else None
    prof_score = int(prof["score"]) if prof else 0

    if cat_score >= prof_score:
        score = cat_score
        by_key = "by.catalog" if cat_score else None
        keys = ([{"key": ("reason.catalogCode" if by_code
                          else "reason.catalogName"),
                  "vars": {"items": ", ".join(matched_products[:5])}}]
                if matched_products else [])
    else:
        score, by_key = prof_score, "by.profile"
        keys = list((prof or {}).get("reason_keys") or [])

    # `by` va `reasons` — O'ZBEKCHA (avvalgidek, sinovlar va boshqa
    # chaqiruvchilar uchun). Xabar esa `by_key`/`reason_keys` dan
    # foydalanuvchi tilida quriladi — `_localize()` ga qarang.
    return {
        "score": score,
        "by": i18n.t(i18n.DEFAULT_LANG, by_key) if by_key else None,
        "by_key": by_key,
        "reasons": [i18n.t(i18n.DEFAULT_LANG, k["key"], **k.get("vars", {}))
                    for k in keys],
        "reason_keys": keys,
        "products": matched_products,
    }


def find_candidates(min_score: Optional[int] = None,
                    since: Optional[datetime] = None,
                    limit: int = DEFAULT_LIMIT,
                    include_sent: bool = False,
                    kind: str = KIND_NEW_MATCH,
                    company_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Xabar yuborilishi kerak bo'lgan tenderlar (ball bo'yicha kamayish
    tartibida).

    min_score      — chegara (None bo'lsa sozlamalardan olinadi)
    since          — shu paytdan keyin BIRINCHI MARTA ko'rilganlar
                     (None bo'lsa oxirgi ETL tsikli)
    include_sent   — True bo'lsa `notify_sent` dagilar ham qaytadi (--force)
    """
    # KOMPANIYA — barcha manbalar uchun BITTA qiymat: sozlama, katalog,
    # profil va "allaqachon yuborilgan" jurnali bir xil ijarachiniki
    # bo'lishi shart, aks holda chegara bir kompaniyaniki, katalog
    # boshqasiniki bo'lib qolardi.
    company_id = _cid(company_id)
    st = get_settings(company_id)
    threshold = _clamp_score(min_score if min_score is not None else st["min_score"])
    since = since or last_cycle_since()

    products = db.query(CATALOG_SQL, {"company_id": company_id})
    # Faqat "xabar yoqilgan" mahsulotlar (catalog_product.notify)
    products = [p for p in products if p.get("notify", True)]
    profile = db.query_one(PROFILE_SQL, {"company_id": company_id})

    already = set() if include_sent else sent_ids(kind, company_id)

    # INDEKS BIR MARTA — nomzod ichida emas. Aks holda 1797 qatorli
    # katalogda bu sikl 59 daqiqa olardi (o'lchangan).
    ix = katalog_indeks(products)

    out: List[Dict[str, Any]] = []
    for c in _fetch_candidates(since):
        if c["id"] in already:
            continue
        s = score_candidate(c, products, profile, indeks=ix)
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
#: OMMAVIY MANZIL — `api/ommaviy_url.py` DA (yagona manba).
#:
#: Ilgari tanlash va tekshirish mantig'i SHU FAYLDA edi. U ilovaning
#: xossasi, bildirishnomaning emas: parol tiklash havolasi ham,
#: chuqur havola ham AYNAN shu manzildan qurilishi kerak. Bu yerda
#: qolsa, ikkinchi chaqiruvchi uni TAKRORLAB yozardi.
#:
#: Quyidagi ikki nom ESKI CHAQIRUVCHILAR uchun qoldirildi va
#: `ommaviy_url` ga UZATADI — ikkinchi nusxa EMAS.
mahalliymi = ommaviy_url.mahalliymi
bazaviy_url = ommaviy_url.bazaviy_url


def card_url(base_url: Optional[str], tender_id: int) -> str:
    """TZ TALABI: tizimdagi tender KARTOCHKASIGA havola.

    Frontend `?tender=<id>` parametrini o'qib drawer'ni ochadi.

    HAVOLA `ommaviy_url.havola()` DA quriladi va SHU YERDA
    tekshiriladi — email matni, email HTML va Telegram uchalasi
    ayni shu funksiyadan o'tadi. Yuborish funksiyalariga alohida
    qo'shilsa, yangi kanal qo'shilganda uni UNUTISH oson bo'lardi.

    XATO TURI O'RALADI: yuborish yo'lidagi chaqiruvchilar FAQAT
    `NotifyError` ni ushlaydi va `OmmaviyUrlXato` ulardan JIMGINA
    o'tib ketardi.
    """
    try:
        return ommaviy_url.havola(f"/?tender={tender_id}", base_url)
    except ommaviy_url.OmmaviyUrlXato as e:
        raise NotifyError(str(e)) from e


def _money(v: Any, currency: Optional[str],
           lang: str = i18n.DEFAULT_LANG) -> str:
    """1234567.0 -> '1 234 567 UZS'. Bo'sh bo'lsa '—'.

    Mingliklar ajratgichi TILGA bog'liq: o'zbek va rus tilida bo'sh joy
    ('1 234 567'), ingliz tilида vergul ('1,234,567') — o'quvchi qaysi
    yozuvni kutsa, o'sha.
    """
    if v is None:
        return "—"
    try:
        s = f"{float(v):,.0f}"
    except (TypeError, ValueError):
        return "—"
    if lang != "en":
        s = s.replace(",", " ")
    return f"{s} {currency or ''}".strip()


def _dt(v: Any, lang: str = i18n.DEFAULT_LANG) -> str:
    """datetime -> '28.07.2026 18:00'. Bo'sh bo'lsa '—'.

    Ingliz tilida ISO ('2026-07-28 18:00'): '07/28' va '28/07' ni bir-biridan
    ajratib bo'lmaydi va muddat — xato qilib bo'lmaydigan maydon.
    """
    if not v:
        return "—"
    if isinstance(v, str):
        return v
    return v.strftime("%Y-%m-%d %H:%M" if lang == "en" else "%d.%m.%Y %H:%M")


def _score(score: Any, lang: str) -> str:
    """'70 ball' / '70 баллов' / '70 pts' — ball SO'ZI bilan birga."""
    try:
        n = int(score)
    except (TypeError, ValueError):
        n = 0
    return i18n.t(lang, "msg.score", n=n)


def _name(t: Dict[str, Any], lang: str) -> str:
    return t.get("name") or i18n.t(lang, "msg.noname")


def _by(t: Dict[str, Any], lang: str) -> Optional[str]:
    """Ball qaysi manbadan — foydalanuvchi tilida ('katalog'/'каталог'...).

    `by_key` bo'lmasa (eski chaqiruv yoki qo'lда tuzilgan tender) tayyor
    `by` matni ishlatiladi — xabar baribir chiqadi.
    """
    key = t.get("by_key")
    return i18n.t(lang, key) if key else (t.get("by") or None)


def _reasons(t: Dict[str, Any], lang: str) -> List[str]:
    """Moslik sabablari foydalanuvchi tilida.

    `reason_keys` (struktura) bo'lsa — lug'atdan quriladi. Bo'lmasa tayyor
    `reasons` matni qaytadi: sabab TUSHIB QOLMASIN, hech bo'lmasa o'zbekcha
    ko'rinsin.
    """
    keys = t.get("reason_keys")
    if keys:
        return [i18n.t(lang, k["key"], **(k.get("vars") or {})) for k in keys]
    return list(t.get("reasons") or [])


def subject(tenders: List[Dict[str, Any]], threshold: int,
            lang: str = i18n.DEFAULT_LANG) -> str:
    n = len(tenders)
    if n == 1:
        return i18n.t(lang, "subject.one", score=_score(tenders[0]["score"], lang))
    return i18n.t(lang, "subject.many", n=n, threshold=_score(threshold, lang))


def render(tenders: List[Dict[str, Any]], base_url: Optional[str] = None,
           threshold: int = 70,
           lang: str = i18n.DEFAULT_LANG) -> Tuple[str, str, str]:
    """Xabar FOYDALANUVCHI TILIDA. Qaytadi: (mavzu, matn, html).

    HAR TENDER UCHUN: nomi, buyurtmachi, summa, muddat, moslik balli va
    TIZIMDAGI KARTOCHKAGA HAVOLA (TZ talabi — ikkala versiyada ham bor).
    """
    lang = i18n.norm_lang(lang)
    subj = subject(tenders, threshold, lang)
    thr = _score(threshold, lang)

    def tr(key: str, **v: Any) -> str:
        return i18n.t(lang, key, **v)

    # --- oddiy matn (HTML ni o'qiy olmaydigan mijozlar uchun) ---
    lines = [
        tr("msg.title"),
        "=" * 40,
        tr("msg.summary", threshold=thr, n=len(tenders)),
        "",
    ]
    for i, t in enumerate(tenders, 1):
        by = _by(t, lang)
        score = _score(t["score"], lang)
        lines += [
            f"{i}. {_name(t, lang)}",
            "   " + (tr("msg.matchBy", score=score, by=by) if by
                     else tr("msg.match", score=score)),
            f"   {tr('msg.buyer')}: {t.get('company_name') or '—'}",
            f"   {tr('msg.sum')}: {_money(t.get('totalcost'), t.get('currency'), lang)}",
            f"   {tr('msg.deadline')}: {_dt(t.get('close_at'), lang)}",
            f"   {tr('msg.region')}: {t.get('region_name') or '—'}",
        ]
        for r in _reasons(t, lang)[:3]:
            lines.append(f"   • {r}")
        # HAVOLA — TZ qabul qilish mezoni
        lines += [f"   {tr('msg.card')}: {card_url(base_url, t['id'])}", ""]
    lines += [
        "-" * 40,
        tr("msg.footAuto"),
        tr("msg.footSettings"),
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
        by = _by(t, lang)
        reasons_html = "".join(
            f"<div style='color:#7a8397;font-size:12px'>• {_esc(r)}</div>"
            for r in _reasons(t, lang)[:3])
        rows.append(f"""
      <tr><td style="padding:14px 0;border-bottom:1px solid #e6e9f0">
        <div style="margin-bottom:6px">
          <span style="display:inline-block;background:#edf1fa;color:#2b5cc4;
            font-weight:700;font-size:12px;padding:2px 8px;border-radius:10px">
            {_esc(_score(t['score'], lang))}{_esc(' · ' + by) if by else ''}</span>
        </div>
        <a href="{escape(url)}" style="color:#1a2233;font-weight:600;
          font-size:15px;text-decoration:none">{_esc(_name(t, lang))}</a>
        <div style="color:#7a8397;font-size:13px;margin-top:4px">
          {_esc(t.get('company_name') or '—')}</div>
        <div style="color:#1a2233;font-size:13px;margin-top:4px">
          {_esc(tr('msg.sum'))}:
          <b>{_esc(_money(t.get('totalcost'), t.get('currency'), lang))}</b>
          &nbsp;·&nbsp; {_esc(tr('msg.deadline'))}:
          <b>{_esc(_dt(t.get('close_at'), lang))}</b>
          &nbsp;·&nbsp; {_esc(t.get('region_name') or '—')}</div>
        {reasons_html}
        <div style="margin-top:8px">
          <a href="{escape(url)}" style="display:inline-block;background:#2b5cc4;
            color:#ffffff;font-size:13px;font-weight:600;padding:7px 14px;
            border-radius:8px;text-decoration:none">{_esc(tr('msg.open'))}</a>
        </div>
      </td></tr>""")

    html = f"""<!DOCTYPE html>
<html lang="{lang}"><head><meta charset="utf-8"><title>{_esc(subj)}</title></head>
<body style="margin:0;padding:24px;background:#f6f7fb;
  font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;color:#1a2233">
  <table role="presentation" cellpadding="0" cellspacing="0" width="100%"
    style="max-width:640px;margin:0 auto;background:#ffffff;border:1px solid #e6e9f0;
    border-radius:12px;padding:20px 24px">
    <tr><td>
      <div style="font-size:18px;font-weight:700">{_esc(tr('msg.titleShort'))}</div>
      <div style="color:#7a8397;font-size:13px;margin-top:2px">
        {_esc(tr('msg.summaryShort', threshold=thr, n=len(tenders)))}</div>
    </td></tr>
    {''.join(rows)}
    <tr><td style="padding-top:16px;color:#7a8397;font-size:12px">
      {_esc(tr('msg.footAuto'))}<br>
      {_esc(tr('msg.footSettings'))}
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


def telegram_block(t: Dict[str, Any], base_url: Optional[str],
                   lang: str = i18n.DEFAULT_LANG) -> str:
    """Bitta tender uchun Telegram HTML bloki.

    HTML ichida FAQAT Telegram qo'llab-quvvatlaydigan teglar: <b>, <a>, <i>.
    Matn `telegram.esc()` dan o'tadi (& < >), apostrof esa TEGILMAYDI —
    o'zbekcha matnда u har qadamda uchraydi.

    MAYDON NOMLARI O'RNIGA EMOJI (🏢 💰 ⏳ 📍) — ATAYIN: Telegramда joy tor,
    belgi esa tilga bog'liq emas va tarjima talab qilmaydi. Tarjima faqat
    o'qiladigan matnга (ball, sabablar, sana/summa formati) tegishli.
    """
    esc = telegram.esc
    lang = i18n.norm_lang(lang)
    url = card_url(base_url, t["id"])
    by_txt = _by(t, lang)
    by = f" · {esc(by_txt)}" if by_txt else ""
    lines = [
        f"{_score_mark(int(t['score']))} <b>{esc(_score(t['score'], lang))}</b>{by}",
        # TZ QABUL MEZONI: tizimdagi kartochkaga havola. Tender nomining o'zi
        # havola — Telegramда eng qulay ko'rinish.
        f"<b><a href=\"{esc(url)}\">{esc(_name(t, lang))}</a></b>",
        f"🏢 {esc(t.get('company_name') or '—')}",
        f"💰 {esc(_money(t.get('totalcost'), t.get('currency'), lang))}"
        f"   ⏳ {esc(_dt(t.get('close_at'), lang))}",
        f"📍 {esc(t.get('region_name') or '—')}",
    ]
    for r in _reasons(t, lang)[:3]:
        lines.append(f"<i>• {esc(r)}</i>")
    return "\n".join(lines)


def render_telegram(tenders: List[Dict[str, Any]],
                    base_url: Optional[str] = None,
                    threshold: int = 70,
                    lang: str = i18n.DEFAULT_LANG) -> Tuple[str, List[str], str]:
    """Telegram xabari qismlari: (sarlavha, tender bloklari, izoh).

    Bo'lib yuborishni `telegram.send_blocks()` bajaradi — bitta xabar 4096
    belgidan oshsa, KESIM BLOK CHEGARASIDAN o'tadi (tender o'rtasidan emas).
    """
    lang = i18n.norm_lang(lang)
    esc = telegram.esc
    head = (f"<b>{esc(i18n.t(lang, 'tg.head', n=len(tenders)))}</b>\n"
            f"<i>{esc(i18n.t(lang, 'tg.threshold', threshold=_score(threshold, lang)))}</i>")
    blocks = [telegram_block(t, base_url, lang) for t in tenders]
    foot = f"<i>{esc(i18n.t(lang, 'tg.foot'))}</i>"
    return head, blocks, foot


def require_subscribers(company_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Xabar ketadigan obunachilar. Bitta ham bo'lmasa — ANIQ xato."""
    subs = enabled_subscribers(company_id)
    if not subs:
        raise NotifyError(
            "Telegram ulanmagan. Akkaunt → Bildirishnoma bo'limida "
            "\"Telegramni ulash\" tugmasini bosing va ochilgan havola orqali "
            "botga /start yuboring.")
    return subs


def send_telegram(chat_id: str, tenders: List[Dict[str, Any]],
                  base_url: Optional[str], threshold: int,
                  lang: str = i18n.DEFAULT_LANG) -> int:
    """BITTA obunachiga yuboradi. Qaytadi: yuborilgan xabarlar soni.

    `telegram.TelegramError` -> `NotifyError` ga o'raladi: chaqiruvchi (API,
    skript, sinovlar) bitta xato turini ushlasa yetadi — email bilan bir xil.
    """
    head, blocks, foot = render_telegram(tenders, base_url, threshold, lang)
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
              kind: str = KIND_NEW_MATCH,
              company_id: Optional[int] = None) -> None:
    """Jurnalga yozadi. Takroriy yozuv ON CONFLICT bilan e'tiborsiz qoladi —
    ya'ni bir tender haqida ikkinchi marta xabar ketmaydi."""
    db.execute_returning(MARK_SENT_SQL, {
        "tender_id": tender_id, "kind": kind, "email": email,
        "score": score, "company_id": _cid(company_id)})


def _sample(st: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Sinov xabari uchun SOXTA tender — ikkala kanal bir xil namunani
    ishlatsin (ko'rinishlar farqi faqat formatда bo'lsin).

    Namuna ham FOYDALANUVCHI TILIDA: sinov xabari aynan "haqiqiy xabar
    qanday keladi" degan savolga javob beradi, ya'ni tili ham o'shaniki
    bo'lishi kerak.
    """
    lang = i18n.norm_lang(st.get("lang"))
    return [{
        "id": 0, "name": i18n.t(lang, "test.name"),
        "company_name": "Tender AI", "totalcost": 100000000, "currency": "UZS",
        "region_name": i18n.t(lang, "test.region"), "close_at": None,
        "score": st["min_score"], "by_key": "by.test",
        "by": i18n.t(i18n.DEFAULT_LANG, "by.test"),
        "reason_keys": [{"key": "test.reason", "vars": {}}], "products": [],
    }]


def send_test(st: Optional[Dict[str, Any]] = None,
              company_id: Optional[int] = None) -> Dict[str, Any]:
    """EMAIL sinov xabari — sozlamalar to'g'riligini tekshirish uchun.
    Haqiqiy tenderlar bilan bog'liq emas, `notify_sent` ga YOZMAYDI."""
    company_id = _cid(company_id)
    st = st or get_settings(company_id)
    lang = i18n.norm_lang(st.get("lang"))
    to = recipient(st, company_id)
    subj, text, html = render(_sample(st), st.get("base_url"), st["min_score"],
                              lang)
    send(st, to, f"{i18n.t(lang, 'test.tag')} {subj}", text, html)
    return {"sent": True, "to": to}


def send_telegram_test(st: Optional[Dict[str, Any]] = None,
                       company_id: Optional[int] = None,
                       chat_id: Optional[str] = None) -> Dict[str, Any]:
    """TELEGRAM sinov xabari. `notify_sent` ga YOZMAYDI.

    TILI — PLATFORMA TILI (sozlamadagi `lang`), xuddi haqiqiy bildirishnoma
    kabi. Sinovning butun mohiyati "haqiqiy xabar qanday keladi" ni
    ko'rsatishда, shuning uchun u haqiqiysidan tili bilan ham farq
    qilmasligi kerak.

    `chat_id` berilsa — faqat o'sha obunachiga (interfeysdagi bitta qatorni
    sinash uchun). Berilmasa — BARCHA yoqilgan obunachilarga, ya'ni haqiqiy
    yuborish qanday ketishini aynan takrorlaydi.

    `telegram_enabled` TEKSHIRILMAYDI — sinov aynan "yoqishdan oldin
    ishlayaptimi?" degan savolga javob beradi.
    """
    company_id = _cid(company_id)
    st = st or get_settings(company_id)
    lang = i18n.norm_lang(st.get("lang"))
    targets = ([{"chat_id": chat_id, "title": None}] if chat_id
               else require_subscribers(company_id))

    head, blocks, foot = render_telegram(_sample(st), st.get("base_url"),
                                         st["min_score"], lang)
    head = f"🧪 <b>{telegram.esc(i18n.t(lang, 'test.tag'))}</b> " + head

    sent: List[str] = []
    errors: List[Dict[str, str]] = []
    messages = 0
    for sub in targets:
        cid = str(sub["chat_id"])
        try:
            messages += telegram.send_blocks(cid, head, blocks, foot)
            sent.append(cid)
        except telegram.TelegramError as e:
            errors.append({"chat_id": cid, "error": str(e)})

    # HAMMASI yiqilsa — bu xato, jimgina "yuborildi" demaymiz.
    if not sent:
        raise NotifyError(errors[0]["error"] if errors
                          else "Telegram obunachisi yo'q.")
    try:
        bot = telegram.get_me()
    except telegram.TelegramError:
        bot = {}
    # `lang` javobда qaytadi — interfeys "qaysi tilda ketdi" ni ko'rsatsin.
    return {"sent": True, "chats": sent, "lang": lang, "messages": messages,
            "errors": errors, "bot": bot.get("username")}


# ---------------------------------------------------------------------------
# Asosiy tsikl (notify_new.py va kelajakdagi jadval shu funksiyani chaqiradi)
# ---------------------------------------------------------------------------
def run(min_score: Optional[int] = None, limit: int = DEFAULT_LIMIT,
        dry_run: bool = False, force: bool = False,
        since_hours: Optional[float] = None,
        company_id: Optional[int] = None) -> Dict[str, Any]:
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
    company_id = _cid(company_id)
    st = get_settings(company_id)
    threshold = _clamp_score(min_score if min_score is not None else st["min_score"])
    # XABAR TILI — sozlamadan (foydalanuvchi interfeysда tanlagani). Ikkala
    # kanal bitta tildan foydalanadi: bir xil xabar ikki joyда boshqa tilda
    # kelsa foydalanuvchi buni nosozlik deb hisoblardi.
    lang = i18n.norm_lang(st.get("lang"))
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
                                company_id=company_id,
                                include_sent=True)

    def for_channel(kind: str) -> List[Dict[str, Any]]:
        seen = set() if force else sent_ids(kind, company_id)
        out = [t for t in all_cands if t["id"] not in seen]
        return out[:limit] if limit else out

    tenders = for_channel(KIND_NEW_MATCH)          # email
    subs = enabled_subscribers(company_id) if st.get("telegram_enabled") else []
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
        "enabled": st["enabled"], "min_score": threshold, "lang": lang,
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
        subj, text, html = render(tenders, st.get("base_url"), threshold, lang)
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
            to = recipient(st, company_id)
            result["to"] = to
            send(st, to, subj, text, html)
            for t in tenders:
                mark_sent(t["id"], to, t["score"], kind=KIND_NEW_MATCH,
                          company_id=company_id)
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
                n = send_telegram(chat_id, items, st.get("base_url"), threshold,
                                  lang)
                for t in items:
                    # `email` ustuniga chat ID yoziladi — jurnal "qayerga ketdi"
                    # degan savolga javob bersin (ustun nomi tarixiy).
                    mark_sent(t["id"], f"tg:{chat_id}", t["score"],
                              company_id=company_id,
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
