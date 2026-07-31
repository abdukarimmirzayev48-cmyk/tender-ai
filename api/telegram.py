"""
TELEGRAM BOT TRANSPORTI — Bot API bilan gaplashadigan YAGONA joy
================================================================
Bu modul FAQAT TRANSPORT: token oladi, HTTP so'rov yuboradi, javobni tekshiradi
va Telegram xatosini o'zbekcha `TelegramError` ga aylantiradi.

XABAR MATNI BU YERDA QURILMAYDI. Nima yozilishi (tender nomi, ball, kartochka
havolasi) — `api/notify.py` ning ishi (`render_telegram()`). Sabab: notify.py
allaqachon summa/sana formatlash va `card_url()` ni saqlaydi; ularni bu yerda
takrorlasak ikkita haqiqat manbai paydo bo'lardi. Shu bo'linish tufayli
notify.py -> telegram.py bir tomonlama import bo'ladi (aylanma import yo'q).

TOKEN BAZADA EMAS — `.env` dagi `TELEGRAM_BOT_TOKEN` (SMTP_PASSWORD bilan bir xil
qoida). Sabab: token bilan botni to'liq boshqarish mumkin, baza dumpi esa ko'p
qo'ldan o'tadi. Token yo'q bo'lsa `TelegramError` OTILADI — jimgina "yuborildi"
deyilmaydi.

CHAT_ID QAYERDAN: foydalanuvchi botga Telegramда "/start" yozadi, so'ng
`discover_chats()` (getUpdates) o'sha suhbatni ko'rsatadi. Bot BIRINCHI
bo'lib yoza olmaydi — bu Telegram cheklovi, aylanib o'tib bo'lmaydi.
"""
import os
from html import escape
from typing import Any, Dict, List, Optional

import requests

# Bot API manzili. Token URL ichida ketadi, shuning uchun xato matnlarига
# HECH QACHON to'liq URL qo'shilmaydi (pastda `_safe_method` ga qarang).
API_ROOT = "https://api.telegram.org"

# Tarmoq kutish vaqti. ETL dan keyin ishlaydigan skript osilib qolmasin.
HTTP_TIMEOUT = 20

# Telegram bitta xabar uchun 4096 belgi beradi. Xavfsiz chegara pastroq:
# HTML teglari hisobga olinadi va chegaraда bo'linish tegni ikkiga bo'lib
# yuborishi mumkin (Telegram bunda butun xabarni rad etadi).
MAX_MESSAGE = 4096
SAFE_MESSAGE = 3600

# getUpdates: uzun so'rov (long polling) KERAK EMAS — biz faqat "kim yozdi"
# ro'yxatini olamiz, shuning uchun timeout=0 (darhol qaytadi).
UPDATES_LIMIT = 100


class TelegramError(RuntimeError):
    """Telegram orqali yuborib bo'lmadi (token/chat/tarmoq xatosi).
    `notify.NotifyError` bilan bir xil rolda — API uni 400 ga aylantiradi."""


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------
def token() -> Optional[str]:
    """Bot tokeni FAQAT .env dan (bazada saqlanmaydi)."""
    t = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    return t or None


def token_set() -> bool:
    """Interfeys uchun: token sozlanganmi (tokenning O'ZI qaytmaydi)."""
    return token() is not None


def require_token() -> str:
    """Token yo'q bo'lsa ANIQ xato — jimgina o'tilmaydi."""
    t = token()
    if not t:
        raise TelegramError(
            "Telegram bot tokeni topilmadi. Uni serverdagi .env fayliga "
            "qo'shing: TELEGRAM_BOT_TOKEN=... (tokenni @BotFather beradi), "
            "so'ng API'ni qayta ishga tushiring.")
    return t


