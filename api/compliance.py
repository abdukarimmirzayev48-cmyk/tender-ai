"""
HUJJATLAR TO'LIQLIGI CHEKLISTI (REJA.md P0-8)
=============================================
"Bu tenderga ariza berish uchun qaysi hujjatlar kerak va ular bizda bormi?"

MVP CHEKLOVI — ONGLI SODDALASHTIRISH:
    Bu STATIK CHEKLIST. Qoidaga asoslangan: tender matnidan hujjat TALABLARI
    qidiriladi va kompaniya bazasidagi hujjatlar bilan solishtiriladi.
    Hujjat MAZMUNINING huquqiy to'g'riligi TEKSHIRILMAYDI va bu ATAYIN
    shunday — aks holda mahsulot noto'g'ri huquqiy kafolat hissini yaratardi.
    Modul HECH QANDAY AI/model chaqirmaydi.

UCHTA MANBA:
    1) BAZAVIY RO'YXAT — biznes-jarayonda (oddiy xarid, 10-11 bosqich)
       buyurtmachi namunaviy ravishda so'raydigan 6 ta hujjat. Ular tender
       matnida yozilmagan bo'lsa ham cheklistda turadi, chunki ariza
       to'plamining odatiy tarkibi shu.
    2) TENDER MATNI — anno, method_marks, tovar spetsifikatsiyasi va
       (mavjud bo'lsa) hujjatlardan ajratilgan matn. Topilgan har talab
       DALIL (evidence) bilan ko'rsatiladi: matnning aynan qaysi bo'lagidan
       kelib chiqqani. Bu NFR shaffoflik talabi.
    3) KOMPANIYA BAZASI — `company_document` (schema_patch_compliance.sql).

HALOL HOLAT: tender matnida hech narsa topilmasa cheklist buni OCHIQ aytadi
    (`detected_from_tender = false`, xabar bilan). O'lchov: 342 tenderning
    aksariyatida anno qisqa (o'rtacha ~132 belgi) va hujjat talablari
    umuman yozilmagan — ular biriktirilgan PDF ichida qoladi. Bo'sh ro'yxat
    ko'rsatib "hujjat kerak emas" degan taassurot qoldirish XATO bo'lardi.

ALIFBO: manba matni aralash (ruscha kirill, o'zbek lotin, o'zbek kirill).
    Barcha qidiruv api/translit.py orqali — o'zak bitta alifboda yozilsa ham
    ikkalasi topiladi ("сертификат" <-> "sertifikat"). Alifbo bilan
    tarjima qilib bo'lmaydigan so'zlar (свидетельство <-> guvohnoma)
    naqshlarда ALOHIDA yoziladi.

ANIQLIK (precision) ustuvor: yalang'och kalit so'z juda ko'p soxta natija
    beradi. O'lchov (342 ta tender, 2113 pozitsiya):
        "соответстви" -> 58 ta tender, deyarli hammasi "в соответствии с ..."
        "налогов"     -> 20 ta, ko'pi "анаЛОГОВых" ichidan (fold qurboni)
        "аккредит"    -> "аккредитива" (akkreditiv, akkreditatsiya emas)
    Shuning uchun qoida bitta so'z emas, O'ZAKLAR YAQINLIGI + ISTISNOLAR.
"""
import datetime as _dt
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Tuple

from api import translit

#: Ko'p o'zakli qoidada o'zaklar orasidagi eng katta masofa (belgi).
#: 80 ~ bitta jumla bo'lagi. Kattaroq qilinса "сертификат" bir jumlada,
#: "соответстви" boshqasida bo'lsa ham mos kelib qolardi.
WINDOW = 80

#: Dalil (evidence) uchun ajratib olinadigan matn bo'lagi uzunligi.
EVIDENCE_PAD = 70

#: Muddati tugashiga shuncha kun qolganda "tugayapti" deb ogohlantiramiz.
EXPIRING_SOON_DAYS = 30


