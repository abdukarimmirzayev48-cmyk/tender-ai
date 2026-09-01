#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SINOV: SAQLANGAN QIDIRUV — HAQIQATAN ISHLAYDIMI
================================================

O'LCHANGAN HOLAT (2026-09-01): `saved_search` jadvalida **0 ta**
qator. Ya'ni imkoniyat kod va interfeysda BOR, lekin HECH KIM
ishlatmagan.

NOL ISHLATISH IKKI XIL MA'NO BERADI va ular ARALASHTIRILMASIN:

    "kerak emas ekan"     — mahsulot qarori
    "ishlamaydi/topilmaydi" — muhandislik nuqsoni

Bu sinov ikkinchisini INKOR ETADI yoki ISBOTLAYDI: CRUD, ijarachi
ajratilishi, filtr saqlanishi va bajarilishi HAQIQIY so'rovlar
bilan tekshiriladi. Shundan keyingina "nol ishlatish" mahsulot
savoli bo'lib qoladi.

QAMROVDAN TASHQARIDA EKANI ANIQ YOZILGAN QISMLAR (`docs/saved_search.md`):
`notify` bayrog'i, `last_seen_at` va `categories` — ular saqlanadi,
lekin HECH NARSAGA ta'sir qilmaydi. Sinov ularning ishlamasligini
ATAYLAB tasdiqlaydi: "bor" deb ko'rsatilib, jimgina ishlamay
turgani eng yomon holat.

Ishga tushirish:
    .venv\\Scripts\\python.exe _tests\\saved_search_test.py
    .venv\\Scripts\\python.exe _tests\\saved_search_test.py --offline
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

#: Sinov hisoblari. `zz` prefiksi — tozalashda ADASHMASLIK uchun.
A_LOGIN, B_LOGIN = "zzsearch_a", "zzsearch_b"
PAROL = "zzSinovQidiruv12345"


def check(nom, ok, tafsilot="", faqat_xatoda=False):
    """`faqat_xatoda` — tafsilot FAQAT yiqilganda chop etilsin.

    Solishtirish tafsiloti o'tganda ham chiqsa (`['a'] != ['a']`)
    chiqish YOLG'ON o'qiladi: PASS yonida "teng emas" yozuvi
    turadi va sinovni ko'zdan kechirgan odam adashadi.
    """
    _natija.append((nom, ok, tafsilot))
    korsat = tafsilot if (tafsilot and not (faqat_xatoda and ok)) else ""
    print(f"  [{'PASS' if ok else 'FAIL'}] {nom}"
          + (f" -- {korsat}" if korsat else ""))
    return ok


def bolim(t):
    print(f"\n--- {t} ---")


def oqi(*yol):
    return io.open(os.path.join(ROOT, *yol), encoding="utf-8").read()


# =====================================================================
def test_manba():
    bolim("1. MANBA — CRUD to'liq va ijarachi bilan cheklangan")
    q = oqi("api", "queries.py")
    m = oqi("api", "main.py")

    # HAR SQL ijarachi bilan cheklangan bo'lsin. Bittasi unutilsa,
    # bir ijarachi boshqasining qidiruvini ko'rardi.
    for nom in ("SEARCHES_LIST_SQL", "SEARCH_GET_SQL", "SEARCH_INSERT_SQL",
                "SEARCH_UPDATE_SQL", "SEARCH_DELETE_SQL"):
        i = q.index(nom)
        blok = q[i:i + 400]
        blok = blok[:blok.index('"""', blok.index("\n"))] if '"""' in blok[:400] \
            else blok[:300]
        check(f"`{nom}` da `company_id` bor", "company_id" in blok)

    for yol in ("@app.get(\"/searches\")", "@app.post(\"/searches\"",
                "@app.put(\"/searches/{search_id}\")",
                "@app.delete(\"/searches/{search_id}\""):
        check(f"endpoint bor: {yol[:34]}", yol in m)

    # O'LIK KOD: chaqiruvchisi yo'q SQL "imkoniyat bor" degan
    # yolg'on taassurot beradi.
    hamma_py = "\n".join(
        oqi(*p.split("/")) for p in
        ("api/main.py", "api/notify.py", "api/queries.py", "api/matching.py"))
    check("`SEARCH_GET_SQL` chaqiruvchisi bor",
          len(re.findall(r"queries\.SEARCH_GET_SQL", hamma_py)) > 0,
          "qisman yangilashda joriy qatorni o'qish uchun kerak")
    # `SEARCH_SEEN_SQL` OLIB TASHLANDI: `last_seen_at` ni to'ldiradigan
    # endpoint ham, interfeys ham yo'q edi — o'lik SQL "imkoniyat bor"
    # degan yolg'on taassurot berardi. Qaytib kelsa, uni CHAQIRADIGAN
    # yo'l ham bo'lsin.
    check("`SEARCH_SEEN_SQL` (o'lik SQL) olib tashlangan",
          "SEARCH_SEEN_SQL" not in q,
          "qaytarilgan bo'lsa uni CHAQIRADIGAN endpoint ham bo'lsin")

    # QISMAN YANGILASH: yuborilmagan maydon yo'qolmasin.
    check("tahrirlash QISMAN (`exclude_unset`)",
          "SavedSearchPatchIn" in m and "exclude_unset=True" in m)


