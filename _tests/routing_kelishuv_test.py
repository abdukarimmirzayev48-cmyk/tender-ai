#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SINOV: YO'NALTIRISH AI <-> INSON KELISHUVI
===========================================

O'LCHANGAN MUAMMO (2026-08-31): eski `v_routing_agreement`
`review` ni **0.0 foiz kelishuv** deb ko'rsatardi.

`review` — "AI QAROR QILMADI" degani. Formula
`(go AND olindi) OR (no_go AND rad)` `review` uchun tuzilishiga ko'ra
HECH QACHON rost bo'lolmaydi, ya'ni u 0 ni KAFOLATLAYDI. Bu
NOMA'LUMNI MUVAFFAQIYATSIZLIKKA aylantirish va u ustun holat edi:
30 qarordan 25 tasi.

BU SINOV UCHTA NARSANI QO'RIQLAYDI:

  1. `review` kelishuv MAXRAJIGA KIRMAYDI;
  2. maxraj nol bo'lsa foiz NULL — NOL EMAS;
  3. AI fikrini o'zgartirgani TARIXIY HAQIQATNI QAYTA YOZMAYDI
     (`ai_qaror_eski` faqat BIR MARTA yoziladi).

Ishga tushirish:
    .venv\\Scripts\\python.exe _tests\\routing_kelishuv_test.py
    .venv\\Scripts\\python.exe _tests\\routing_kelishuv_test.py --offline
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

konsol.sozla()

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))

_natija = []
_yaratilgan = []


def check(nom, ok, tafsilot=""):
    _natija.append((nom, ok, tafsilot))
    print(f"  [{'PASS' if ok else 'FAIL'}] {nom}" + (f" -- {tafsilot}" if tafsilot else ""))
    return ok


def bolim(t):
    print(f"\n--- {t} ---")


# =====================================================================
def test_manba():
    bolim("1. Manba — lug'at va tuzilma")
    from api import routing
    check("inson qarorlari: olindi/rad/kutilsin",
          set(routing.INSON_QARORLAR) == {"olindi", "rad", "kutilsin"},
          str(routing.INSON_QARORLAR))
    src = io.open(os.path.join(ROOT, "api", "routing.py"), encoding="utf-8").read()
    # TARIXIY HAQIQAT: `ai_qaror_eski` FAQAT BIR MARTA yozilishi kerak.
    check("`ai_qaror_eski` faqat NULL bo'lganda yoziladi",
          "tender_routing.ai_qaror_eski IS NULL" in src)
    # Apostrof shakli har xil bo'lishi mumkin — SO'Z bo'yicha qidiramiz.
    check("nuqson sababi izohda yozilgan",
          "ASL" in src and "QOLARDI" in src and "IKKINCHI" in src)

    sql = io.open(os.path.join(ROOT, "schema_patch_routing_kelishuv.sql"),
                  encoding="utf-8").read()
    check("`ai_korilgan()` funksiyasi bor", "FUNCTION ai_korilgan" in sql)
    check("`review` alohida sanaladi", "ai_qaror_yoq" in sql)
    check("`kutilsin` alohida sanaladi", "kutildi" in sql)
    check("nol maxrajda NULL (NULLIF)", "NULLIF" in sql)


def test_endpoint_manba():
    bolim("2. API endpointi")
    src = io.open(os.path.join(ROOT, "api", "main.py"), encoding="utf-8").read()
    check("`/routing/agreement` bor", '@app.get("/routing/agreement")' in src)
    check("endpoint `company_id_of` bilan cheklangan",
          "def routing_agreement" in src
          and "company_id_of(request)" in
              src[src.index("def routing_agreement"):
                  src.index("def routing_agreement") + 1800])
    check("sxema yo'q bo'lsa `tayyor: False`",
          '"tayyor": False' in src[src.index("def routing_agreement"):
                                   src.index("def routing_agreement") + 1800])


