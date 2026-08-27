"""
XABAR MATNLARI UCH TILDA (uz / ru / en) — SERVER TOMONI
=======================================================
Bildirishnoma FOYDALANUVCHI PLATFORMANI QAYSI TILDA ishlatayotgan bo'lsa,
o'sha tilda ketishi shart. Interfeys tili brauzerda tanlanadi
(`frontend/src/i18n.tsx`), lekin xabarni brauzer emas — SERVER yuboradi
(`notify_new.py` ETL dan keyin, foydalanuvchi ilovani ochmagan bo'lsa ham).
Shuning uchun tanlangan til bazaga (`notify_settings.lang`) yoziladi va
xabar shu yerdagi lug'atdan quriladi.

FRONTEND LUG'ATI TAKRORLANMAYDI. Bu yerda FAQAT xabarga tushadigan matnlar
bor (mavzu, maydon nomlari, moslik sabablari). Interfeys matnlari
brauzerda qoladi — ular hech qachon emailga tushmaydi.

KO'PLIK — rus tili uchun SHART: "1 балл / 2 балла / 5 баллов". Kalit
`<kalit>_one` / `_few` / `_many` / `_other` ko'rinishida yoziladi va
`t(...)` `n` o'zgaruvchisiga qarab to'g'risini tanlaydi. Frontenddagi
`translate()` bilan AYNAN bir xil qoida — ikki tomon bir xil o'ylasin.
Kalit topilmasa kalitning O'ZI qaytadi (jimgina bo'sh joy emas).
"""
from typing import Any, Dict, Optional

# Qo'llab-quvvatlanadigan tillar — frontend `LANGS` bilan bir xil ro'yxat.
LANGS = ("uz", "ru", "en")

# Til noma'lum bo'lsa (eski baza, buzilgan qiymat) — o'zbekcha. Platforma
# standart tili shu.
DEFAULT_LANG = "uz"


def norm_lang(v: Any) -> str:
    """Har qanday qiymatni yaroqli til kodiga keltiradi.

    'ru-RU', 'RU', ' ru ' -> 'ru'. Tanilmagani -> DEFAULT_LANG. Bu funksiya
    tilni QABUL QILADIGAN yagona darvoza: API ham, baza ham, xabar quruvchi
    ham shundan o'tadi, shuning uchun boshqa joyda tekshirish kerak emas.
    """
    s = str(v or "").strip().lower().replace("_", "-").split("-")[0]
    return s if s in LANGS else DEFAULT_LANG


def _plural(lang: str, n: int) -> str:
    """Son shakli toifasi (CLDR qoidalarining bizga kerakli qismi)."""
    if lang == "ru":
        if n % 10 == 1 and n % 100 != 11:
            return "one"
        if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
            return "few"
        return "many"
    return "one" if n == 1 else "other"