def test_hujjat():
    bolim("2. HUJJAT — bajarilmagani ANIQ yozilgan")
    p = os.path.join(ROOT, "docs", "saved_search.md")
    check("`docs/saved_search.md` mavjud", os.path.exists(p))
    if not os.path.exists(p):
        return
    d = oqi("docs", "saved_search.md")
    for atama in ("0 ta", "notify", "last_seen_at", "categories",
                  "KEYINGA QOLDIRILGAN"):
        check(f"hujjatda `{atama}` bor", atama in d)
    # "Nol ishlatish = muvaffaqiyat" degan xulosa CHIQMASIN.
    check("hujjat nol ishlatishni MUVAFFAQIYAT deb ko'rsatmaydi",
          "muvaffaqiyat" not in d.lower() or "EMAS" in d)


def test_frontend():
    bolim("3. INTERFEYS — topiladimi")
    sb = oqi("frontend", "src", "components", "Sidebar.tsx")
    app = oqi("frontend", "src", "App.tsx")
    pf = oqi("frontend", "src", "components", "ProfileForm.tsx")

    check("yon panelda ro'yxat bor", "nav.savedSearches" in sb)
    check("yangi qidiruv tugmasi bor", "onNewSearch" in sb)
    check("bo'sh holat matni bor", "nav.noSearches" in sb)
    check("qo'llash ishlovchisi bor", "onApplySearch" in sb)
    check("tahrirlash ishlovchisi bor", "onEditSearch" in sb)
    check("o'chirish ishlovchisi bor", "onDeleteSearch" in sb)
    check("shakl yaratadi va yangilaydi",
          "api.createSearch" in pf and "api.updateSearch" in pf)

    # XATO YASHIRILMASIN. `catch { }` o'chirish muvaffaqiyatsiz
    # bo'lsa ham interfeys "o'chdi" deb ko'rsatardi va element
    # yangilanishdan keyin QAYTA PAYDO bo'lardi — sababsiz.
    blok = app[app.index("async function removeSearch"):]
    blok = blok[:blok.index("\n  }") + 4]
    # IZOH QATORLARI OLIB TASHLANADI: izohda NEGA o'zgartirilgani
    # yozilgan va u yerda eski `catch { }` iborasi uchraydi — u
    # tekshiruvni SOXTA yiqitardi. Naqsh KODNI qidirsin, matnni emas.
    kod = "\n".join(ln for ln in blok.split("\n")
                    if not ln.strip().startswith("//"))
    check("o'chirish xatosi YUTILMAYDI",
          not re.search(r"catch\s*(\([^)]*\))?\s*\{\s*(/\*.*?\*/)?\s*\}",
                        kod, re.S),
          kod.strip()[:120])
    check("o'chirish xatosi FOYDALANUVCHIGA ko'rsatiladi",
          "setError(" in kod, kod.strip()[:120])


# =====================================================================
def _hisob(db, A, login):
    """Sinov hisobi — bor bo'lsa qayta ishlatiladi."""
    r = db.query_one(A.ACC_BY_NAME_SQL, {"username": login})
    if r:
        db.execute_returning(
            "UPDATE company_account SET active=TRUE WHERE id=%(id)s "
            "RETURNING id", {"id": r["id"]})
        A.set_password(r["id"], PAROL)
        return int(r["id"])
    return int(A.create_account(login, f"SINOV {login}", PAROL)["id"])