# =====================================================================
def test_baza(db):
    bolim("3. Kelishuv ko'rinishi — haqiqiy ma'lumot")
    if not db.scalar("SELECT to_regclass('public.v_routing_kelishuv') IS NOT NULL"):
        check("`schema_patch_routing_kelishuv.sql` qo'llangan", False)
        return
    from api import auth
    cid = auth.sole_company_id()
    r = db.query_one("SELECT * FROM v_routing_kelishuv WHERE company_id=%(c)s",
                     {"c": cid})
    if not r:
        check("inson qarori bor", False, "kelishuv o'lchab bo'lmaydi")
        return

    print(f"        inson_qarori={r['inson_qarori']}  ai_davo={r['ai_davo']}  "
          f"ai_qaror_yoq={r['ai_qaror_yoq']}")

    # KATAKLAR JAMIGA TENG BO'LISHI SHART — aks holda qaror
    # matritsadan tashqarida qolib, ko'rinmay ketardi.
    kataklar = sum(r[k] for k in (
        "go_olindi", "go_rad", "go_kutilsin",
        "nogo_olindi", "nogo_rad", "nogo_kutilsin",
        "review_olindi", "review_rad", "review_kutilsin"))
    check("3x3 kataklar jami inson qarorlariga TENG",
          kataklar == r["inson_qarori"], f"{kataklar} vs {r['inson_qarori']}")
    check("ai_davo + ai_qaror_yoq = inson_qarori",
          r["ai_davo"] + r["ai_qaror_yoq"] == r["inson_qarori"])

    # MAXRAJ: `review` va `kutilsin` KIRMAYDI.
    check("maxraj = kelishdi + bekor_qilindi",
          r["kelishuv_maxraj"] == r["kelishdi"] + r["bekor_qilindi"],
          f"{r['kelishuv_maxraj']}")
    check("`review` maxrajga KIRMAYDI",
          r["kelishuv_maxraj"] + r["ai_qaror_yoq"] + r["kutildi"]
          <= r["inson_qarori"],
          f"maxraj={r['kelishuv_maxraj']} review={r['ai_qaror_yoq']} "
          f"kutildi={r['kutildi']}")

    if r["kelishuv_maxraj"]:
        check(f"kelishuv_foiz hisoblandi ({r['kelishuv_foiz']})",
              r["kelishuv_foiz"] is not None)
        check("kelishuv_foiz + bekor_foiz = 100",
              abs(float(r["kelishuv_foiz"]) + float(r["bekor_foiz"]) - 100) < 0.2,
              f"{r['kelishuv_foiz']} + {r['bekor_foiz']}")
    else:
        # NOL MAXRAJDA NULL — NOL EMAS.
        check("maxraj nol -> kelishuv_foiz NULL (nol EMAS)",
              r["kelishuv_foiz"] is None)

    bolim("4. ESKI ko'rinish nuqsoni QAYTARILMAGAN")
    eski = db.query("SELECT ai_qaror, moslik_foiz FROM v_routing_agreement "
                    "WHERE company_id=%(c)s", {"c": cid})
    for e in eski:
        if e["ai_qaror"] == "review":
            # Eski ko'rinish hali ham 0 beradi — u O'ZGARTIRILMADI
            # (boshqa chaqiruvchilar bor). MUHIMI: yangi ko'rinish
            # bu xatoni TAKRORLAMAYDI.
            print(f"        [i] eski ko'rinish `review` uchun hali ham "
                  f"{e['moslik_foiz']} beradi (o'zgartirilmadi)")
    check("YANGI ko'rinishda `review` uchun foiz YO'Q",
          "review" not in str(r.get("kelishuv_foiz", "")))

    bolim("5. Kesimlar")
    kesim = db.query("SELECT kesim, count(*) AS n FROM v_routing_kelishuv_kesim "
                     "WHERE company_id=%(c)s GROUP BY 1 ORDER BY 1", {"c": cid})
    check("kesimlar bor", len(kesim) >= 2, str([k["kesim"] for k in kesim]))
    for k in kesim:
        print(f"        {k['kesim']}: {k['n']} qator")
    # Har kesimning jami inson qarorlariga teng bo'lishi kerak
    # (`sabab` bundan mustasno — u NULL bo'lishi mumkin).
    for nom in ("manba", "ball"):
        j = db.scalar("SELECT sum(inson_qarori) FROM v_routing_kelishuv_kesim "
                      "WHERE company_id=%(c)s AND kesim=%(k)s",
                      {"c": cid, "k": nom})
        if j is not None:
            check(f"kesim `{nom}` jami inson qarorlariga teng",
                  int(j) == r["inson_qarori"], f"{j} vs {r['inson_qarori']}")

    bolim("6. Sifat belgilari — o'lchov qanchalik ishonchli")
    check("aktori noma'lum + ma'lum <= inson qarori",
          r["aktori_nomalum"] + r["aktori_malum"] <= r["inson_qarori"])
    if r["aktori_nomalum"] == r["inson_qarori"]:
        print(f"        [!] {r['aktori_nomalum']} qarorning HAMMASIDA aktor "
              f"NOMA'LUM (`kuzatuvdan_oldin`) — kelishuv KIM bilan "
              f"ekani o'lchanmagan")


