#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SINOVLARNI YURGIZUVCHI — NOINTERAKTIV, CI UCHUN.

NEGA BU FAYL BOR
----------------
Sinovlar shu paytgacha qo'lda, bittalab yurgizilardi. Bu ikki
muammoni berdi:

  1. KODLASH. Chiqish quvurga yo'naltirilganda (CI da HAR DOIM
     shunday) Windows'da Python `locale.getpreferredencoding()` ni
     oladi — bu mashinada `cp1251`. O'zbek kirill va to'liq
     kenglikdagi belgilar u yerda yo'q va chop etish butun
     to'plamni `UnicodeEncodeError` bilan o'ldiradi.
     `_tests/import_test.py` AYNAN shu sababdan 143 ta tekshiruvni
     BAJARMASDAN yiqilardi va uni hech kim payqamadi, chunki
     terminalda yurgizilganda muammo KO'RINMAYDI.

  2. CHIQISH KODI. Bittalab yurgizishda "hammasi o'tdimi" degan
     savolga javob odamning e'tiboriga bog'liq edi.

Bu yurgizuvchi ikkalasini ham hal qiladi: har bola jarayonga
`PYTHONIOENCODING=utf-8` beriladi, chiqish UTF-8 deb o'qiladi, va
yakuniy chiqish kodi HAR QANDAY yiqilishda nolga teng bo'lmaydi.

ISHGA TUSHIRISH
---------------
    python run_tests.py                 # hammasi, bazasiz rejimda
    python run_tests.py --online        # tarmoq/uchidan-uchiga ham
    python run_tests.py --only import   # nomida "import" bori
    python run_tests.py --list          # ro'yxat, yurgizmaydi

CHIQISH KODI: 0 — hammasi o'tdi; 1 — kamida bittasi yiqildi.
"""
from __future__ import annotations

import argparse
import glob
import os
import subprocess
import sys
import time
from typing import List, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.join(HERE, "_tests")

sys.path.insert(0, TESTS)
import konsol  # noqa: E402

#: Bitta to'plamning yuqori vaqt chegarasi. Osilgan sinov butun
#: CI ni to'sib qo'ymasin.
TIMEOUT = int(os.environ.get("TEST_TIMEOUT", "900"))


def toplamlar(filtr: str = "") -> List[str]:
    hammasi = sorted(glob.glob(os.path.join(TESTS, "*_test.py")))
    if filtr:
        hammasi = [p for p in hammasi if filtr.lower() in os.path.basename(p).lower()]
    return hammasi


def yurgiz(yol: str, online: bool) -> Tuple[str, int, float, str]:
    """Bitta to'plamni yurgizadi. -> (nom, chiqish_kodi, sekund, oxirgi_qator)."""
    nom = os.path.basename(yol)[:-3]
    args = [sys.executable, yol] + ([] if online else ["--offline"])

    # BOLAGA UTF-8 MAJBURAN BERILADI. Bu yurgizuvchining o'zi UTF-8
    # bo'lgani yetarli emas — har bola O'Z oqimini o'zi ochadi.
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")

    t0 = time.time()
    try:
        r = subprocess.run(args, cwd=HERE, env=env, capture_output=True,
                           # CHIQISH UTF-8 DEB O'QILADI. `errors` ATAYLAB
                           # "backslashreplace": bola kutilmagan bayt
                           # yuborsa ham yurgizuvchi YIQILMAYDI, lekin
                           # bayt YO'QOLMAYDI — u `\xNN` bo'lib ko'rinadi.
                           encoding="utf-8", errors="backslashreplace",
                           timeout=TIMEOUT)
        kod = r.returncode
        chiqish = (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return nom, -1, time.time() - t0, f"TIMEOUT ({TIMEOUT}s)"
    dt = time.time() - t0

    # Natija qatorini topamiz. To'plamlar turli shakl ishlatadi,
    # shuning uchun bir nechta naqsh qaraladi.
    xulosa = ""
    for ln in reversed(chiqish.strip().splitlines()):
        past = ln.lower()
        if any(k in past for k in ("natija:", "hammasi o'tdi", "sinov o'tdi",
                                   "o'tdi", "yiqildi")):
            xulosa = ln.strip()
            break
    if not xulosa:
        # XULOSA TOPILMASA — bu SIGNAL, jimgina o'tkazib yuborilmaydi.
        # `import_test` aynan shunday holatda edi: chiqish bor, natija
        # qatori yo'q, chunki to'plam o'rtada o'lgan.
        oxiri = chiqish.strip().splitlines()[-1:] or ["(chiqish bo'sh)"]
        xulosa = f"XULOSA QATORI YO'Q — {oxiri[0][:80]}"
    return nom, kod, dt, xulosa


def main() -> None:
    konsol.sozla()

    ap = argparse.ArgumentParser(description="Sinovlarni yurgizuvchi (CI)")
    ap.add_argument("--online", action="store_true",
                    help="Tarmoq va uchidan-uchiga sinovlar ham "
                         "(standart: --offline)")
    ap.add_argument("--only", default="",
                    help="Faqat nomida shu bo'lak bor to'plamlar")
    ap.add_argument("--list", action="store_true", help="Ro'yxat, yurgizmaydi")
    args = ap.parse_args()

    yollar = toplamlar(args.only)
    if not yollar:
        print(f"To'plam topilmadi (filtr: {args.only!r})")
        sys.exit(1)

    if args.list:
        for p in yollar:
            print("  " + os.path.basename(p))
        return

    print("=" * 78)
    print(f"SINOVLAR: {len(yollar)} ta to'plam · "
          f"rejim: {'ONLINE' if args.online else 'OFFLINE'} · "
          f"chegara: {TIMEOUT}s")
    print(f"stdout.encoding = {sys.stdout.encoding} · "
          f"Unicode xavfsiz: {konsol.tekshir()}")
    print("=" * 78)

    natijalar = []
    t0 = time.time()
    for yol in yollar:
        nom, kod, dt, xulosa = yurgiz(yol, args.online)
        natijalar.append((nom, kod, dt, xulosa))
        belgi = "OK  " if kod == 0 else "XATO"
        print(f"  [{belgi}] {nom:<24} {dt:6.1f}s  {xulosa}")
        sys.stdout.flush()

    yiqilgan = [n for n, k, _d, _x in natijalar if k != 0]
    print("=" * 78)
    print(f"JAMI: {len(natijalar)} to'plam, {len(natijalar) - len(yiqilgan)} o'tdi, "
          f"{len(yiqilgan)} yiqildi · {time.time() - t0:.0f}s")
    if yiqilgan:
        print("YIQILGAN: " + ", ".join(yiqilgan))
    print("=" * 78)
    sys.exit(1 if yiqilgan else 0)


if __name__ == "__main__":
    main()
