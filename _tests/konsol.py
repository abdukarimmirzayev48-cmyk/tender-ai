# -*- coding: utf-8 -*-
"""
SINOV CHIQISHINI UTF-8 GA SOZLASH — Windows kod sahifasidan MUSTAQIL.

NEGA BU MODUL BOR (o'lchangan 2026-08-30)
------------------------------------------
`_tests/import_test.py` UMUMAN YURMASDI. U bazadan kelgan mahsulot
nomlarini chop etayotganda yiqilardi:

    UnicodeEncodeError: 'charmap' codec can't encode character
    '\\uff09' in position 17317: character maps to <undefined>

Natijada to'plam BIRORTA tekshiruv natijasini bermasdan o'lardi.
Bu "yiqilgan" emas, "YURMAGAN" — va bu yomonroq, chunki qizil chiroq
ham yonmasdi: 143 ta tekshiruv bor edi va ularning hech biri
bajarilmasdi.

NOSOZLIK AYNAN QAYERDA CHIQADI
-------------------------------
Windows'da Python 3.6+ HAQIQIY KONSOLGA yozganda UTF-16 va
`WriteConsoleW` ni ishlatadi — u hech qachon yiqilmaydi. Lekin
chiqish QUVURGA yoki FAYLGA yo'naltirilganda Python
`locale.getpreferredencoding()` ni oladi va bu mashinada u `cp1251`:

    $ python sinov.py | cat          -> stdout.encoding = cp1251  -> YIQILADI
    $ python sinov.py > out.txt      -> stdout.encoding = cp1251  -> YIQILADI
    $ python sinov.py   (konsolda)   -> UTF-16 WriteConsoleW      -> ishlaydi

Ya'ni nosozlik AYNAN CI SHAROITIDA chiqadi va odam terminalda
yurgizganda KO'RINMAYDI. Shuning uchun u uzoq payqalmadi.

YECHIM TAMOYILI
---------------
UNICODE CHIQISHNI OLIB TASHLAMAYMIZ — kodlashni ANIQ belgilaymiz.
Mahsulot nomlari, tender sarlavhalari va xato matnlari uch alifboda
keladi (lotin, kirill, rus) va ular sinov chiqishining MAZMUNI.
Ularni `?` ga almashtirish yoki ASCII ga qisqartirish sinovni
o'qib bo'lmaydigan qiladi.

    1. Oqimlar `encoding="utf-8"` ga qayta sozlanadi. UTF-8 butun
       Unicode ni qamraydi, ya'ni kodlash xatosi UMUMAN chiqmaydi.
    2. HAQIQIY konsol bo'lsa, konsolning kod sahifasi ham 65001
       (UTF-8) ga o'tkaziladi — aks holda baytlar to'g'ri yozilsa
       ham ekranda buzuq ko'rinardi.
    3. `errors="backslashreplace"` — FAQAT zaxira. `replace` EMAS:
       u `?` qo'yib MA'LUMOTNI YO'QOTADI, `backslashreplace` esa
       `\\uff09` deb yozadi va belgi qaysi ekani BILINADI.
    4. Qayta sozlab bo'lmasa — oqim ANIQ `TextIOWrapper` bilan
       o'raladi. Bu ham imkonsiz bo'lsa, XATO YASHIRILMAYDI:
       ogohlantirish chiqadi va `sozla()` muvaffaqiyatsizlikni
       QAYTARADI.

XATO YASHIRILMAYDI
------------------
Bu modul FAQAT kodlashni sozlaydi. Sinov mantiqidagi istisnolarni
ushlamaydi va yutmaydi — yiqilgan sinov yiqilgan bo'lib qolishi
kerak.
"""
from __future__ import annotations

import io
import sys
from typing import List, Optional, Tuple

#: UTF-8 kod sahifasi (Windows).
_CP_UTF8 = 65001


def _konsol_kod_sahifasini_qoy() -> Optional[Tuple[int, int]]:
    """Windows konsolining kod sahifasini UTF-8 ga o'tkazadi.

    Qaytadi: `(eski_chiqish_cp, eski_kirish_cp)` yoki `None`
    (Windows emas / konsol yo'q / ruxsat yo'q).

    FAQAT HAQIQIY KONSOLGA ta'sir qiladi. Quvur yoki faylga
    yo'naltirilganda kod sahifasi ahamiyatsiz — u yerda muhimi
    oqimning `encoding` i.
    """
    if not sys.platform.startswith("win"):
        return None
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        eski_out = k32.GetConsoleOutputCP()
        eski_in = k32.GetConsoleCP()
        if not eski_out:                    # konsol biriktirilmagan
            return None
        if eski_out != _CP_UTF8:
            k32.SetConsoleOutputCP(_CP_UTF8)
        if eski_in != _CP_UTF8:
            k32.SetConsoleCP(_CP_UTF8)
        return (eski_out, eski_in)
    except Exception:                                        # noqa: BLE001
        # Kod sahifasini o'zgartirib bo'lmasligi HALOKAT EMAS:
        # asosiy himoya — oqimning `encoding` i (2-qadam). Shuning
        # uchun bu yerda faqat "bajarilmadi" deb qaytamiz va
        # `sozla()` buni hisobotida ko'rsatadi.
        return None