def test_baza(db):
    bolim("4. HAQIQIY QO'LLANISH — o'lchov")
    n = db.scalar("SELECT count(*) FROM saved_search") or 0
    print(f"      saved_search qatorlari: {n}")
    # BU TEKSHIRUV EMAS, O'LCHOV. Nol bo'lishi ham, bo'lmasligi ham
    # muhandislik nuqsoni EMAS — muhimi, u hujjatda yozilgan bo'lsin.
    d = oqi("docs", "saved_search.md")
    check("hujjatdagi son bazadagi bilan MOS",
          f"{n} ta" in d, f"bazada {n} ta, hujjatda bu son topilmadi",
          faqat_xatoda=True)

    # IJARACHI CHEGARASI BAZADA — kodga tayanmaydi.
    fk = db.query("""SELECT conname, pg_get_constraintdef(oid) AS def
                     FROM pg_constraint
                     WHERE conrelid='saved_search'::regclass
                       -- PostgreSQL 17+ da NOT NULL ham `pg_constraint`
                       -- da turadi (`contype='n'`); 'f' = FK, 'c' = CHECK.
                       AND contype IN ('f','c','n')""")
    defs = " ".join(r["def"] for r in fk)
    check("`company_id` NOT NULL (baza darajasida)",
          "NOT NULL company_id" in defs, defs[:160])
    check("`company_id` -> `company_account` FK",
          "REFERENCES company_account(id)" in defs, defs[:160])
    check("hisob o'chirilsa qidiruvlar ham o'chadi (CASCADE)",
          "ON DELETE CASCADE" in defs, defs[:160])


def test_crud(db):
    bolim("5. CRUD va IJARACHI AJRATILISHI — haqiqiy so'rovlar")
    from fastapi.testclient import TestClient

    from api import auth as A
    from api.main import app

    a_id = _hisob(db, A, A_LOGIN)
    b_id = _hisob(db, A, B_LOGIN)
    ta = A.login(A_LOGIN, PAROL)["token"]
    tb = A.login(B_LOGIN, PAROL)["token"]
    HA = {"Authorization": f"Bearer {ta}"}
    HB = {"Authorization": f"Bearer {tb}"}

    yaratilgan = []
    try:
        with TestClient(app) as c:
            # --- YARATISH ---
            tana = {"name": "ZZ sinov qidiruvi", "keywords": ["kabel", "simi"],
                    "regions": ["1726"], "currency": "UZS",
                    "min_cost": 1000.0, "max_cost": 5000000.0,
                    "categories": ["31"], "notify": False}
            r = c.post("/searches", headers=HA, json=tana)
            check("yaratish -> 201", r.status_code == 201,
                  f"{r.status_code}: {str(r.json())[:120]}")
            if r.status_code != 201:
                return
            sid = r.json()["id"]
            yaratilgan.append(sid)

            # --- FILTR SAQLANISHI ---
            got = r.json()
            for k in ("keywords", "regions", "currency", "min_cost",
                      "max_cost", "categories"):
                check(f"yaratishda `{k}` saqlandi", got.get(k) == tana[k],
                      f"{got.get(k)!r} != {tana[k]!r}", faqat_xatoda=True)
            check("`notify` saqlandi", got.get("notify") == tana["notify"],
                  str(got.get("notify")))

            # --- O'QISH + BAJARILISH ---
            r = c.get("/searches", headers=HA)
            check("ro'yxat -> 200", r.status_code == 200)
            royxat = r.json()
            meniki = [x for x in royxat if x["id"] == sid]
            check("yaratilgan qidiruv ro'yxatda", len(meniki) == 1)
            if meniki:
                check("`match_count` hisoblanadi (bajarilish)",
                      isinstance(meniki[0].get("match_count"), int),
                      str(meniki[0].get("match_count")))

            # --- TAHRIRLASH: BERILMAGAN maydon YO'QOLMASIN ---
            # Interfeys shakli `categories` va `notify` ni YUBORMAYDI.
            # To'liq almashtirish semantikasida ular JIMGINA
            # tozalanardi — foydalanuvchi buni hech qayerda ko'rmasdi.
            r = c.put(f"/searches/{sid}", headers=HA,
                      json={"name": "ZZ sinov qidiruvi 2",
                            "keywords": ["kabel", "simi"],
                            "regions": ["1726"], "currency": "UZS",
                            "min_cost": 1000.0, "max_cost": 5000000.0})
            check("tahrirlash -> 200", r.status_code == 200,
                  f"{r.status_code}: {str(r.json())[:120]}")
            if r.status_code == 200:
                y = r.json()
                check("tahrirlashda nom o'zgardi",
                      y["name"] == "ZZ sinov qidiruvi 2", y["name"])
                check("BERILMAGAN `categories` YO'QOLMADI",
                      y.get("categories") == ["31"],
                      f"{y.get('categories')!r} (kutilgan ['31'])")
                check("BERILMAGAN `notify` YO'QOLMADI",
                      y.get("notify") is False, str(y.get("notify")))

            # --- IJARACHI AJRATILISHI ---
            r = c.get("/searches", headers=HB)
            check("B ijarachi A ning qidiruvini KO'RMAYDI",
                  all(x["id"] != sid for x in r.json()),
                  str([x["id"] for x in r.json()]))
            r = c.put(f"/searches/{sid}", headers=HB,
                      json={"name": "O'G'IRLANDI"})
            check("B ijarachi A ning qidiruvini TAHRIRLAY OLMAYDI",
                  r.status_code == 404, str(r.status_code))
            r = c.delete(f"/searches/{sid}", headers=HB)
            check("B ijarachi A ning qidiruvini O'CHIRA OLMAYDI",
                  r.status_code == 404, str(r.status_code))
            # Va u haqiqatan JOYIDA turibdi.
            check("A ning qidiruvi hali ham bazada",
                  db.scalar("SELECT company_id FROM saved_search "
                            "WHERE id=%(i)s", {"i": sid}) == a_id)

            # --- O'CHIRISH ---
            r = c.delete(f"/searches/{sid}", headers=HA)
            check("o'chirish -> 204", r.status_code == 204, str(r.status_code))
            if r.status_code == 204:
                yaratilgan.remove(sid)
            r = c.delete(f"/searches/{sid}", headers=HA)
            check("qayta o'chirish -> 404", r.status_code == 404,
                  str(r.status_code))
            check("javob KODLI (20-vazifa)",
                  r.json().get("error", {}).get("code") == "SEARCH_NOT_FOUND",
                  str(r.json())[:120])
    finally:
        # TOZALASH HOVUZNI QAYTA OCHADI: `TestClient` kontekstidan
        # chiqishda `lifespan` `db.close_pool()` ni chaqiradi va
        # keyingi so'rov `DBUnavailable` beradi. Ilgari tozalash
        # aynan shu sababdan BAJARILMASDI va sinov hisoblari FAOL
        # holda qolib ketardi.
        db.init_pool()
        for sid in yaratilgan:
            db.execute_returning("DELETE FROM saved_search WHERE id=%(i)s "
                                 "RETURNING id", {"i": sid})
        for cid in (a_id, b_id):
            db.execute_returning(
                "UPDATE company_account SET active=FALSE WHERE id=%(i)s "
                "RETURNING id", {"i": cid})


