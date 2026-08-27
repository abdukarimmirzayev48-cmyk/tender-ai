"""
AI MOSLIK TAHLILI — bu tender sizga mos keladimi?
=================================================
`api/ai.py` dan FARQI: u bitta tenderni MUSTAQIL tahlil qiladi (xulosa,
teglar). Bu modul esa MUNOSABATNI baholaydi — tender ↔ foydalanuvchi
katalogi/profili. Javob: mos / qisman / mos emas + sabab.

NEGA AI KERAK (deterministik filtr yetmasligi):
    Katalogda "Насос" bo'lsa, matn qidiruvi "Насос гидравлический" ni topadi.
    Lekin u BILMAYDI:
      - tender aslida nasos EMAS, nasos uchun ehtiyot qism ekanini
      - texnik talab (bosim, quvvat, sertifikat) mahsulotga to'g'ri kelmasligini
      - "Услуга по ремонту насосов" — bu xizmat, mahsulot sotuvchiga mos emasligini
    Bu farqlarni faqat ma'noni tushunadigan model ajrata oladi.

KESHLASH — XARAJAT NAZORATI:
    Hukm IKKI narsaga bog'liq: tender mazmuni VA foydalanuvchi katalogi.
    Shuning uchun `content_hash` = sha256(tender matni + katalog izi).
    Ikkalasidan biri o'zgarmasa AI QAYTA CHAQIRILMAYDI. Natija `ai_analysis`
    jadvalida kind='match_v1' bilan yotadi (sxema o'zgarishi shart emas —
    jadval allaqachon `kind` bo'yicha versiyalangan).

API KALITI:
    .env dagi ANTHROPIC_API_KEY. Kalit yo'q bo'lsa modul baribir import
    bo'ladi; xato faqat chaqiruv paytida chiqadi (ai.AIUnavailable).
"""
import hashlib
import json
import os
from typing import Any, Dict, List, Optional

from api import ai  # build_input(), AIUnavailable, get_client() — qayta yozmaymiz

#: Claude Opus 5 — Opus 4.8 bilan bir xil narxda, chuqurroq mulohaza.
#: Fikrlash SHU MODELDA DEFAULT YOQIQ: `max_tokens` fikrlash + javob matnini
#: BIRGA cheklaydi, shuning uchun byudjet kengroq olingan.
MODEL = "claude-opus-5"
KIND = "match_v2"            # v2: promptga BIRIKTIRILGAN HUJJAT MATNI qo'shildi
MAX_TOKENS = 6000
DEFAULT_EFFORT = os.environ.get("AI_MATCH_EFFORT", "medium")

#: Xavfsizlik klassifikatori so'rovni rad etsa, Anthropic tavsiya qilgan
#: zaxira modelga o'tkazadi (server tomonda, bitta so'rov ichida).
_FALLBACK_BETA = "server-side-fallback-2026-07-01"

VERDICTS = ["mos", "qisman", "mos_emas"]

