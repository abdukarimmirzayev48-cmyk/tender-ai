#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SINOV: TALAB QAYTA ISHLASH QAMROVI
===================================

O'LCHANGAN MUAMMO (2026-08-31): sodda metrika
`talabi bor / hamma tender` = 1161/3605 = 32.2 foiz. Bu raqam
"ajratish yomon ishlayapti" degan taassurot beradi, HOLBUKI:

    ishlangan tenderlarda topilish   100.0 foiz   (SIFAT)
    yaroqlilarning ishlangani         32.2 foiz   (O'TKAZUVCHANLIK)

Ya'ni past raqam SIFAT emas, ISHLANMAGANI. Ikkalasini bitta
foizga qo'shish "talab yo'q" degan YOLG'ON xulosaga olib boradi.

BU SINOV QO'RIQLAYDI:

  1. Holatlar JAMIGA yarashadi (`hisobga_olinmagan` = 0);
  2. `navbatda` (ishlanmagan) MAXRAJGA KIRMAYDI — noma'lum
     salbiy natijaga aylanmaydi;
  3. "Topilmadi" (natija) va "navbatda" (natija YO'QLIGI) ALOHIDA;
  4. HAR USULNING O'Z maxraji bor;
  5. "Hujjat yopiq" YAKUNIY holat emas, agar reyestr yo'li ochiq
     bo'lsa.

Ishga tushirish:
    .venv\\Scripts\\python.exe _tests\\req_qamrov_test.py
    .venv\\Scripts\\python.exe _tests\\req_qamrov_test.py --offline
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


#: Holatlar — SQL dagi `requirement_holat()` bilan BIR XIL bo'lishi
#: kerak. Ikki joyda saqlanishi noqulay, lekin sinov MOSLIGINI
#: tekshiradi va ajralib ketishga yo'l qo'ymaydi.
HOLATLAR = ("talab_bor", "ishlandi_topilmadi", "hujjat_yopiq_reyestr_navbatda",
            "hujjat_yopiq", "navbatda", "ajratish_xato", "tegishli_emas")


def test_manba():
    bolim("1. Manba — holat lug'ati va ajratish")
    sql = io.open(os.path.join(ROOT, "schema_patch_req_qamrov.sql"),
                  encoding="utf-8").read()
    for h in HOLATLAR:
        check(f"holat `{h}` mavjud", f"'{h}'" in sql)
    # "TOPILMADI" va "NAVBATDA" ATAYLAB ajratilgan.
    check("ikki foiz ALOHIDA hisoblanadi",
          "ishlanganda_topildi_foiz" in sql and "ishlangan_foiz" in sql)
    check("nazorat ustuni bor", "hisobga_olinmagan" in sql)
    check("nol maxrajda NULL (NULLIF)", sql.count("NULLIF") >= 2)
    check("har usulning O'Z maxraji bor",
          "reyestr_yaroqli" in sql and "naqsh_yaroqli" in sql)


def test_endpoint_manba():
    bolim("2. API endpointi")
    src = io.open(os.path.join(ROOT, "api", "main.py"), encoding="utf-8").read()
    check("`/requirements/coverage` bor",
          '@app.get("/requirements/coverage")' in src)
    blok = src[src.index("def requirements_coverage"):]
    blok = blok[:blok.index("\n\n\n")]
    check("ijarachi bilan cheklangan", "company_id_of(request)" in blok)
    check("`yarashadi` bayrog'i qaytadi", '"yarashadi"' in blok)
    # Sodda metrika endpointda BO'LMASLIGI kerak.
    check("sodda `talab/hamma tender` metrikasi YO'Q",
          "count(DISTINCT tender_id) FROM tender_requirement" not in blok)


# =====================================================================
def test_baza(db):
    bolim("3. Holatlar JAMIGA yarashadi")
    if not db.scalar("SELECT to_regclass('public.v_requirement_qamrov') IS NOT NULL"):
        check("`schema_patch_req_qamrov.sql` qo'llangan", False)
        return
    from api import auth
    cid = auth.sole_company_id()
    r = db.query_one("SELECT * FROM v_requirement_qamrov WHERE company_id=%(c)s",
                     {"c": cid})
    check("qamrov ko'rinishi qaytdi", bool(r))
    if not r:
        return

    for k in HOLATLAR:
        # Ko'rinishdagi ustun nomi qisqartirilgan bo'lishi mumkin.
        pass
    yigindi = (r["talab_bor"] + r["ishlandi_topilmadi"]
               + r["hujjat_yopiq_navbatda"] + r["hujjat_yopiq"]
               + r["navbatda"] + r["ajratish_xato"] + r["tegishli_emas"])
    check("holatlar yig'indisi = tender soni", yigindi == r["tender"],
          f"{yigindi} vs {r['tender']}")
    # NAZORAT USTUNI — nol bo'lmasa tasnifdan tashqarida tender bor.
    check("`hisobga_olinmagan` = 0", r["hisobga_olinmagan"] == 0,
          str(r["hisobga_olinmagan"]))
    print(f"        talab_bor={r['talab_bor']}  navbatda={r['navbatda']}  "
          f"hujjat_yopiq_navbatda={r['hujjat_yopiq_navbatda']}")

    bolim("4. `navbatda` MAXRAJGA KIRMAYDI")
    # ISHLANGAN = talab_bor + ishlandi_topilmadi. Navbatdagilar YO'Q.
    check("ishlangan = talab_bor + ishlandi_topilmadi",
          r["ishlangan"] == r["talab_bor"] + r["ishlandi_topilmadi"],
          f"{r['ishlangan']}")
    check("ishlangan < tender (navbatdagilar kirmagan)",
          r["ishlangan"] < r["tender"] or r["navbatda"] == 0,
          f"ishlangan={r['ishlangan']} tender={r['tender']}")
    if r["ishlangan"]:
        check(f"sifat foizi hisoblandi ({r['ishlanganda_topildi_foiz']})",
              r["ishlanganda_topildi_foiz"] is not None)
        # SIFAT va O'TKAZUVCHANLIK BOSHQA raqam bo'lishi kerak —
        # aks holda ajratish ma'nosiz.
        check("sifat va o'tkazuvchanlik BOSHQA raqam",
              r["ishlanganda_topildi_foiz"] != r["ishlangan_foiz"]
              or r["navbatda"] == 0,
              f"sifat={r['ishlanganda_topildi_foiz']} "
              f"o'tkazuvchanlik={r['ishlangan_foiz']}")
    else:
        check("ishlangan nol -> sifat foizi NULL (nol EMAS)",
              r["ishlanganda_topildi_foiz"] is None)

    bolim("5. HAR USULNING O'Z maxraji")
    usul = db.query("SELECT * FROM v_requirement_qamrov_usul "
                    "WHERE company_id=%(c)s ORDER BY usul", {"c": cid})
    check("ikkala usul ham bor", {u["usul"] for u in usul} == {"naqsh", "reyestr"},
          str([u["usul"] for u in usul]))
    for u in usul:
        print(f"        {u['usul']:<9} yaroqli={u['yaroqli']:<6} "
              f"urinildi={u['urinildi']:<6} topildi={u['topildi']}")
        check(f"`{u['usul']}`: urinildi <= yaroqli",
              u["urinildi"] <= u["yaroqli"],
              f"{u['urinildi']} vs {u['yaroqli']}")
        check(f"`{u['usul']}`: topildi <= urinildi",
              u["topildi"] <= u["urinildi"])
    # MAXRAJLAR BOSHQA bo'lishi kerak — aks holda ajratish bekor.
    maxrajlar = {u["usul"]: u["yaroqli"] for u in usul}
    check("usullarning maxraji BOSHQA",
          len(set(maxrajlar.values())) > 1, str(maxrajlar))

    bolim("6. `hujjat_yopiq` YAKUNIY holat EMAS (reyestr ochiq bo'lsa)")
    # `no_text` bo'lgan, lekin LOTI BOR tenderlar `navbatda` deb
    # belgilanishi kerak — "qayta ishlab bo'lmaydi" deb EMAS.
    n = db.scalar("""
        SELECT count(*) FROM v_requirement_tender_holat
         WHERE company_id=%(c)s AND holat='hujjat_yopiq_reyestr_navbatda'""",
        {"c": cid})
    check("holat mavjud va sanaladi", n is not None, f"{n} ta")
    if n:
        # Hammasida LOT bo'lishi SHART — aks holda tasnif noto'g'ri.
        lotsiz = db.scalar("""
            SELECT count(*) FROM v_requirement_tender_holat h
             WHERE h.company_id=%(c)s
               AND h.holat='hujjat_yopiq_reyestr_navbatda'
               AND NOT EXISTS (SELECT 1 FROM tender_good g
                                WHERE g.tender_id=h.tender_id)""",
            {"c": cid})
        check("bu holatdagi HAR tenderda lot BOR (reyestr yo'li ochiq)",
              lotsiz == 0, f"lotsiz={lotsiz}")

    bolim("7. `requirement_holat()` — chegara holatlari")
    # Natija bor -> talab_bor (boshqa hamma narsadan ustun)
    check("talab bor -> `talab_bor`",
          db.scalar("SELECT requirement_holat(true,false,false,false,"
                    "true,true,false)") == "talab_bor")
    # Xato -> yashirilmaydi
    check("xato -> `ajratish_xato`",
          db.scalar("SELECT requirement_holat(false,false,false,true,"
                    "true,true,true)") == "ajratish_xato")
    # Matnsiz + lot bor + reyestr urinilmagan -> NAVBATDA (yakuniy EMAS)
    check("matnsiz, lekin reyestr ochiq -> navbatda",
          db.scalar("SELECT requirement_holat(false,false,true,false,"
                    "true,true,false)") == "hujjat_yopiq_reyestr_navbatda")
    # Matnsiz + lot yo'q -> hujjat_yopiq (haqiqatan yakuniy)
    check("matnsiz va lot yo'q -> `hujjat_yopiq`",
          db.scalar("SELECT requirement_holat(false,false,true,false,"
                    "false,true,false)") == "hujjat_yopiq")
    # Hech qanday yo'l yo'q
    check("lot ham, hujjat ham yo'q -> `tegishli_emas`",
          db.scalar("SELECT requirement_holat(false,false,false,false,"
                    "false,false,false)") == "tegishli_emas")
    # Yaroqli, urinilmagan
    check("yaroqli, urinilmagan -> `navbatda`",
          db.scalar("SELECT requirement_holat(false,false,false,false,"
                    "true,false,false)") == "navbatda")


# =====================================================================
def main():
    ap = argparse.ArgumentParser(description="Talab qamrovi sinovi")
    rejim.bayroqlar(ap)
    args = rejim.moslash(ap.parse_args())

    print("=" * 70)
    print("SINOV: TALAB QAYTA ISHLASH QAMROVI")
    print("=" * 70)

    test_manba()
    test_endpoint_manba()

    if args.bazasiz or not os.environ.get("XT_DB_DSN"):
        print("\n[i] Bazali tekshiruvlar o'tkazib yuborildi.")
    else:
        from api import db
        try:
            db.init_pool()
            test_baza(db)
        except Exception as e:                                # noqa: BLE001
            check("bazali tekshiruv", False, str(e)[:110])

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
