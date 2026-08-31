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

SABABLAR IKKI KO'RINISHDA qaytadi:
    `reasons`      — TAYYOR O'ZBEKCHA matn (interfeys shuni ko'rsatadi, avvalgidek)
    `reason_keys`  — [{"key": ..., "vars": {...}}] STRUKTURA
Bildirishnoma xabari `reason_keys` dan foydalanadi va sababni foydalanuvchi
tanlagan tilda quradi (api/i18n.py). Bir mantiq — ikki ko'rinish: matn shu
yerda ham lug'atdan olinadi, ya'ni ikkita haqiqat manbai paydo bo'lmaydi.
"""
import datetime as _dt
import re
from typing import Any, Dict, List, Optional

from api import i18n, translit

# Ball og'irliklari (o'zgartirish oson — bitta joyda)
W_KEYWORD = 60
W_REGION = 20
W_BUDGET = 15
W_CURRENCY = 5


def _norm(s: Optional[str]) -> str:
    """Solishtirishga tayyorlaydi: kichik harf + alifbo yig'ish.

    Yig'ish (ь ъ o'chadi, э->е, ы й->и) SQL tomondagi translit.SQL_FOLD bilan
    bir xil — shu sabab "kalit so'z topildi" natijasi qidiruv natijasiga mos
    keladi. Batafsil: api/translit.py.
    """
    return translit.norm_text(s)


def _hits(term: Optional[str], blob: str) -> bool:
    """`term` matnда bormi — alifbodan qat'i nazar, SO'Z BOSHIDAN.

    Profilга "nasos" yozilgan bo'lsa, "Насос" tovarli tender ham topilsin
    (aks holda lotin alifbosida yozilgan profil hech narsa topmaydi).

    SO'Z CHEGARASI (`\\b`) MAJBURIY — o'lchangan nosozlik:
        "stol"  ⊂ "столб"   (ustun)      -> soxta moslik
        "stol"  ⊂ "престол"              -> soxta moslik
    Chegarasiz `in` tekshiruvi so'zning O'RTASIDAN ham topardi.

    QO'SHIMCHA CHEKLOV YO'Q va bu ATAYLAB. O'lchandi (ochiq korpus):
        monitor -> monitoring(+3), monitoringi(+4)   XATO
        nasos   -> насосини(+3), nasoslarning(+7)    TO'G'RI
        stol    -> столовая(+4, oshxona) XATO / стола(+1) TO'G'RI
    Ya'ni bir xil qo'shimcha uzunligida ham to'g'ri, ham xato moslik bor —
    uzunlik chegarasi ularni AJRATA OLMAYDI. Ularni ajratish morfologik
    tahlil talab qiladi. Shuning uchun matn mosligi bu yerda IKKILAMCHI
    signal bo'lib qoldi: birlamchi yo'l — `good_code` (tilga bog'liq
    emas, qamrovi 100%). `product_matches()` ga qarang.
    """
    return hits_variants(translit.variants(term or ""), blob)


def hits_variants(variants: List[str], blob: str) -> bool:
    """`_hits` ning OLDINDAN hisoblangan variantlar bilan ishlaydigan shakli.

    NEGA AJRATILDI: `translit.variants()` qimmat, va u HAR nomzod uchun
    QAYTA hisoblanardi. Katalog 1797 qatorga o'sgach bu quyidagini
    berdi (o'lchangan):

        bildirishnoma ballashi: 10 nomzod = 67 s -> 528 nomzod = 59 DAQIQA

    Ya'ni soatlik ETL ning bildirishnoma qadami hech qachon tugamasdi.
    Variantlarni bir marta hisoblab, keyin faqat qidirish kerak.
    """
    for v in variants:
        if v and re.search(r"\b" + re.escape(v), blob):
            return True
    return False


def score_tender(tender: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """Bitta tenderni profilga qarab ballaydi. Natija: score + sabablar + tarkib."""
    keywords: List[str] = [k.strip() for k in (profile.get("keywords") or []) if k.strip()]
    regions: List[str] = profile.get("regions") or []
    pref_cur: Optional[str] = profile.get("currency")
    min_cost = profile.get("min_cost")
    max_cost = profile.get("max_cost")

    score = 0.0
    breakdown: Dict[str, float] = {}
    # Sabablar STRUKTURA sifatida yig'iladi; o'zbekcha matn oxirida shulardan
    # quriladi. Shu sabab bildirishnoma ularni istalgan tilda qayta chiza oladi.
    keys: List[Dict[str, Any]] = []

    def reason(key: str, **vars_: Any) -> None:
        keys.append({"key": key, "vars": vars_})

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
            if _hits(kw, blob):
                matched_kw.append(kw)
        kw_score = W_KEYWORD * (len(matched_kw) / len(keywords)) if matched_kw else 0.0
        if matched_kw:
            reason("reason.keywords", n=len(matched_kw), items=", ".join(matched_kw))
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
            reason("reason.region", region=tender.get("region_name") or hit)
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
            reason("reason.budgetOk")
        else:
            budget_score = 0.0
            reason("reason.budgetLow" if below else "reason.budgetHigh")
    else:
        budget_score = W_BUDGET / 2  # chegara yo'q — neytral
    breakdown["budget"] = round(budget_score, 1)
    score += budget_score

    # --- 💱 Valyuta (0–5) ---
    if pref_cur:
        if tender.get("currency") == pref_cur:
            cur_score = W_CURRENCY
            reason("reason.currency", currency=pref_cur)
        else:
            cur_score = 0.0
    else:
        cur_score = W_CURRENCY / 2  # afzallik yo'q — neytral
    breakdown["currency"] = round(cur_score, 1)
    score += cur_score

    return {
        "score": round(score),
        # Interfeys uchun — avvalgidek tayyor o'zbekcha matn
        "reasons": [i18n.t(i18n.DEFAULT_LANG, k["key"], **k["vars"]) for k in keys],
        # Bildirishnoma uchun — foydalanuvchi tilida qayta chizish imkoni
        "reason_keys": keys,
        "matched_keywords": matched_kw,
        "breakdown": breakdown,
    }


# ---------------------------------------------------------------------------
# KATALOG MOSLIGI — "bu tender mening mahsulotimga tegishlimi?"
#
# `score_tender()` dan FARQI: u profil bo'yicha 0–100 ball beradi, bu esa
# bitta MAHSULOT bilan bog'liqlikni aniqlaydi va sababini qaytaradi.
#
# NEGA SHU YERDA: qoidani uchta joy ishlatadi — `/catalog` va `/catalog/match`
# endpointlari (`api/main.py`), bildirishnoma (`api/notify.py` orqali) va
# hujjat qamrovi (`etl_doc_text.py --catalog`). Uch nusxa bo'lmasligi uchun
# yagona manba shu funksiya (reja_ai_chat.md §15.3.1).
# ---------------------------------------------------------------------------
def product_matches(cand: Dict[str, Any], product: Dict[str, Any], *,
                    allow_text: bool = True) -> Optional[str]:
    """Tender mahsulotga mos keladimi? -> 'kod' | 'nom' | None.

    `cand` — `queries.match_candidates_sql()` qatori: `good_codes`,
    `name`, `goods_blob` maydonlari kerak.
    `product` — katalog qatori; `codes` (tasdiqlangan prefikslar) bo'lsa
    BIRLAMCHI yo'l shu bo'ladi.

    ------------------------------------------------------------------
    KATEGORIYA MOSLIGI OLIB TASHLANDI — o'lchangan nosozlik
    ------------------------------------------------------------------
    Ilgari tenderning kategoriyasi mahsulotnikiga teng bo'lsa `'category'`
    qaytardi va interfeys uni **100 ball** deb ko'rsatardi. Bu moslik
    emas, shunchaki bir bo'limda ekanlik. O'lchangan oqibat (25 qatorli
    sinov katalogi, 782 ochiq tender):

        substring moslikning 131/206 tasi `category` orqali kelgan;
        faqat-substring topilgan 136 tadan 94 tasi shu yo'ldan.

    Aniq holatlar (ekranda ko'rilgan):
        "Andijon GES T-2 kuch transformatorini ta'mirlash"
            -> "Kondensator (tibbiy muzlatgich)"   100 ball  (mashina)
        "Farg'ona ... maktablar uchun jihoz"  (4 kategoriya)
            -> 25 mahsulotdan 23 tasi              100 ball

    Ya'ni bitta keng kategoriyali mahsulot butun bo'limni "100% mos"
    qilardi. Kategoriya endi FILTR (interfeysda alohida bor), moslik
    dalili EMAS.
    """
    # --- 1. KOD (birlamchi) — tilga bog'liq emas, qamrovi 100% ---
    kodlar = product.get("codes") or []
    if kodlar:
        for gc in (cand.get("good_codes") or []):
            if not gc:
                continue
            for pref in kodlar:
                if pref and gc.startswith(pref):
                    return "kod"
        # MUHIM: kodi BOR mahsulot uchun matnga TUSHMAYMIZ. Kod aniq
        # javob beradi; matn esa (yuqoridagi o'lchovga qarang) shovqin
        # qo'shadi. "Bemor monitori" -> "Axborot xavfsizligi
        # monitoringi" aynan shu yo'l bilan chiqqandi.
        return None

    # --- 2. NOM (ikkilamchi) — faqat kodi YO'Q mahsulot uchun ---
    # Standart "Mos tenderlar" faqat kod dalilini qabul qiladi. Matn yo'li
    # alohida taxminiy rejim uchun saqlangan: "monitor" so'zi kompyuter va
    # tibbiy qurilmada bir xil bo'lishi mumkin.
    if not allow_text:
        return None

    terms = [product.get("name")] + (product.get("keywords") or [])

    # DALIL TOVAR LOTIDAN KELISHI SHART.
    #
    # O'LCHANGAN SABAB (2026-08-31, 784 ochiq tender). Matn mosligining
    # 99.1% i bitta keng atamadan (`Кабель`) kelardi va u 13 tenderga
    # mos kelib, 4 tasi SOXTA edi (precision 69.2%). To'rtalasi ham
    # XIZMAT tavsifidan yoki tender SARLAVHASIDAN kelgandi:
    #     "Услуга по прокладке ... кабеля"      (kabel yotqizish)
    #     "Строительно-монтажные работы"        (sarlavhada)
    #     "Услуга по ... испытанию изоляции"    (sinov xizmati)
    #
    # `tovar_blob` da FAQAT tovar lotlari nomi bor
    # (`lot_tovarmi()`, `schema_patch_xizmat.sql`). Tender sarlavhasi
    # va xizmat lotlari QO'SHILMAYDI.
    #
    # O'LCHANGAN NATIJA (yorliq — tenderda 27.3x loti bormi):
    #     ESKI   mos 13  TP 9  FP 4  precision  69.2%  recall 56.2%
    #     YANGI  mos  9  TP 9  FP 0  precision 100.0%  recall 56.2%
    # Recall O'ZGARMADI.
    #
    # `Кабель` QORA RO'YXATGA OLINMAGAN — u hali ham mos keladi,
    # lekin faqat TOVAR loti dalil bo'lganda.
    #
    # ORQAGA MOSLIK: `tovar_blob` kaliti YO'Q bo'lsa (eski chaqiruvchi,
    # sinov qatori) eski xulq saqlanadi. BO'SH bo'lsa (hamma lot
    # xizmat) — moslik YO'Q, va bu KUTILGAN.
    if "tovar_blob" in cand:
        blob = _norm(cand.get("tovar_blob") or "")
    else:
        blob = _norm(f"{cand.get('name') or ''} {cand.get('goods_blob') or ''}")

    for t in terms:
        # _hits — alifbodan qat'i nazar va SO'Z BOSHIDAN: katalogda
        # "nasos" bo'lsa "Насос" tovarli tender ham mos keladi.
        if t and _hits(t, blob):
            return "nom"
    return None


# ---------------------------------------------------------------------------
# TENDER TIRIKMI — "bunga hali taklif berish mumkinmi?"
#
# NEGA KERAK: yopilgan yoki muddati o'tgan tender bo'yicha tahlil qilish
# — bekorga sarflangan pul (AI chaqiruvi) va foydalanuvchini chalg'itadigan
# javob. Ro'yxat filtrlari (`queries.build_tender_filters`) buni allaqachon
# ushlaydi, lekin AI qatlami ro'yxatdan MUSTAQIL chaqirilishi mumkin:
# to'g'ridan-to'g'ri havola, eski kartochka, ERP so'rovi, chat tool'i.
# Shuning uchun tekshiruv ikkinchi marta, model chaqirilishidan OLDIN
# bajariladi (reja_ai_chat.md §16.2).
#
# TERMINAL_STATUSES `dim_status.is_terminal` ning NUSXASI. Qator `is_terminal`
# ustunini olib kelsa (masalan `match_candidates_sql`) — o'sha ustunlik qiladi.
# ---------------------------------------------------------------------------
TERMINAL_STATUSES = frozenset({"close", "cancel", "not_realized", "expired"})


def closed_reason(tender: Dict[str, Any],
                  now: Optional[_dt.datetime] = None) -> Optional[str]:
    """Tender yopiqmi? -> sabab matni (o'zbekcha) yoki `None` (tirik).

    `tender` — kamida `status`, ixtiyoriy `close_at` va `is_terminal`.
    `now` — sinov uchun; berilmasa joriy vaqt (UTC).
    """
    status = (tender.get("status") or "").strip()

    if tender.get("is_terminal") is True or status in TERMINAL_STATUSES:
        label = {"expired": "muddati tugagan", "close": "yakunlangan",
                 "cancel": "bekor qilingan",
                 "not_realized": "amalga oshmagan"}.get(status, status or "noma'lum")
        return f"tender yopilgan ({label})"

    close_at = _as_dt(tender.get("close_at"))
    if close_at is not None:
        now = now or _dt.datetime.now(_dt.timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=_dt.timezone.utc)
        if close_at <= now:
            return "takliflar muddati tugagan"

    return None


def _as_dt(v: Any) -> Optional[_dt.datetime]:
    """`close_at` ni datetime ga keltiradi.

    Funksiya IKKI xil kirish bilan chaqiriladi: xom DB qatori (psycopg2
    `datetime` beradi) va SHAKLLANTIRILGAN JSON (`main._iso()` ISO satrga
    aylantiradi). Ikkalasini ham qabul qilamiz — aks holda tekshiruv
    chaqiruvchiga qarab yiqilardi.

    Naive qiymat UTC deb olinadi: solishtirish xato bermasin.
    """
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, str):
        try:
            v = _dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(v, _dt.datetime):
        return None
    return v if v.tzinfo else v.replace(tzinfo=_dt.timezone.utc)