# ---------------------------------------------------------------------------
# Bot API chaqiruvi
# ---------------------------------------------------------------------------
def _uz_error(method: str, code: Optional[int], desc: str,
              retry_after: Optional[int] = None) -> str:
    """Telegram xatosini foydalanuvchi TUZATA OLADIGAN matnga aylantiradi.
    Inglizcha `description` ham qoldiriladi — qo'llab-quvvatlash uchun kerak."""
    d = (desc or "").lower()
    if code == 401 or "unauthorized" in d:
        return ("Telegram tokeni noto'g'ri (401). .env dagi TELEGRAM_BOT_TOKEN ni "
                "tekshiring — @BotFather > /mybots > API Token.")
    if "chat not found" in d:
        return ("Chat topilmadi. Telegramда botga yozing (/start bosing), so'ng "
                "\"Chatlarni aniqlash\" tugmasi bilan chat ID ni tanlang. "
                "Bot suhbatni O'ZI boshlay olmaydi — bu Telegram cheklovi.")
    if "bot was blocked" in d or "bot was kicked" in d:
        return ("Bot bloklangan yoki guruhdan chiqarilgan. Telegramда botni "
                "blokdan chiqaring (yoki guruhga qayta qo'shing) va qaytadan urining.")
    if "not enough rights" in d or "have no rights" in d:
        return ("Botning bu guruhда xabar yozishga huquqi yo'q. Uni administrator "
                "qiling yoki xabar yuborish ruxsatini bering.")
    if code == 429:
        return (f"Telegram so'rovlar chegarasi (429). {retry_after or 'Bir necha'} "
                f"soniyadan keyin qayta urinib ko'ring.")
    return f"Telegram xatosi ({method}, {code}): {desc or 'noma’lum'}"


