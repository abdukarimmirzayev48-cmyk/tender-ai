# -*- coding: utf-8 -*-
"""ATAMA LUG'ATI — o'zbek tili UCH XIL yozuvda keladi, manba BITTA.

NEGA BU MODUL BOR
═════════════════
Loyihada bir xil xato UCH MARTA takrorlandi, har safar boshqa joyda:

  1. `translit.variants()` YOZUVNI o'giradi, TARJIMA qilmaydi:
     "kafolat" -> "кафолат", hujjatda esa "гарантийный". Leksik
     qidiruv tillararo 0/8 berardi (reja_ai_chat.md §16.28).

  2. Eval baholovchisidagi "topilmadi" naqshi tor edi — model
     "duch kelinmadi" deganda TO'G'RI javob yiqilgan deb sanaldi
     (§16.29).

  3. `.doc` ajratgichi sifat mezonida faqat KIRILL kalit so'zlar bor
     edi — lotincha yozilgan 4 ta muvaffaqiyatli ajratish "yiqildi"
     deb ko'rsatildi, 92% o'rniga 64% (§16.33).

Uchtasi bir sinf: O'zbekiston hujjatlari lotin, kirill va rus tilida
aralash keladi, va har safar kimdir bittasini unutadi. Uchinchi marta
takrorlangan xato — tasodif emas, arxitektura bo'shlig'i.

Shu sababli barcha atama ro'yxatlari SHU YERDA. Iste'molchilar
(`api/ai_chat.py` tsquery, `_tests/ai_eval/run_eval.py` baholovchisi,
`etl_doc_text.py` sifat mezoni) o'z ro'yxatini SAQLAMAYDI — shundan
o'qiydi.

`api/translit.py` BILAN FARQI
═════════════════════════════
`translit` — YOZUV qatlami: bir so'zning lotin/kirill ko'rinishlari
(mexanik o'girish). `atama` — MA'NO qatlami: bir tushunchaning turli
TILDAGI atamalari ("kafolat" = "гарантия"). Ikkalasi birga ishlaydi.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Set

from api import translit

# =====================================================================
# 1. XARID ATAMALARI
# =====================================================================
#
# Har guruh — BITTA TUSHUNCHA, uch yozuvda. Elementlar PREFIKS:
# `to_tsquery` da `:*` bilan ishlatiladi va regexda ham prefiks
# sifatida mos keladi ("гарант" -> гарантия/гарантийный/гарантийного).
#
# QISQA PREFIKS QO'YMANG (3 belgidan kam): "ой:*" "ойлик", "ойна" ga
# ham tushadi. Shu sababli birlik so'zlari (kun/oy/yil) BU YERDA YO'Q —
# ular moslikni hal qilmaydi, shovqinni esa ko'paytiradi.
GURUHLAR: Dict[str, List[str]] = {
    "kafolat":    ["kafolat", "кафолат", "гарант"],
    "muddat":     ["muddat", "муддат", "срок"],
    # "to'lov" apostrofda bo'linadi ("to" + "lov") — ustunda ham,
    # so'rovda ham bir xil, shuning uchun "lov" ham kiritiladi.
    "tolov":      ["lov", "tolov", "тулов", "оплат", "платеж"],
    "avans":      ["avans", "аванс", "предоплат", "oldindan", "олдиндан"],
    "yetkazish":  ["yetkazib", "етказиб", "поставк", "доставк"],
    "sertifikat": ["sertifikat", "сертификат"],
    "litsenziya": ["litsenziya", "лицензи"],
    "shartnoma":  ["shartnoma", "шартнома", "договор", "контракт"],
    "narx":       ["narx", "нарх", "цена", "стоимост"],
    "tovar":      ["tovar", "товар", "продукц", "mahsulot", "махсулот"],
    "sifat":      ["sifat", "сифат", "качеств"],
    "talab":      ["talab", "талаб", "требован"],
    "hujjat":     ["hujjat", "хужжат", "документ"],
    "ish":        ["ishlar", "ишлар", "работ"],
    "xizmat":     ["xizmat", "хизмат", "услуг"],
    "zakalat":    ["zakalat", "закалат", "залог", "обеспечен"],
    "jarima":     ["jarima", "жарима", "штраф", "пеня"],
    "muvofiq":    ["muvofiq", "мувофик", "соответств"],
    "summa":      ["summa", "сумма", "қиймат", "qiymat"],
    # TAJRIBA — malaka mezoni uchun. O'lchandi: korpusda 2 578 bo'lakda
    # uchraydi va 216 tasida SONLI talab bor.
    "tajriba":    ["tajriba", "тажриб", "опыт", "стаж"],
}


def _fold(x: str) -> str:
    return translit.fold_cyr(x.lower())


#: prefiks -> o'sha guruhning BARCHA prefikslari (yig'ilgan alifboda)
_LUGAT: Dict[str, List[str]] = {}
for _nom, _gr in GURUHLAR.items():
    _f = sorted({_fold(x) for x in _gr})
    for _a in _f:
        _LUGAT[_a] = _f

#: guruh nomi -> yig'ilgan prefikslar
GURUH_PREFIKS: Dict[str, List[str]] = {
    nom: sorted({_fold(x) for x in gr}) for nom, gr in GURUHLAR.items()
}

#: TALABGA OID guruhlar — hujjat bo'lagini tanlashda ishlatiladi.
#:
#: NEGA SHU YERDA. Ro'yxat avval `requirement_ai._talab_tsquery()`
#: ichida QATTIQ YOZILGAN edi. `tajriba` guruhi qo'shilganda uni
#: o'sha ro'yxatga qo'shish UNUTILDI va natijada tajriba atamasi
#: bor bo'laklar TANLANMAY qoldi — ajratgich yozilgan, qoidasi bor,
#: sinovi o'tgan, lekin KIRISH YETIB BORMAGAN.
#:
#: O'lchandi: bo'lak skani 73 tenderda tajriba talabi bor dedi,
#: ajratgich esa 22 ta topdi.
#:
#: Endi ro'yxat SHU YERDA va sinov uni `QOIDALAR` bilan taqqoslaydi:
#: yangi tur qo'shilib, bu ro'yxatga tushmasa — sinov yiqiladi.
TALAB_GURUHLARI: List[str] = [
    "kafolat", "sertifikat", "litsenziya", "muddat", "tolov",
    "talab", "sifat", "yetkazish", "jarima", "zakalat",
    "shartnoma", "muvofiq", "avans", "tajriba",
]

#: Ro'yxatdagi har guruh HAQIQATAN mavjud bo'lsin — nom xato
#: yozilsa u jimgina e'tiborsiz qolardi (`.get(g, [])`).
_yoq = [g for g in TALAB_GURUHLARI if g not in GURUHLAR]
if _yoq:
    raise RuntimeError(f"TALAB_GURUHLARI da noma'lum guruh: {_yoq}")


def guruh(soz: str) -> List[str]:
    """So'z qaysi atama guruhiga tushadi (prefiks bo'yicha). Yo'q -> []."""
    soz = _fold(soz)
    eng, natija = 0, []
    for prefiks, gr in _LUGAT.items():
        if len(prefiks) >= 3 and soz.startswith(prefiks) and len(prefiks) > eng:
            eng, natija = len(prefiks), gr
    return natija


