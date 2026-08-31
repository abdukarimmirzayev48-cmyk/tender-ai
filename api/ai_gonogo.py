"""
GO / NO-GO TAVSIYASI — tenderda qatnashish kerakmi?
===================================================
11 ta mezon bo'yicha baholab, uchta qarordan birini beradi:
    go     — qatnashish tavsiya qilinadi
    review — inson tekshiruvi kerak (odatda ma'lumot yetishmaydi)
    no_go  — qatnashish maqsadga muvofiq emas

`ai_match.py` DAN FARQI: u faqat "mahsulotim mos keladimi" degan savolga
javob beradi. Bu esa qatnashish qarorini butun kesimda ko'radi — muddat,
byudjet, sertifikat, tajriba, resurs.

MVP DARAJASIGA MOSLASH — eng muhim dizayn qarori:
    O'lchov ko'rsatdiki, 11 mezondan faqat 4 tasi to'liq, 2 tasi qisman
    baholanadi; 5 tasi (sertifikat, moliya, tajriba, resurs, xavfsizlik
    ruxsati) uchun bazada MANBA YO'Q edi. Ikki qadam qilindi:
      1. `company_profile` shu 5 mezonni yopadigan maydonlar bilan kengaytirildi
         (schema_patch_gonogo.sql). Hammasi ixtiyoriy.
      2. Har mezon `malumot_yoq` holatini QAYTARA OLADI. Model bo'sh joyni
         taxmin bilan to'ldirmaydi — qaror "review" ga tushadi va qaysi
         ma'lumot yetishmayotgani aniq aytiladi.
    Ya'ni funksiya bor ma'lumot darajasida halol ishlaydi, ko'proq emas.

TAYANCH FAKTLAR (grounding):
    Muddat, hudud mosligi, byudjet chegarasi kabi ANIQ hisoblanadigan narsalar
    Pythonда hisoblanib, promptga "FAKTLAR" bo'limi sifatida beriladi. Model
    ularni qayta hisoblamaydi — shu bilan sana/summa xatolari yo'qoladi.

KESHLASH: `ai_analysis`, kind='gonogo_v2'. Kalit = tender + HUJJAT MATNI + katalog + profil.
"""
import datetime as _dt
import hashlib
import json
import os
from typing import Any, Dict, List, Optional

from api import ai, ai_match

MODEL = "claude-opus-5"
KIND = "gonogo_v2"   # v2: promptga biriktirilgan hujjat matni qo'shildi
#: Fikrlash bu modelda default yoqiq va `max_tokens` fikrlash + javobni BIRGA
#: cheklaydi. 11 mezonli javob uzun, shuning uchun byudjet kengroq.
MAX_TOKENS = 10000
DEFAULT_EFFORT = os.environ.get("AI_GONOGO_EFFORT", "high")

_FALLBACK_BETA = "server-side-fallback-2026-07-01"

DECISIONS = ["go", "review", "no_go"]
STATUSES = ["ok", "risk", "fail", "malumot_yoq"]

#: 11 mezon — foydalanuvchi so'ragan ro'yxat. Kalitlar QAT'IY: frontend shu
#: nomlarга qarab yorliq va tartibni chizadi.
CRITERIA: List[Dict[str, str]] = [
    {"key": "majburiy_talablar",        "label": "Majburiy talablar"},
    {"key": "faoliyat_mosligi",         "label": "Faoliyat mosligi"},
    {"key": "sertifikat",               "label": "Sertifikat / litsenziya"},
    {"key": "moliyaviy_salohiyat",      "label": "Moliyaviy salohiyat"},
    {"key": "tajriba",                  "label": "Tajriba"},
    {"key": "deadline",                 "label": "Muddat (deadline)"},
    {"key": "geografik_cheklov",        "label": "Geografik cheklov"},
    {"key": "resurs_yetarliligi",       "label": "Resurs yetarliligi"},
    {"key": "xavfsizlik_ruxsatnomalari", "label": "Xavfsizlik ruxsatnomalari"},
    {"key": "tender_qiymati",           "label": "Tender qiymati"},
    {"key": "foyda_xarajat",            "label": "Foyda va xarajat"},
]
_KEYS = [c["key"] for c in CRITERIA]

