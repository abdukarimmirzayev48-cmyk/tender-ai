#!/usr/bin/env python3
"""
SINOV: hujjat matnini BO'LAKKA BO'LISH (J2)
===========================================
BAZA KERAK EMAS — `etl_embed.chunk_text()` sof funksiya.

Eng muhim kafolat: `text[char_start:char_end] == bo'lak matni`. Iqtibos
shu ofsetlarga tayanadi — ular bir belgiga siljisa, foydalanuvchi
hujjatda BOSHQA joyni ko'radi va "qora quti bo'lmasin" tamoyili buziladi.

Ishga tushirish:
    .venv\\Scripts\\python.exe _tests\\chunk_test.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):                   # pragma: no cover
    pass

from etl_embed import (CHUNK_OVERLAP, CHUNK_SIZE, MIN_CHUNK,  # noqa: E402
                       chunk_text, content_hash, guess_lang)

_results = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _results.append((name, bool(ok)))
    print(f"  {'OK  ' if ok else 'FAIL'} {name}" +
          (f"\n       {detail}" if detail and not ok else ""))
    return bool(ok)


def eq(name, got, want):
    return check(name, got == want, f"kutilgan={want!r} olingan={got!r}")


# =========================================================================
# 1. OFSETLAR — eng muhim kafolat
# =========================================================================
def test_ofsetlar():
    print("\n[1] char_start/char_end ASL matnga aniq mos keladi")
    matn = ("Texnik topshiriq. " * 200) + "\n\nKafolat muddati 24 oy.\n\n" + \
           ("Yetkazib berish sharti. " * 150)
    chunks = chunk_text(matn)
    check("bo'laklar hosil bo'ldi", len(chunks) > 1, f"-> {len(chunks)}")

    xato = [(a, b) for a, b, t in chunks if matn[a:b] != t]
    check("har bo'lak: matn[a:b] == bo'lak", not xato, f"nomos: {xato[:3]}")

    check("birinchi bo'lak 0 dan boshlanadi", chunks[0][0] == 0,
          f"-> {chunks[0][0]}")
    check("oxirgi bo'lak matn oxirigacha", chunks[-1][1] == len(matn),
          f"-> {chunks[-1][1]} / {len(matn)}")

    tartib = all(chunks[i][0] < chunks[i + 1][0] for i in range(len(chunks) - 1))
    check("bo'laklar TARTIBLI", tartib)

    # Butun matn qoplangan: har keyingi bo'lak oldingisi TUGAMASDAN oldin
    # yoki AYNAN uning oxirida boshlanadi (bo'shliq qolmasin).
    bosh = [c[0] for c in chunks]
    oxir = [c[1] for c in chunks]
    teshik = [(oxir[i], bosh[i + 1]) for i in range(len(chunks) - 1)
              if bosh[i + 1] > oxir[i]]
    check("qoplashda TESHIK yo'q", not teshik, f"teshiklar: {teshik[:3]}")


# =========================================================================
# 2. USTMA-USTLIK
# =========================================================================
def test_ustma_ustlik():
    print("\n[2] Ustma-ustlik — chegarada kesilgan jumla yo'qolmaydi")
    matn = "".join(f"Band {i}. Bu {i}-bandning matni. " for i in range(400))
    chunks = chunk_text(matn)
    check("ko'p bo'lak", len(chunks) >= 3, f"-> {len(chunks)}")

    kichik = [i for i in range(len(chunks) - 1)
              if chunks[i][1] - chunks[i + 1][0] <= 0]
    check("qo'shni bo'laklar USTMA-UST tushadi", not kichik,
          f"ustma-ustliksiz: {kichik[:3]}")

    # Ustma-ustlik `CHUNK_OVERLAP` dan katta bo'lmasligi kerak (chegara
    # tabiiy joyga surilgani uchun undan KICHIK bo'lishi mumkin).
    ortiq = [chunks[i][1] - chunks[i + 1][0] for i in range(len(chunks) - 1)
             if chunks[i][1] - chunks[i + 1][0] > CHUNK_OVERLAP + 5]
    check(f"ustma-ustlik <= {CHUNK_OVERLAP}(+5)", not ortiq, f"-> {ortiq[:3]}")


# =========================================================================
# 3. TABIIY CHEGARA
# =========================================================================
def test_tabiiy_chegara():
    print("\n[3] Kesish TABIIY joyda — so'z o'rtasidan emas")
    xatboshi = "\n\n".join(f"{i}-band. " + ("mazmun " * 30) for i in range(30))
    chunks = chunk_text(xatboshi)

    # Bo'lakning oxirgi belgisi so'z o'rtasi bo'lmasligi kerak: oxiri
    # bo'shliq/tinish belgisi bilan tugashi yoki matn oxiri bo'lishi shart.
    yomon = []
    for a, b, t in chunks[:-1]:
        if t and t[-1].isalnum():
            yomon.append(t[-25:])
    check("bo'lak so'z o'rtasida tugamaydi", not yomon, f"-> {yomon[:2]}")

    # Jadval qatorini o'rtasidan kesmaslik: yagona uzun qator bo'lsa ham
    # funksiya yiqilmasligi kerak.
    bir_qator = "A" * (CHUNK_SIZE * 3)
    ch = chunk_text(bir_qator)
    check("tabiiy chegarasiz matn ham bo'linadi", len(ch) >= 3, f"-> {len(ch)}")
    check("bo'shliqsiz matnda ham ofset to'g'ri",
          all(bir_qator[a:b] == t for a, b, t in ch))


# =========================================================================
# 4. CHEKKA HOLATLAR
# =========================================================================
def test_chekka():
    print("\n[4] Chekka holatlar")
    eq("bo'sh matn -> bo'sh ro'yxat", chunk_text(""), [])
    eq("None emas, bo'sh satr", chunk_text("   \n  "), [])

    qisqa = "Kafolat 24 oy."
    ch = chunk_text(qisqa)
    eq("qisqa matn -> 1 bo'lak", len(ch), 1)
    eq("qisqa matn ofseti", (ch[0][0], ch[0][1]), (0, len(qisqa)))

    # MIN_CHUNK dan qisqa QOLDIQ alohida bo'lak bo'lib qolmasligi kerak
    matn = "x" * (CHUNK_SIZE + 10)
    ch = chunk_text(matn)
    juda_qisqa = [t for _, _, t in ch if len(t) < MIN_CHUNK]
    check(f"MIN_CHUNK({MIN_CHUNK}) dan qisqa bo'lak yo'q", not juda_qisqa,
          f"-> {[len(t) for t in juda_qisqa]}")

    # Cheksiz tsikl bo'lmasligi (himoya shartini tekshiramiz)
    ch = chunk_text("a b " * 5000, size=200, overlap=190)
    check("katta ustma-ustlikda ham tugaydi", len(ch) < 10000, f"-> {len(ch)}")


# =========================================================================
# 5. YORDAMCHILAR
# =========================================================================
def test_yordamchi():
    print("\n[5] content_hash va guess_lang")
    a, b = content_hash("Kafolat"), content_hash("Kafolat")
    eq("bir xil matn -> bir xil hash", a, b)
    check("boshqa matn -> boshqa hash", a != content_hash("Kafolat "))
    eq("hash uzunligi", len(a), 64)

    eq("kirill -> ru", guess_lang("Гарантийный срок составляет 24 месяца всего"), "ru")
    eq("lotin -> uz", guess_lang("Kafolat muddati kamida yigirma tort oy"), "uz")
    eq("qisqa matn -> None", guess_lang("ok"), None)
    eq("bo'sh -> None", guess_lang(""), None)


def main():
    print("=" * 62)
    print(f"BO'LAKKA BO'LISH SINOVI  (size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP})")
    print("=" * 62)
    test_ofsetlar()
    test_ustma_ustlik()
    test_tabiiy_chegara()
    test_chekka()
    test_yordamchi()

    yiqilgan = [n for n, ok in _results if not ok]
    print("\n" + "=" * 62)
    print(f"NATIJA: {len(_results) - len(yiqilgan)}/{len(_results)} o'tdi")
    for n in yiqilgan:
        print(f"  FAIL: {n}")
    print("=" * 62)
    sys.exit(1 if yiqilgan else 0)


if __name__ == "__main__":
    main()