# ---------------------------------------------------------------------------
# KANONIK HUJJAT TURLARI
# ---------------------------------------------------------------------------
# Har tur: kod, o'zbekcha nom, izoh, bazaviymi, aniqlash naqshlari, istisnolar.
#
# `patterns` — variantlar ro'yxati. Har variant O'ZAKLAR KORTEJI: hammasi
#   matnda VA bir-biridan WINDOW belgi ichida bo'lsa — mos keldi.
#   Bitta o'zakli variant faqat so'z o'z-o'zidan aniq bo'lganda ishlatiladi
#   ("доверенност", "ishonchnoma").
# `exclude` — BITTA o'zaklar (ibora emas!): topilgan oyna atrofida shulardan
#   biri bo'lsa moslik BEKOR qilinadi. Ibora yozib bo'lmaydi, chunki rus tili
#   qo'shimchalari orada turadi ("гарантийный срок" != "гарантийн срок").
#
# O'zaklar QISQARTIRILGAN holda yoziladi (so'z oxiri kesilgan): rus tilida
# kelishik qo'shimchalari o'zgaradi — "сертификат / сертификата / сертификатов".
DOC_TYPES: List[Dict[str, Any]] = [
    {
        "code": "reg_certificate",
        "label": "Davlat ro'yxatidan o'tganlik guvohnomasi",
        "hint": "Yuridik shaxsning davlat ro'yxatidan o'tkazilganligi haqidagi guvohnoma.",
        "base": True,
        "patterns": [
            ("свидетельств", "регистрац"),
            ("свидетельств", "государственн"),
            # Apostrof canon() da tushib qoladi -> "ro'yxat" ham, "royxat" ham
            # bir xil qidiriladi. O'zbek KIRILL yozuvi esa alifbo qoidasi bilan
            # chiqmaydi (ў -> у emas), shuning uchun alohida yoziladi.
            ("guvohnoma", "ro'yxat"),
            ("гувохнома", "руйхат"),
            ("гувохнома", "рўйхат"),
            ("davlat ro'yxatidan",),
            ("выписк", "егрюл"),
        ],
        # "система сбора и РЕГИСТРАЦИИ данных" — texnik matn, hujjat emas.
        "exclude": ("датчик", "сигнал"),
    },
    {
        "code": "power_of_attorney",
        "label": "Ishonchnoma",
        "hint": "Ariza va shartnomani imzolovchi vakilga berilgan ishonchnoma.",
        "base": True,
        "patterns": [
            ("доверенност",),
            ("ishonchnoma",),
            ("ишончнома",),
            ("vakolat xat",),
        ],
        "exclude": (),
    },
    {
        "code": "license",
        "label": "Litsenziya / faoliyat ruxsatnomasi",
        "hint": "Litsenziyalanadigan faoliyat turi uchun litsenziya yoki ruxsatnoma.",
        "base": True,
        "patterns": [
            ("лиценз", "деятельност"),
            ("лиценз", "осуществлен"),
            ("лиценз", "вид работ"),
            ("litsenziya", "faoliyat"),
            ("литсензия", "фаолият"),
            ("faoliyat turi uchun litsenziya",),
            ("ruxsatnoma", "faoliyat"),
        ],
        # "Лицензия (бессрочная) для программного обеспечения",
        # "tizimning litsenziyalangan dasturiy ta'minoti" — bu SOTIB
        # OLINAYOTGAN dastur litsenziyasi (tovarning o'zi), yetkazuvchidan
        # talab qilinadigan hujjat EMAS. O'lchangan holatlar: tender 4221601,
        # 20000504422.
        "exclude": ("программн", "software", "бессрочн", "подписк",
                    "dastur", "дастур"),
    },
    {
        "code": "conformity_certificate",
        "label": "Muvofiqlik sertifikati",
        "hint": "Tovarning standart/texnik reglamentga muvofiqligi sertifikati.",
        "base": True,
        "patterns": [
            ("сертификат", "соответстви"),
            ("сертификат", "качеств"),
            ("сертификат", "происхожден"),
            ("sertifikat", "muvofiqlik"),
            ("сертификат", "мувофиклик"),
            ("muvofiqlik sertifikat",),
            ("sifat sertifikat",),
            ("декларац", "соответстви"),
            ("гигиеническ", "сертификат"),
        ],
        # "в соответствии с ..." ("...ga muvofiq") eng ko'p uchraydigan soxta
        # moslik manbai edi: yalang'och "соответстви" 342 tenderдan 58 tasiga
        # mos kelardi. IKKI O'ZAK talabi ("сертификат" ham yonida bo'lsin)
        # ularning hammasini yopdi — alohida istisno kerak emas.
        "exclude": (),
    },
    {
        "code": "guarantee_letter",
        "label": "Kafolat xati",
        "hint": "Yetkazib berish/sifat majburiyatini tasdiqlovchi kafolat xati.",
        "base": True,
        # DIQQAT: XAT (письмо) so'zi SHART. "Гарантийные обязательства",
        # "гарантийный срок эксплуатации" — bular tovarning kafolat SHARTI,
        # topshiriladigan hujjat emas (o'lchangan soxta holat: tender 2115330).
        "patterns": [
            ("гарантийн", "письм"),
            ("письм", "гаранти"),
            ("банковск", "гаранти"),
            ("kafolat xat",),
            ("кафолат хат",),
        ],
        "exclude": ("пробег", "эксплуатац"),
    },
    {
        "code": "bank_details",
        "label": "Bank rekvizitlari",
        "hint": "Hisob raqami, MFO, STIR — to'lov uchun rekvizitlar.",
        "base": True,
        "patterns": [
            ("банковск", "реквизит"),
            ("реквизит", "счет"),
            ("bank rekvizit",),
            ("банк реквизит",),
            ("hisob raqam",),
            ("хисоб раками",),
            ("расчетн счет",),
        ],
        # "банковской системы" (bank tizimi haqidagi qarorlar) anno da ko'p
        # uchraydi — "реквизит" yonida turishi talabi uni allaqachon yopadi.
        "exclude": ("систем", "сектор"),
    },

    # --- Bazaviy emas: faqat tender matnidan aniqlansa qo'shiladi -----------
    {
        "code": "tax_reference",
        "label": "Soliq ma'lumotnomasi (qarzdorlik yo'qligi)",
        "hint": "Soliq organidan qarzdorlik yo'qligi haqidagi ma'lumotnoma.",
        "base": False,
        "patterns": [
            ("справк", "налогов"),
            ("отсутстви", "задолженност"),
            ("налогов", "задолженност"),
            ("soliq", "qarzdorlik"),
            ("солик", "карздорлик"),
            ("soliq malumotnoma",),
        ],
        "exclude": ("аналогов", "каталогов"),
    },
    {
        "code": "charter",
        "label": "Ustav / ta'sis hujjatlari",
        "hint": "Ustav va ta'sis shartnomasining nusxalari.",
        "base": False,
        "patterns": [
            ("устав", "копи"),
            ("учредительн", "документ"),
            ("копи", "устав"),
            ("ustav", "nusxa"),
            ("ta'sis hujjat",),
            ("таъсис хужжат",),
        ],
        "exclude": ("уставн капитал",),
    },
    {
        "code": "financial_report",
        "label": "Moliyaviy hisobot / balans",
        "hint": "Buxgalteriya balansi yoki moliyaviy hisobot nusxasi.",
        "base": False,
        "patterns": [
            ("бухгалтерск", "баланс"),
            ("финансов", "отчетност"),
            ("moliyaviy hisobot",),
            ("buxgalteriya balans",),
            ("бухгалтерия баланс",),
        ],
        # "Разработка ФИНАНСОВОЙ МОДЕЛИ ... Отчет по разработке" — bu xarid
        # qilinayotgan XIZMAT, ariza hujjati emas (tender 3854512, 3943887).
        # Shu sabab ("финансов","отчет") naqshi olib tashlandi: "отчет" juda
        # keng, faqat "отчетност" (hisobot shakli) qoldirildi.
        "exclude": ("модел", "разработк"),
    },
    {
        "code": "technical_proposal",
        "label": "Texnik taklif (texnik topshiriqqa javob)",
        "hint": "Texnik topshiriq talablariga muvofiqlik jadvali/texnik taklif.",
        "base": False,
        "patterns": [
            ("техническ", "предложен"),
            ("техническ задани",),
            ("texnik topshiriq",),
            ("техник топширик",),
            ("texnik taklif",),
        ],
        "exclude": (),
    },
    {
        "code": "price_offer",
        "label": "Narx taklifi",
        "hint": "Tijorat/narx taklifi (smeta bilan).",
        "base": False,
        "patterns": [
            ("ценов", "предложен"),
            ("коммерческ", "предложен"),
            ("narx taklif",),
            ("нарх таклиф",),
        ],
        "exclude": (),
    },
]

