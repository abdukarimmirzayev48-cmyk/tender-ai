"""Katalog mahsulotini foydalanuvchiga ko'rinmas tarzda aniq kodlash.

Bu modul alohida "kodlash navbati" talab qilmaydi. Mahsulot nomi (yoki import
qilingan katalogdagi mahsulot turi) tender lotlarining tarixiy nomlari bilan
solishtiriladi. Faqat barcha mazmunli so'zlar bir lotda uchragan va bitta
8-belgili kod mutlaq ustun bo'lgan holat avtomatik qabul qilinadi.

Noaniq holatda kod taxmin qilinmaydi. Bu recall hisobiga precisionni saqlaydi:
bo'sh natija noto'g'ri "mos" tenderdan xavfsizroq va foydalanuvchi texnik
jarayonni boshqarishga majbur bo'lmaydi.
"""
import re
from typing import Any, Dict, List, Optional

from api import atama, db, kodlash, translit

SYSTEM_ACTOR = "tizim:auto"
MIN_EVIDENCE = 2
MIN_SHARE = 0.75
MAX_TOKENS = 4

_STOP = {
    "uchun", "bilan", "hamda", "yoki", "va", "the", "for", "with",
    "dlya", "and", "product", "mahsulot", "tovar", "xizmat", "usluga",
}


def _type_text(product: Dict[str, Any]) -> str:
    """Import katalogidagi tur maydonini, oddiy formada esa nomni oladi."""
    kws = [str(x).strip() for x in (product.get("keywords") or []) if str(x).strip()]
    # Amaldagi importlarda: brand, mahsulot turi, tavsif. Ikkinchi qiymat
    # model/SKU nomidan ko'ra klassifikatsiya uchun ancha barqaror.
    if len(kws) >= 2 and len(kws[1]) <= 40:
        return kws[1]
    return (product.get("name") or "").strip()


def _tokens(product: Dict[str, Any]) -> List[str]:
    normalized = atama.normal(_type_text(product))
    out: List[str] = []
    for token in re.findall(r"[^\W\d_]+", normalized, flags=re.UNICODE):
        token = token.strip().lower()
        if len(token) < 3 or token in _STOP or token in out:
            continue
        out.append(token)
    # Uzunroq so'z ko'proq ma'no tashiydi. Juda uzun tavsif SQL ni
    # haddan tashqari toraytirmasin.
    return sorted(out, key=len, reverse=True)[:MAX_TOKENS]


