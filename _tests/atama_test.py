# -*- coding: utf-8 -*-
"""SINOV: `api/atama.py` — uch yozuv bitta manbadan.

Bu sinov UCHTA HAQIQIY XATONI qaytmasligi uchun yozilgan. Har biri
alohida joyda chiqqan, lekin bir sinfdan:

  1. §16.28 — leksik qidiruv tillararo 0/8 berardi: "kafolat" ni
     "кафолат" ga o'girish TARJIMA emas, hujjatda "гарантийный".
  2. §16.29 — eval baholovchisi "duch kelinmadi" ni tanimadi va
     TO'G'RI javobni yiqilgan deb sanadi.
  3. §16.33 — `.doc` sifat mezonida faqat kirill kalit so'zlar bor
     edi, lotincha o'qilgan 4 fayl "yiqildi" deb ko'rsatildi (64%
     o'rniga haqiqiy 92%).

Modelga chiqmaydi, bazaga tegmaydi, PUL SARFLAMAYDI.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# KONSOL KODLASHI — Windows kod sahifasidan MUSTAQIL UTF-8.
#
# Chiqish QUVUR yoki FAYLGA yo'naltirilganda (ya'ni CI da) Python
# `locale.getpreferredencoding()` ni oladi — bu mashinada `cp1251`.
# O'zbek kirill (`ҳ`, `қ`, `ў`) va to'liq kenglikdagi belgilar
# (`）`) u yerda YO'Q va chop etish `UnicodeEncodeError` bilan
# BUTUN TO'PLAMNI o'ldiradi. `import_test` aynan shu sababdan
# 143 ta tekshiruvni bajarmasdan yiqilardi. Tafsilot: _tests/konsol.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import konsol  # noqa: E402

konsol.sozla()

from api import atama                                   # noqa: E402

PASS = FAIL = 0


def check(nom: str, shart: bool, izoh: str = "") -> None:
    global PASS, FAIL
    if shart:
        PASS += 1
        print(f"  OK   {nom}")
    else:
        FAIL += 1
        print(f"  XATO {nom}" + (f"\n       {izoh}" if izoh else ""))


def section(t: str) -> None:
    print(f"\n=== {t} ===")


# ---------------------------------------------------------------------
section("1. UCH YOZUV — har uchalasi ham qamralganmi")
# ---------------------------------------------------------------------
# XATO 1 (§16.28) shu yerda tutiladi: o'zbekcha so'z RUSCHA ekvivalentga
# ham bog'lanishi SHART, aks holda ruscha hujjat topilmaydi.
UCHLIK = [
    ("kafolat", "кафолат", "гарант"),
    ("muddat", "муддат", "срок"),
    ("sertifikat", "сертификат", "сертификат"),
    ("shartnoma", "шартнома", "договор"),
    ("yetkazib", "етказиб", "поставк"),
]
for lot, kir, rus in UCHLIK:
    v = atama.variantlar(lot)
    check(f"{lot!r} -> kirill shakli", any(kir[:5] in x for x in v), str(v))
    check(f"{lot!r} -> ruscha ekvivalent", any(rus in x for x in v), str(v))
    # Teskari yo'nalish ham ishlashi SHART: ruscha savol, o'zbek hujjat.
    vr = atama.variantlar(rus)
    check(f"{rus!r} -> o'zbekcha ekvivalent",
          any(lot[:5] in x for x in vr), str(vr))

# Atama bo'lmagan so'z guruhsiz qoladi — lekin yozuv variantlari qoladi
v = atama.variantlar("nasos")
check("atama emas: yozuv variantlari saqlanadi", "насос" in v, str(v))
check("atama emas: begona guruh qo'shilmaydi", len(v) <= 3, str(v))


# ---------------------------------------------------------------------
section("2. tsquery guruhi — prefiks bilan")
# ---------------------------------------------------------------------
g = atama.tsquery_guruh("kafolat")
check("prefiks `:*` bilan chiqadi", any(x.endswith(":*") for x in g), str(g))
check("ruscha prefiks bor", any(x.startswith("гарант") for x in g), str(g))
check("so'zning o'zi birinchi", g[0] == "kafolat", str(g))

# `to_tsquery` uchun xavfsiz belgilar
yomon = [x for x in atama.tsquery_guruh("kafolat muddati")
         if any(ch in x for ch in "&|!()<>")]
check("tsquery uchun xavfli belgi yo'q", not yomon, str(yomon))


# ---------------------------------------------------------------------
section("3. QISQA PREFIKS bo'lmasin (shovqin manbai)")
# ---------------------------------------------------------------------
# "ой:*" -> "ойлик", "ойна" — birlik so'zlari ATAYLAB kiritilmagan.
qisqa = [(nom, p) for nom, gr in atama.GURUH_PREFIKS.items()
         for p in gr if len(p) < 3]
check("3 belgidan qisqa prefiks yo'q", not qisqa, str(qisqa))
for birlik in ("oy", "kun", "yil", "ой", "кун", "йил"):
    check(f"birlik so'zi {birlik!r} guruhga tushmaydi",
          not atama.guruh(birlik), str(atama.guruh(birlik)))


# ---------------------------------------------------------------------
section("4. TOPILMADI iboralari — §16.29 xatosi")
# ---------------------------------------------------------------------
n = atama.naqsh(atama.TOPILMADI)
for ibora in ("hujjatlarda topilmadi", "duch kelinmadi", "ko'rsatilmagan",
              "aniqlanmadi", "mavjud emas", "uchramadi",
              "не найден", "отсутствует", "ma'lumot berilmagan"):
    check(f"tanidi: {ibora!r}", bool(n.search(ibora)))
check("oddiy javobni NOTO'G'RI belgilamaydi",
      not n.search("Kafolat muddati 12 oyni tashkil etadi."))


# ---------------------------------------------------------------------
section("5. XARID NAQSHI — §16.33 xatosi")
# ---------------------------------------------------------------------
# Lotin ham, kirill ham, rus ham TOPILISHI shart. Birinchi o'lchovda
# faqat kirill bor edi va lotincha hujjatlar "yiqildi" deb sanaldi.
x = atama.xarid_naqshi()
for matn, til in [
    ("XIZMAT KO'RSATISHGA OID SHARTNOMA", "lotin"),
    ("ХИЗМАТ КЎРСАТИШ ШАРТНОМАСИ", "kirill"),
    ("ДОГОВОР на оказание услуг", "rus"),
    ("Kafolat muddati 12 oy", "lotin"),
    ("Гарантийный срок 24 месяца", "rus"),
]:
    check(f"{til}: {matn[:30]!r}", bool(x.search(matn)))
check("aloqasiz matnda mos kelmaydi",
      not x.search("Bugun ob-havo issiq va quyoshli"))


# ---------------------------------------------------------------------
section("6. Manba BITTA — takroriy ro'yxat qolmaganmi")
# ---------------------------------------------------------------------
import io                                                # noqa: E402
import re as _re                                         # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for yol, nom in [("api/ai_chat.py", "ai_chat"),
                 ("_tests/ai_eval/run_eval.py", "run_eval")]:
    matn = io.open(os.path.join(ROOT, yol), encoding="utf-8").read()
    check(f"{nom}: TERM_GROUPS ta'rifi yo'q",
          not _re.search(r"^TERM_GROUPS\s*[:=]", matn, _re.M))
    check(f"{nom}: 'гарант' ro'yxati qattiq yozilmagan",
          "гарант" not in matn or "atama" in matn,
          "atama modulidan o'qilsin")


# =====================================================================
# KANONIK SHAKL — `atama.normal()`
#
# NEGA QULFLANADI: bu `catalog_code_rule` ning KALITI. Buzilsa qoida
# jadvali uch-alifbo muammosini MA'LUMOT darajasida takrorlaydi —
# "Коммутаторы" va "Kommutatorlar" ikki alohida qoida bo'lib qolardi
# va o'zbek-lotin katalog kelganda hammasi qaytadan qo'lda kiritilardi.
# =====================================================================
print("\n[normal] kanonik shakl")

_TENG = [
    ("Коммутаторы", "Kommutatorlar"),      # ru ko'plik <-> uz ko'plik
    ("Коммутаторы", "kommutator"),         # ko'plik <-> birlik
    ("КОММУТАТОР", "kommutator"),          # registr
    ("IP камеры", "IP kameralar"),         # ko'p so'zli
    ("камера", "kamera"),                  # alifbo
    ("Мониторы", "monitorlar"),
    ("Мониторы", "монитор"),
    ("Датчики", "datchik"),
    ("Терминалы", "terminallar"),
]
for _a, _b in _TENG:
    check("normal: %r == %r" % (_a, _b),
          atama.normal(_a) == atama.normal(_b),
          "%r != %r" % (atama.normal(_a), atama.normal(_b)))

# `monitor`/`monitoring` juftligi ENG MUHIMI: aynan u soxta moslik
# manbai bo'lgan ("Bemor monitori" -> "Axborot xavfsizligi
# monitoringi"). Qo'shimchalar ro'yxatiga `ing` qo'shilsa SHU SINOV
# yiqiladi — bu ataylab.
#
# BU RO'YXAT TO'LIQ EMAS va to'liq bo'lishi ham mumkin emas.
# `atama._QOSHIMCHALAR` dan `ing` ni chiqarish — QO'LDA tanlangan
# istisno, ya'ni `TERM_GROUPS` bilan bir sinf: boshqa soha kelganda
# yangi soxta juftlik chiqadi ("прокат"/"прокатка",
# "montaj"/"montajchi" kabi).
#
# STANDART: yangi soxta juftlik topilganda —
#   1. uni SHU ro'yxatga qo'shing (sinov darhol yiqiladi);
#   2. `atama._QOSHIMCHALAR` ni shunga qarab tuzating;
#   3. sinov yashillansin.
# Ro'yxat o'sishi KUTILADI, bu nuqson emas.
_FARQ = [
    ("monitor", "monitoring"),
    ("kamera", "kabel"),
    ("stol", "stolb"),                     # "stol" c "столб" (ustun)
    ("коммутатор", "компьютер"),
    ("камера", "камин"),
    ("nasos", "naushnik"),
    ("dori", "doska"),
    ("server", "servis"),
]
for _a, _b in _FARQ:
    check("normal: %r != %r" % (_a, _b),
          atama.normal(_a) != atama.normal(_b),
          "ikkalasi ham %r" % (atama.normal(_a),))

check("normal: qisqa so'z butun qoladi", atama.normal("dori") == "dori",
      atama.normal("dori"))
check("normal: bo'sh kirish -> bo'sh", atama.normal("") == "")
check("normal: None -> bo'sh", atama.normal(None) == "")

# Kanonik shaklni QAYTA normallash o'zgartirmasin — aks holda kalit
# qayerda hisoblanganiga qarab farq qilardi.
for _s in ["Коммутаторы", "IP камеры", "monitoring", "dori vositalari"]:
    check("normal idempotent: %r" % (_s,),
          atama.normal(atama.normal(_s)) == atama.normal(_s),
          "%r -> %r" % (atama.normal(_s), atama.normal(atama.normal(_s))))


print("\n" + "=" * 58)
print(f"NATIJA: {PASS}/{PASS + FAIL} o'tdi")
sys.exit(1 if FAIL else 0)
