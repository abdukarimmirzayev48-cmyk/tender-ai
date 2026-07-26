"""
KATEGORIYA TAKSONOMIYASI — yagona manba (B bosqich)
==================================================
Platformalar bo'ylab YAGONA kategoriya qolipi. AI'siz, deterministik:

  - Mahsulot tenderlari (xt-xarid, uzex): tovar kodi (good_code) 2-xonali
    prefiksi = milliy klassifikator (ИКПУ/ОКЭД, NACE bo'limi). Bu ikkala
    platformada BIR XIL. Prefiks -> kategoriya.
  - Qurilish (mc): tovar kodi yo'q, lekin butunlay qurilish. object_type
    (Общестроительный/Дороги/Мелиорация/Проектно-изыскательный) -> ichki tur.

Ikki daraja: PARENT (keng kategoriya) + ichki (sub). tender_category.code
yaproq kodni saqlaydi (parent yoki 'parent/sub'); parent kodидan aniqlanadi.

AI KELGACH: 5a category_tags shu kodlarni ANIQLASHTIRADI (kodsiz yoki
noaniq tenderlar uchun). Kod = poydevor, AI = sayqal.
"""
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# 1. KATEGORIYA DARAXTI — parent (level 1) + ichki (level 2)
#    (code, parent, name_uz, sort)
# ---------------------------------------------------------------------------
CATEGORY_TREE = [
    # code                    parent          name_uz                              sort
    ("qurilish",              None,          "Qurilish va infratuzilma",           10),
    ("qurilish/umumiy",       "qurilish",    "Umumqurilish",                       11),
    ("qurilish/material",     "qurilish",    "Qurilish materiallari",              15),

    ("transport",             None,          "Avtomobil va transport",             20),
    ("transport/avto",        "transport",   "Avtomobil va ehtiyot qismlar",       21),
    ("transport/boshqa",      "transport",   "Boshqa transport vositalari",        22),
    ("transport/xizmat",      "transport",   "Yuk tashish va transport xizmati",   23),

    ("mashina",               None,          "Mashina va uskunalar",               30),
    ("elektronika",           None,          "Kompyuter va elektronika",           40),
    ("elektr",                None,          "Elektr uskunalari",                  50),
    ("tibbiyot",              None,          "Tibbiyot va farmatsevtika",          60),
    ("kimyo",                 None,          "Kimyo va materiallar",               70),
    ("metall",                None,          "Metall va mahsulotlari",             80),
    ("mebel",                 None,          "Mebel",                              90),
    ("oziq",                  None,          "Oziq-ovqat va ovqatlanish",         100),
    ("qishloq",               None,          "Qishloq xo‘jaligi",                 110),
    ("it",                    None,          "IT va aloqa",                       120),
    ("konsalting",            None,          "Konsalting va professional xizmatlar", 130),
    ("talim",                 None,          "Ta’lim va fan",                     140),
    ("kommunal",              None,          "Tozalash va kommunal",              150),
    ("boshqa",                None,          "Boshqa",                            999),
]

# ---------------------------------------------------------------------------
# 2. NACE bo'lim (2-xonali) -> yaproq kategoriya kodi
#    (mahsulot tenderlari: good_code[:2])
# ---------------------------------------------------------------------------
OKED_MAP: Dict[str, str] = {
    # Qishloq xo'jaligi
    "01": "qishloq", "02": "qishloq", "03": "qishloq",
    # Oziq-ovqat
    "10": "oziq", "11": "oziq", "56": "oziq",
    # Kimyo / materiallar
    "20": "kimyo", "22": "kimyo",
    "23": "qurilish/material",           # nometall mineral (sement, g'isht...)
    # Metall
    "24": "metall", "25": "metall",
    # Elektronika / elektr / mashina
    "26": "elektronika", "27": "elektr", "28": "mashina", "33": "mashina",
    # Transport
    "29": "transport/avto", "30": "transport/boshqa", "45": "transport/avto",
    "49": "transport/xizmat", "50": "transport/xizmat", "51": "transport/xizmat",
    "52": "transport/xizmat", "53": "transport/xizmat",
    # Mebel
    "31": "mebel",
    # Tibbiyot / farma
    "21": "tibbiyot", "32": "tibbiyot", "86": "tibbiyot", "87": "tibbiyot", "88": "tibbiyot",
    # Qurilish
    "41": "qurilish/umumiy", "42": "qurilish/umumiy", "43": "qurilish/umumiy",
    # IT / aloqa
    "58": "it", "59": "it", "60": "it", "61": "it", "62": "it", "63": "it",
    # Konsalting / professional / moliya / admin
    "64": "konsalting", "65": "konsalting", "66": "konsalting",
    "69": "konsalting", "70": "konsalting", "71": "konsalting", "72": "konsalting",
    "73": "konsalting", "74": "konsalting", "75": "konsalting",
    "77": "konsalting", "78": "konsalting", "79": "konsalting", "80": "konsalting", "82": "konsalting",
    # Tozalash / kommunal
    "81": "kommunal", "95": "kommunal", "96": "kommunal",
    # Ta'lim
    "85": "talim",
}

def code_for_division(division: str) -> str:
    """2-xonali NACE prefiksi -> yaproq kategoriya kodi ('boshqa' agar noma'lum)."""
    return OKED_MAP.get(division, "boshqa")


def parent_of(code: str) -> str:
    """Yaproq kod -> parent kod ('qurilish/yol' -> 'qurilish')."""
    return code.split("/", 1)[0]