#: Kod -> tur (tez topish uchun)
BY_CODE: Dict[str, Dict[str, Any]] = {d["code"]: d for d in DOC_TYPES}

#: Bazaviy (deyarli har tenderда kerak) turlar — biznes-jarayon 10-11 bosqich.
BASE_CODES: List[str] = [d["code"] for d in DOC_TYPES if d["base"]]

#: Cheklist band holatlari
STATUSES = ("ok", "expiring_soon", "expired", "missing")

BASE_EVIDENCE = ("Biznes-jarayonning odatiy ariza to'plami "
                 "(davlat xaridi, 10-11 bosqich)")


# ---------------------------------------------------------------------------
# MATNNI KANONIK SHAKLGA KELTIRISH
# ---------------------------------------------------------------------------
#: O'zbek lotin yozuvidagi apostrof shakllari. Manbada bir xil so'z uch xil
#: yoziladi: "ro'yxat", "ro‘yxat", "roʻyxat". Hammasini olib tashlaymiz —
#: naqshlar ham shu qoidadan o'tadi, ya'ni bitta yozuv yetarli.
_APOSTROPHES = "'‘’ʻ`´"

#: O'ZBEK KIRILL harflari -> eng yaqin ruscha kirill.
#: api/translit.py ruscha kirill uchun sozlangan: uning yig'ish jadvalida
#: ҳ/қ/ў/ғ yo'q, lotin->kirill o'girishi esa "guvohnoma" ni "гувохнома" (х
#: bilan) qiladi. Manbada esa "гувоҳнома" (ҳ bilan) yoziladi va ular
#: uchrashmaydi. Shu qo'shimcha yig'ish ikkalasini bir nuqtaga keltiradi:
#:      гувоҳнома -> гувохнома   <-  guvohnoma
#:      рўйхат    -> руихат      <-  ro'yxat
#: DIQQAT: translit.py O'ZGARTIRILMAYDI — bu faqat shu moduldagi qo'shimcha
#: qatlam (u yerdagi SQL_FOLD bilan mos bo'lishi shart emas: cheklist
#: qidiruvni SQL da emas, Python tomonda bajaradi).
_UZ_CYR_FOLD = {"ҳ": "х", "қ": "к", "ў": "у", "ғ": "г", "ҷ": "ж", "ө": "о"}

