#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SINOV: KATALOG KODLASH — PRECISION QO'RIQCHISI
===============================================

Bu to'plam qamrovni EMAS, ANIQLIKNI qo'riqlaydi. Kodlash qamrovini
oshirishning eng oson yo'li chegarani pasaytirish, va u JIMGINA
ishlaydi: raqam o'sadi, xato mos kelishlar esa faqat broker
"bu tender menga umuman mos emas" deganda bilinadi.

NIMA TEKSHIRILADI VA NEGA

  1. CHEGARALAR O'ZGARMAGAN. `MIN_EVIDENCE` va `MIN_SHARE` qattiq
     yozilgan: ular pasaysa sinov yiqiladi va o'zgarish ONGLI
     bo'lishga majbur qiladi.

  2. MA'LUM SOXTA MOSLIKLAR to'silgan:
     - `monitor` `monitoring` ichidan topilmaydi (qism-so'z);
     - dalil ikkitadan kam bo'lsa kod BERILMAYDI;
     - ikki oila teng bo'lsa kod BERILMAYDI (`noaniq`);
     - nomdan ma'noli so'z chiqmasa kod BERILMAYDI (`tokensiz`).

  3. ANIQLIK HAQIQIY INSON YORLIG'IGA qarshi o'lchanadi.
     960 ta keng kodni ODAM bergan — bu sintetik emas, haqiqiy
     yorliq. Avtomatik taklif ular bilan solishtiriladi.

  4. SABAB LUG'ATI Python va SQL da BIR XIL.

Ishga tushirish:
    .venv\\Scripts\\python.exe _tests\\catalog_kod_test.py
    .venv\\Scripts\\python.exe _tests\\catalog_kod_test.py --offline
"""
from __future__ import annotations

import argparse
import io
import os
import re
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


# =====================================================================
def test_chegaralar():
    bolim("1. Chegaralar O'ZGARMAGAN (precision qo'riqchisi)")
    from api import catalog_auto as C
    # BU RAQAMLAR ATAYLAB QATTIQ YOZILGAN. Ular pasaysa sinov
    # yiqiladi — qamrovni chegara pasaytirib oshirish JIMGINA
    # sodir bo'lmasin.
    check("`MIN_EVIDENCE` = 2", C.MIN_EVIDENCE == 2, str(C.MIN_EVIDENCE))
    check("`MIN_SHARE` = 0.75", abs(C.MIN_SHARE - 0.75) < 1e-9, str(C.MIN_SHARE))
    check("`MAX_TOKENS` = 4", C.MAX_TOKENS == 4, str(C.MAX_TOKENS))
    check("kuchsiz band chegarasi 0.80", abs(C.KUCHSIZ_ISHONCH - 0.80) < 1e-9)
    check("kuchsiz band dalili 4", C.KUCHSIZ_DALIL == 4)


def test_lugat():
    bolim("2. Sabab lug'ati — Python va SQL BIR XIL")
    from api import catalog_auto as C
    sql = io.open(os.path.join(ROOT, "schema_patch_kod_tahlil.sql"),
                  encoding="utf-8").read()
    blok = sql[sql.index("catalog_kod_tahlil_sabab_chk"):]
    blok = blok[:blok.index("END IF")]
    sqlda = set(re.findall(r"'([a-z_]+)'", blok)) - {"catalog_kod_tahlil_sabab_chk"}
    check("sabablar MOS", sqlda == set(C.SABABLAR),
          f"sql={sorted(sqlda)} py={sorted(C.SABABLAR)}")
    check("`kod` lug'atda bor", "kod" in C.SABABLAR)
    # "Kod yo'q" YAGONA chelak bo'lmasligi kerak — bu tuzatishning
    # asosiy maqsadi edi.
    check("kodsizlik sabablari BIR NECHTA", len(C.SABABLAR) >= 5,
          str(len(C.SABABLAR)))


def test_tokenlar():
    bolim("3. Tokenlash")
    from api import catalog_auto as C
    check("stop so'zlar tushiriladi",
          C._tokens({"name": "mahsulot uchun va bilan"}) == [],
          str(C._tokens({"name": "mahsulot uchun va bilan"})))
    check("qisqa so'z (<3) tushiriladi",
          "ab" not in C._tokens({"name": "ab kabel"}))
    t = C._tokens({"name": "kabel elektr quvvat"})
    check("uzun so'z BIRINCHI (ko'proq ma'no tashiydi)",
          t == sorted(t, key=len, reverse=True), str(t))
    check("token soni MAX_TOKENS dan oshmaydi",
          len(C._tokens({"name": "bir ikki uch tort besh olti yetti"})) <= C.MAX_TOKENS)
    # Model/SKU nomlari — ma'noli so'z bermaydi va bu KUTILGAN.
    for nom in ("LC-LC", "SC-LC", "DS-K1T341"):
        toks = C._tokens({"name": nom})
        check(f"model nomi `{nom}` -> ma'noli token kam",
              len(toks) <= 1, str(toks))


def test_manba_qism_soz():
    bolim("4. MA'LUM SOXTA MOSLIK: qism-so'z")
    src = io.open(os.path.join(ROOT, "api", "catalog_auto.py"),
                  encoding="utf-8").read()
    # `monitor` `monitoring` ichidan topilmasligi kerak. Kod buni
    # kanonik SO'Z tekshiruvi bilan hal qiladi.
    check("kanonik so'z bo'yicha yakuniy tekshiruv bor",
          "atama.normal(row[\"name\"]" in src or "set(atama.normal(" in src)
    check("prefiks toleransi CHEKLANGAN (<=2 harf)",
          "len(word) - len(base) <= 2" in src)
    check("sabab `sozlar_mos_emas` mavjud", "sozlar_mos_emas" in src)


def test_qolla_qorovuli():
    bolim("5. Kuchsiz dalil bandi avtomatik QO'LLANMAYDI")
    src = io.open(os.path.join(ROOT, "api", "catalog_auto.py"),
                  encoding="utf-8").read()
    # IKKALA yo'l ham (CRUD va ommaviy) shu yagona bayroqni o'qishi
    # kerak — aks holda bitta yo'l qattiq, ikkinchisi yumshoq bo'lardi.
    check("`classify_product` bandni hurmat qiladi",
          'natija.get("kuchsiz_dalil")' in src)
    check("bandda `review` holati qaytadi", '"status": "review"' in src)
    cli = io.open(os.path.join(ROOT, "catalog_kodla.py"), encoding="utf-8").read()
    check("ommaviy qo'llash bandni chetlab o'tmaydi",
          "NOT t.kuchsiz_dalil" in cli)
    check("ommaviy qo'llash `classify_product` ni chaqiradi "
          "(mantiq takrorlanmaydi)", "classify_product(" in cli)
    check("standart QURUQ emas, TAHLIL", "--tahlil" in cli and "--qolla" in cli)


# =====================================================================
def test_baza(db):
    bolim("6. Tahlil bazada — sabab taqsimoti")
    from api import auth
    cid = auth.sole_company_id()
    rows = db.query("SELECT sabab, soni FROM v_catalog_kod_sabab "
                    "WHERE company_id=%(c)s ORDER BY soni DESC", {"c": cid})
    if not rows:
        check("tahlil yurgizilgan", False, "catalog_kodla.py --tahlil")
        return
    jami = sum(r["soni"] for r in rows)
    mahsulot = db.scalar("SELECT count(*) FROM catalog_product "
                         "WHERE company_id=%(c)s", {"c": cid})
    # SABABLAR JAMIGA TENG BO'LISHI SHART. Teng bo'lmasa — tahlildan
    # tashqarida qolgan mahsulot bor va u KO'RINMAY qolardi.
    check("sabablar jami mahsulot soniga TENG", jami == mahsulot,
          f"{jami} vs {mahsulot}")
    for r in rows:
        print(f"        {r['sabab']:<18}{r['soni']:>6}")

    bolim("7. ANIQLIK — haqiqiy inson yorlig'iga qarshi")
    # 960 ta keng kodni ODAM bergan. Bu sintetik yorliq EMAS.
    #
    # `v_catalog_code_active` EMAS, `catalog_product_code` o'qiladi:
    # aniq kod qo'llangach keng kod FAOLSIZLANTIRILADI va faol
    # ko'rinishdan chiqadi. Yorliq esa YO'QOLMAYDI — qator qoladi
    # (`tasdiqlandi=NULL`). Faol ko'rinishga tayanish yorliqni
    # o'z harakatimiz bilan yo'q qilardi va sinov jimgina
    # ma'nosiz bo'lib qolardi (bu HAQIQATAN sodir bo'ldi:
    # 383 juftlik 4 taga tushdi).
    r = db.query_one("""
        SELECT count(*) AS jami,
               count(*) FILTER (WHERE left(t.taklif_code,2)=left(v.code,2)) AS div_mos,
               count(*) FILTER (WHERE left(t.taklif_code,5)=v.code) AS toliq_mos
          FROM catalog_kod_tahlil t
          JOIN catalog_product_code v
            ON v.product_id=t.product_id AND v.company_id=t.company_id
           AND length(v.code)=5 AND v.tasdiqlagan <> 'tizim:auto'
         WHERE t.company_id=%(c)s AND t.sabab='kod'
    """, {"c": cid}) or {}
    jami = r.get("jami") or 0
    if jami < 20:
        check("solishtirish uchun yetarli juftlik", False, f"{jami} ta")
        return
    div = 100.0 * (r["div_mos"] or 0) / jami
    tol = 100.0 * (r["toliq_mos"] or 0) / jami
    # CHEGARA o'lchangan qiymatdan PAST qo'yilgan: oddiy siljish
    # sinovni yiqitmasin, HAQIQIY regressiya esa yiqitsin.
    # O'lchangan (2026-08-31): division 100.0%, to'liq 99.7%.
    check(f"division mosligi >= 98% ({div:.1f}%)", div >= 98.0,
          f"{r['div_mos']}/{jami}")
    check(f"to'liq 5-belgi mosligi >= 95% ({tol:.1f}%)", tol >= 95.0,
          f"{r['toliq_mos']}/{jami}")

    bolim("8. Kuchsiz band ajratilgan")
    s = db.query_one("SELECT * FROM v_catalog_kod_sifat WHERE company_id=%(c)s",
                     {"c": cid}) or {}
    check("taklif = avtomatik + navbatga",
          (s.get("taklif") or 0) == (s.get("avtomatik") or 0) + (s.get("navbatga") or 0),
          f"{s.get('taklif')} = {s.get('avtomatik')} + {s.get('navbatga')}")
    check("kuchsiz band BO'SH EMAS (ajratish ishlayapti)",
          (s.get("navbatga") or 0) > 0, str(s.get("navbatga")))
    # Kuchsiz band KICHIK bo'lishi kerak — u katta bo'lsa chegara
    # noto'g'ri joyda demakdir.
    ulush = 100.0 * (s.get("navbatga") or 0) / max(s.get("taklif") or 1, 1)
    check(f"kuchsiz band kichik (<20%, hozir {ulush:.1f}%)", ulush < 20.0)

    bolim("9. Baza cheklovlari")
    def rad(sql, p):
        try:
            db.execute_returning(sql, p)
            return False
        except Exception:                                     # noqa: BLE001
            return True
    pid = db.scalar("SELECT id FROM catalog_product WHERE company_id=%(c)s "
                    "ORDER BY id DESC LIMIT 1", {"c": cid})
    check("`kod` sababi DALILSIZ yozilmaydi",
          rad("INSERT INTO catalog_kod_tahlil(company_id,product_id,sabab,"
              "taklif_code,ishonch,dalil,jami) VALUES(%(c)s,%(p)s,'kod',"
              "NULL,NULL,0,0)", {"c": cid, "p": pid}))
    check("noma'lum sabab rad etiladi",
          rad("INSERT INTO catalog_kod_tahlil(company_id,product_id,sabab) "
              "VALUES(%(c)s,%(p)s,'bilmadim')", {"c": cid, "p": pid}))
    check("ishonch 1 dan katta bo'la olmaydi",
          rad("INSERT INTO catalog_kod_tahlil(company_id,product_id,sabab,"
              "ishonch) VALUES(%(c)s,%(p)s,'noaniq',1.5)",
              {"c": cid, "p": pid}))

    bolim("10. Qamrov ANIQ va KENG kodni ajratadi")
    q = db.query_one("SELECT * FROM v_catalog_kod_qamrov WHERE company_id=%(c)s",
                     {"c": cid}) or {}
    check("qamrov ko'rinishi qaytdi", bool(q))
    # ANIQ va KENG qo'shilsa 26.40 chelagidagi 612 mahsulot "aniq
    # kodlangan" bo'lib ko'rinardi.
    check("`aniq_kod` va `keng_kod` ALOHIDA",
          "aniq_kod" in q and "keng_kod" in q)
    jami = (q.get("aniq_kod") or 0) + (q.get("keng_kod") or 0) + (q.get("kodsiz") or 0)
    check("aniq + keng + kodsiz = mahsulot", jami == (q.get("mahsulot") or 0),
          f"{jami} vs {q.get('mahsulot')}")
    print(f"        aniq={q.get('aniq_kod')}  keng={q.get('keng_kod')}  "
          f"kodsiz={q.get('kodsiz')}")


# =====================================================================
def main():
    ap = argparse.ArgumentParser(description="Katalog kodlash sinovi")
    rejim.bayroqlar(ap)
    args = rejim.moslash(ap.parse_args())

    print("=" * 70)
    print("SINOV: KATALOG KODLASH — PRECISION QO'RIQCHISI")
    print("=" * 70)

    test_chegaralar()
    test_lugat()
    test_tokenlar()
    test_manba_qism_soz()
    test_qolla_qorovuli()

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