RESULT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "decision": {
            "type": "string", "enum": DECISIONS,
            "description": "go — qatnashish tavsiya qilinadi; review — inson "
                           "tekshiruvi kerak; no_go — qatnashish maqsadga "
                           "muvofiq emas.",
        },
        "confidence": {
            "type": "integer",
            "description": "0-100: qarorga qanchalik ishonch. Ma'lumot ko'p "
                           "yetishmasa PAST bo'lishi kerak.",
        },
        "summary_uz": {
            "type": "string",
            "description": "2-3 jumla, SOF O'ZBEK TILIDA (lotin): qaror va uning "
                           "asosiy sababi. Buyurtmachi nomini emas, MOHIYATNI yoz.",
        },
        "criteria": {
            "type": "array",
            "description": "AYNAN 11 ta band, ro'yxatdagi tartibda.",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "enum": _KEYS},
                    "status": {
                        "type": "string", "enum": STATUSES,
                        "description": "ok — talab bajariladi; risk — bajariladi "
                                       "lekin xavf bor; fail — bajarilmaydi "
                                       "(bu No-Go sababi); malumot_yoq — "
                                       "baholash uchun ma'lumot yetarli emas.",
                    },
                    "note_uz": {
                        "type": "string",
                        "description": "1 jumla o'zbekcha izoh. `malumot_yoq` "
                                       "bo'lsa — QAYSI ma'lumot kerakligini ayt.",
                    },
                },
                "required": ["key", "status", "note_uz"],
                "additionalProperties": False,
            },
        },
        "blockers": {
            "type": "array", "items": {"type": "string"},
            "description": "Qatnashishga to'sqinlik qiladigan aniq sabablar "
                           "(faqat `fail` mezonlardan). Yo'q bo'lsa bo'sh.",
        },
        "next_steps": {
            "type": "array", "items": {"type": "string"},
            "description": "1-4 ta amaliy keyingi qadam. `review` qarorida — "
                           "aynan nimani tekshirish kerakligi.",
        },
        "missing_data": {
            "type": "array", "items": {"type": "string"},
            "description": "Qaror aniqroq bo'lishi uchun profilda to'ldirilishi "
                           "kerak bo'lgan ma'lumotlar. Yo'q bo'lsa bo'sh.",
        },
    },
    "required": ["decision", "confidence", "summary_uz", "criteria",
                 "blockers", "next_steps", "missing_data"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = f"""Sen O'zbekiston davlat xaridlarida ta'minotchiga maslahat
beruvchi tahlilchisan. Senga bitta tender, ta'minotchining mahsulot katalogi va
kompaniya profili beriladi. Vazifang — QATNASHISH KERAKMI degan savolga asosli
javob berish.

QARORLAR:
  go     — barcha hal qiluvchi mezonlar bajariladi, jiddiy to'siq yo'q
  review — biror hal qiluvchi mezonda ma'lumot yetishmaydi yoki jiddiy xavf bor;
           inson tekshirishi kerak
  no_go  — kamida bitta mezon BAJARILMAYDI (status=fail)

QAT'IY QOIDALAR:
1. `criteria` da AYNAN 11 ta band bo'lishi shart, quyidagi tartibda:
   {", ".join(_KEYS)}
2. MA'LUMOT YO'Q BO'LSA — `malumot_yoq` deb belgila. TAXMIN QILMA.
   Kompaniya profilida sertifikat/tajriba/moliya ko'rsatilmagan bo'lsa,
   bu "yomon" degani EMAS — bu "bilmayman" degani. Bunday holda `note_uz` da
   qanday ma'lumot kerakligini ayt va uni `missing_data` ga ham qo'sh.
3. Kamida bitta `fail` bo'lsa — qaror `no_go`, sababi `blockers` da.
   `fail` faqat ANIQ dalilga asoslanadi (masalan muddat allaqachon o'tgan,
   tender summasi kompaniya salohiyatidan bir necha barobar katta).
4. Hal qiluvchi mezonda `malumot_yoq` yoki `risk` bo'lsa — qaror `review`.
   Hal qiluvchi mezonlar: majburiy_talablar, faoliyat_mosligi, deadline,
   tender_qiymati, moliyaviy_salohiyat.
5. `confidence` ni halol ber: ma'lumot qancha kam bo'lsa, shuncha past.
6. Barcha matn SOF O'ZBEK TILIDA (lotin alifbosi). Manba ruscha bo'lgani
   uchun atamalarni TARJIMA qil, ko'chirma.
7. "FAKTLAR" bo'limidagi hisoblangan qiymatlarni QAYTA HISOBLAMA — ular
   aniq. Ularga tayan.
8. Ma'lumotda yo'q talabni o'ylab topma. Tender matnida sertifikat talabi
   ko'rsatilmagan bo'lsa, uni "kerak" deb faraz qilma.
9. BIRIKTIRILGAN HUJJAT MATNI berilgan bo'lsa — QAROR ASOSAN O'SHANGA
   TAYANADI. Qatnashishga to'sqinlik qiladigan shartlar kartochkada
   deyarli hech qachon bo'lmaydi; ular texnik topshiriq va shartnoma
   loyihasida yoziladi. Hujjatdan AYNIQSA shularni qidir:
   - malaka talablari (tajriba yillari, o'xshash shartnomalar, aylanma);
   - majburiy sertifikat / litsenziya / ruxsatnoma;
   - to'lov sharti (avans bormi, kechiktirilgan to'lov necha kun);
   - jarima, penya, ta'minot puli (zalog) miqdori;
   - bajarish muddati va bosqichlari.
   Har `note_uz` da dalilni hujjat nomi bilan ko'rsat.
10. Hujjat matni QISQARTIRILGAN yoki O'QILMAGAN deb ogohlantirilgan bo'lsa —
   tegishli mezonni `malumot_yoq` qil va `missing_data` ga "hujjatni qo'lda
   o'qish kerak" deb yoz. Bo'lakda ko'rinmagan narsani "yo'q" deb hisoblama."""


# ---------------------------------------------------------------------------
# Tayanch faktlar — Pythonда aniq hisoblanadi, model qayta hisoblamaydi
# ---------------------------------------------------------------------------
def _facts(tender: Dict[str, Any], profile: Optional[Dict[str, Any]],
           now: Optional[_dt.datetime] = None) -> List[str]:
    out: List[str] = []
    now = now or _dt.datetime.now(_dt.timezone.utc)

    close = tender.get("close_at")
    if isinstance(close, str):
        try:
            close = _dt.datetime.fromisoformat(close)
        except ValueError:
            close = None
    if isinstance(close, _dt.datetime):
        if close.tzinfo is None:
            close = close.replace(tzinfo=_dt.timezone.utc)
        days = (close - now).total_seconds() / 86400
        out.append(f"- Ariza muddati: {close.date()} "
                   + (f"({days:.1f} kun qoldi)" if days >= 0
                      else f"(MUDDAT O'TGAN, {abs(days):.1f} kun oldin)"))
    else:
        out.append("- Ariza muddati: ko'rsatilmagan")

    # Yetkazish muddati: tenderning eng uzun talabi vs kompaniyaning odatiy muddati
    need = max((it.get("delivery_period") or 0)
               for it in (tender.get("items") or [{}])) or None
    lead = (profile or {}).get("lead_time_days")
    if need and lead is not None:
        out.append(f"- Yetkazish: tender {need} kun talab qiladi, kompaniya odatda "
                   f"{lead} kunda bajaradi -> "
                   + ("YETADI" if lead <= need else "YETMAYDI"))
    elif need:
        out.append(f"- Yetkazish: tender {need} kun talab qiladi; "
                   f"kompaniya muddati KO'RSATILMAGAN")
    elif lead is not None:
        out.append(f"- Kompaniya odatiy yetkazish muddati: {lead} kun "
                   f"(tenderда talab ko'rsatilmagan)")

    cost, cur = tender.get("totalcost"), tender.get("currency") or ""
    if cost is not None:
        out.append(f"- Tender qiymati: {float(cost):,.0f} {cur}".replace(",", " "))
        lo, hi = (profile or {}).get("min_cost"), (profile or {}).get("max_cost")
        if lo is not None or hi is not None:
            inside = ((lo is None or float(cost) >= float(lo))
                      and (hi is None or float(cost) <= float(hi)))
            out.append(f"- Kompaniya maqbul tender oralig'i: "
                       f"{('' if lo is None else f'{float(lo):,.0f}')}"
                       f"–{('' if hi is None else f'{float(hi):,.0f}')} -> "
                       .replace(",", " ")
                       + ("ORALIQDA" if inside else "ORALIQDAN TASHQARIDA"))
        cap = (profile or {}).get("max_contract_value")
        cap_cur = (profile or {}).get("max_contract_currency")
        if cap is not None:
            same = (not cap_cur) or (not cur) or cap_cur == cur
            ratio = float(cost) / float(cap) if float(cap) else None
            out.append(f"- Kompaniya moliyaviy salohiyati: {float(cap):,.0f} "
                       f"{cap_cur or ''}".replace(",", " ")
                       + (f" -> tender undan {ratio:.1f} barobar "
                          f"{'KATTA' if ratio > 1 else 'kichik'}"
                          if same and ratio else " (valyutalar har xil, taqqoslanmadi)"))
        else:
            out.append("- Kompaniya moliyaviy salohiyati: KO'RSATILMAGAN")
    else:
        out.append("- Tender qiymati: ko'rsatilmagan")

    regions = (profile or {}).get("regions") or []
    area = tender.get("area_path") or ""
    if regions:
        hit = any(area == r or area.startswith(r + ".") for r in regions)
        out.append(f"- Hudud: tender '{tender.get('region_name') or area}', "
                   f"kompaniya hududlari {regions} -> "
                   + ("MOS" if hit else "MOS EMAS"))
    else:
        out.append("- Kompaniya hududlari: KO'RSATILMAGAN (cheklov yo'q deb qaraladi)")

    exp = (profile or {}).get("experience_years")
    out.append(f"- Tajriba: {exp} yil" if exp is not None
               else "- Tajriba: KO'RSATILMAGAN")
    certs = (profile or {}).get("certificates") or []
    out.append(f"- Sertifikatlar: {', '.join(certs)}" if certs
               else "- Sertifikatlar: KO'RSATILMAGAN")
    clr = (profile or {}).get("clearances") or []
    out.append(f"- Xavfsizlik ruxsatnomalari: {', '.join(clr)}" if clr
               else "- Xavfsizlik ruxsatnomalari: KO'RSATILMAGAN")
    emp = (profile or {}).get("employees")
    note = (profile or {}).get("capacity_note")
    res = []
    if emp is not None:
        res.append(f"{emp} xodim")
    if note:
        res.append(note)
    out.append(f"- Resurs: {'; '.join(res)}" if res else "- Resurs: KO'RSATILMAGAN")

    margin = (profile or {}).get("min_margin_percent")
    out.append(f"- Minimal maqbul foyda: {float(margin):g}%" if margin is not None
               else "- Minimal maqbul foyda: KO'RSATILMAGAN")
    cons = (profile or {}).get("constraints_note")
    out.append(f"- Kompaniya cheklovlari: {cons}" if cons
               else "- Kompaniya cheklovlari: KO'RSATILMAGAN")
    return out


def build_input(tender: Dict[str, Any], products: List[Dict[str, Any]],
                profile: Optional[Dict[str, Any]] = None,
                now: Optional[_dt.datetime] = None,
                docs: str = "", talablar: str = "") -> str:
    """Promptning to'liq matni: tender + hujjatlar + katalog + kompaniya + faktlar.

    `docs` — `ai_docs.prompt_block()`. Go/No-Go uchun hujjat matni AYNIQSA
    muhim: avans, jarima, ta'minot puli va malaka talablari kartochkada
    deyarli hech qachon bo'lmaydi — ular texnik topshiriq va shartnoma
    loyihasida yoziladi.
    """
    parts = ["=== TENDER ===", ai.build_input(tender)]

    det = tender.get("detail") or {}
    extra = []
    if det.get("anno"):
        extra.append(f"Izoh/talablar: {str(det['anno'])[:1200]}")
    if det.get("method_marks"):
        extra.append(f"Baholash usuli: {det['method_marks']}")
    if det.get("offer_period"):
        extra.append(f"Takliflar qabuli: {det['offer_period']}")
    if extra:
        parts += ["", "=== TENDER SHARTLARI ==="] + extra

    # TALABLAR XOM MATNDAN OLDIN. Sabab: bu yerda talab allaqachon
    # ajratilgan, ISHONCH darajasi va IQTIBOS ko'rsatkichi bilan (J3).
    # Model uni qayta ajratishi shart emas — faqat baholaydi. Xom matn
    # esa QO'SHIMCHA sifatida qoladi: talablar ro'yxati hujjatning
    # hammasi emas.
    if talablar:
        parts += ["", talablar]
    if docs:
        parts += ["", docs]

    parts += ["", "=== KOMPANIYA KATALOGI ===", ai_match._fmt_catalog(products)]

    prof_lines = []
    if (profile or {}).get("about"):
        prof_lines.append(f"Faoliyat: {profile['about']}")
    if (profile or {}).get("name"):
        prof_lines.append(f"Nomi: {profile['name']}")
    parts += ["", "=== KOMPANIYA PROFILI ==="]
    parts += prof_lines or ["(profil to'ldirilmagan)"]

    parts += ["", "=== FAKTLAR (aniq hisoblangan — qayta hisoblama) ==="]
    parts += _facts(tender, profile, now)
    return "\n".join(parts)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Javobni tekshirish — 11 mezon to'liq va tartibda kelishini kafolatlaymiz
# ---------------------------------------------------------------------------
def normalize(result: Dict[str, Any]) -> Dict[str, Any]:
    """Yetishmagan mezonni `malumot_yoq` bilan to'ldiradi, tartibni tiklaydi.

    Sxema `enum` ni majburlaydi, lekin BANDLAR SONINI emas — model 9 ta
    qaytarsa frontend jadvali teshik bo'lardi. Shuning uchun bu yerda
    to'ldiramiz: interfeys doim 11 qatorli bo'ladi.
    """
    by_key = {c.get("key"): c for c in (result.get("criteria") or [])
              if isinstance(c, dict)}
    result["criteria"] = [
        by_key.get(k) or {"key": k, "status": "malumot_yoq",
                          "note_uz": "Model bu mezon bo'yicha javob bermadi."}
        for k in _KEYS
    ]
    if result.get("decision") not in DECISIONS:
        result["decision"] = "review"
    return result


def analyze(tender: Dict[str, Any], products: List[Dict[str, Any]],
            profile: Optional[Dict[str, Any]] = None,
            effort: str = DEFAULT_EFFORT,
            docs: str = "", talablar: str = "") -> Dict[str, Any]:
    """Bitta tender uchun Go/No-Go tavsiyasi. Kesh chaqiruvchida."""
    client = ai.get_client()
    text = build_input(tender, products, profile, docs=docs,
                       talablar=talablar)

    kwargs: Dict[str, Any] = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "output_config": {
            "effort": effort,
            "format": {"type": "json_schema", "schema": RESULT_SCHEMA},
        },
        "messages": [{"role": "user", "content": text}],
    }

    try:
        resp = client.beta.messages.create(
            betas=[_FALLBACK_BETA], fallbacks="default", **kwargs)
    except TypeError:
        resp = client.messages.create(**kwargs)
    except Exception as e:  # noqa: BLE001
        if _FALLBACK_BETA in str(e) or "fallback" in str(e).lower():
            try:
                resp = client.messages.create(**kwargs)
            except Exception as e2:  # noqa: BLE001
                raise ai.AIUnavailable(f"Claude chaqiruvi muvaffaqiyatsiz: {e2}",
                                       kod="AI_CALL_FAILED") from e2
        else:
            raise ai.AIUnavailable(f"Claude chaqiruvi muvaffaqiyatsiz: {e}",
                                   kod="AI_CALL_FAILED") from e

    return {
        "result": normalize(ai_match._extract(resp)),
        "model": resp.model,
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
    }