_CHAR_CACHE: Dict[str, str] = {}


def _canon_char(ch: str) -> str:
    """Bitta belgining kanonik shakli (bo'sh satr = tushib qoladi).

    translit.norm_text() belgi-ba-belgi ishlaydi (kichik harf + yig'ish,
    ь/ъ o'chadi), shuning uchun butun matnni belgi bo'yicha o'tkazish
    norm_text(matn) bilan bir xil natija beradi. Bizga belgi bo'yicha kerak —
    dalil (evidence) uchun XOM matndagi pozitsiya saqlanishi shart.
    """
    v = _CHAR_CACHE.get(ch)
    if v is None:
        if ch in _APOSTROPHES:
            v = ""
        else:
            low = ch.lower()
            v = translit.norm_text(_UZ_CYR_FOLD.get(low, low))
        _CHAR_CACHE[ch] = v
    return v


def canon(s: str) -> str:
    """Matnning kanonik shakli (naqsh va matn uchun bir xil quvur)."""
    return "".join(_canon_char(c) for c in s or "")


def _canon_indexed(raw: str) -> Tuple[str, List[int]]:
    """Kanonik matn + har kanonik belgining XOM matndagi indeksi.

    Yig'ish ba'zi belgilarni o'chiradi (ь, ъ, apostrof), shuning uchun
    pozitsiyalar siljiydi. Xarita busiz dalil noto'g'ri joydan kesilardi.
    """
    parts: List[str] = []
    idx: List[int] = []
    for i, ch in enumerate(raw):
        f = _canon_char(ch)
        if not f:
            continue
        parts.append(f)
        idx.extend([i] * len(f))
    return "".join(parts), idx


