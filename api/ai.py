"""
AI qatlami — Claude orqali tender tahlili (5a bosqich)
=====================================================
Har tender uchun: O'ZBEKCHA XULOSA + KANONIK KATEGORIYA TEGLARI.

NEGA KERAK:
    Hozirgi matching.py kalit so'z bo'yicha ILIKE qiladi. Foydalanuvchi
    "kompyuter" deb yozsa, bazadagi "Моноблок", "МФУ", "Персональный
    компьютер", "Ноутбук" TOPILMAYDI — harflar mos kelmaydi. AI har tenderni
    kanonik teglarga normalizatsiya qiladi, shundan keyin moslashtirish
    ma'no bo'yicha ishlaydi (5b bosqich shu teglarga tayanadi).

XARAJAT NAZORATI (muhim):
    Natija bazada (ai_analysis) `content_hash` bilan saqlanadi. Tender
    ma'lumoti o'zgarmasa AI QAYTA CHAQIRILMAYDI. Ya'ni bir martalik xarajat.

API KALITI:
    .env da ANTHROPIC_API_KEY. Faqat backendда o'qiladi, frontendga
    hech qachon chiqmaydi. Kalitsiz ham modul import bo'ladi — chaqiruv
    paytidagina aniq xato beradi (AIUnavailable).
"""
import hashlib
import json
import os
from typing import Any, Dict, List, Optional

from api import xatolar

MODEL = "claude-opus-4-8"
KIND = "summary_v1"          # prompt/sxema o'zgarsa versiyani oshiring
MAX_TOKENS = 8000
DEFAULT_EFFORT = os.environ.get("AI_EFFORT", "medium")   # low | medium | high


class AIUnavailable(RuntimeError):
    """API kaliti yo'q yoki chaqiruv muvaffaqiyatsiz.

    XATO KODI (`kod`) — TILGA BOG'LIQ EMAS. Xabar matni SERVER
    JURNALI uchun qoladi va javobga TUSHMAYDI: ilgari
    `detail=str(e)` orqali aynan shu o'zbekcha matn mijozga
    ketardi va rus/ingliz foydalanuvchisi uni o'zbekcha ko'rardi.
    Kod `api/xatolar.py:KODLAR` da tekshiriladi — imlo xatosi
    ISHLAB CHIQISHDA chiqadi.
    """

    def __init__(self, xabar: str, *, kod: str = "",
                 params: Optional[Dict[str, Any]] = None):
        if kod and kod not in xatolar.KODLAR:
            raise KeyError(f"noma'lum xato kodi: {kod!r}")
        super().__init__(xabar)
        self.kod = kod
        self.params = params or {}


# ---------------------------------------------------------------------------
# KANONIK TAKSONOMIYA
# Erkin teg emas, QAT'IY ro'yxat — chunki 5b moslashtirish teglar bir xil
# yozilishiga tayanadi. "kompyuter-texnika" har doim shunday yoziladi.
# ---------------------------------------------------------------------------
TAXONOMY: List[str] = [
    "kompyuter-texnika",        # kompyuter, monitor, MFU, server, tarmoq
    "dasturiy-taminot",         # dastur, litsenziya, IT xizmat
    "ofis-jihozlari",           # ofis texnikasi va jihozlari
    "kanselyariya-bosmaxona",   # qog'oz, kanselyariya, bosma mahsulot
    "mebel",
    "qurilish-materiallari",
    "qurilish-ishlari",         # qurilish, ta'mirlash, montaj xizmatlari
    "elektr-energetika",        # kabel, transformator, elektr uskunalari
    "sanoat-uskunalari",        # dastgoh, stanok, ishlab chiqarish uskunasi
    "ehtiyot-qismlar",
    "transport-avtomobil",
    "neft-gaz-kimyo",
    "metall-mahsulotlari",
    "tibbiyot-jihozlari",
    "dori-vositalari",
    "oziq-ovqat",
    "qishloq-xojaligi",
    "kiyim-tekstil",
    "tozalash-kommunal",        # tozalash vositalari, kommunal xizmat
    "xavfsizlik",               # qo'riqlash, yong'in, videokuzatuv
    "xizmatlar",                # konsalting, ta'lim, ovqatlanish va h.k.
    "boshqa",
]