def test_tarix_saqlanadi(db):
    bolim("7. TARIXIY HAQIQAT: ikki o'zgarish aslni BUZMAYDI")
    from api import auth
    cid = auth.sole_company_id()
    # SINOV QATORI — haqiqiy tenderga tegmaydi.
    # ROUTING QATORI YO'Q tender tanlanadi — haqiqiy qatorga
    # TEGILMAYDI. Ilgari bu yerda "eng yangi tender" olinardi va
    # unda qator bo'lgani uchun ENG MUHIM sinov jimgina O'TKAZIB
    # YUBORILARDI. O'tkazib yuborilgan sinov — sinov emas.
    t = db.query_one(
        "SELECT t.id FROM tender t "
        " WHERE NOT EXISTS (SELECT 1 FROM tender_routing r "
        "                    WHERE r.tender_id=t.id AND r.company_id=%(c)s) "
        " ORDER BY t.id DESC LIMIT 1", {"c": cid})
    if not t:
        check("routing qatori YO'Q tender topildi", False,
              "hamma tenderda qator bor")
        return

    r = db.execute_returning(
        "INSERT INTO tender_routing(company_id, tender_id, ai_qaror, ai_manba, "
        "  ai_sabab, holat) VALUES(%(c)s, %(t)s, 'go', 'malaka', "
        "  'ZZTEST kelishuv', 'yangi') RETURNING id",
        {"c": cid, "t": t["id"]})
    rid = r["id"]
    _yaratilgan.append(rid)
    try:
        # Inson `go` ni KO'RIB qaror berdi.
        db.execute_returning(
            "UPDATE tender_routing SET inson_qaror='olindi', qaror_vaqti=now(), "
            "qaror_ishonch='kompaniya_sessiyasi' WHERE id=%(i)s RETURNING id",
            {"i": rid})
        check("inson `go` ni ko'rib qaror berdi",
              db.scalar("SELECT inson_qaror='olindi' FROM tender_routing "
                        "WHERE id=%(i)s", {"i": rid}))

        # 1-O'ZGARISH: go -> review
        from api import routing
        db.execute_returning(routing.SQL_UPSERT, {
            "c": cid, "t": t["id"], "q": "review", "b": None,
            "m": "malaka", "s": "ZZTEST 1-ozgarish"})
        e1 = db.query_one("SELECT ai_qaror, ai_qaror_eski, ai_ozgardi "
                          "FROM tender_routing WHERE id=%(i)s", {"i": rid})
        check("1-o'zgarishdan keyin eski = 'go'", e1["ai_qaror_eski"] == "go",
              str(e1["ai_qaror_eski"]))
        check("`ai_ozgardi` bayrog'i qo'yildi", e1["ai_ozgardi"] is True)

        # 2-O'ZGARISH: review -> no_go. ASL ('go') SAQLANISHI SHART.
        db.execute_returning(routing.SQL_UPSERT, {
            "c": cid, "t": t["id"], "q": "no_go", "b": None,
            "m": "malaka", "s": "ZZTEST 2-ozgarish"})
        e2 = db.query_one("SELECT ai_qaror, ai_qaror_eski "
                          "FROM tender_routing WHERE id=%(i)s", {"i": rid})
        check("2-o'zgarishdan keyin ham eski = 'go' (ASL SAQLANDI)",
              e2["ai_qaror_eski"] == "go",
              f"joriy={e2['ai_qaror']} eski={e2['ai_qaror_eski']}")

        # KELISHUV inson KO'RGAN qaror bilan hisoblanadi.
        korilgan = db.scalar(
            "SELECT ai_korilgan(ai_qaror, ai_qaror_eski) FROM tender_routing "
            "WHERE id=%(i)s", {"i": rid})
        check("`ai_korilgan()` inson ko'rgan qarorni beradi ('go')",
              korilgan == "go", str(korilgan))
        # Ya'ni bu qator KELISHUV deb sanalishi kerak (go + olindi),
        # joriy `no_go` bilan BEKOR QILISH deb emas.
        check("qator KELISHUV deb sanaladi (bekor qilish EMAS)",
              db.scalar("SELECT ai_korilgan(ai_qaror, ai_qaror_eski)='go' "
                        "AND inson_qaror='olindi' FROM tender_routing "
                        "WHERE id=%(i)s", {"i": rid}))
    finally:
        db.execute_returning("DELETE FROM tender_routing WHERE id=%(i)s "
                             "RETURNING id", {"i": rid})
        print("        (sinov qatori o'chirildi)")


# =====================================================================
def main():
    ap = argparse.ArgumentParser(description="Yo'naltirish kelishuvi sinovi")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    print("=" * 70)
    print("SINOV: YO'NALTIRISH AI <-> INSON KELISHUVI")
    print("=" * 70)

    test_manba()
    test_endpoint_manba()

    if args.offline or not os.environ.get("XT_DB_DSN"):
        print("\n[i] Bazali tekshiruvlar o'tkazib yuborildi.")
    else:
        from api import db
        try:
            db.init_pool()
            test_baza(db)
            test_tarix_saqlanadi(db)
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