# ---------------------------------------------------------------------------
# NAQSH ANIQLASH
# ---------------------------------------------------------------------------
@lru_cache(maxsize=512)
def _stem_variants(stem: str) -> Tuple[str, ...]:
    """O'zakning barcha alifbo yozuvlari — KANONIK shaklda.

    "сертификат" -> kirill yig'ilgan + "sertifikat" + boshqa o'qilishlar.
    Ya'ni o'zakni bitta alifboda yozish yetarli (api/translit.py variants()).
    Alifbo bilan bog'lanmagan so'zlar (свидетельство <-> guvohnoma) esa
    naqshlarda ALOHIDA yoziladi — translit tarjimon emas.
    """
    base = canon(stem)
    out, seen = [], set()
    for v in translit.variants(stem):
        c = canon(v)
        if not c or c in seen:
            continue
        # QISQARIB ketgan variantni tashlaymiz. Misol: "счет" -> lotinga
        # "schet" -> qayta kirillga "шет" (sch -> ш). Uch harfli "шет"
        # "реШЕТка" ga ham mos kelib, soxta natija berardi. Faqat o'zakning
        # to'liq uzunligidagi variant bunday qisqa bo'lishi mumkin.
        if len(c) < 4 and len(c) < len(base):
            continue
        seen.add(c)
        out.append(c)
    return tuple(out)


def _find_all(hay: str, needles: Sequence[str]) -> List[Tuple[int, int]]:
    """`needles` dan har birining barcha uchrashlari: (boshlanish, tugash)."""
    out: List[Tuple[int, int]] = []
    for n in needles:
        start = 0
        while True:
            i = hay.find(n, start)
            if i < 0:
                break
            out.append((i, i + len(n)))
            start = i + 1
    return sorted(out)


def _match_alternative(blob: str, stems: Sequence[str],
                       exclude: Sequence[str]) -> Optional[Tuple[int, int]]:
    """Bitta variant (o'zaklar korteji) matnда bormi?

    Hamma o'zak topilishi VA ular WINDOW belgi ichida bo'lishi shart.
    Topilgan oyna atrofida `exclude` o'zaklaridan biri bo'lsa — moslik
    BEKOR qilinadi (o'lchangan soxta natijalarni yopadi).
    Natija: kanonik matndagi (boshlanish, tugash) — dalil kesish uchun.
    """
    per_stem: List[List[Tuple[int, int]]] = []
    for st in stems:
        pos = _find_all(blob, _stem_variants(st))
        if not pos:
            return None
        per_stem.append(pos)

    # Birinchi o'zakning har uchrashi uchun qolganlari yaqinda turibdimi?
    for a0, b0 in per_stem[0]:
        lo, hi, ok = a0, b0, True
        for pos in per_stem[1:]:
            near = [p for p in pos if abs(p[0] - a0) <= WINDOW]
            if not near:
                ok = False
                break
            a, b = min(near, key=lambda p: abs(p[0] - a0))
            lo, hi = min(lo, a), max(hi, b)
        if not ok:
            continue
        ctx = blob[max(0, lo - 40):hi + 40]
        if any(v in ctx for ex in exclude for v in _stem_variants(ex)):
            continue
        return lo, hi
    return None


def _evidence(raw: str, idx: Sequence[int], lo: int, hi: int) -> str:
    """Dalil bo'lagi — foydalanuvchi yig'ilgan emas, ASL matnni ko'radi."""
    if not idx:
        return ""
    a = idx[max(0, lo - EVIDENCE_PAD)]
    b = idx[min(len(idx) - 1, hi + EVIDENCE_PAD)] + 1
    frag = re.sub(r"\s+", " ", raw[a:b]).strip()
    return ("…" if a > 0 else "") + frag + ("…" if b < len(raw) else "")


