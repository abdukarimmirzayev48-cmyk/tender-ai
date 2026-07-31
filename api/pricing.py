"""
NARX HISOBI — tavsiya etilgan taklif narxi (REJA.md P0-7)
=========================================================
Tannarx + logistika + xavf zaxirasi + ustama + QQS -> tavsiya etilgan narx,
kutilayotgan foyda va tender byudjetiga nisbat.

AI YO'Q. Bu SOF FORMULA. Model chaqiruvi, taxmin, "aqlli" tuzatish yo'q —
har raqam kiruvchi ma'lumotdan arifmetika bilan chiqadi.

SHAFFOFLIK (TZ nofunksional talabi: "qora quti bo'lmasligi kerak")
------------------------------------------------------------------
Natija bitta summa emas — BOSQICHLAR RO'YXATI. Har bosqichda:
    key     — barqaror kalit (frontend shunga qarab chizadi)
    label   — o'zbekcha nomi
    rule    — formulaning O'ZI, belgilar bilan: "(tannarx + logistika) × zaxira%"
    formula — o'sha formula RAQAMLAR qo'yilgan holda: "(650 + 20) × 5%"
    value   — natija
Foydalanuvchi butun zanjirni ko'radi va istalgan bosqichni tekshira oladi.

BITTA MANBA — IKKI IJRO
-----------------------
Ayni shu formula `frontend/src/pricing.ts` da ham bor: brauzerda har tugmachani
bosganda SERVERSIZ qayta hisoblanadi (TZ: "sahifani qayta yuklamasdan").
Ikki ijro bir-biridan chetga chiqmasligi uchun ular ATAYLAB bir xil yozilgan:
    - bir xil kiruvchi/chiquvchi obyekt shakli,
    - bir xil arifmetika (float64 — Python va JavaScriptda IEEE 754 double,
      amallar bit darajasida bir xil),
    - bir xil yaxlitlash funksiyasi (pastga qarang).
`_tests/pricing_test.py` ikkalasini bir necha holatda yonma-yon ishga tushirib,
natijalar AYNAN teng ekanini tekshiradi. Formulani o'zgartirsangiz — IKKALA
faylni ham o'zgartiring, sinov aks holda yiqiladi.

YAXLITLASH QOIDASI
------------------
Har pul qiymati 2 kasrgacha, NOLDAN UZOQLASHTIRIB (half-up: 0.125 -> 0.13,
-0.125 -> -0.13) yaxlitlanadi. Yaxlitlash HAR BOSQICHDA qilinadi, oxirida
emas: ko'rinib turgan raqam — hisobda ishlatilgan raqamning O'ZI. Aks holda
foydalanuvchi qo'lda qo'shganda jamiga to'g'ri kelmasdi ("650 + 20 + 30 = 700
deb yozilgan, lekin ichkarida 700.004").
Decimal EMAS, float ishlatilgan — chunki brauzerdagi ikkinchi ijro bilan
BIT DARAJASIDA bir xil natija kerak (JavaScriptda Decimal yo'q). float64 da
15-16 ta muhim raqam bor; UZS milliardlari 2 kasr bilan ~13 raqam — yetarli.
Ikkilik kasrning ma'lum kamchiligi (1.005 * 100 = 100.49999999999999)
1e-9 epsilon bilan tuzatiladi — ikkala tilda bir xil.

VALYUTA
-------
Loyihada UZS ham, USD ham bor, KURS KONVERTATSIYASI YO'Q. Shuning uchun turli
valyutali qiymatlar HECH QACHON qo'shilmaydi: aralashuv aniqlansa hisob umuman
bajarilmaydi (`ok=false`, `errors`), chunki jimgina qo'shilgan summa —
foydalanuvchini adashtiradigan ENG XAVFLI natija.

"FOYDA" ATAMASI — biznes-jarayon hujjatidagi ikki ma'no
-------------------------------------------------------
Hujjatda: "Jami 700, byudjet 1000 -> foyda 300" va "broker 750 qo'ydi ->
foyda 50". Bular BIR XIL kattalik emas:
    300 = byudjet − narx      (byudjetdan qolgan zaxira, raqobat maydoni)
     50 = narx − jami xarajat (bizning haqiqiy foydamiz)
Ikkisi ham hisoblanadi va ALOHIDA nomlanadi — `profit` (kutilayotgan foyda)
va `budget_left` (byudjet zaxirasi). Bitta "foyda" so'zi ostida birlashtirish
xato bo'lardi.
"""
import math
import re
from typing import Any, Dict, List, Optional

