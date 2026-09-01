#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SINOV: MATN MOSLIGI — SOXTA MUSBATLARGA QARSHI
===============================================

O'LCHANGAN MUAMMO (2026-08-31, 784 ochiq tender, haqiqiy katalog):

    matn mosligi (juftlik)                     328
    shundan KABEL atamali mahsulotdan          328  (100.0 foiz)
    shundan YALANG'OCH `Кабель` kalit so'zidan 325  (99.1 foiz)

Ya'ni matn mosligining deyarli hammasi BITTA keng atamadan kelardi.
`Кабель` 13 tenderga mos kelib, 4 tasi SOXTA edi — precision 0.692.

YORLIQ HAQIQIY DALILDAN: tenderda 27.3x (kabel/sim) loti bormi.
Bu davlat portali bergan rasmiy tasnif — sintetik emas.

QUYIDAGI MISOLLAR HAQIQIY TENDERLARDAN olingan (nomlari ommaviy
xarid e'lonlari). Ular O'ZGARMAS fikstura: korpus o'zgarsa ham
qoida shu misollarda ishlashi kerak.

`Кабель` QORA RO'YXATGA OLINMAGAN va bu sinov shuni ham tekshiradi.

Ishga tushirish:
    .venv\\Scripts\\python.exe _tests\\matn_moslik_test.py
    .venv\\Scripts\\python.exe _tests\\matn_moslik_test.py --offline
"""
from __future__ import annotations

import argparse
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import konsol  # noqa: E402
import rejim  # noqa: E402

konsol.sozla()

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))

_natija = []


def check(nom, ok, tafsilot=""):
    _natija.append((nom, ok, tafsilot))
    print(f"  [{'PASS' if ok else 'FAIL'}] {nom}" + (f" -- {tafsilot}" if tafsilot else ""))
    return ok


def bolim(t):
    print(f"\n--- {t} ---")


#: HAQIQIY holatlar (2026-08-31 o'lchovidan). `tovar_blob` — TOVAR
#: lotlari nomi; `goods_blob` — hamma lot (eski xulq uchun).
KABEL = {"name": "Кабель", "keywords": ["Кабель"], "codes": []}

SOXTA_HOLATLAR = [
    # 20000508561 — kabel YOTQIZISH xizmati, tovar loti YO'Q
    {"id": 20000508561,
     "name": "“O‘zsanoatqurilishbank” ATB Bosh ofis bilan AT markazini "
             "to‘g‘ridan-to‘g‘ri ulash",
     "goods_blob": "Услуга по прокладке волоконно-оптического кабеля связи",
     "tovar_blob": ""},
    # 20000509689 — so'z faqat TENDER SARLAVHASIDA
    {"id": 20000509689,
     "name": "Выполнение проекта переноса кабельной линии электропередачи "
             "КЛ-35 кВ",
     "goods_blob": "Строительно-монтажные работы",
     "tovar_blob": ""},
    # 20000509350 — tarkibiy kabel tizimi QURISH xizmati
    {"id": 20000509350,
     "name": "Xalq bankiga tegishli binoga tarkibiy kabel tizimini qurish "
             "xizmatlari",
     "goods_blob": "Услуга по широкополосному доступу к информационно-"
                   "коммуникационной сети",
     "tovar_blob": ""},
    # 20000508552 — izolyatsiya SINOVI xizmati
    {"id": 20000508552,
     "name": "Ustyurt GQChB obyektlaridagi elektr uskunalarini profilaktik "
             "sinovdan o‘tkazish",
     "goods_blob": "Услуга по профилактическому осмотру сопротивления "
                   "изоляции силовых кабелей",
     "tovar_blob": ""},
]

HAQIQIY_HOLATLAR = [
    # 20000508911 — tarmoq kabeli (TOVAR)
    {"id": 20000508911, "name": "Tarmoq jihozlari xaridi",
     "goods_blob": "Сетевой кабель Коммутатор",
     "tovar_blob": "Сетевой кабель Коммутатор"},
    # 8368020 — kuchlanish kabeli (TOVAR)
    {"id": 8368020, "name": "Elektr jihozlari",
     "goods_blob": "Кабели силовые с медной жилой на напряжение более 1 кВ",
     "tovar_blob": "Кабели силовые с медной жилой на напряжение более 1 кВ"},
    # 20000509676 — optik kabel (TOVAR)
    {"id": 20000509676, "name": "Aloqa jihozlari",
     "goods_blob": "Кабель оптический Муфта",
     "tovar_blob": "Кабель оптический Муфта"},
]


# =====================================================================
def test_soxta_musbat():
    bolim("1. SOXTA MUSBATLAR to'siladi (haqiqiy holatlar)")
    from api import matching
    for h in SOXTA_HOLATLAR:
        r = matching.product_matches(h, KABEL, allow_text=True)
        check(f"{h['id']}: `Кабель` MOS KELMAYDI", r is None,
              f"qaytdi={r!r} — {h['goods_blob'][:44]}")


def test_haqiqiy_musbat():
    bolim("2. HAQIQIY mosliklar SAQLANADI (recall yo'qolmasin)")
    from api import matching
    for h in HAQIQIY_HOLATLAR:
        r = matching.product_matches(h, KABEL, allow_text=True)
        check(f"{h['id']}: `Кабель` MOS KELADI", r == "nom",
              f"qaytdi={r!r}")


def test_qora_royxat_yoq():
    bolim("3. `Кабель` QORA RO'YXATDA EMAS")
    src = io.open(os.path.join(ROOT, "api", "matching.py"),
                  encoding="utf-8").read()
    q = io.open(os.path.join(ROOT, "api", "queries.py"), encoding="utf-8").read()
    # Atama nomi FAQAT izohda uchrashi mumkin (sabab tushuntirilgan),
    # LEKIN u shartda ishlatilmasligi kerak.
    for fayl, matn in (("matching.py", src), ("queries.py", q)):
        kod = "\n".join(l for l in matn.splitlines()
                        if not l.strip().startswith(("#", "--")))
        check(f"{fayl}: `кабел` kodda (izohdan tashqari) YO'Q",
              "кабел" not in kod.lower() and "kabel" not in kod.lower(),
              "")
    # Boshqa keng atamalar ham to'silmagan bo'lishi kerak.
    from api import matching
    tovar = {"id": 1, "name": "x", "goods_blob": "Кабель силовой",
             "tovar_blob": "Кабель силовой"}
    check("`Кабель` TOVAR lotida hali ham mos keladi",
          matching.product_matches(tovar, KABEL, allow_text=True) == "nom")


def test_kod_ustunligi():
    bolim("4. KOD mosligi matn ustidan USTUN (o'zgarmadi)")
    from api import matching
    kodli = {"name": "Kabel mahsuloti", "keywords": ["Кабель"],
             "codes": ["27.32"]}
    # Kod mos kelsa -> 'kod'
    t1 = {"id": 1, "name": "x", "good_codes": ["27.32.13.000-00001"],
          "goods_blob": "Кабель", "tovar_blob": "Кабель"}
    check("kod mos -> 'kod'", matching.product_matches(t1, kodli) == "kod")
    # Kodi BOR mahsulot matn yo'liga UMUMAN tushmaydi
    t2 = {"id": 2, "name": "x", "good_codes": ["99.99.99.000-00001"],
          "goods_blob": "Кабель", "tovar_blob": "Кабель"}
    check("kodi BOR mahsulot matnga tushmaydi",
          matching.product_matches(t2, kodli) is None)
    # `allow_text=False` — standart "Mos tenderlar" yo'li
    check("`allow_text=False` matnni rad etadi",
          matching.product_matches(
              {"id": 3, "name": "x", "goods_blob": "Кабель",
               "tovar_blob": "Кабель"},
              KABEL, allow_text=False) is None)


def test_orqaga_moslik():
    bolim("5. Orqaga moslik")
    from api import matching
    # `tovar_blob` KALITI YO'Q -> eski xulq (eski chaqiruvchi buzilmasin)
    eski = {"id": 1, "name": "Кабель liniyasi", "goods_blob": "Услуга"}
    check("`tovar_blob` kaliti yo'q -> ESKI xulq (mos keladi)",
          matching.product_matches(eski, KABEL, allow_text=True) == "nom")
    # `tovar_blob` BO'SH -> moslik yo'q (hamma lot xizmat)
    bosh = {"id": 2, "name": "Кабель liniyasi", "goods_blob": "Услуга",
            "tovar_blob": ""}
    check("`tovar_blob` BO'SH -> moslik YO'Q",
          matching.product_matches(bosh, KABEL, allow_text=True) is None)


# =====================================================================
def test_baza(db):
    bolim("6. `lot_tovarmi()` — haqiqiy ma'lumotda")
    bor = db.scalar("SELECT to_regprocedure('lot_tovarmi(text,text)') IS NOT NULL")
    if not bor:
        check("`schema_patch_xizmat.sql` qo'llangan", False)
        return
    # Xizmat nomi -> tovar EMAS
    check("`Услуга по ...` -> tovar EMAS",
          db.scalar("SELECT NOT lot_tovarmi('27.32.13.000-00001', "
                    "'Услуга по прокладке кабеля')"))
    # NOMA'LUM kod -> tovar EMAS (jimgina musbatga aylanmaydi)
    check("lug'atda YO'Q kod -> tovar EMAS (NOMA'LUM)",
          db.scalar("SELECT NOT lot_tovarmi('99.99.99.999-99999', 'Кабель')"))
    # Haqiqiy tovar loti -> tovar
    r = db.query_one("""SELECT g.good_code, g.name
                          FROM tender_good g
                         WHERE g.good_code LIKE '27.3%%'
                           AND g.name NOT ILIKE 'Услуга%%' LIMIT 1""")
    if r:
        check("haqiqiy kabel loti -> TOVAR",
              db.scalar("SELECT lot_tovarmi(%(k)s, %(n)s)",
                        {"k": r["good_code"], "n": r["name"]}),
              (r["name"] or "")[:40])

    bolim("7. Bo'lim kesimida tovar/xizmat ajratilgan")
    rows = db.query("SELECT * FROM v_lot_tovar_xizmat WHERE lot > 200 "
                    "ORDER BY bolim")
    check("ko'rinish qator qaytardi", len(rows) >= 5, f"{len(rows)} ta")
    ish = {r["bolim"]: r for r in rows}
    # ISHLAB CHIQARISH bo'limlari asosan TOVAR bo'lishi kerak.
    for b in ("26", "27", "28"):
        if b in ish:
            r = ish[b]
            ulush = 100.0 * r["tovar"] / max(r["lot"], 1)
            check(f"bo'lim {b} asosan TOVAR (>90 foiz, hozir {ulush:.0f})",
                  ulush > 90, f"{r['tovar']}/{r['lot']}")
    # XIZMAT bo'limlari asosan XIZMAT bo'lishi kerak.
    for b in ("49", "66", "71"):
        if b in ish:
            r = ish[b]
            ulush = 100.0 * r["xizmat"] / max(r["lot"], 1)
            check(f"bo'lim {b} asosan XIZMAT (>80 foiz, hozir {ulush:.0f})",
                  ulush > 80, f"{r['xizmat']}/{r['lot']}")

    bolim("8. `tovar_blob` so'rovda bor va xizmatni CHIQARIB tashlaydi")
    from api import queries
    sql = queries.match_candidates_sql(
        "WHERE t.status='open' AND (t.close_at IS NULL OR t.close_at>now())", 60)
    rows = db.query(sql, {})
    check("nomzod so'rovi ishladi", len(rows) > 0, f"{len(rows)} ta")
    check("`tovar_blob` maydoni bor", "tovar_blob" in (rows[0] if rows else {}))
    # `goods_blob` BILAN SOLISHTIRISH ARZON O'TARDI: unda AI matni
    # ham bor, ya'ni `tovar_blob` HAR DOIM qisqaroq chiqardi va
    # tekshiruv hech narsa o'lchamasdi (birinchi urinishda 60/60 —
    # aynan shu bo'ldi).
    #
    # Endi TO'G'RIDAN-TO'G'RI lot nomlari bilan solishtiriladi:
    # xizmat loti bor tenderda `tovar_blob` UNDA yo'q bo'lishi kerak.
    xizmatli = db.query("""
        SELECT t.id,
               (SELECT string_agg(DISTINCT g.name, ' ') FROM tender_good g
                 WHERE g.tender_id=t.id
                   AND NOT lot_tovarmi(g.good_code, g.name)) AS xizmat_nom
          FROM tender t
         WHERE t.status='open' AND (t.close_at IS NULL OR t.close_at>now())
           AND EXISTS (SELECT 1 FROM tender_good g2 WHERE g2.tender_id=t.id
                        AND NOT lot_tovarmi(g2.good_code, g2.name))
         LIMIT 20""")
    check("xizmat loti bor ochiq tenderlar bor", len(xizmatli) > 0,
          f"{len(xizmatli)} ta")
    kartochka = {r["id"]: r for r in rows}
    tekshirildi = chiqarildi = 0
    for x in xizmatli:
        k = kartochka.get(x["id"])
        if not k or not x["xizmat_nom"]:
            continue
        tekshirildi += 1
        # Xizmat loti nomining birinchi so'zi `tovar_blob` da
        # BO'LMASLIGI kerak (u faqat o'sha lotda uchrasa).
        if (x["xizmat_nom"] or "")[:30] not in (k.get("tovar_blob") or ""):
            chiqarildi += 1
    if tekshirildi:
        check("xizmat loti nomi `tovar_blob` ga TUSHMAGAN",
              chiqarildi == tekshirildi, f"{chiqarildi}/{tekshirildi}")
    else:
        print("        [i] solishtirish uchun umumiy tender topilmadi")

    # AI SINONIM YO'LI: `tovar_blob` da AI matni YO'Q va bu ATAYLAB.
    # AI xulosasi BUTUN tenderni tasvirlaydi (xizmatlar bilan), ya'ni
    # uni qo'shish aynan to'silgan soxta yo'lni qayta ochardi.
    # O'lchandi (2026-08-31): `ai_analysis` da summary_v1 = 0 qator,
    # ya'ni bu yo'l bugun UMUMAN faol emas edi.
    ai = db.scalar("SELECT count(*) FROM ai_analysis WHERE kind='summary_v1'")
    print(f"        [i] AI sinonim yo'li: ai_analysis summary_v1 = {ai} qator")
    # FOIZ BELGISI SQL izohida bo'lmasligi kerak — psycopg2 uni
    # platsderjatel deb o'qiydi. Bu HAQIQATAN sodir bo'ldi.
    check("nomzod SQL izohlarida foiz belgisi YO'Q",
          "%" not in "\n".join(l for l in sql.splitlines()
                               if l.strip().startswith("--")))


# =====================================================================
def main():
    ap = argparse.ArgumentParser(description="Matn mosligi sinovi")
    rejim.bayroqlar(ap)
    args = rejim.moslash(ap.parse_args())

    print("=" * 70)
    print("SINOV: MATN MOSLIGI — SOXTA MUSBATLARGA QARSHI")
    print("=" * 70)

    test_soxta_musbat()
    test_haqiqiy_musbat()
    test_qora_royxat_yoq()
    test_kod_ustunligi()
    test_orqaga_moslik()

    if args.bazasiz or not os.environ.get("XT_DB_DSN"):
        print("\n[i] Bazali tekshiruvlar o'tkazib yuborildi.")
    else:
        from api import db
        try:
            db.init_pool()
            test_baza(db)
        except Exception as e:                                # noqa: BLE001
            check("bazali tekshiruv", False, str(e)[:100])

    otdi = sum(1 for _n, ok, _d in _natija if ok)
    jami = len(_natija)
    print("\n" + "=" * 70)
    for n, ok, d in _natija:
        if not ok:
            print(f"  YIQILDI: {n}" + (f" -- {d}" if d else ""))
    print(f"NATIJA: {otdi}/{jami} o'tdi")
    print("=" * 70)
    sys.exit(0 if otdi == jami else 1)


if __name__ == "__main__":
    main()