def detect_required(tender_texts: Sequence[Any]) -> List[Dict[str, Any]]:
    """Tender matnidan majburiy hujjatlarni aniqlaydi.

    `tender_texts` — matn manbalari. Har element:
        {"source": "Tender izohi", "text": "..."}  yoki  ("Tender izohi", "...")
        yoki oddiy satr (manba nomi "tender matni" bo'ladi).

    Natija: [{doc_type, label, evidence, source, confidence}] — faqat
    TOPILGANLARI. Bazaviy ro'yxat bu yerga QO'SHILMAYDI (uni check() qo'shadi),
    chunki bu funksiyaning vazifasi — "tender AYNAN nimani so'ragan".
    """
    found: Dict[str, Dict[str, Any]] = {}

    for item in tender_texts or []:
        if isinstance(item, dict):
            source, raw = item.get("source") or "tender matni", item.get("text")
        elif isinstance(item, (tuple, list)) and len(item) == 2:
            source, raw = item
        else:
            source, raw = "tender matni", item
        if not raw:
            continue
        raw = str(raw)
        blob, idx = _canon_indexed(raw)

        for d in DOC_TYPES:
            if d["code"] in found:
                continue  # birinchi (eng ishonchli) dalil yetarli
            for stems in d["patterns"]:
                hit = _match_alternative(blob, stems, d.get("exclude") or ())
                if not hit:
                    continue
                lo, hi = hit
                found[d["code"]] = {
                    "doc_type": d["code"],
                    "label": d["label"],
                    "source": source,
                    "evidence": _evidence(raw, idx, lo, hi),
                    # Bir o'zakli qoida kuchsizroq dalil: so'z boshqa ma'noda
                    # kelgan bo'lishi mumkin. Ko'p o'zakli qoida ancha aniq.
                    "confidence": 90 if len(stems) > 1 else 70,
                }
                break

    # DOC_TYPES tartibini saqlaymiz (interfeys tartibi barqaror bo'lsin)
    return [found[d["code"]] for d in DOC_TYPES if d["code"] in found]


# ---------------------------------------------------------------------------
# KOMPANIYA BAZASI bilan solishtirish
# ---------------------------------------------------------------------------
def _as_date(v: Any) -> Optional[_dt.date]:
    if v is None or v == "":
        return None
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    try:
        return _dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def doc_status(doc: Optional[Dict[str, Any]],
               today: Optional[_dt.date] = None) -> str:
    """Bitta hujjatning holati: missing | expired | expiring_soon | ok."""
    if not doc:
        return "missing"
    today = today or _dt.date.today()
    vu = _as_date(doc.get("valid_until"))
    if vu is None:
        return "ok"          # muddatsiz — "ma'lumot yo'q" emas, "cheklanmagan"
    if vu < today:
        return "expired"
    if (vu - today).days <= EXPIRING_SOON_DAYS:
        return "expiring_soon"
    return "ok"


_STATUS_RANK = {"ok": 0, "expiring_soon": 1, "expired": 2, "missing": 3}


def _pick_best(docs: Sequence[Dict[str, Any]],
               today: _dt.date) -> Optional[Dict[str, Any]]:
    """Bir turdagi bir necha hujjatdan ENG YAROQLISINI tanlaydi.

    Kompaniyada eski va yangilangan nusxa birga turishi mumkin — eskisi
    tufayli butun band "muddati tugagan" bo'lib qolmasin.
    """
    if not docs:
        return None
    def key(d):
        vu = _as_date(d.get("valid_until"))
        # muddatsiz eng yaxshi (0), keyin uzoq muddatlisi
        return (_STATUS_RANK[doc_status(d, today)], 0 if vu is None else 1,
                -(vu.toordinal() if vu else 0))
    return sorted(docs, key=key)[0]


def shape_document(r: Dict[str, Any]) -> Dict[str, Any]:
    """DB qatorini JSON ga tayyorlaydi (endpoint ham, cheklist ham ishlatadi)."""
    def iso(v):
        d = _as_date(v)
        return d.isoformat() if d else None
    return {
        "id": r.get("id"),
        "doc_type": r.get("doc_type"),
        "label": (BY_CODE.get(r.get("doc_type")) or {}).get("label"),
        "name": r.get("name"),
        "number": r.get("number"),
        "issued_at": iso(r.get("issued_at")),
        "valid_until": iso(r.get("valid_until")),
        "file_name": r.get("file_name"),
        "file_ref": r.get("file_ref"),
        "note": r.get("note"),
        "status": doc_status(r),
        "days_left": _days_left(r.get("valid_until")),
    }


def _days_left(valid_until: Any) -> Optional[int]:
    vu = _as_date(valid_until)
    return None if vu is None else (vu - _dt.date.today()).days