# ---------------------------------------------------------------------------
# Lug'at
# ---------------------------------------------------------------------------
# O'ZBEKCHA — MANBA. Boshqa tillar shu kalitlar bo'yicha tuziladi; kalit
# faqat bir tilda bo'lsa `t()` uni topa olmay kalitning o'zini qaytaradi va
# nosozlik darhol ko'zga tashlanadi.
UZ: Dict[str, str] = {
    # --- Email mavzusi ---
    # DIQQAT: `{score}` va `{threshold}` — TAYYOR matn ("70 ball"), son emas.
    # Sabab: rus tilida "1 балл / 2 балла / 5 баллов" — son shakli ballning
    # O'ZIGA bog'liq, ya'ni u shu yerда emas, `msg.score` da hal qilinadi.
    "subject.one": "Tender AI: 1 ta yangi mos tender ({score})",
    "subject.many": "Tender AI: {n} ta yangi mos tender (chegara {threshold})",

    # --- Xabar tanasi (matn va HTML uchun umumiy) ---
    "msg.title": "Tender AI — yangi mos tenderlar",
    "msg.titleShort": "Yangi mos tenderlar",
    "msg.summary": "Moslik chegarasi: {threshold}. Topildi: {n} ta.",
    "msg.summaryShort": "Moslik chegarasi: {threshold} · Topildi: {n} ta",
    "msg.noname": "(nomsiz)",
    "msg.match": "Moslik: {score}",
    "msg.matchBy": "Moslik: {score} ({by} bo‘yicha)",
    "msg.score": "{n} ball",
    "msg.buyer": "Buyurtmachi",
    "msg.sum": "Summa",
    "msg.deadline": "Muddat",
    "msg.region": "Hudud",
    "msg.card": "Kartochka",
    "msg.open": "Tender kartochkasini ochish",
    "msg.footAuto": "Bu xabar Tender AI tizimidan avtomatik yuborildi.",
    "msg.footSettings": "Chegarani o‘zgartirish yoki o‘chirish: "
                        "Akkaunt > Bildirishnoma.",

    # --- Telegram ---
    "tg.head": "Tender AI — {n} ta yangi mos tender",
    "tg.threshold": "Moslik chegarasi: {threshold}",
    "tg.foot": "Sozlamalar: Akkaunt → Bildirishnoma",

    # --- Ball qaysi manbadan ---
    "by.catalog": "katalog",
    "by.profile": "profil",
    "by.test": "sinov",

    # --- Sinov xabari ---
    "test.tag": "[SINOV]",
    "test.name": "Sinov xabari — Tender AI sozlamalari ishlayapti",
    "test.reason": "Bu sinov xabari — haqiqiy tender emas.",
    "test.region": "Toshkent shahri",

    # --- Moslik sabablari (api/matching.py va katalog mosligi) ---
    # DIQQAT: o'zbekcha variantlar `matching.score_tender()` ilgari qaytargan
    # matnlarning AYNAN o'zi — /match javobini ko'radigan interfeys uchun
    # hech narsa o'zgarmasin.
    "reason.keywords": "{n} ta kalit so‘z mos: {items}",
    "reason.region": "Hududingizda: {region}",
    "reason.budgetOk": "Byudjetingizga mos",
    "reason.budgetLow": "Byudjetdan tashqari (past)",
    "reason.budgetHigh": "Byudjetdan tashqari (yuqori)",
    "reason.currency": "Valyuta mos: {currency}",
    "reason.catalogCode": "Katalogingizga mos: {items} (tasniflagich kodi bo‘yicha)",
    "reason.catalogName": "Katalogingizga mos: {items} (nom bo‘yicha)",
}

RU: Dict[str, str] = {
    "subject.one": "Tender AI: 1 новый подходящий тендер ({score})",
    "subject.many_one": "Tender AI: {n} новый подходящий тендер "
                        "(порог {threshold})",
    "subject.many_few": "Tender AI: {n} новых подходящих тендера "
                        "(порог {threshold})",
    "subject.many_many": "Tender AI: {n} новых подходящих тендеров "
                         "(порог {threshold})",

    "msg.title": "Tender AI — новые подходящие тендеры",
    "msg.titleShort": "Новые подходящие тендеры",
    "msg.summary": "Порог соответствия: {threshold}. Найдено: {n}.",
    "msg.summaryShort": "Порог соответствия: {threshold} · Найдено: {n}",
    "msg.noname": "(без названия)",
    "msg.match": "Соответствие: {score}",
    "msg.matchBy": "Соответствие: {score} (по источнику: {by})",
    "msg.score_one": "{n} балл",
    "msg.score_few": "{n} балла",
    "msg.score_many": "{n} баллов",
    "msg.buyer": "Заказчик",
    "msg.sum": "Сумма",
    "msg.deadline": "Срок",
    "msg.region": "Регион",
    "msg.card": "Карточка",
    "msg.open": "Открыть карточку тендера",
    "msg.footAuto": "Это сообщение отправлено системой Tender AI автоматически.",
    "msg.footSettings": "Изменить порог или отключить: Аккаунт > Уведомления.",

    "tg.head_one": "Tender AI — {n} новый подходящий тендер",
    "tg.head_few": "Tender AI — {n} новых подходящих тендера",
    "tg.head_many": "Tender AI — {n} новых подходящих тендеров",
    "tg.threshold": "Порог соответствия: {threshold}",
    "tg.foot": "Настройки: Аккаунт → Уведомления",

    "by.catalog": "каталог",
    "by.profile": "профиль",
    "by.test": "проверка",

    "test.tag": "[ПРОВЕРКА]",
    "test.name": "Проверочное сообщение — настройки Tender AI работают",
    "test.reason": "Это проверочное сообщение, а не реальный тендер.",
    "test.region": "город Ташкент",

    "reason.keywords_one": "Совпало {n} ключевое слово: {items}",
    "reason.keywords_few": "Совпало {n} ключевых слова: {items}",
    "reason.keywords_many": "Совпало {n} ключевых слов: {items}",
    "reason.region": "В вашем регионе: {region}",
    "reason.budgetOk": "Подходит по бюджету",
    "reason.budgetLow": "Вне бюджета (ниже)",
    "reason.budgetHigh": "Вне бюджета (выше)",
    "reason.currency": "Валюта совпадает: {currency}",
    "reason.catalogCode": "Есть в вашем каталоге: {items} (по коду классификатора)",
    "reason.catalogName": "Есть в вашем каталоге: {items} (по названию)",
}