def _oqimni_sozla(nom: str) -> Tuple[bool, str]:
    """Bitta oqimni UTF-8 ga o'tkazadi. -> (muvaffaqiyat, tafsilot)."""
    oqim = getattr(sys, nom, None)
    if oqim is None:
        return False, f"{nom}: oqim yo'q"

    hozirgi = (getattr(oqim, "encoding", None) or "").lower().replace("-", "")
    if hozirgi in ("utf8", "utf8sig"):
        return True, f"{nom}: allaqachon {oqim.encoding}"

    # 1-yo'l: `reconfigure` (Python 3.7+, TextIOWrapper).
    try:
        oqim.reconfigure(encoding="utf-8", errors="backslashreplace")
        return True, f"{nom}: {hozirgi or '?'} -> utf-8 (reconfigure)"
    except (AttributeError, ValueError, OSError) as e:
        birinchi_xato = f"{type(e).__name__}: {e}"

    # 2-yo'l: xom baytlar oqimini ANIQ o'raymiz. `reconfigure`
    # ishlamaydigan holatlar bor (masalan oqim allaqachon
    # almashtirilgan yoki `TextIOWrapper` emas).
    buf = getattr(oqim, "buffer", None)
    if buf is None:
        return False, f"{nom}: reconfigure yiqildi ({birinchi_xato}), buffer yo'q"
    try:
        setattr(sys, nom, io.TextIOWrapper(
            buf, encoding="utf-8", errors="backslashreplace",
            line_buffering=True))
        return True, f"{nom}: {hozirgi or '?'} -> utf-8 (TextIOWrapper)"
    except Exception as e:                                   # noqa: BLE001
        return False, (f"{nom}: UTF-8 ga o'tkazib bo'lmadi — "
                       f"reconfigure: {birinchi_xato}; wrapper: {e}")


def sozla(ovoz: bool = False) -> bool:
    """`sys.stdout` va `sys.stderr` ni UTF-8 ga o'tkazadi.

    Qaytadi: `True` — ikkala oqim ham UTF-8; `False` — kamida bittasi
    o'tkazilmadi (va bu haqda OGOHLANTIRISH chiqariladi, jimgina
    o'tkazib yuborilmaydi).

    `ovoz=True` — nima qilingani chop etiladi (nosozlik izlashda).

    IDEMPOTENT: bir necha marta chaqirsa bo'ladi.
    """
    kod_sahifa = _konsol_kod_sahifasini_qoy()
    natijalar: List[Tuple[bool, str]] = [_oqimni_sozla("stdout"),
                                         _oqimni_sozla("stderr")]
    hammasi = all(ok for ok, _ in natijalar)

    if ovoz:
        if kod_sahifa:
            print(f"[konsol] kod sahifasi {kod_sahifa[0]} -> {_CP_UTF8}")
        for _ok, izoh in natijalar:
            print(f"[konsol] {izoh}")

    if not hammasi:
        # JIMGINA O'TKAZIB YUBORILMAYDI. Agar UTF-8 o'rnatib
        # bo'lmasa, sinov chiqishi kesilishi mumkin va buni
        # BILISH kerak — aks holda "sinov o'tdi" degan xulosa
        # to'liq bo'lmagan chiqishga asoslanardi.
        xabar = "; ".join(izoh for ok, izoh in natijalar if not ok)
        try:
            sys.stderr.write(
                "[konsol] OGOHLANTIRISH: UTF-8 o'rnatilmadi — "
                f"{xabar}. Chiqish kesilishi mumkin.\n")
        except Exception:                                    # noqa: BLE001
            pass
    return hammasi


def tekshir() -> bool:
    """Oqimlar HAQIQATAN Unicode ni qabul qiladimi — AMALDA sinaydi.

    `encoding` atributiga ishonish yetarli emas: u to'g'ri ko'rinib,
    yozuv baribir yiqilishi mumkin. Shuning uchun haqiqiy yozuv
    urinib ko'riladi.

    Sinov belgilari AYNAN import_test ni yiqitganlar:
        \\uff09  FULLWIDTH RIGHT PARENTHESIS  — mahsulot nomlarida
        \\u04b3  o'zbek kirill "ҳ"
        \\u2019  o'ng qo'shtirnoq
    """
    namuna = "）ҳ’"
    for nom in ("stdout", "stderr"):
        oqim = getattr(sys, nom, None)
        if oqim is None:
            continue
        kodlash = getattr(oqim, "encoding", None)
        if not kodlash:
            return False
        try:
            namuna.encode(kodlash, errors="strict")
        except (UnicodeEncodeError, LookupError):
            return False
    return True
