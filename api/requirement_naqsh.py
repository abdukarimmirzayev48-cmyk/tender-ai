# -*- coding: utf-8 -*-
r"""J3 — talablarni NAQSH bilan ajratish (`method='naqsh'`).

BEPUL. Model chaqirilmaydi.

NEGA ISHLAYDI
═════════════
O'zbekiston tender hujjatlari SHABLON asosida yoziladi. LLM
namunasidan ko'rinadiki, talablarning katta qismi sonli va naqshli:

    Гарантийный срок на запасные части 12 месяцев
    Форма платежа – предоплата в 50 %
    Yetkazib berish muddati ... 30 (o'ttiz) ish kuni

Bularning hammasi `atama + raqam + birlik` shaklida. `api/atama.py`
allaqachon uch yozuvli atama variantlarini beradi — ustiga miqdor
naqshlarini qo'yamiz.

NIMA OLINADI, NIMA OLINMAYDI
════════════════════════════
    OLINADI                          OLINMAYDI (LLM ishi)
    ────────────────────────────     ──────────────────────────────
    kafolat muddati (oy/soat)        "asosiy uzellar 24 oy, ehtiyot
    oldindan to'lov (%)               qismlar 12 oy" — QAYSI biri
    yetkazib berish muddati (kun)     nimaga tegishli
    jarima stavkasi (%)              kontekstli izoh
    INCOTERMS bazisi                 ziddiyat tahlili
    bo'sh shablon (`_____`)          umumlashtirish

Ya'ni: sodda, sonli, takrorlanuvchi talablar BEPUL olinadi. LLM ga
faqat kontekstli qism qoladi va xarajat tushadi.

ISHONCH
═══════
Naqsh topgan talab `confidence = 0.75` oladi — reyestr (1.00) dan
past, chunki naqsh kontekstni bilmaydi: "kafolat muddati 12 oy" jumla
bo'lakning O'RTASIDA turgan bo'lsa, u nimaga tegishli ekani noaniq
qolishi mumkin. Bo'sh shablon esa 0.40 — LLM bilan bir xil daraja.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from api import atama, db, requirement

METHOD = "naqsh"

#: Naqsh topgan talabning ishonchi. Reyestrdan past, LLM bilan
#: taqqoslanadigan daraja.
CONF_NAQSH = 0.75
CONF_BOSH_SHABLON = 0.40      # `_____` — qiymat ko'rsatilmagan

#: Atama va raqam orasida ruxsat etilgan masofa (belgi).
#:
#: O'LCHANGAN: 80 da t7475137 dagi ikkinchi kafolat muddati TUSHIB
#: QOLDI — "Гарантийный срок на основные узлы: РМК, генераторы,
#: электродвигателя, статоры, роторы составляет 24 месяца" da atama
#: bilan raqam orasi ~85 belgi (uzun ro'yxat tufayli).
#:
#: 130 ga ko'tarildi. Yuqoriroq qilish xavfli: jumla chegarasidan
#: o'tib, aloqasiz raqam qo'shilib qoladi. `[^.\n]` cheklovi jumla
#: ichida ushlab turadi.
ORALIQ = 130

#: Naqsh ajratgichi ko'radigan bo'laklar soni.
#:
#: LLM YO'LIDAN KATTA VA BUNING SABABI BOR. `requirement_ai` da
#: `k = 40` — u yerda har bo'lak TOKEN, ya'ni pul. Naqsh esa BEPUL:
#: bu faqat regex, xarajati protsessor vaqti.
#:
#: O'LCHANGAN YO'QOTISH: `k = 40` bilan tajriba talabi bo'lagida BOR
#: 50 ta ochiq tenderdan faqat 30 tasi ajratildi — 20 tasi tanlovga
#: umuman tushmadi (namuna 8/8 da sabab shu edi).
#:
#: Ochiq tenderlarda bo'lak soni: mediana 106, p90 321, eng ko'p 913.
#: 400 mediananing 4 barobari va p90 dan yuqori — ya'ni tenderlarning
#: aksariyati TO'LIQ ko'riladi.
NAQSH_K = 400


def _atama_alt(*guruhlar: str) -> str:
    """`api/atama.py` guruhlaridan regex alternativasi.

    UCH YOZUV shu yerdan keladi — §16.34 dagi "kimdir bittasini
    unutadi" xatosi qaytmasin.
    """
    p: List[str] = []
    for g in guruhlar:
        p.extend(atama.GURUH_PREFIKS.get(g, []))
    # Prefiks: so'z shundan BOSHLANSA yetarli (гарант -> гарантийный)
    return "|".join(re.escape(x) for x in sorted(set(p), key=len, reverse=True))


#: Birlik guruhlari — uch yozuvda.
BIRLIK = {
    "oy":    r"(?:oy|ой|мес(?:яц\w*)?)",
    "kun":   r"(?:kun|кун|дн\w*|день|дней|суток)",
    "yil":   r"(?:yil|йил|год\w*|лет)",
    "soat":  r"(?:soat|соат|час\w*|мото\W?час\w*|mototsoat|моточас\w*)",
    "foiz":  r"(?:%|foiz|фоиз|процент\w*)",
}

#: INCOTERMS — chekli lug'at, ya'ni naqsh emas, RO'YXAT.
INCOTERMS = ["EXW", "FCA", "FAS", "FOB", "CFR", "CIF", "CPT", "CIP",
             "DAP", "DPU", "DDP"]

#: TALAB QILINADIGAN HUJJATLAR — chekli lug'at.
#:
#: Bular naqsh emas, RO'YXAT: xarid hujjatlarida qayta-qayta o'sha
#: nomlar uchraydi. LLM o'lchovida aynan shular "qoplanmagan" ro'yxatda
#: turgan edi (sifat sertifikati, kelib chiqish sertifikati, texnik
#: pasport, qadoqlash varaqasi) — ya'ni bepul olinishi mumkin bo'lgan
#: narsa uchun pul to'lanardi.
#:
#: Har element: (nom, uch yozuvdagi naqsh)
HUJJATLAR: List[Tuple[str, str]] = [
    ("Sifat sertifikati",
     r"(?:sifat\s+sertifikat|сифат\s+сертификат|сертификат\w*\s+качества)"),
    ("Muvofiqlik sertifikati",
     r"(?:muvofiqlik\s+sertifikat|мувофиклик|сертификат\w*\s+соответствия|"
     r"деклараци\w*\s+о\s+соответствии)"),
    ("Kelib chiqish sertifikati",
     r"(?:kelib\s+chiqish\s+sertifikat|сертификат\w*\s+происхождения)"),
    ("Texnik pasport",
     r"(?:texnik\s+pasport|техник\s+паспорт|техническ\w*\s+паспорт)"),
    ("Qadoqlash varaqasi",
     r"(?:qadoqlash\s+varaqa|упаковочн\w*\s+лист)"),
    ("Litsenziya",
     r"(?:litsenziya|лицензи\w*)"),
    ("ISO standarti",
     r"(?:ISO\s*\d{4,5}(?:[:\-]\d{2,4})?)"),
    ("GOST talabi",
     r"(?:GOST|ГОСТ)\s*[\d.\-]*"),
    ("Kafolat xati",
     r"(?:kafolat\s+xat|кафолат\s+хат|гарантийн\w*\s+пис\w*)"),
    # BANK AYLANMASI — HUJJAT sifatida, SONLI CHEGARA sifatida EMAS.
    #
    # O'LCHANGAN QAROR. Korpusda `оборот` / `выручка` / `aylanma`
    # deyarli hamma joyda IKKI shaklda uchraydi:
    #   1. balans SHAKLI maydoni ("1.Чистая выручка от реализации");
    #   2. SO'Z bilan yozilgan miqdor ("kamida uch oylik shartnoma
    #      summasiga teng aylanma mablag'").
    # Sonli chegara ("aylanma kamida 500 mln") deyarli YO'Q.
    #
    # Shuning uchun sonli ajratgich yozilmadi — u SHOVQIN ishlab
    # chiqarardi. Amalda so'raladigan narsa HUJJAT: bankdan
    # ma'lumotnoma. Shuni olamiz.
    ("Bank aylanmasi ma'lumotnomasi",
     r"(?:bank\s+aylanma|банк\s+айланма|"
     r"оборот\w*\s+(?:по\s+)?(?:банковск|расчетн|расчётн)\w*\s+"
     r"(?:счет|счёт)\w*|"
     r"справк\w*[^.\n]{0,30}(?:оборот|выручк)\w*)"),
]


def _naqsh(atamalar: str, birlik: str) -> re.Pattern:
    """`atama ... raqam birlik` — oradagi masofa cheklangan."""
    return re.compile(
        rf"(?P<atama>{atamalar})\w*"
        rf"[^.\n]{{0,{ORALIQ}}}?"
        rf"(?P<son>\d{{1,4}})\s*(?P<birlik>{birlik})",
        re.IGNORECASE)


def _naqsh_teskari(atamalar: str, birlik: str) -> re.Pattern:
    """`raqam birlik ... atama` — SONI ATAMADAN OLDIN keladigan shakl.

    NEGA KERAK — O'LCHANGAN, taxmin emas. Tajriba talabi korpusda
    ASOSAN teskari tartibda yoziladi:

        "камида 8 йиллик тажрибага эга бўлиши"
        "kamida 3 yillik tajriba"
        "стаж работы не менее 3 (трех) лет"   <- bu to'g'ri tartibda

    2 578 bo'lakda o'lchandi:

        atama -> son :  88
        son -> atama : 128     <- USTUN

    Faqat mavjud `_naqsh()` ishlatilganda talablarning ~59% i
    TUSHIB QOLARDI va `qualification` mezoni ko'r qolaverardi.

    Oraliq qisqaroq (60): son bilan atama orasi bu shaklda yaqin
    turadi, uzun oraliq esa aloqasiz raqamni tortib olardi.
    """
    return re.compile(
        rf"(?P<son>\d{{1,3}})\s*(?P<birlik>{birlik})\w*"
        rf"[^.\n]{{0,60}}?(?P<atama>{atamalar})",
        re.IGNORECASE)


#: (talab nomi, tur, naqsh, birlik nomi)
QOIDALAR: List[Tuple[str, str, re.Pattern, str]] = [
    ("Kafolat muddati", "kafolat",
     _naqsh(_atama_alt("kafolat"), BIRLIK["oy"]), "oy"),
    ("Kafolat muddati", "kafolat",
     _naqsh(_atama_alt("kafolat"), BIRLIK["yil"]), "yil"),
    ("Kafolat resursi", "kafolat",
     _naqsh(_atama_alt("kafolat"), BIRLIK["soat"]), "soat"),
    ("Yetkazib berish muddati", "muddat",
     _naqsh(_atama_alt("yetkazish"), BIRLIK["kun"]), "kun"),
    ("To'lov muddati", "tolov",
     _naqsh(_atama_alt("tolov"), BIRLIK["kun"]), "kun"),
    ("Oldindan to'lov", "tolov",
     _naqsh(_atama_alt("avans"), BIRLIK["foiz"]), "%"),
    ("Jarima stavkasi", "boshqa",
     _naqsh(_atama_alt("jarima"), BIRLIK["foiz"]), "%"),
    ("Shartnoma bajarilishi kafolati", "moliyaviy",
     _naqsh(_atama_alt("zakalat"), BIRLIK["foiz"]), "%"),
    # TAJRIBA — IKKALA TARTIBDA. Teskarisi ustun (128 vs 88), lekin
    # to'g'ri tartib ham uchraydi ("стаж работы не менее 3 лет").
    ("Tajriba talabi", "tajriba",
     _naqsh(_atama_alt("tajriba"), BIRLIK["yil"]), "yil"),
    ("Tajriba talabi", "tajriba",
     _naqsh_teskari(_atama_alt("tajriba"), BIRLIK["yil"]), "yil"),
]

#: Bo'sh shablon: atama yonida uch va undan ko'p pastki chiziq.
BOSH_SHABLON = re.compile(
    rf"(?P<atama>{_atama_alt('kafolat', 'muddat', 'tolov')})\w*"
    rf"[^.\n]{{0,{ORALIQ}}}?_{{3,}}", re.IGNORECASE)

INCOTERMS_RE = re.compile(
    r"\b(" + "|".join(INCOTERMS) + r")\b[^.\n]{0,40}?"
    r"(?:Incoterms|ИНКОТЕРМС|инкотермс)?", re.IGNORECASE)

HUJJAT_RE: List[Tuple[str, re.Pattern]] = [
    (nom, re.compile(p, re.IGNORECASE)) for nom, p in HUJJATLAR]


def _kontekst(matn: str, a: int, b: int, atrof: int = 90) -> str:
    """Topilma atrofidagi jumla — shaffoflik uchun."""
    return " ".join(matn[max(0, a - atrof):b + atrof].split())


# =====================================================================
# Ajratish
# =====================================================================

def extract(tender_id: int, company_id: int) -> Dict[str, Any]:
    """Hujjat bo'laklaridan naqsh bo'yicha talab ajratadi. BEPUL."""
    from api import requirement_ai      # bo'lak tanlash bir xil bo'lsin

    chunks = requirement_ai.select_chunks(tender_id, k=NAQSH_K)

    # KESISH JIMGINA O'TMASIN. `NAQSH_K` p90 dan yuqori, lekin
    # o'lchandi: 510 ta ochiq tenderdan 36 tasi 400 dan ko'p bo'lakka
    # ega va ularda jami 5 561 bo'lak ko'rilmay qoladi. Bu qamrov
    # TESHIGI — va u "muvaffaqiyat" kabi ko'rinardi.
    jami_bolak = requirement_ai.chunks_soni(tender_id)
    kesildi = max(0, jami_bolak - len(chunks))

    if not chunks:
        requirement._run_yoz(company_id, tender_id, METHOD, "no_text", 0,
                             None, None, error="talabga oid bo'lak yo'q")
        return {"status": "no_text", "n": 0,
                "jami_bolak": jami_bolak, "kesildi": kesildi}

    topilgan: Dict[Tuple[str, str], dict] = {}

    for c in chunks:
        matn = c.get("text") or ""

        # --- 1. atama + raqam + birlik ---
        for nom, tur, naqsh, birlik in QOIDALAR:
            for m in naqsh.finditer(matn):
                qiymat = f"{m.group('son')} {birlik}"
                kalit = (nom, qiymat)
                if kalit in topilgan:
                    continue
                topilgan[kalit] = {
                    "name": nom, "tur": tur, "qiymat": qiymat,
                    "conf": CONF_NAQSH, "chunk": c,
                    "iqtibos": _kontekst(matn, m.start(), m.end()),
                }

        # --- 2. bo'sh shablon ---
        for m in BOSH_SHABLON.finditer(matn):
            kalit = ("Bo'sh shablon", m.group("atama").lower())
            if kalit in topilgan:
                continue
            topilgan[kalit] = {
                "name": f"To'ldirilmagan shart ({m.group('atama')})",
                "tur": "boshqa",
                "qiymat": "ko'rsatilmagan (shablon bo'sh)",
                "conf": CONF_BOSH_SHABLON, "chunk": c,
                "iqtibos": _kontekst(matn, m.start(), m.end()),
            }

        # --- 3. Talab qilinadigan HUJJATLAR — chekli lug'at ---
        for nom, naqsh in HUJJAT_RE:
            m = naqsh.search(matn)
            if not m:
                continue
            kalit = ("hujjat", nom)
            if kalit in topilgan:
                continue
            topilgan[kalit] = {
                "name": nom, "tur": "sertifikat",
                # AYNAN topilgan shakl — "ISO 9001" va "ISO 14001" bir
                # xil emas.
                "qiymat": " ".join(m.group(0).split())[:80],
                "conf": CONF_NAQSH, "chunk": c,
                "iqtibos": _kontekst(matn, m.start(), m.end()),
            }

        # --- 4. INCOTERMS — chekli lug'at ---
        for m in INCOTERMS_RE.finditer(matn):
            kod = m.group(1).upper()
            kalit = ("INCOTERMS", kod)
            if kalit in topilgan:
                continue
            topilgan[kalit] = {
                "name": "Yetkazib berish bazisi (INCOTERMS)",
                # ATAYLAB "muddat" EMAS: INCOTERMS — yetkazib berish
                # BAZISI (kim qayerda javobgar), muddat emas. Avval
                # "muddat" deb belgilangan edi va `compare_tenders`
                # jadvalining "yetkazish muddati" ustunida "CIP" chiqib
                # qoldi — foydalanuvchi uchun ma'nosiz.
                "tur": "bazis", "qiymat": kod,
                "conf": CONF_NAQSH, "chunk": c,
                "iqtibos": _kontekst(matn, m.start(), m.end()),
            }

    if not topilgan:
        requirement._run_yoz(company_id, tender_id, METHOD, "ok", 0, None,
                             _hash(chunks), error="naqsh mos kelmadi")
        return {"status": "ok", "n": 0,
                "jami_bolak": jami_bolak, "kesildi": kesildi}

    eng_past = 1.0
    for i, (_kalit, t) in enumerate(sorted(topilgan.items()), 1):
        c = t["chunk"]
        eng_past = min(eng_past, t["conf"])
        db.execute_returning(requirement.SQL_UPSERT, {
            "company_id": company_id, "tender_id": tender_id,
            "lot_id": None, "source": "document", "method": METHOD,
            # NAQSH — AI natijasi, inson TEKSHIRISHI kerak.
            "review_status": "pending_review",
            "mashina_holat": "ajratilgan",
            "position_no": i, "name": t["name"][:2000],
            "attrs": json.dumps({"tur": t["tur"], "qiymat": t["qiymat"],
                                 "manba": "naqsh"}, ensure_ascii=False),
            "qty": None, "unit": None, "delivery_days": None,
            # NAQSH MAJBURIYLIKNI BILMAYDI: "shart" va "mumkin" ni
            # ajratish kontekst talab qiladi — bu LLM ishi.
            "is_mandatory": False,
            "confidence": t["conf"],
            "raw_snippet": t["iqtibos"][:2000],
            "file_ref": c["file_ref"], "char_start": c["char_start"],
            "char_end": c["char_end"], "model": None,
        })

    status = "needs_review" if eng_past < 0.60 else "ok"
    # KESILGAN tender ham `needs_review` — qamrov to'liq emas, ya'ni
    # "talab topilmadi" degan xulosa ishonchsiz.
    if kesildi:
        status = "needs_review"
    requirement._run_yoz(
        company_id, tender_id, METHOD, status,
        len(topilgan), eng_past, _hash(chunks),
        error=(f"bo'lak kesildi: {jami_bolak} dan {len(chunks)} ko'rildi"
               if kesildi else None))
    return {"status": status, "n": len(topilgan),
            "eng_past_ishonch": eng_past,
            "jami_bolak": jami_bolak, "kesildi": kesildi}


def _hash(chunks: List[dict]) -> str:
    return requirement.content_hash(
        "|".join(f"{c['file_ref']}:{c['char_start']}" for c in chunks))


# =====================================================================
# Taqqoslash — naqsh LLM ning qanchasini qopladi?
# =====================================================================

def _sonlar(x: Optional[str]) -> set:
    return set(re.findall(r"\d+", x or ""))


def _kalit_sozlar(x: Optional[str]) -> set:
    """Nomdan MA'NOLI so'zlar — taqqoslash uchun.

    `api/atama.py` orqali yig'iladi, ya'ni "sertifikat" va
    "сертификат" BIR XIL kalitga tushadi. Aks holda uch yozuv
    masalasi bu yerda ham qaytardi.
    """
    out = set()
    for soz in re.split(r"[^\w]+", (x or "").lower()):
        if len(soz) < 4:
            continue
        gr = atama.guruh(soz)
        out.add(gr[0] if gr else atama._fold(soz)[:6])
    return out


def taqqosla(tender_id: int, company_id: int) -> Dict[str, Any]:
    """Naqsh va LLM natijalarini yonma-yon qo'yadi.

    O'LCHOV MEZONI: naqsh qatlami LLM topgan talablarning qanchasini
    BEPUL qoplaydi. Qoplanmagan qismi — LLM haqiqatan kerak bo'lgan joy.

    IKKI MEZON, chunki bittasi YETMAYDI:
      - RAQAM mosligi — "12 oy" <-> "12 oy yoki 8000 mototsoat";
      - NOM mosligi   — "Sifat sertifikati" da raqam YO'Q.

    Birinchi o'lchovda faqat raqam bor edi va sertifikatlar HECH QACHON
    "qoplangan" deb sanalmasdi — lug'at qo'shilgandan keyin ham foiz
    o'zgarmadi. Ya'ni mezon ajratgichni emas, O'ZINI o'lchayotgan edi.
    """
    rows = db.query("""
        SELECT method, name, attrs->>'qiymat' AS qiymat, confidence
        FROM tender_requirement
        WHERE company_id=%(c)s AND tender_id=%(t)s AND source='document'
        ORDER BY method, name""", {"c": company_id, "t": tender_id})
    naqsh = [r for r in rows if r["method"] == METHOD]
    llm = [r for r in rows if r["method"] == "llm"]

    naqsh_sonlar = {s for r in naqsh for s in _sonlar(r["qiymat"])}
    naqsh_sozlar = [(_kalit_sozlar(r["name"]) | _kalit_sozlar(r["qiymat"]))
                    for r in naqsh]

    def qoplandimi(r: dict) -> bool:
        if _sonlar(r["qiymat"]) & naqsh_sonlar:
            return True
        k = _kalit_sozlar(r["name"])
        # Kamida IKKI ma'noli so'z mos kelsa — tasodifiy moslik emas.
        return any(len(k & n) >= 2 for n in naqsh_sozlar)

    qoplangan = [r for r in llm if qoplandimi(r)]
    return {
        "naqsh": len(naqsh),
        "llm": len(llm),
        "llm_dan_qoplangan": len(qoplangan),
        "ulush": (round(100 * len(qoplangan) / len(llm)) if llm else None),
        "qoplanmagan": [r["name"] for r in llm if not qoplandimi(r)][:12],
    }