def test_bildirishnoma_ulanmagan(db):
    bolim("6. BILDIRISHNOMA — ULANMAGANI ATAYLAB tasdiqlanadi")
    # `notify` bayrog'i jadvalda ham, API da ham bor. Lekin
    # bildirishnoma tsikli `company_profile` dan o'qiydi. Ya'ni
    # bayroqni yoqish HECH NARSA qilmaydi.
    #
    # BU TEKSHIRUV "buzuq" demaydi — u HOLATNI QULFLAYDI: ulanish
    # qo'shilsa sinov YIQILADI va hujjatni yangilash MAJBUR bo'ladi.
    n = oqi("api", "notify.py")
    check("bildirishnoma `company_profile` dan o'qiydi",
          "PROFILE_SQL = queries.PROFILE_GET_SQL" in n)
    check("bildirishnoma `saved_search` ni O'QIMAYDI",
          "saved_search" not in n and "SEARCHES_LIST_SQL" not in n,
          "ulanish qo'shilgan bo'lsa `docs/saved_search.md` yangilansin",
          faqat_xatoda=True)

    # `last_seen_at` hech qachon to'ldirilmaydi — "oxirgi ko'rgandan
    # keyingi yangilar" belgisi YO'Q.
    tuldirilgan = db.scalar("SELECT count(*) FROM saved_search "
                            "WHERE last_seen_at IS NOT NULL") or 0
    check("`last_seen_at` hech qayerda to'ldirilmagan", tuldirilgan == 0,
          f"{tuldirilgan} ta to'ldirilgan — ulanish paydo bo'lgan",
          faqat_xatoda=True)


# =====================================================================
def main():
    ap = argparse.ArgumentParser(description="Saqlangan qidiruv sinovi")
    rejim.bayroqlar(ap)
    args = rejim.moslash(ap.parse_args())

    print("=" * 70)
    print("SINOV: SAQLANGAN QIDIRUV — HAQIQATAN ISHLAYDIMI")
    print("=" * 70)

    test_manba()
    test_hujjat()
    test_frontend()

    if args.bazasiz or not os.environ.get("XT_DB_DSN"):
        print("\n[i] Bazali tekshiruvlar o'tkazib yuborildi.")
    else:
        from api import db
        try:
            db.init_pool()
            test_baza(db)
            test_crud(db)
            test_bildirishnoma_ulanmagan(db)
        except Exception as e:                                # noqa: BLE001
            import traceback
            traceback.print_exc()
            check("bazali tekshiruv", False, f"{type(e).__name__}: {e}")

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
