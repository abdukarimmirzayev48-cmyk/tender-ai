"""
Aqlli moslashtirish — deterministik (qoidaga asoslangan) skorlash.

DIZAYN: butun "aql" shu yagona `score_tender()` funksiyasida jamlangan.
Kelajakda AI integratsiyasiда faqat SHU funksiyani (yoki uni chaqiruvchi
qatlamни) Claude API bilan almashtiramiz — endpoint/DB/frontend o'zgarmaydi.

Ball tarkibi (jami 0–100, shaffof):
    🔑 kalit so'z    0–60   profil kalit so'zlari tender matnida (nom+buyurtmachi+tovarlar)
    📍 hudud         0–20   tender profil hududlaridan birida (prefix)
    💰 byudjet       0–15   totalcost profil [min,max] diapazonида
    💱 valyuta       0–5    afzal valyutaga mos
"""
from typing import Any, Dict, List, Optional

# Ball og'irliklari (o'zgartirish oson — bitta joyda)
W_KEYWORD = 60
W_REGION = 20
W_BUDGET = 15
W_CURRENCY = 5


def _norm(s: Optional[str]) -> str:
    """Kichik harfga (Python .lower() kirillcha ham to'g'ri ishlaydi, C-locale'dan farqli)."""
    return (s or "").lower()


def score_tender(tender: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """Bitta tenderni profilga qarab ballaydi. Natija: score + sabablar + tarkib."""
    keywords: List[str] = [k.strip() for k in (profile.get("keywords") or []) if k.strip()]
    regions: List[str] = profile.get("regions") or []
    pref_cur: Optional[str] = profile.get("currency")
    min_cost = profile.get("min_cost")
    max_cost = profile.get("max_cost")

    score = 0.0
    reasons: List[str] = []
    breakdown: Dict[str, float] = {}

    # --- Kalit so'z (0–60) ---
    # MUHIM: company_name ATAYIN kiritilmaydi. Kalit so'z NIMA sotib olinishini
    # tavsiflaydi (tovar/xizmat), KIM sotib olishini emas. Aks holda nomida
    # "QURILISH"/"MEBEL" bor kompaniyalar soxta moslik beradi (masalan
    # "BUXOROSUVQURILISHINVEST" -> "qurilish"). Buyurtmachi bo'yicha qidiruv
    # allaqachon alohida `q` filtrida mavjud.
    blob = _norm(" ".join(filter(None, [
        tender.get("name"), tender.get("goods_blob"),
    ])))
    matched_kw: List[str] = []
    if keywords:
        for kw in keywords:
            if _norm(kw) in blob:
                matched_kw.append(kw)
        kw_score = W_KEYWORD * (len(matched_kw) / len(keywords)) if matched_kw else 0.0
        if matched_kw:
            reasons.append(f"{len(matched_kw)} ta kalit so‘z mos: {', '.join(matched_kw)}")
    else:
        kw_score = 0.0  # profilda kalit so'z yo'q — bu komponent neytral (0)
    breakdown["keyword"] = round(kw_score, 1)
    score += kw_score

    # --- 📍 Hudud (0–20) ---
    area_path = tender.get("area_path") or ""
    if regions:
        hit = next((r for r in regions if area_path == r or area_path.startswith(r + ".")), None)
        if hit:
            region_score = W_REGION
            reasons.append(f"Hududingizda: {tender.get('region_name') or hit}")
        else:
            region_score = 0.0
    else:
        region_score = W_REGION / 2  # hudud afzalligi yo'q — neytral (yarim ball)
    breakdown["region"] = round(region_score, 1)
    score += region_score

    # --- 💰 Byudjet (0–15) ---
    cost = tender.get("totalcost")
    # Byudjetni faqat valyuta mos (yoki afzallik yo'q) bo'lganda taqqoslaymiz —
    # UZS va USD ni aralashtirmaymiz
    cur_ok_for_budget = (not pref_cur) or (tender.get("currency") == pref_cur)
    if (min_cost is not None or max_cost is not None) and cost is not None and cur_ok_for_budget:
        below = (min_cost is not None and cost < float(min_cost))
        above = (max_cost is not None and cost > float(max_cost))
        if not below and not above:
            budget_score = W_BUDGET
            reasons.append("Byudjetingizga mos")
        else:
            budget_score = 0.0
            reasons.append("Byudjetdan tashqari" + (" (past)" if below else " (yuqori)"))
    else:
        budget_score = W_BUDGET / 2  # chegara yo'q — neytral
    breakdown["budget"] = round(budget_score, 1)
    score += budget_score

    # --- 💱 Valyuta (0–5) ---
    if pref_cur:
        if tender.get("currency") == pref_cur:
            cur_score = W_CURRENCY
            reasons.append(f"Valyuta mos: {pref_cur}")
        else:
            cur_score = 0.0
    else:
        cur_score = W_CURRENCY / 2  # afzallik yo'q — neytral
    breakdown["currency"] = round(cur_score, 1)
    score += cur_score

    return {
        "score": round(score),
        "reasons": reasons,
        "matched_keywords": matched_kw,
        "breakdown": breakdown,
    }