#: Odatiy parametrlar — `pricing_settings` jadvali DEFAULT lari bilan bir xil.
#: Baza yo'q joyda ham (sof funksiya sinovi) shu qiymatlar ishlaydi.
DEFAULTS: Dict[str, float] = {
    "markup_percent": 15.0,
    "risk_reserve_percent": 5.0,
    "risk_reserve_fixed": 0.0,
    "logistics_percent": 0.0,
    "logistics_fixed": 0.0,
    "vat_percent": 12.0,
}

#: Formulada ko'rsatiladigan pozitsiyalar soni chegarasi — 20 ta tovarli
#: tenderda qator cho'zilib ketmasin. Qolgani "+ …(N ta)" bo'lib qisqaradi.
_MAX_FORMULA_ITEMS = 4


# ---------------------------------------------------------------------------
# Arifmetika yordamchilari — frontend/src/pricing.ts dagi nusxasi bilan
# BIT DARAJASIDA bir xil bo'lishi SHART.
# ---------------------------------------------------------------------------
def round2(x: float) -> float:
    """2 kasrgacha, noldan uzoqlashtirib yaxlitlaydi (half-up).

    JavaScriptdagi `Math.round(v)` aynan `floor(v + 0.5)`; shuning uchun
    bu yerda ham `math.floor(v + 0.5)` — ikkala til bir xil natija beradi.
    Musbatga keltirib yaxlitlaymiz, so'ng ishorani qaytaramiz: manfiy son
    ham noldan uzoqlashadi (-0.125 -> -0.13), ya'ni qoida simmetrik.
    """
    if x != x or x in (float("inf"), float("-inf")):  # NaN / cheksizlik
        return 0.0
    sign = -1.0 if x < 0 else 1.0
    v = abs(x) * 100.0
    # 1e-9 — ikkilik kasr xatosini tuzatish: 1.005*100 = 100.49999999999999
    # bo'lib qoladi va yaxlitlash 1.00 ga tushardi. Epsilon uni 1.01 qiladi.
    r = math.floor(v + 1e-9 + 0.5)
    out = sign * r / 100.0
    return 0.0 if out == 0 else out


def _num(v: Any, default: float = 0.0) -> float:
    """Har qanday kiruvchini songa aylantiradi (None/bo'sh/xato -> default).

    psycopg2 NUMERIC ni Decimal qilib qaytaradi, frontend esa matn yuborishi
    mumkin ("15" yoki "15,5") — ikkalasi ham shu yerda normallashadi.
    """
    if v is None or v == "":
        return default
    if isinstance(v, bool):  # True/False son sifatida qabul qilinmasin
        return default
    try:
        if isinstance(v, str):
            return float(v.strip().replace(" ", "").replace(",", "."))
        return float(v)
    except (TypeError, ValueError):
        return default


def _fmt(x: float) -> str:
    """Formula matnidagi son: ortiqcha nollarsiz ("650", "6.67", "1000.5")."""
    s = f"{round2(x):.2f}"
    if s.endswith(".00"):
        s = s[:-3]
    elif s.endswith("0"):
        s = s[:-1]
    return s


def _step(key: str, label: str, rule: str, formula: str, value: float) -> Dict[str, Any]:
    return {"key": key, "label": label, "rule": rule, "formula": formula,
            "value": round2(value)}


def _msg(code: str, message: str) -> Dict[str, str]:
    return {"code": code, "message": message}