# Strukturali javob sxemasi — Claude AYNAN shu shaklda qaytaradi
# (structured outputs: parse xatosi bo'lmaydi)
RESULT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary_uz": {
            "type": "string",
            "description": "2-3 jumlalik SODDA o'zbekcha (lotin) xulosa: nima "
                           "sotib olinadi, kim uchun, asosiy shart. Ruscha "
                           "atamalarni tarjima qil.",
        },
        "category_tags": {
            "type": "array",
            "items": {"type": "string", "enum": TAXONOMY},
            "description": "1-3 ta kanonik kategoriya (ro'yxatdan).",
        },
        "keywords_uz": {
            "type": "array",
            "items": {"type": "string"},
            "description": "O'zbekcha (lotin) kalit so'zlar — moslashtirish uchun.",
        },
        "keywords_ru": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Ruscha sinonim/atamalar, shu jumladan manbadagi "
                           "asl nomlar va ularning keng tarqalgan variantlari.",
        },
        "supplier_profile": {
            "type": "string",
            "description": "Qanday kompaniya bu tenderga mos keladi (qisqa).",
        },
        "key_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Tadbirkor e'tibor berishi kerak bo'lgan 2-4 nuqta "
                           "(muddat, kafolat, hajm, maxsus talab).",
        },
    },
    "required": ["summary_uz", "category_tags", "keywords_uz", "keywords_ru",
                 "supplier_profile", "key_points"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = f"""Sen O'zbekiston davlat xaridlari (tenderlar) bo'yicha tahlilchisan.
Vazifang — bitta xarid protsedurasini tadbirkor uchun tushunarli qilish.

MUHIM QOIDALAR:
1. `summary_uz` — SOF O'ZBEK TILIDA (lotin alifbosi). Manba ma'lumoti ruscha
   bo'lgani uchun atamalarni TARJIMA qil, ko'chirma. Qisqa va aniq yoz:
   nima sotib olinadi, qancha, qanday shart bilan.
2. `category_tags` — faqat berilgan ro'yxatdan tanla. Mos kelmasa "boshqa".
3. `keywords_ru` — bu ENG MUHIM maydon. Tadbirkor "kompyuter" deb qidirganда
   bu tender topilishi uchun barcha ruscha sinonimlarni yoz (masalan:
   компьютер, моноблок, МФУ, ноутбук, системный блок). Manbadagi asl
   nomlarni ham kirit.
4. Ma'lumotda yo'q narsani O'YLAB TOPMA. Noaniq bo'lsa umumiy yoz.

Kategoriyalar ro'yxati: {", ".join(TAXONOMY)}"""


# ---------------------------------------------------------------------------
# Kirish matnini qurish + hash
# ---------------------------------------------------------------------------
def _prop_pair(p: Any) -> Optional[str]:
    """Texnik xususiyatni 'nom: qiymat' ko'rinishiga keltiradi.

    PLATFORMALAR HAR XIL KALIT REGISTRI ishlatadi:
      xt-xarid      -> prop_name / val_name
      etender.uzex  -> Property_Name / User_Value   (bosh harf!)
    Shuning uchun kalitlarni kichik harfga keltirib solishtiramiz.
    """
    if not isinstance(p, dict):
        return None
    low = {str(k).lower(): v for k, v in p.items()}
    name = low.get("prop_name") or low.get("property_name")
    val = low.get("val_name") or low.get("user_value")
    if name in (None, "") and val in (None, ""):
        return None
    return f"{name}: {val}"


def build_input(t: Dict[str, Any]) -> str:
    """Tender ma'lumotidan Claude uchun ixcham matn quradi.

    Faqat MA'NOGA ta'sir qiladigan maydonlar kiradi — shunda `content_hash`
    bejiz o'zgarmaydi (masalan fetched_at o'zgarsa qayta tahlil qilmaymiz).
    """
    parts: List[str] = []
    parts.append(f"Turi: {t.get('type') or 'tender'}")
    if t.get("name"):
        parts.append(f"Nomi: {t['name']}")
    if t.get("company_name"):
        parts.append(f"Buyurtmachi: {t['company_name']}")
    if t.get("region_name"):
        parts.append(f"Hudud: {t['region_name']}")
    if t.get("totalcost") is not None:
        parts.append(f"Summa: {t['totalcost']} {t.get('currency') or ''}".strip())

    for lot in (t.get("lots") or []):
        head = f"Lot {lot.get('lot_id')}"
        if lot.get("title"):
            head += f": {lot['title']}"
        parts.append(head)

    goods = [g for g in (t.get("goods") or []) if g]
    if goods:
        parts.append("Tovar/xizmatlar: " + "; ".join(goods[:25]))

    for it in (t.get("items") or [])[:12]:
        bits = [it.get("name") or ""]
        if it.get("unit"):
            bits.append(f"birlik: {it['unit']}")
        if it.get("delivery_period"):
            bits.append(f"yetkazish: {it['delivery_period']} kun")
        if it.get("guarantee"):
            bits.append(f"kafolat: {it['guarantee']} kun")
        if it.get("spec"):
            bits.append(str(it["spec"])[:200])
        pairs = [s for s in (_prop_pair(p) for p in (it.get("properties") or [])[:8]) if s]
        if pairs:
            bits.append("xususiyatlar: " + "; ".join(pairs))
        parts.append("Pozitsiya — " + ", ".join(b for b in bits if b))

    if t.get("doc_count"):
        parts.append(f"Biriktirilgan hujjatlar: {t['doc_count']} ta")

    return "\n".join(parts)


def content_hash(text: str) -> str:
    """Kirish matnining barqaror hash'i — keshni boshqaradi."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Claude chaqiruvi
# ---------------------------------------------------------------------------
_client = None


# =====================================================================
# PULLIK CHAQIRUV QULFI
#
# STANDART HOLAT — BLOKLANGAN. Loyiha egasi qat'iy shart qo'ydi:
# ishlab chiqarish holatiga chiqmaguncha HECH QANDAY pullik amal
# bajarilmaydi.
#
# NEGA KODDA, ESLAB QOLISHDA EMAS: bu loyihada pullik chaqiruv TO'RT
# modulda va bitta sinov jabdug'ida bor (`ai`, `ai_gonogo`,
# `ai_match`, `requirement_ai`, `_tests/ai_eval`). Ularning birortasi
# tasodifan chaqirilsa — pul sarflanadi va buni QAYTARIB BO'LMAYDI.
# Qoidani odam eslab qolishiga tayanish yetarli emas.
#
# Yoqish: `.env` da `AI_PAID_ENABLED=1`. Bu ATAYLAB env orqali —
# kodni o'zgartirmasdan, bitta joydan, va o'chirish ham shunchalik
# oson.
#
# QULF NIMANI QAMRAMAYDI: lokal embedding (`multilingual-e5-small`),
# naqsh ajratgichi, retrieval, ETL — ular pul sarflamaydi va
# bloklanmaydi.
PAID_ENV = "AI_PAID_ENABLED"


def paid_allowed() -> bool:
    """Pullik chaqiruvga ruxsat bormi. Standart: YO'Q."""
    return os.environ.get(PAID_ENV, "0").strip().lower() in (
        "1", "true", "yes", "on")


def paid_guard(nima: str = "AI chaqiruvi") -> None:
    """Pullik amal oldidan chaqiriladi. Ruxsat bo'lmasa TO'XTATADI.

    `AIUnavailable` ko'tariladi — loyihaning "AI ixtiyoriy" tamoyili
    bo'yicha chaqiruvchilar buni allaqachon xato emas, HOLAT deb
    ishlaydi (interfeys ogohlantirish ko'rsatadi, ETL davom etadi).
    """
    if not paid_allowed():
        raise AIUnavailable(
            f"{nima} BLOKLANGAN: pullik amallar o'chirilgan "
            f"(AI_PAID_ENABLED).",
            kod="AI_PAID_DISABLED", params={"amal": nima})


def get_client():
    """Anthropic mijozi (lazy). Kalit yo'q bo'lsa aniq xato beradi."""
    global _client
    # QULF BIRINCHI — kesh tekshiruvidan ham OLDIN. Aks holda bir
    # marta yaratilgan mijoz qulfni chetlab o'tardi.
    paid_guard("Anthropic mijozi")
    if _client is not None:
        return _client
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise AIUnavailable("ANTHROPIC_API_KEY o'rnatilmagan.",
                            kod="AI_KEY_MISSING")
    try:
        import anthropic
    except ImportError as e:
        raise AIUnavailable("`pip install anthropic` bajarilmagan.",
                            kod="AI_LIB_MISSING") from e
    _client = anthropic.Anthropic()
    return _client


def analyze(tender: Dict[str, Any], effort: str = DEFAULT_EFFORT) -> Dict[str, Any]:
    """Bitta tenderni tahlil qiladi. Kesh MANTIG'I BU YERDA EMAS —
    chaqiruvchi (etl_ai_summary.py / backend) content_hash ni tekshiradi.

    Qaytadi: {"result": {...}, "input_tokens": N, "output_tokens": N, "model": ...}
    """
    client = get_client()
    text = build_input(tender)

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            # Adaptiv fikrlash — Claude qanchalik o'ylashni o'zi tanlaydi.
            thinking={"type": "adaptive"},
            output_config={
                "effort": effort,
                # Strukturali javob: Claude AYNAN shu sxemada qaytaradi,
                # shuning uchun parse xatosi bo'lmaydi.
                "format": {"type": "json_schema", "schema": RESULT_SCHEMA},
            },
            messages=[{"role": "user", "content": text}],
        )
    except Exception as e:  # noqa: BLE001 — SDK xatolarini yuqoriga aniq uzatamiz
        raise AIUnavailable(f"Claude chaqiruvi muvaffaqiyatsiz: {e}",
                            kod="AI_CALL_FAILED") from e

    if resp.stop_reason == "refusal":
        raise AIUnavailable("Claude so'rovni rad etdi (xavfsizlik).",
                            kod="AI_REFUSED")

    raw = next((b.text for b in resp.content if b.type == "text"), None)
    if not raw:
        raise AIUnavailable("Claude bo'sh javob qaytardi.",
                            kod="AI_EMPTY_RESPONSE")

    return {
        "result": json.loads(raw),
        "model": resp.model,
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
    }