EN: Dict[str, str] = {
    "subject.one": "Tender AI: 1 new matching tender ({score})",
    "subject.many": "Tender AI: {n} new matching tenders (threshold {threshold})",

    "msg.title": "Tender AI — new matching tenders",
    "msg.titleShort": "New matching tenders",
    "msg.summary": "Match threshold: {threshold}. Found: {n}.",
    "msg.summaryShort": "Match threshold: {threshold} · Found: {n}",
    "msg.noname": "(untitled)",
    "msg.match": "Match: {score}",
    "msg.matchBy": "Match: {score} (by {by})",
    "msg.score_one": "{n} pt",
    "msg.score_other": "{n} pts",
    "msg.buyer": "Buyer",
    "msg.sum": "Amount",
    "msg.deadline": "Deadline",
    "msg.region": "Region",
    "msg.card": "Card",
    "msg.open": "Open tender card",
    "msg.footAuto": "This message was sent automatically by Tender AI.",
    "msg.footSettings": "Change the threshold or turn it off: "
                        "Account > Notifications.",

    "tg.head_one": "Tender AI — {n} new matching tender",
    "tg.head_other": "Tender AI — {n} new matching tenders",
    "tg.threshold": "Match threshold: {threshold}",
    "tg.foot": "Settings: Account → Notifications",

    "by.catalog": "catalog",
    "by.profile": "profile",
    "by.test": "test",

    "test.tag": "[TEST]",
    "test.name": "Test message — your Tender AI settings work",
    "test.reason": "This is a test message, not a real tender.",
    "test.region": "Tashkent city",

    "reason.keywords_one": "{n} keyword matched: {items}",
    "reason.keywords_other": "{n} keywords matched: {items}",
    "reason.region": "In your region: {region}",
    "reason.budgetOk": "Fits your budget",
    "reason.budgetLow": "Outside budget (below)",
    "reason.budgetHigh": "Outside budget (above)",
    "reason.currency": "Currency matches: {currency}",
    "reason.catalogCode": "In your catalog: {items} (by classifier code)",
    "reason.catalogName": "In your catalog: {items} (by name)",
}

MESSAGES: Dict[str, Dict[str, str]] = {"uz": UZ, "ru": RU, "en": EN}


def t(lang: Optional[str], key: str, **vars_: Any) -> str:
    """Kalitni matnga aylantiradi.

        t("ru", "msg.score", n=70)      -> "70 баллов"
        t("uz", "reason.region", region="Toshkent shahri")

    `n` berilsa avval `<kalit>_<toifa>`, so'ng `<kalit>_other`, so'ng
    `<kalit>` qidiriladi — ya'ni ko'plik kerak bo'lmagan kalitga qo'shimcha
    yozish SHART EMAS.

    Tilda kalit topilmasa o'zbekchaga (manba lug'atga) tushiladi: yangi
    kalit qo'shilib tarjimasi kechiksa ham xabar BUZILMAYDI.
    """
    code = norm_lang(lang)
    dicts = (MESSAGES[code], UZ) if code != DEFAULT_LANG else (UZ,)

    raw = None
    for d in dicts:
        if "n" in vars_ and isinstance(vars_["n"], int):
            cat = _plural(code, vars_["n"])
            raw = d.get(f"{key}_{cat}") or d.get(f"{key}_other")
        raw = raw or d.get(key)
        if raw:
            break
    if raw is None:
        return key          # nosozlik ko'rinib tursin

    for name, val in vars_.items():
        raw = raw.replace("{" + name + "}", str(val))
    return raw