def build_checklist(detected: Sequence[Dict[str, Any]],
                    company_docs: Sequence[Dict[str, Any]],
                    today: Optional[_dt.date] = None) -> Dict[str, Any]:
    """Cheklistni yig'adi — BAZAVIY ro'yxat + tenderda topilganlari.

    DB'ga bog'liq emas: sof funksiya, shuning uchun sinovi oson.
    """
    today = today or _dt.date.today()
    det = {d["doc_type"]: d for d in detected or []}

    # Turlar bo'yicha guruhlash (notanish kodlar ham saqlanadi)
    by_type: Dict[str, List[Dict[str, Any]]] = {}
    for r in company_docs or []:
        by_type.setdefault(r.get("doc_type"), []).append(r)

    codes = [c for c in BASE_CODES]
    for c in [d["code"] for d in DOC_TYPES]:
        if c in det and c not in codes:
            codes.append(c)

    items: List[Dict[str, Any]] = []
    for code in codes:
        meta = BY_CODE[code]
        hit = det.get(code)
        best = _pick_best(by_type.get(code) or [], today)
        st = doc_status(best, today)
        items.append({
            "doc_type": code,
            "label": meta["label"],
            "hint": meta["hint"],
            # TENDERда topilgani bazaviydan kuchliroq: dalil bor.
            "required_by": "tender" if hit else "bazaviy",
            "evidence": hit["evidence"] if hit else BASE_EVIDENCE,
            "evidence_source": hit["source"] if hit else None,
            "confidence": hit["confidence"] if hit else None,
            "in_base": best is not None,
            "document": shape_document(best) if best else None,
            "status": st,
            "days_left": _days_left(best.get("valid_until")) if best else None,
        })

    # Kompaniyada bor, lekin cheklistга kirmagan hujjatlar — ularni ham
    # ko'rsatamiz (broker "bu ham kerak bo'lishi mumkin" deb ko'radi),
    # lekin ALOHIDA ro'yxatда, majburiy sifatida emas.
    listed = {i["doc_type"] for i in items}
    extra = []
    for code, rows in by_type.items():
        if code in listed:
            continue
        best = _pick_best(rows, today)
        extra.append({
            "doc_type": code,
            "label": (BY_CODE.get(code) or {}).get("label") or code,
            "document": shape_document(best) if best else None,
            "status": doc_status(best, today),
        })
    extra.sort(key=lambda x: x["label"])

    n_missing = sum(1 for i in items if i["status"] == "missing")
    n_expired = sum(1 for i in items if i["status"] == "expired")
    n_soon = sum(1 for i in items if i["status"] == "expiring_soon")
    n_ok = sum(1 for i in items if i["status"] == "ok")

    detected_any = bool(det)
    if detected_any:
        note = (f"Tender matnidan {len(det)} ta hujjat talabi aniqlandi. "
                "Qolganlari — odatiy ariza to'plami.")
    else:
        note = ("Tender matnida aniq hujjat talabi topilmadi — bazaviy ro'yxat "
                "ko'rsatilmoqda. To'liq talablar tenderning biriktirilgan "
                "hujjatlarida bo'lishi mumkin, ularni qo'lda tekshiring.")

    return {
        "items": items,
        "extra_documents": extra,
        "summary": {
            "total": len(items),
            "ready": n_ok,
            "missing": n_missing,
            "expired": n_expired,
            "expiring_soon": n_soon,
            # Ariza berishga to'sqinlik qiladiganlar (yo'q + muddati tugagan)
            "blocking": n_missing + n_expired,
            "detected_from_tender": detected_any,
            "detected_count": len(det),
            "note": note,
            # Cheklist nima QILMAYDI — noto'g'ri kafolat hissini yo'qotamiz.
            "disclaimer": ("Cheklist hujjat BORLIGINI va MUDDATINI tekshiradi, "
                           "mazmunining huquqiy to'g'riligini emas."),
        },
    }