# ---------------------------------------------------------------------------
# ASOSIY HISOB — sof funksiya (bazasiz, tarmoqsiz, holatsiz)
# ---------------------------------------------------------------------------
def calculate(inp: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Smetani hisoblaydi va HAR BOSQICHNI formulasi bilan qaytaradi.

    Kiruvchi (barchasi ixtiyoriy, yo'g'i DEFAULTS dan olinadi)::

        {
          "currency": "USD",
          "items": [{"name","qty","unit_cost","unit","currency"}],
          "markup_percent": 15, "risk_reserve_percent": 5,
          "risk_reserve_fixed": 0, "logistics_percent": 0,
          "logistics_fixed": 0, "vat_percent": 12,
          "manual_price": null,          # broker qo'lda kiritgan YAKUNIY narx
          "budget": 1000, "budget_currency": "USD",
          "min_margin_percent": 10       # company_profile dan (faqat o'qish)
        }

    Chiquvchi::

        {"ok", "currency", "items", "steps", "totals", "warnings", "errors",
         "inputs"}

    Xato (`errors`) bo'lsa `ok=false` va HISOB UMUMAN BAJARILMAYDI — `steps`
    bo'sh, `totals` nol. Bu ataylab: noto'g'ri kiruvchidan chiqqan chiroyli
    raqam — eng xavfli natija.
    """
    inp = dict(inp or {})
    errors: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []

    currency = (str(inp.get("currency") or "").strip().upper() or None)

    # --- 1. Pozitsiyalarni normallashtirish -------------------------------
    items: List[Dict[str, Any]] = []
    seen_currencies: List[str] = []
    for i, raw in enumerate(inp.get("items") or []):
        raw = raw or {}
        qty = _num(raw.get("qty"))
        unit_cost = _num(raw.get("unit_cost"))
        cur = (str(raw.get("currency") or "").strip().upper() or None)
        name = (raw.get("name") or f"Pozitsiya {i + 1}")
        if cur and cur not in seen_currencies:
            seen_currencies.append(cur)
        if qty < 0:
            errors.append(_msg("qty_negative",
                               f"«{name}»: miqdor manfiy ({_fmt(qty)}) — bo'lishi mumkin emas."))
        if unit_cost < 0:
            errors.append(_msg("cost_negative",
                               f"«{name}»: birlik tannarxi manfiy ({_fmt(unit_cost)}) — bo'lishi mumkin emas."))
        items.append({
            "name": name,
            "unit": raw.get("unit") or None,
            "qty": qty,
            "unit_cost": unit_cost,
            "currency": cur,
            # Buyurtmachi e'lon qilgan birlik narxi — mo'ljal uchun, hisobga
            # KIRMAYDI (bu bizning tannarx emas, tenderdagi talab narxi).
            "ref_price": (None if raw.get("ref_price") in (None, "")
                          else round2(_num(raw.get("ref_price")))),
            "total": round2(qty * unit_cost),
        })

    # --- 2. Valyuta nazorati — aralashtirilmaydi --------------------------
    # Pozitsiyada valyuta ko'rsatilmagan bo'lsa — smeta valyutasi deb qaraladi.
    # Ikki xil valyuta uchrasa (yoki pozitsiya smeta valyutasidan farq qilsa)
    # hisob TO'XTAYDI.
    if len(seen_currencies) > 1 or (currency and seen_currencies
                                    and any(c != currency for c in seen_currencies)):
        errors.append(_msg(
            "currency_mix",
            "Valyutalar aralashgan (" + ", ".join(sorted(set(
                seen_currencies + ([currency] if currency else [])))) + "). "
            "Tizimda kurs konvertatsiyasi yo'q — turli valyutali summalar "
            "qo'shilmaydi. Bitta valyutaga keltiring."))

    # --- 3. Parametrlar ---------------------------------------------------
    markup = _num(inp.get("markup_percent"), DEFAULTS["markup_percent"])
    risk_pct = _num(inp.get("risk_reserve_percent"), DEFAULTS["risk_reserve_percent"])
    risk_fix = _num(inp.get("risk_reserve_fixed"), DEFAULTS["risk_reserve_fixed"])
    log_pct = _num(inp.get("logistics_percent"), DEFAULTS["logistics_percent"])
    log_fix = _num(inp.get("logistics_fixed"), DEFAULTS["logistics_fixed"])
    vat = _num(inp.get("vat_percent"), DEFAULTS["vat_percent"])

    for key, val, label in (("markup_percent", markup, "Ustama"),
                            ("risk_reserve_percent", risk_pct, "Xavf zaxirasi (%)"),
                            ("risk_reserve_fixed", risk_fix, "Xavf zaxirasi (summa)"),
                            ("logistics_percent", log_pct, "Logistika (%)"),
                            ("logistics_fixed", log_fix, "Logistika (summa)"),
                            ("vat_percent", vat, "QQS")):
        if val < 0:
            errors.append(_msg(f"{key}_negative",
                               f"{label} manfiy ({_fmt(val)}) — bo'lishi mumkin emas."))
    if vat > 100:
        errors.append(_msg("vat_range", f"QQS {_fmt(vat)}% — 100% dan katta bo'la olmaydi."))

    manual_raw = inp.get("manual_price")
    manual: Optional[float] = None
    if manual_raw not in (None, ""):
        manual = round2(_num(manual_raw))
        if manual < 0:
            errors.append(_msg("manual_negative",
                               f"Qo'lda kiritilgan narx manfiy ({_fmt(manual)})."))

    budget_raw = inp.get("budget")
    budget: Optional[float] = None if budget_raw in (None, "") else round2(_num(budget_raw))
    budget_currency = (str(inp.get("budget_currency") or "").strip().upper() or None)

    min_margin_raw = inp.get("min_margin_percent")
    min_margin: Optional[float] = (None if min_margin_raw in (None, "")
                                   else _num(min_margin_raw))

    normalized = {
        "currency": currency, "items": items,
        "markup_percent": markup, "risk_reserve_percent": risk_pct,
        "risk_reserve_fixed": risk_fix, "logistics_percent": log_pct,
        "logistics_fixed": log_fix, "vat_percent": vat,
        "manual_price": manual, "budget": budget,
        "budget_currency": budget_currency, "min_margin_percent": min_margin,
    }

    if errors:
        # Xato bor — hisob QILINMAYDI. Bo'sh natija qaytadi, foydalanuvchi
        # avval kiruvchini tuzatadi.
        return {"ok": False, "currency": currency, "items": items,
                "steps": [], "totals": _empty_totals(), "warnings": warnings,
                "errors": errors, "inputs": normalized}

    if not items:
        warnings.append(_msg("no_items",
                             "Pozitsiya kiritilmagan — tannarx 0 deb olindi. "
                             "Hisob faqat sozlamalar bo'yicha ishlaydi."))

    # --- 4. BOSQICHLAR ----------------------------------------------------
    steps: List[Dict[str, Any]] = []

    # 4.1 Tannarx: Σ (miqdor × birlik tannarxi)
    cost_base = round2(sum(it["total"] for it in items))
    shown = items[:_MAX_FORMULA_ITEMS]
    parts = [f"{_fmt(it['qty'])} × {_fmt(it['unit_cost'])}" for it in shown]
    if len(items) > _MAX_FORMULA_ITEMS:
        parts.append(f"…(yana {len(items) - _MAX_FORMULA_ITEMS} ta)")
    steps.append(_step(
        "cost_base", "Tannarx (pozitsiyalar)",
        "Σ (miqdor × birlik tannarxi)",
        " + ".join(parts) if parts else "0",
        cost_base))

    # 4.2 Logistika: tannarxdan foiz + belgilangan summa
    logistics = round2(cost_base * log_pct / 100.0 + log_fix)
    steps.append(_step(
        "logistics", "Logistika",
        "tannarx × logistika% + logistika (belgilangan)",
        f"{_fmt(cost_base)} × {_fmt(log_pct)}% + {_fmt(log_fix)}",
        logistics))

    # 4.3 Xavf zaxirasi: tannarx + logistikadan foiz + belgilangan summa.
    #     BAZA — tannarx VA logistika, chunki yetkazib berish xarajati ham
    #     xavfga uchraydi (kurs, ikkinchi reys).
    risk_base = round2(cost_base + logistics)
    risk = round2(risk_base * risk_pct / 100.0 + risk_fix)
    steps.append(_step(
        "risk_reserve", "Xavf zaxirasi",
        "(tannarx + logistika) × zaxira% + zaxira (belgilangan)",
        f"({_fmt(cost_base)} + {_fmt(logistics)}) × {_fmt(risk_pct)}% + {_fmt(risk_fix)}",
        risk))

    # 4.4 Jami xarajat — bu bizga tenderni bajarish QANCHAGA tushishi
    total_cost = round2(cost_base + logistics + risk)
    steps.append(_step(
        "total_cost", "Jami xarajat",
        "tannarx + logistika + xavf zaxirasi",
        f"{_fmt(cost_base)} + {_fmt(logistics)} + {_fmt(risk)}",
        total_cost))

    # 4.5 Ustama — ko'zlangan foyda. Bazasi JAMI XARAJAT (faqat tannarx emas):
    #     logistika va zaxirani ham qoplashimiz kerak.
    markup_sum = round2(total_cost * markup / 100.0)
    steps.append(_step(
        "markup", "Ustama (ko'zlangan foyda)",
        "jami xarajat × ustama%",
        f"{_fmt(total_cost)} × {_fmt(markup)}%",
        markup_sum))

    # 4.6 Taklif narxi, QQSsiz
    price_ex_vat = round2(total_cost + markup_sum)
    steps.append(_step(
        "price_ex_vat", "Taklif narxi (QQSsiz)",
        "jami xarajat + ustama",
        f"{_fmt(total_cost)} + {_fmt(markup_sum)}",
        price_ex_vat))

    # 4.7 QQS
    vat_sum = round2(price_ex_vat * vat / 100.0)
    steps.append(_step(
        "vat", "QQS",
        "taklif narxi (QQSsiz) × QQS%",
        f"{_fmt(price_ex_vat)} × {_fmt(vat)}%",
        vat_sum))

    # 4.8 TAVSIYA ETILGAN NARX — tizim taklifi
    recommended = round2(price_ex_vat + vat_sum)
    steps.append(_step(
        "recommended_price", "Tavsiya etilgan taklif narxi",
        "taklif narxi (QQSsiz) + QQS",
        f"{_fmt(price_ex_vat)} + {_fmt(vat_sum)}",
        recommended))

    # 4.9 Yakuniy narx — broker qo'lda kiritgan bo'lsa O'SHA.
    #     Qo'lda kiritilgan narx ham QQS BILAN tushuniladi (tavsiya bilan bir
    #     asosda), aks holda taqqoslash ma'nosiz bo'lardi.
    manual_used = manual is not None
    final_price = manual if manual_used else recommended
    steps.append(_step(
        "final_price", "Yakuniy narx",
        "qo'lda kiritilgan narx (bo'lmasa — tavsiya etilgan)",
        (f"qo'lda: {_fmt(final_price)}" if manual_used
         else f"tavsiya: {_fmt(final_price)}"),
        final_price))

    # 4.10 Yakuniy narxni QQSdan tozalash — foyda faqat QQSsiz asosda
    #      hisoblanadi (QQS bizning daromadimiz emas, byudjetga o'tadi).
    final_ex_vat = round2(final_price / (1.0 + vat / 100.0))
    steps.append(_step(
        "final_ex_vat", "Yakuniy narx (QQSsiz)",
        "yakuniy narx ÷ (1 + QQS%)",
        f"{_fmt(final_price)} ÷ (1 + {_fmt(vat)}%)",
        final_ex_vat))

    # 4.11 KUTILAYOTGAN FOYDA
    profit = round2(final_ex_vat - total_cost)
    steps.append(_step(
        "profit", "Kutilayotgan foyda",
        "yakuniy narx (QQSsiz) − jami xarajat",
        f"{_fmt(final_ex_vat)} − {_fmt(total_cost)}",
        profit))

    profit_percent = round2(profit / final_ex_vat * 100.0) if final_ex_vat else 0.0
    steps.append(_step(
        "profit_percent", "Foyda ulushi, %",
        "foyda ÷ yakuniy narx (QQSsiz) × 100",
        (f"{_fmt(profit)} ÷ {_fmt(final_ex_vat)} × 100" if final_ex_vat
         else "narx 0 — ulush hisoblanmaydi"),
        profit_percent))

    # --- 5. Tender byudjetiga nisbat --------------------------------------
    budget_left: Optional[float] = None
    budget_ratio: Optional[float] = None
    budget_comparable = budget is not None
    if budget is not None and budget_currency and currency and budget_currency != currency:
        budget_comparable = False
        warnings.append(_msg(
            "budget_currency",
            f"Tender byudjeti {budget_currency}, smeta {currency} — kurs "
            f"konvertatsiyasi yo'q, taqqoslanmadi."))

    if budget_comparable and budget is not None:
        budget_left = round2(budget - final_price)
        steps.append(_step(
            "budget_left", "Byudjet zaxirasi",
            "tender byudjeti − yakuniy narx",
            f"{_fmt(budget)} − {_fmt(final_price)}",
            budget_left))
        budget_ratio = round2(final_price / budget * 100.0) if budget else 0.0
        steps.append(_step(
            "budget_ratio", "Byudjetga nisbatan, %",
            "yakuniy narx ÷ tender byudjeti × 100",
            (f"{_fmt(final_price)} ÷ {_fmt(budget)} × 100" if budget
             else "byudjet 0 — nisbat hisoblanmaydi"),
            budget_ratio))
        if budget_left < 0:
            warnings.append(_msg(
                "over_budget",
                f"Yakuniy narx tender byudjetidan {_fmt(abs(budget_left))} "
                f"{currency or ''} ga yuqori — taklif rad etilishi mumkin.".replace("  ", " ")))

    # --- 6. Ogohlantirishlar ----------------------------------------------
    if profit < 0:
        warnings.append(_msg("loss", f"Zarar: foyda {_fmt(profit)} "
                                     f"{currency or ''}".strip() + "."))
    elif profit == 0:
        warnings.append(_msg("zero_profit",
                             "Foyda nolga teng — narx aynan tannarx darajasida."))

    if min_margin is not None and profit_percent < min_margin:
        warnings.append(_msg(
            "below_min_margin",
            f"Foyda ulushi {_fmt(profit_percent)}% — kompaniya profilidagi "
            f"minimal maqbul chegara {_fmt(min_margin)}% dan past."))

    totals = {
        "cost_base": cost_base,
        "logistics": logistics,
        "risk_reserve": risk,
        "total_cost": total_cost,
        "markup": markup_sum,
        "price_ex_vat": price_ex_vat,
        "vat": vat_sum,
        "recommended_price": recommended,
        "manual_price": manual,
        "manual_used": manual_used,
        "final_price": final_price,
        "final_ex_vat": final_ex_vat,
        "profit": profit,
        "profit_percent": profit_percent,
        "budget": budget,
        "budget_left": budget_left,
        "budget_ratio_percent": budget_ratio,
    }
    return {"ok": True, "currency": currency, "items": items, "steps": steps,
            "totals": totals, "warnings": warnings, "errors": errors,
            "inputs": normalized}


def _empty_totals() -> Dict[str, Any]:
    return {
        "cost_base": 0.0, "logistics": 0.0, "risk_reserve": 0.0,
        "total_cost": 0.0, "markup": 0.0, "price_ex_vat": 0.0, "vat": 0.0,
        "recommended_price": 0.0, "manual_price": None, "manual_used": False,
        "final_price": 0.0, "final_ex_vat": 0.0, "profit": 0.0,
        "profit_percent": 0.0, "budget": None, "budget_left": None,
        "budget_ratio_percent": None,
    }


# ---------------------------------------------------------------------------
# Kiruvchini tayyorlash — endpoint uchun yordamchilar (ular ham sof)
# ---------------------------------------------------------------------------
#: '2.00 dona', ' 1 500,5 kg' kabi MATN miqdorlardan sonni ajratadi.
#: `tender_item.amount_text` manbada matn ko'rinishida keladi (sxema shunday).
_AMOUNT_RE = re.compile(r"-?\d[\d\s ]*(?:[.,]\d+)?")


def parse_amount_text(text: Any) -> Optional[float]:
    """'2.00 dona' -> 2.0. Son topilmasa None (0 EMAS — «yo'q» va «nol» farqli)."""
    if text is None:
        return None
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text)
    m = _AMOUNT_RE.search(str(text))
    if not m:
        return None
    raw = m.group(0).replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def positions_from_goods(goods: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """`tender_good` qatorlaridan smeta pozitsiyalarini tayyorlaydi.

    MUHIM: `unit_cost` (BIZNING tannarximiz) 0 bilan boshlanadi va uni
    foydalanuvchi kiritadi. Tenderdagi narx `ref_price` sifatida yonida
    ko'rsatiladi — bu BUYURTMACHI e'lon qilgan narx, tannarx emas; uni
    tannarx o'rniga qo'yish smetani boshidanoq soxta qilardi.
    """
    out: List[Dict[str, Any]] = []
    for g in goods or []:
        qty = g.get("amount")
        if qty is None:
            qty = parse_amount_text(g.get("amount_text"))
        out.append({
            "name": g.get("name") or g.get("good_code") or "Pozitsiya",
            "unit": g.get("unit"),
            "qty": float(qty) if qty is not None else 0.0,
            "unit_cost": 0.0,
            "ref_price": None if g.get("price") is None else float(g["price"]),
        })
    return out


def build_inputs(settings: Optional[Dict[str, Any]] = None,
                 tender: Optional[Dict[str, Any]] = None,
                 goods: Optional[List[Dict[str, Any]]] = None,
                 profile: Optional[Dict[str, Any]] = None,
                 saved: Optional[Dict[str, Any]] = None,
                 override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Kiruvchi obyektni yig'adi. Ustunlik tartibi (keyingisi oldingisini bosadi):
    sozlamalar -> saqlangan smeta -> so'rovdagi qiymatlar (`override`).

    Byudjet va valyuta TENDERdan olinadi (`totalcost`, `currency`),
    minimal maqbul foyda esa PROFILdan — faqat o'qish, jadval o'zgarmaydi.
    """
    s = settings or {}
    t = tender or {}
    base: Dict[str, Any] = {
        "markup_percent": _num(s.get("markup_percent"), DEFAULTS["markup_percent"]),
        "risk_reserve_percent": _num(s.get("risk_reserve_percent"), DEFAULTS["risk_reserve_percent"]),
        "risk_reserve_fixed": _num(s.get("risk_reserve_fixed"), DEFAULTS["risk_reserve_fixed"]),
        "logistics_percent": _num(s.get("logistics_percent"), DEFAULTS["logistics_percent"]),
        "logistics_fixed": _num(s.get("logistics_fixed"), DEFAULTS["logistics_fixed"]),
        "vat_percent": _num(s.get("vat_percent"), DEFAULTS["vat_percent"]),
        "currency": (t.get("currency") or s.get("currency") or None),
        "items": positions_from_goods(goods),
        "manual_price": None,
        "budget": None if t.get("totalcost") is None else float(t["totalcost"]),
        "budget_currency": t.get("currency") or None,
        # Profildagi NUMERIC psycopg2 da Decimal bo'lib keladi — JSON uchun float.
        "min_margin_percent": (None if (profile or {}).get("min_margin_percent") is None
                               else float(profile["min_margin_percent"])),
    }
    if saved and saved.get("inputs"):
        prev = saved["inputs"] or {}
        for k in ("items", "markup_percent", "risk_reserve_percent",
                  "risk_reserve_fixed", "logistics_percent", "logistics_fixed",
                  "vat_percent", "currency", "manual_price"):
            if prev.get(k) not in (None, []):
                base[k] = prev[k]
    for k, v in (override or {}).items():
        if v is not None:
            base[k] = v
    return base