def suggest_exact_code(product: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Dominant 8-belgili lot kodini topadi; dalil yetmasa ``None``.

    Foiz modelning o'ziga bergan bahosi emas: shu mahsulot kontekstiga mos
    tarixiy lotlarning necha qismi aynan bitta kodda ekanining ulushi.
    """
    tokens = _tokens(product)
    if not tokens:
        return None

    params: Dict[str, Any] = {}
    clauses: List[str] = []
    folded = translit.sql_fold("g.name")
    for i, token in enumerate(tokens):
        pats: List[str] = []
        # `atama.normal()` ayrim egalik shakllarida bitta yakuniy undoshni
        # qoldiradi: "kreslosi" -> "kreslos", korpusda esa "кресло".
        # Bitta belgilik zaxira faqat uzun so'zda ishlaydi va barcha tokenlar
        # baribir AND bilan tekshiriladi.
        bases = [token] + ([token[:-1]] if len(token) >= 6 else [])
        for base in bases:
            for variant in translit.variants(base):
                if variant and len(variant) >= 3:
                    pat = f"%{variant}%"
                    if pat not in pats:
                        pats.append(pat)
        if not pats:
            continue
        key = f"p{i}"
        params[key] = pats
        clauses.append(f"{folded} LIKE ANY(%({key})s)")
    if not clauses:
        return None

    divisions = kodlash.divisions_for_category(product.get("category_code"))
    family = ""
    if divisions:
        params["divisions"] = divisions
        family = "AND substring(g.good_code from 1 for 2) = ANY(%(divisions)s)"

    candidates = db.query(f"""
        SELECT g.good_code, g.name
        FROM tender_good g
        WHERE g.good_code IS NOT NULL
          AND length(g.good_code) >= 8
          AND g.name IS NOT NULL
          AND ({' OR '.join(clauses)})
          {family}
    """, params)
    # SQL faqat arzon nomzod olish uchun. Yakuniy tekshiruv kanonik SO'Z
    # bo'yicha: `monitor` `monitoring` ichidan topilmaydi.
    counts: Dict[str, int] = {}
    examples: Dict[str, List[str]] = {}
    for row in candidates:
        words = set(atama.normal(row["name"] or "").split())
        matched = True
        for token in tokens:
            bases = {token}
            if len(token) >= 6:
                bases.add(token[:-1])
            # Ruscha sifat oxiri kanonik shaklda 1-2 harf qoldirishi mumkin:
            # `ofis` <-> `ofisno`. Uch va undan uzun davom (`monitoring`)
            # ataylab qabul qilinmaydi.
            token_ok = any(
                base == word
                or (len(base) >= 4 and word.startswith(base)
                    and len(word) - len(base) <= 2)
                for base in bases for word in words)
            if not token_ok:
                matched = False
                break
        if not matched:
            continue
        code = (row["good_code"] or "")[:8]
        counts[code] = counts.get(code, 0) + 1
        bucket = examples.setdefault(code, [])
        if row["name"] not in bucket and len(bucket) < 4:
            bucket.append(row["name"])
    if not counts:
        return None

    ranked = sorted(counts, key=lambda code: (-counts[code], code))
    code = ranked[0]
    total = sum(counts.values())
    evidence = counts[code]
    share = evidence / total if total else 0.0
    if evidence < MIN_EVIDENCE or share < MIN_SHARE:
        return None
    return {
        "code": code,
        "confidence": round(share, 3),
        "evidence": evidence,
        "total": total,
        "examples": examples.get(code) or [],
        "source": "historical_lots",
    }


def classify_product(company_id: int, product_id: int, *, force: bool = False
                     ) -> Dict[str, Any]:
    """Mahsulotga ishonchli aniq kodni bog'laydi.

    Inson tasdiqlagan 8-belgili kod ustidan yozilmaydi. Avvalgi keng
    (5-belgili) kod esa kuchli 8-belgili dalil topilgandagina faolsizlanadi;
    qator o'chmaydi va audit tarixi saqlanadi.
    """
    product = db.query_one(
        "SELECT id, name, category_code, keywords FROM catalog_product "
        "WHERE id=%(p)s AND company_id=%(c)s",
        {"p": product_id, "c": company_id})
    if not product:
        return {"status": "not_found"}

    active = db.query(
        "SELECT code, tasdiqlagan FROM v_catalog_code_active "
        "WHERE product_id=%(p)s AND company_id=%(c)s",
        {"p": product_id, "c": company_id})
    exact = [r for r in active if len(r["code"] or "") >= 8]
    if exact and not force:
        return {"status": "ready", "code": exact[0]["code"]}
    # Qo'lda berilgan aniq kod avtomatik taxmindan ustun.
    human_exact = [r for r in exact if r.get("tasdiqlagan") != SYSTEM_ACTOR]
    if human_exact:
        return {"status": "ready", "code": human_exact[0]["code"]}

    suggestion = suggest_exact_code(product)
    if not suggestion:
        # Nomi o'zgargan mahsulotda eski avtomatik kod qolib ketmasin.
        if force:
            db.execute_returning(
                "UPDATE catalog_product_code SET tasdiqlandi=NULL "
                "WHERE product_id=%(p)s AND company_id=%(c)s "
                "AND tasdiqlagan=%(actor)s RETURNING product_id",
                {"p": product_id, "c": company_id, "actor": SYSTEM_ACTOR})
        return {"status": "unresolved"}

    code = suggestion["code"]
    rejected = db.query_one(
        "SELECT 1 AS x FROM catalog_product_code "
        "WHERE product_id=%(p)s AND company_id=%(c)s AND code=%(code)s "
        "AND rad_etildi IS NOT NULL",
        {"p": product_id, "c": company_id, "code": code})
    if rejected:
        return {"status": "rejected"}

    if force:
        db.execute_returning(
            "UPDATE catalog_product_code SET tasdiqlandi=NULL "
            "WHERE product_id=%(p)s AND company_id=%(c)s "
            "AND tasdiqlagan=%(actor)s AND code<>%(code)s RETURNING product_id",
            {"p": product_id, "c": company_id, "actor": SYSTEM_ACTOR,
             "code": code})

    # Taklif qatorini yaratamiz, keyin tizim qarori sifatida faollashtiramiz.
    kodlash.taklif_yoz(company_id, product_id, [{
        "code": code, "skor": min(float(suggestion["confidence"]), 0.999),
    }])
    row = db.execute_returning(
        "UPDATE catalog_product_code "
        "SET tasdiqlandi=now(), tasdiqlagan=%(actor)s, rad_etildi=NULL "
        "WHERE product_id=%(p)s AND company_id=%(c)s AND code=%(code)s "
        "AND rad_etildi IS NULL RETURNING product_id",
        {"p": product_id, "c": company_id, "code": code,
         "actor": SYSTEM_ACTOR})
    if not row:
        return {"status": "unresolved"}

    # Aniq kod bor ekan, keng kodlar natijani yana shishirmasin.
    db.execute_returning(
        "UPDATE catalog_product_code SET tasdiqlandi=NULL "
        "WHERE product_id=%(p)s AND company_id=%(c)s "
        "AND length(code)<8 AND tasdiqlandi IS NOT NULL RETURNING product_id",
        {"p": product_id, "c": company_id})
    return {"status": "ready", **suggestion}