def call(method: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """Bot API metodini chaqiradi va `result` ni qaytaradi.

    Har qanday nosozlik — HTTP, JSON, `ok:false` — bitta `TelegramError` ga
    o'raladi, chunki chaqiruvchi (notify/API/skript) faqat shu turni ushlaydi.
    Xato matnida TOKEN CHIQMAYDI (URL qo'shilmaydi).
    """
    t = require_token()
    url = f"{API_ROOT}/bot{t}/{method}"
    try:
        r = requests.post(url, json=params or {}, timeout=HTTP_TIMEOUT)
    except requests.RequestException as e:
        # str(e) ichida URL (ya'ni TOKEN) bo'lishi mumkin — shuning uchun
        # xato TURI yoziladi, matni emas.
        raise TelegramError(
            f"Telegram serveriga ulanib bo'lmadi ({method}): "
            f"{type(e).__name__}. Internet/proksi sozlamalarini tekshiring."
        ) from e

    try:
        body = r.json()
    except ValueError as e:
        raise TelegramError(
            f"Telegram tushunarsiz javob qaytardi ({method}, HTTP {r.status_code})."
        ) from e

    if not body.get("ok"):
        params_ = body.get("parameters") or {}
        raise TelegramError(_uz_error(
            method, body.get("error_code") or r.status_code,
            str(body.get("description") or ""), params_.get("retry_after")))
    return body.get("result")


# ---------------------------------------------------------------------------
# Metodlar
# ---------------------------------------------------------------------------
def get_me() -> Dict[str, Any]:
    """Bot haqida ma'lumot (username, ismi). Interfeysда "qaysi botga yozish
    kerak" degan savolga javob bo'ladi."""
    me = call("getMe") or {}
    return {"id": me.get("id"), "username": me.get("username"),
            "first_name": me.get("first_name")}


def esc(v: Any) -> str:
    """Telegram HTML rejimi uchun escape.

    FAQAT `&`, `<`, `>` — Telegram shuni talab qiladi. Apostrof/qo'shtirnoq
    TEGILMAYDI (`quote=False`): o'zbekcha matnda apostrof har qadamda uchraydi
    va `&#x27;` ga aylansa xabar o'qib bo'lmas holga keladi.
    """
    return escape("" if v is None else str(v), quote=False)


def send_message(chat_id: str, text: str, preview: bool = False) -> Dict[str, Any]:
    """Bitta HTML xabar. `text` MAX_MESSAGE dan uzun bo'lmasligi kerak —
    bo'lish `send_blocks()` ning ishi."""
    return call("sendMessage", {
        "chat_id": str(chat_id).strip(),
        "text": text,
        "parse_mode": "HTML",
        # Havola oldi ko'rinishi (preview) o'chirilgan: har tender uchun havola
        # bor, aks holda Telegram ularni katta rasmlar bilan to'ldirib yuboradi.
        "link_preview_options": {"is_disabled": not preview},
        "disable_web_page_preview": not preview,   # eski Bot API versiyalari uchun
    })


def send_blocks(chat_id: str, header: str, blocks: List[str],
                footer: str = "") -> int:
    """Bloklarni 4096 belgilik chegaraga sig'diradigan qilib bo'lib yuboradi.

    BLOK O'RTASIDAN KESILMAYDI — aks holda ochilgan `<b>`/`<a>` tegi yopilmay
    qolib, Telegram BUTUN xabarni rad etadi (400: can't parse entities).
    Bitta blokning o'zi chegaradan uzun bo'lsa — u qirqiladi (teglar bloklar
    ichида muvozanatli, qirqim esa oxiridan bo'ladi -> pastda `_trim`).

    Qaytadi: yuborilgan xabarlar soni.
    """
    parts: List[str] = []
    cur = header
    for b in blocks:
        b = _trim(b)
        # +2 — bloklar orasidagi bo'sh qator
        if cur and len(cur) + len(b) + 2 > SAFE_MESSAGE:
            parts.append(cur)
            cur = b
        else:
            cur = f"{cur}\n\n{b}" if cur else b
    if footer:
        if len(cur) + len(footer) + 2 > SAFE_MESSAGE:
            parts.append(cur)
            cur = footer
        else:
            cur = f"{cur}\n\n{footer}" if cur else footer
    if cur:
        parts.append(cur)

    for p in parts:
        send_message(chat_id, p)
    return len(parts)


def _trim(block: str) -> str:
    """Bitta blok chegaradan uzun bo'lsa qisqartiradi. Bloklar HTML jihatdan
    o'zi-o'ziga yetarli (teglar ichида ochilib-yopiladi), lekin qirqim tegni
    kesib qo'ymasligi uchun oxirgi '<' dan keyingi qism tashlanadi."""
    if len(block) <= SAFE_MESSAGE:
        return block
    cut = block[:SAFE_MESSAGE - 20]
    lt, gt = cut.rfind("<"), cut.rfind(">")
    if lt > gt:                      # yarim ochilgan teg qoldi
        cut = cut[:lt]
    return cut + "…"


def discover_chats() -> List[Dict[str, Any]]:
    """`getUpdates` — botga YAQINDA yozgan suhbatlar va ular YUBORGAN MATN.

    Har element: chat ma'lumoti + `texts` (o'sha suhbatdan kelgan xabarlar).
    `texts` ULASH TOKENINI topish uchun kerak: foydalanuvchi platformadagi
    havolani bosganda Telegram botga `/start <token>` yuboradi.

    DIQQAT — Telegram cheklovlari, ular aylanib o'tib bo'lmaydigan:
      * Bot suhbatni o'zi boshlay olmaydi — avval /start bosilishi shart.
      * getUpdates yangilanishlarni ~24 soat saqlaydi, keyin o'chiradi.
      * Webhook o'rnatilgan bo'lsa getUpdates ishlamaydi (bizда webhook yo'q).

    O'QILGAN DEB BELGILANMAYDI (`offset` yuborilmaydi) — agar bazaga yozish
    yiqilsa, yangilanish Telegramда qolib, keyingi urinishда qaytadi.
    """
    updates = call("getUpdates", {
        "limit": UPDATES_LIMIT,
        "timeout": 0,
        "allowed_updates": ["message", "channel_post", "my_chat_member"],
    }) or []

    out: Dict[str, Dict[str, Any]] = {}
    for u in updates:
        msg = (u.get("message") or u.get("channel_post")
               or u.get("my_chat_member") or {})
        chat = msg.get("chat") or {}
        cid = chat.get("id")
        if cid is None:
            continue
        title = (chat.get("title")
                 or " ".join(filter(None, [chat.get("first_name"),
                                           chat.get("last_name")]))
                 or chat.get("username") or str(cid))
        key = str(cid)
        # dict kaliti bo'yicha — bitta suhbat bir necha update bersa ham
        # ro'yxatда bir marta chiqadi (oxirgi ma'lumot bilan), lekin
        # MATNLAR YIG'ILADI: token ular orasida bo'lishi mumkin.
        prev_texts = out.get(key, {}).get("texts", [])
        text = msg.get("text") or msg.get("caption")
        out[key] = {
            "chat_id": key,
            "title": title,
            "type": chat.get("type"),          # private | group | supergroup | channel
            "username": chat.get("username"),
            "texts": prev_texts + ([text] if text else []),
        }
    return list(out.values())
