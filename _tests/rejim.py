# -*- coding: utf-8 -*-
"""
SINOV REJIMI — BAZA va TARMOQ ALOHIDA BAYROQLAR

O'LCHANGAN MUAMMO (2026-09-01)
------------------------------
`run_tests.py` standart holatda har sinovga `--offline` uzatardi va
`--offline` IKKI XIL narsani bir vaqtda o'chirardi:

    22 ta sinovda   `--offline` = BAZASIZ
     3 ta sinovda   `--offline` = TARMOQSIZ
       (doctext, etl_coverage, etl_ishonch)

Ya'ni standart yurgizishda BAZALI tekshiruvlarning HAMMASI
o'tkazib yuborilardi — aynan haqiqiy ma'lumot nuqsonlarini
ushlaydiganlari. "O'tkazib yuborilgan sinov — sinov emas".

BU ALLAQACHON ZARAR KELTIRDI. Ikki misol o'lchandi:

    review_butunlik_test   11-vazifadan beri IKKI tekshiruv
                           yiqilib turgan (eskirgan fikstura)
    doc_qamrov_test        26 ta hujjat DALILSIZ `ok` deb
                           belgilangani ko'rinmagan

Ikkalasi ham faqat `--online` da chiqardi va hech kim
`--online` yurgizmagan.

O'LCHOV (2026-09-01):

    --offline   33 to'plam, 33 o'tdi              246 s
    --online    33 to'plam, 31 o'tdi, 2 YIQILDI   502 s

YECHIM: IKKI MUSTAQIL O'Q
--------------------------
    --bazasiz     bazali tekshiruvlar o'tkaziladi
    --tarmoqsiz   tarmoqqa chiqadigan tekshiruvlar o'tkaziladi
    --offline     ESKI nom — IKKALASI ham (moslik uchun)

Standart yurgizish endi `--tarmoqsiz`: baza MAHALLIY va har doim
bor, tarmoq esa tashqi xizmatga bog'liq. Ya'ni ma'lumot nuqsoni
ko'rinadi, tashqi uzilish esa to'plamni bloklamaydi.
"""
from __future__ import annotations

import argparse


def bayroqlar(ap: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Uchala bayroqni qo'shadi. Har sinov `main()` ida chaqiriladi."""
    ap.add_argument("--bazasiz", action="store_true",
                    help="Bazali tekshiruvlarni O'TKAZIB YUBORADI")
    ap.add_argument("--tarmoqsiz", action="store_true",
                    help="Tarmoqqa chiqadigan tekshiruvlarni O'TKAZIB YUBORADI")
    ap.add_argument("--offline", action="store_true",
                    help="ESKI nom: `--bazasiz --tarmoqsiz` bilan bir xil")
    return ap


def moslash(args: argparse.Namespace) -> argparse.Namespace:
    """`--offline` ni ikkala yangi bayroqqa yoyadi.

    Eski buyruqlar (`... --offline`) o'z ma'nosini SAQLAB QOLADI:
    ular haqiqatan ham hech narsaga chiqmasin degan niyat bilan
    yozilgan.
    """
    if getattr(args, "offline", False):
        args.bazasiz = True
        args.tarmoqsiz = True
    return args