# ---------------------------------------------------------------------------
# DB QATLAMI — endpoint shu ikki funksiyani chaqiradi
# ---------------------------------------------------------------------------
#: Tender matn manbalari. `tender_document_text` (boshqa modul jadvali) —
#: IXTIYORIY: mavjud bo'lsa qo'shiladi, bo'lmasa so'rov shunchaki NULL beradi.
#: to_regclass() bilan tekshiramiz — jadval yo'q bo'lsa xato chiqmasin.
TENDER_TEXTS_SQL = """
SELECT t.name          AS tender_name,
       d.anno          AS anno,
       d.method_marks  AS method_marks,
       d.offer_period  AS offer_period,
       (SELECT string_agg(DISTINCT COALESCE(i.spec, ''), E'\\n')
          FROM tender_item i WHERE i.tender_id = t.id)   AS item_spec,
       (SELECT string_agg(DISTINCT COALESCE(l.title, ''), E'\\n')
          FROM tender_lot l WHERE l.tender_id = t.id)    AS lot_titles
FROM tender t
LEFT JOIN tender_detail d ON d.tender_id = t.id
WHERE t.id = %(tender_id)s
"""

#: Biriktirilgan hujjatlardan ajratilgan matn (agar boshqa modul to'ldirgan
#: bo'lsa). Jadval yo'q bo'lishi MUMKIN — chaqiruvchi xatoni yutadi.
DOC_TEXT_SQL = """
SELECT string_agg(x.text, E'\\n') AS doc_text
FROM (SELECT text FROM tender_document_text
      WHERE tender_id = %(tender_id)s AND text IS NOT NULL
      LIMIT 20) x
"""

_TEXT_LABELS = {
    "tender_name": "Tender nomi",
    "anno": "Tender izohi (anno)",
    "method_marks": "Baholash usuli",
    "offer_period": "Takliflar muddati",
    "item_spec": "Pozitsiya spetsifikatsiyasi",
    "lot_titles": "Lot nomlari",
    "doc_text": "Biriktirilgan hujjat matni",
}

_DOC_COLS = ("id, doc_type, name, number, issued_at, valid_until, "
             "file_name, file_ref, note, created_at, updated_at")

DOCS_LIST_SQL = f"SELECT {_DOC_COLS} FROM company_document ORDER BY doc_type, id"

DOC_INSERT_SQL = f"""
INSERT INTO company_document
    (doc_type, name, number, issued_at, valid_until, file_name, file_ref, note)
VALUES (%(doc_type)s, %(name)s, %(number)s, %(issued_at)s, %(valid_until)s,
        %(file_name)s, %(file_ref)s, %(note)s)
RETURNING {_DOC_COLS}
"""

DOC_UPDATE_SQL = f"""
UPDATE company_document SET
    doc_type=%(doc_type)s, name=%(name)s, number=%(number)s,
    issued_at=%(issued_at)s, valid_until=%(valid_until)s,
    file_name=%(file_name)s, file_ref=%(file_ref)s, note=%(note)s,
    updated_at=now()
WHERE id=%(id)s
RETURNING {_DOC_COLS}
"""

DOC_DELETE_SQL = "DELETE FROM company_document WHERE id=%(id)s RETURNING id"


def tender_texts(tender_id: int) -> List[Dict[str, str]]:
    """Tenderning barcha matn manbalari (manba nomi bilan — dalil uchun)."""
    from api import db  # kech import: modulni DB'siz ham sinash mumkin bo'lsin

    row = db.query_one(TENDER_TEXTS_SQL, {"tender_id": tender_id})
    if not row:
        return []
    out = [{"source": _TEXT_LABELS[k], "text": v}
           for k, v in row.items() if v and str(v).strip()]

    # Hujjat matni — ixtiyoriy manba (jadval boshqa modulniki).
    try:
        r2 = db.query_one(DOC_TEXT_SQL, {"tender_id": tender_id})
        if r2 and r2.get("doc_text"):
            out.append({"source": _TEXT_LABELS["doc_text"], "text": r2["doc_text"]})
    except Exception:
        pass  # jadval hali yo'q yoki bo'sh — cheklist busiz ham ishlaydi
    return out


def check(tender_id: int) -> Dict[str, Any]:
    """Tender bo'yicha to'liq cheklist — endpoint shuni qaytaradi."""
    from api import db

    texts = tender_texts(tender_id)
    docs = db.query(DOCS_LIST_SQL)
    res = build_checklist(detect_required(texts), docs)
    res["tender_id"] = tender_id
    res["text_sources"] = [t["source"] for t in texts]
    return res