RESULT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": VERDICTS,
            "description": "mos — katalogdagi mahsulot/xizmat aynan shu tenderда "
                           "talab qilinadi; qisman — bog'liq, lekin to'liq mos "
                           "emas (masalan faqat bir qismi yoki turdosh mahsulot); "
                           "mos_emas — aloqasi yo'q.",
        },
        "score": {
            "type": "integer",
            "description": "0-100 ishonch balli. mos>=70, qisman 35-69, mos_emas<35.",
        },
        "reason_uz": {
            "type": "string",
            "description": "2-3 jumla, SOF O'ZBEK TILIDA (lotin): nega shunday "
                           "hukm chiqardingiz. Aniq dalilga tayan — qaysi "
                           "pozitsiya, qaysi katalog bandi.",
        },
        "matched_items": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Katalogning qaysi bandlari mos keldi (aynan nomi). "
                           "Hech biri mos kelmasa bo'sh massiv.",
        },
        "requirements": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Qatnashish uchun bajarilishi kerak bo'lgan 0-4 ta "
                           "aniq talab (muddat, kafolat, sertifikat, hajm).",
        },
        "risks": {
            "type": "array",
            "items": {"type": "string"},
            "description": "0-3 ta xavf yoki e'tibor talab qiladigan nuqta. "
                           "Yo'q bo'lsa bo'sh massiv.",
        },
    },
    "required": ["verdict", "score", "reason_uz", "matched_items",
                 "requirements", "risks"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """Sen O'zbekiston davlat xaridlari bo'yicha tahlilchisan.
Sanga BITTA tender va ta'minotchining MAHSULOT KATALOGI beriladi. Vazifang —
shu ta'minotchi bu tenderда qatnasha oladimi yoki yo'qmi, aniq hukm chiqarish.

QAT'IY QOIDALAR:
1. Faqat berilgan ma'lumotga tayan. Tenderда yo'q talabni O'YLAB TOPMA,
   katalogda yo'q imkoniyatni ham taxmin qilma.
2. Nom o'xshashligi YETARLI EMAS. Quyidagilarni ajrat:
   - mahsulotning O'ZI kerakmi yoki uning EHTIYOT QISMImi;
   - mahsulot yetkazib berish kerakmi yoki XIZMAT (ta'mirlash, montaj,
     loyihalash) kerakmi — bular har xil ish;
   - texnik xususiyatlar (o'lcham, quvvat, tur) haqiqatan mos keladimi.
   Masalan katalogda "Насос" bo'lib, tenderда "Кольцо для ремонта насосов"
   talab qilinsa — bu MOS EMAS, bu nasos emas, uning zichlagichi.
3. Katalog bo'sh bo'lsa: verdict="mos_emas", score=0, reason_uz da
   katalogni to'ldirish kerakligini yoz.
4. `reason_uz` — sof o'zbek tilida (lotin alifbosi). Manba ruscha bo'lgani
   uchun atamalarni TARJIMA qil, ko'chirma. Qisqa va dalilga asoslangan yoz.
5. `matched_items` ga faqat katalogda AYNAN yozilgan nomlarni kiritasan.
6. Ikkilanayotgan bo'lsang "qisman" ni tanla va sababini ayt — noto'g'ri
   "mos" degandan ko'ra halol "qisman" foydaliroq.
7. BIRIKTIRILGAN HUJJAT MATNI berilgan bo'lsa — ASOSIY MANBA O'SHA.
   Kartochkadagi qisqa nom umumiy bo'ladi, aniq texnik talab esa texnik
   topshiriqda yoziladi. Ikkalasi ziddiyat qilsa hujjatga ishon.
   - `requirements` va `risks` ni imkon qadar hujjatdan ol va qaysi
     hujjatdan olganingni qavsda ko'rsat: "GOST 12.4.011 talab (Техник
     топшириқ)".
   - Hujjat matni QISQARTIRILGAN deb ogohlantirilgan bo'lsa: bo'lakda
     ko'rinmagan narsani "yo'q" dema, "hujjat bo'lagida ko'rsatilmagan" de.
   - Hujjat umuman o'qilmagan bo'lsa — buni `risks` ga yoz, chunki tahlil
     to'liq emas."""


# ---------------------------------------------------------------------------
# Kirish matni va kesh kaliti
# ---------------------------------------------------------------------------
def _fmt_catalog(products: List[Dict[str, Any]]) -> str:
    """Katalogni ixcham matnga. Tartib BARQAROR — hash bejiz o'zgarmasin."""
    if not products:
        return "(katalog bo'sh)"
    lines = []
    for p in sorted(products, key=lambda x: (x.get("name") or "").lower()):
        bits = [p.get("name") or ""]
        if p.get("category_code"):
            bits.append(f"kategoriya: {p['category_code']}")
        kws = [k for k in (p.get("keywords") or []) if k]
        if kws:
            bits.append("kalit so'zlar: " + ", ".join(sorted(kws)))
        if p.get("unit"):
            bits.append(f"birlik: {p['unit']}")
        lines.append("- " + ", ".join(b for b in bits if b))
    return "\n".join(lines)


def _fmt_profile(profile: Optional[Dict[str, Any]]) -> str:
    if not profile:
        return ""
    bits = []
    if profile.get("regions"):
        bits.append("hududlar: " + ", ".join(sorted(profile["regions"])))
    if profile.get("currency"):
        bits.append(f"valyuta: {profile['currency']}")
    if profile.get("min_cost") is not None:
        bits.append(f"min summa: {profile['min_cost']}")
    if profile.get("max_cost") is not None:
        bits.append(f"max summa: {profile['max_cost']}")
    return ("Ta'minotchi cheklovlari: " + "; ".join(bits)) if bits else ""


def build_input(tender: Dict[str, Any], products: List[Dict[str, Any]],
                profile: Optional[Dict[str, Any]] = None,
                docs: str = "") -> str:
    """Claude'ga yuboriladigan to'liq matn (tender + hujjatlar + katalog).

    Tender qismi `ai.build_input()` dan olinadi — ikkita modulda bir xil
    formatlash mantig'i bo'lmasligi uchun.

    `docs` — `ai_docs.prompt_block()` natijasi. U KATALOGDAN OLDIN turadi:
    model avval "tenderда nima talab qilinyapti" ni to'liq o'qisin, keyin
    katalog bilan solishtirsin.
    """
    parts = ["=== TENDER ===", ai.build_input(tender)]
    if docs:
        parts += ["", docs]
    parts += ["", "=== KATALOG ===", _fmt_catalog(products)]
    prof = _fmt_profile(profile)
    if prof:
        parts += ["", prof]
    return "\n".join(parts)


def content_hash(text: str) -> str:
    """Kesh kaliti. Matn tender VA katalogni qamragani uchun ikkalasidan
    biri o'zgarsa hash o'zgaradi va tahlil qayta yuritiladi."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Claude chaqiruvi
# ---------------------------------------------------------------------------
def _extract(resp) -> Dict[str, Any]:
    """Javobni tekshirib, JSON natijani ajratadi."""
    # Rad etish HTTP 200 bilan keladi — content ga qo'l urishdan OLDIN tekshiramiz
    if resp.stop_reason == "refusal":
        cat = getattr(getattr(resp, "stop_details", None), "category", None)
        raise ai.AIUnavailable(f"Claude so'rovni rad etdi (xavfsizlik: {cat}).")
    if resp.stop_reason == "max_tokens":
        # Opus 5 da fikrlash va javob matni BITTA byudjetni bo'lishadi
        raise ai.AIUnavailable(
            "Javob token chegarasiga yetdi — MAX_TOKENS ni oshiring.")
    raw = next((b.text for b in resp.content if b.type == "text"), None)
    if not raw:
        raise ai.AIUnavailable("Claude bo'sh javob qaytardi.")
    return json.loads(raw)


def analyze(tender: Dict[str, Any], products: List[Dict[str, Any]],
            profile: Optional[Dict[str, Any]] = None,
            effort: str = DEFAULT_EFFORT,
            docs: str = "") -> Dict[str, Any]:
    """Bitta tenderni katalogga nisbatan baholaydi.

    Kesh MANTIG'I BU YERDA EMAS — chaqiruvchi content_hash ni tekshiradi.
    Qaytadi: {"result": {...}, "model": ..., "input_tokens": N, "output_tokens": N}
    """
    client = ai.get_client()
    text = build_input(tender, products, profile, docs)

    kwargs: Dict[str, Any] = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "output_config": {
            "effort": effort,
            # Strukturali javob — sxemadan chetga chiqmaydi, parse xatosi yo'q
            "format": {"type": "json_schema", "schema": RESULT_SCHEMA},
        },
        "messages": [{"role": "user", "content": text}],
    }

    try:
        # Zaxira model bilan: klassifikator rad etsa so'rov shu yerda
        # Anthropic tavsiya qilgan modelga o'tadi (qo'shimcha so'rov emas).
        resp = client.beta.messages.create(
            betas=[_FALLBACK_BETA], fallbacks="default", **kwargs)
    except TypeError:
        # SDK bu parametrni bilmaydi (eski versiya) — zaxirasiz davom etamiz
        resp = client.messages.create(**kwargs)
    except Exception as e:  # noqa: BLE001
        # Beta bayrog'i qabul qilinmasa oddiy yo'l bilan qayta urinamiz;
        # boshqa xatolarni yuqoriga aniq uzatamiz.
        if _FALLBACK_BETA in str(e) or "fallback" in str(e).lower():
            try:
                resp = client.messages.create(**kwargs)
            except Exception as e2:  # noqa: BLE001
                raise ai.AIUnavailable(f"Claude chaqiruvi muvaffaqiyatsiz: {e2}") from e2
        else:
            raise ai.AIUnavailable(f"Claude chaqiruvi muvaffaqiyatsiz: {e}") from e

    return {
        "result": _extract(resp),
        "model": resp.model,
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
    }