def variantlar(soz: str) -> Set[str]:
    """Bitta so'zning BARCHA izlanadigan shakllari.

    Uch manbadan yig'iladi:
      1. so'zning o'zi (yig'ilgan alifboda);
      2. YOZUV variantlari — `translit.variants()` (lotin <-> kirill);
      3. TIL ekvivalentlari — shu moduldagi `GURUHLAR`.

    Aynan shu uchlik har safar unutilardi. Endi bitta chaqiruv.
    """
    out: Set[str] = {_fold(soz)}
    for v in translit.variants(soz):
        v = v.strip()
        if v and " " not in v:
            out.add(v)
    out.update(guruh(soz))
    return {x for x in out if x}


def tsquery_guruh(soz: str) -> List[str]:
    """`to_tsquery` uchun muqobillar: yozuv variantlari + `prefiks:*`."""
    out: List[str] = []
    korilgan: Set[str] = set()

    def qosh(x: str) -> None:
        if x and x not in korilgan:
            korilgan.add(x)
            out.append(x)

    qosh(_fold(soz))
    for v in translit.variants(soz):
        v = v.strip()
        if v and " " not in v:
            qosh(v)
    for p in guruh(soz):
        qosh(p + ":*")
    return out


# =====================================================================
# 2. IBORALAR — baholash va sifat mezonlari uchun
# =====================================================================
#
# Bular ATAMA emas, IBORA: model javobini yoki hujjat matnini
# baholashda ishlatiladi. Ular ham uch yozuvda keladi va ayni shu
# sababdan alohida ro'yxatda saqlanmasligi kerak.

#: "Hujjatda topilmadi" ma'nosidagi iboralar.
#: RO'YXAT ATAYLAB KENG: model bir fikrni turlicha ifodalaydi, tor
#: ro'yxat esa TO'G'RI javobni "taxmin qildi" deb belgilab qo'yadi.
TOPILMADI: List[str] = [
    "topilmadi", "topa olmadim", "topilmagan", "topolmadim",
    "uchramadi", "uchratmadim", "duch kelinmadi", "duch kelmadim",
    "ko['‘’]rsatilmagan", "ko['‘’]rinmadi",
    "keltirilmagan", "belgilanmagan", "aniqlanmadi",
    "aniqlab bo['‘’]lmadi", "yozilmagan", "aytilmagan",
    "mavjud emas", "berilmagan",
    "yo['‘’]q\\b",
    "не (найден|указан|содержит)", "отсутству", "не обнаруж",
]

#: Model "taxmin qilyapman" deb OCHIQ aytsa — bu xato emas, halollik.
#: Alohida sanaladi.
TAXMIN: List[str] = [
    "odatda", "odatdagi", "ko['‘’]pincha", "taxmin", "taxminan",
    "amaliyotda", "as a rule", "обычно",
    "как правило",
]


def naqsh(iboralar: Iterable[str], bayroq: int = re.I) -> "re.Pattern[str]":
    """Ibora ro'yxatidan bitta regex — takroriy `re.compile` bo'lmasin."""
    return re.compile("(" + "|".join(iboralar) + ")", bayroq)


def xarid_naqshi() -> "re.Pattern[str]":
    """HAR QANDAY xarid atamasiga mos regex — sifat mezonlari uchun.

    `etl_doc_text` sifat o'lchovi shundan foydalanadi: matnda xarid
    atamalari bormi. Uch yozuv ham qamraladi, ya'ni §16.33 dagi
    "faqat kirill" xatosi qaytmaydi.
    """
    hamma = sorted({p for gr in GURUH_PREFIKS.values() for p in gr})
    return re.compile("(" + "|".join(hamma) + ")", re.I)
