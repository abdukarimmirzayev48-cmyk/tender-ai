#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SINOV: RAG BAHOLASH BAZAVIY O'LCHOVI — REGRESSIYA QO'RIQCHISI
==============================================================

`_tests/ai_eval/rag_eval.py` bazaviy o'lchovni beradi. Bu sinov uch
narsani qo'riqlaydi:

  1. GROUND TRUTH HAQIQIY. Har dalil satri KORPUSDA borligini
     tekshiradi. Dalil yo'qolsa (hujjat qayta ishlangan, bo'lak
     chegarasi siljigan) yorliq JIMGINA yolg'onga aylanardi.

  2. SIZIB CHIQISH YO'Q. Qidiruvga faqat savol beriladi.

  3. METRIKA PASAYMAGAN. Bazaviy fayl bilan taqqoslanadi. Pasayish
     TO'XTATADI — aks holda sifat sekin-asta yo'qolib, buni hech
     narsa ko'rsatmasdi.

NEGA CHEGARA BOR (`TOLERANS`): korpus o'sib boradi va yangi bo'laklar
tartibni biroz siljitishi mumkin. Katta pasayish esa REGRESSIYA.

Ishga tushirish:
    .venv\\Scripts\\python.exe _tests\\rag_eval_test.py
    .venv\\Scripts\\python.exe _tests\\rag_eval_test.py --offline
"""
import argparse
import io
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import konsol  # noqa: E402
import rejim  # noqa: E402

konsol.sozla()

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))

try:
    import psycopg2
except ImportError:                                           # pragma: no cover
    psycopg2 = None

EVAL = os.path.join(ROOT, "_tests", "ai_eval", "rag_eval.py")
CASES = os.path.join(ROOT, "_tests", "ai_eval", "cases.jsonl")
BASELINE = os.path.join(ROOT, "_tests", "ai_eval", "results",
                        "rag_eval_baseline.json")

#: Metrika shuncha pasaysa — REGRESSIYA. Korpus o'sishi tartibni
#: biroz siljitadi, shuning uchun nol emas; lekin katta pasayish
#: to'xtatadi.
TOLERANS = 0.10

_results = []


def check(name, ok, detail=""):
    _results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    return ok


def section(t):
    print(f"\n--- {t} ---")


def cases():
    return [json.loads(l) for l in io.open(CASES, encoding="utf-8")
            if l.strip() and '"id"' in l]


# =====================================================================
def test_toplam_shakli():
    section("To'plam shakli — har holat to'liq")
    cs = cases()
    check("holatlar bor", len(cs) >= 10, f"{len(cs)} ta")
    kerak = ("id", "guruh", "tender_id", "savol", "haqiqat", "kutilgan")
    for c in cs:
        yoq = [k for k in kerak if k not in c]
        check(f"{c.get('id', '?')}: barcha maydonlar bor", not yoq, str(yoq))
    turlar = {c["kutilgan"]["tur"] for c in cs}
    check("javobsiz holatlar BOR",
          {"topilmadi"} & turlar == {"topilmadi"},
          "gallyutsinatsiyani faqat ular o'lchaydi")
    check("id lar TAKRORSIZ", len({c["id"] for c in cs}) == len(cs))


def test_sizib_chiqish():
    section("Sizib chiqish — ground truth qidiruvga bormaydi")
    r = subprocess.run([sys.executable, EVAL, "--sizish-tekshir"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="backslashreplace", cwd=ROOT, timeout=300)
    check("sizish tekshiruvi O'TDI", r.returncode == 0,
          (r.stdout or "")[-200:])


def test_ground_truth(conn):
    section("Ground truth KORPUSDA tasdiqlanadi")
    if conn is None:
        check("baza kerak", False, "o'tkazib yuborildi")
        return
    dalilli = [c for c in cases() if c["kutilgan"].get("manba_matn")]
    check("dalilli holatlar bor", len(dalilli) >= 5, f"{len(dalilli)} ta")
    for c in dalilli:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM doc_chunk "
                        "WHERE tender_id=%s AND text ILIKE %s",
                        (c["tender_id"], "%" + c["kutilgan"]["manba_matn"] + "%"))
            n = cur.fetchone()[0]
        # DALIL YO'QOLSA YORLIQ YOLG'ONGA AYLANADI. Jimgina
        # o'tkazib yuborilmaydi.
        # Tafsilot FAQAT yiqilganda ma'noli — `check()` uni ikkala
        # holatda ham chop etadi, shuning uchun shartli beriladi.
        check(f"{c['id']}: dalil korpusda BOR ({n} bo'lak)", n > 0,
              "" if n else (f"{c['kutilgan']['manba_matn'][:40]!r} KORPUSDA "
                            f"YO'Q — yorliq endi YOLG'ON"))

    # Javobsiz holatlarda dalil BO'LMASLIGI shart — aks holda ular
    # "javobsiz" emas edi.
    javobsiz = [c for c in cases() if c["kutilgan"]["tur"] == "topilmadi"]
    for c in javobsiz:
        check(f"{c['id']}: javobsiz holatda dalil YO'Q",
              not c["kutilgan"].get("manba_matn"))


def test_bazaviy_fayl():
    section("Bazaviy o'lchov fayli")
    check("bazaviy JSON mavjud", os.path.exists(BASELINE), BASELINE)
    if not os.path.exists(BASELINE):
        return None
    b = json.loads(io.open(BASELINE, encoding="utf-8").read())
    for k in ("k", "usullar", "iqtibos", "cheklovlar", "sana"):
        check(f"bazaviy faylda '{k}' bor", k in b)
    check("uchala usul ham o'lchangan",
          set(b["usullar"]) == {"leksik", "semantik", "gibrid"},
          str(sorted(b["usullar"])))
    for u, d in b["usullar"].items():
        for m in ("recall_at_k", "precision_at_k", "mrr", "ndcg_at_k"):
            check(f"{u}: '{m}' hisoblangan", d.get(m) is not None, str(d.get(m)))
    # T-2: QAYSI QATLAM O'LCHANMAGANI ANIQ YOZILGAN bo'lsin.
    #
    # Reyestrda T-2 "RAG qatlamlari O'LCHANMAGAN" deb yozilgan edi
    # va bu ANIQ EMAS: qidiruv va iqtibos O'LCHANADI (modelsiz),
    # faqat javob/tool/gallyutsinatsiya o'lchanmaydi. Bu farq
    # yo'qolsa, "hech narsa o'lchanmagan" degan yolg'on xulosa
    # qaytardi.
    matn = " ".join(b["cheklovlar"])
    check("javob/tool/gallyutsinatsiya O'LCHANMAGANI yozilgan",
          "O'LCHANMADI" in matn and "model chaqiruvi" in matn,
          matn[:120])
    # NAMUNA HAJMI OSHKOR: 7 javobli holatdagi 0.705 recall ni
    # statistik da'vo deb o'qib bo'lmaydi.
    check("namuna hajmi oshkor qilingan",
          isinstance(b.get("javobli_holat"), int) and b["javobli_holat"] > 0,
          str(b.get("javobli_holat")))
    check("namuna KICHIK ekani yozilgan", "NAMUNA KICHIK" in matn)
    # O'LCHANGAN qatlamlar HAM aniq: "hammasi o'lchanmagan" degan
    # teskari yolg'on ham chiqmasin.
    check("qidiruv metrikalari HAQIQATAN bor",
          all(m in b["usullar"]["gibrid"]
              for m in ("recall_at_k", "precision_at_k", "mrr", "ndcg_at_k")),
          str(sorted(b["usullar"]["gibrid"].keys()))[:100])
    check("iqtibos o'lchovi bor", "citation_hit_rate" in b.get("iqtibos", {}))

    check("CHEKLOVLAR ro'yxati BO'SH EMAS", len(b["cheklovlar"]) >= 3,
          "past metrika va cheklovlar YASHIRILMAYDI")
    # O'LCHANMAGAN QATLAMLAR ANIQ AYTILGAN.
    matn = " ".join(b["cheklovlar"])
    check("o'lchanmagan qatlamlar (javob/tool/gallyutsinatsiya) AYTILGAN",
          "O'LCHANMADI" in matn or "o'lchanmadi" in matn.lower())
    return b


def test_regressiya(b):
    section(f"Regressiya — metrika {TOLERANS:.0%} dan ko'p pasaymadi")
    if b is None:
        check("bazaviy fayl kerak", False, "o'tkazib yuborildi")
        return
    r = subprocess.run(
        [sys.executable, EVAL, "--json",
         os.path.join(ROOT, "_tests", "ai_eval", "results", "_joriy.json")],
        capture_output=True, text=True, encoding="utf-8",
        errors="backslashreplace", cwd=ROOT, timeout=900)
    if r.returncode != 0:
        check("baholash yurdi", False, (r.stderr or "")[-300:])
        return
    joriy_yol = os.path.join(ROOT, "_tests", "ai_eval", "results", "_joriy.json")
    j = json.loads(io.open(joriy_yol, encoding="utf-8").read())
    check("baholash yurdi", True)

    for u in ("leksik", "semantik", "gibrid"):
        for m in ("recall_at_k", "mrr", "ndcg_at_k"):
            eski, yangi = b["usullar"][u].get(m), j["usullar"][u].get(m)
            if eski is None or yangi is None:
                continue
            check(f"{u}.{m}: pasaymadi ({eski:.3f} -> {yangi:.3f})",
                  yangi >= eski - TOLERANS,
                  f"pasayish {eski - yangi:.3f} > tolerans {TOLERANS}")

    e_iq = (b["iqtibos"] or {}).get("citation_hit_rate")
    y_iq = (j["iqtibos"] or {}).get("citation_hit_rate")
    if e_iq is not None and y_iq is not None:
        check(f"citation hit rate pasaymadi ({e_iq:.3f} -> {y_iq:.3f})",
              y_iq >= e_iq - TOLERANS)

    # GIBRID ENG YAXSHI BO'LIB QOLSIN — bu arxitektura qarori va
    # u o'lchov bilan himoyalanadi.
    g = j["usullar"]["gibrid"]
    check("gibrid MRR leksik va semantikadan past emas",
          g["mrr"] >= max(j["usullar"]["leksik"]["mrr"],
                          j["usullar"]["semantik"]["mrr"]) - 1e-9,
          f"gibrid={g['mrr']:.3f} leksik={j['usullar']['leksik']['mrr']:.3f} "
          f"semantik={j['usullar']['semantik']['mrr']:.3f}")
    # IKKALA faylni ham tozalaymiz. `rag_eval.py` JSON yonida `.txt`
    # ham yozadi va faqat JSON o'chirilsa `.txt` ishchi daraxtda
    # qolib ketardi — kuzatilmagan artefakt.
    for yol in (joriy_yol, os.path.splitext(joriy_yol)[0] + ".txt"):
        try:
            os.remove(yol)
        except OSError:
            pass


# =====================================================================
def main():
    ap = argparse.ArgumentParser(description="RAG baholash regressiyasi")
    rejim.bayroqlar(ap)
    args = rejim.moslash(ap.parse_args())

    print("=" * 70)
    print("SINOV: RAG BAHOLASH BAZAVIY O'LCHOVI")
    print("=" * 70)

    test_toplam_shakli()
    b = test_bazaviy_fayl()

    conn = None
    if psycopg2 and os.environ.get("XT_DB_DSN"):
        try:
            conn = psycopg2.connect(os.environ["XT_DB_DSN"], connect_timeout=8)
            conn.autocommit = True
        except Exception as e:                                # noqa: BLE001
            print(f"  [i] baza yetib bo'lmadi: {str(e)[:80]}")

    test_ground_truth(conn)

    if args.bazasiz:
        print("\n[i] --offline: sizish va regressiya tekshiruvi "
              "o'tkazib yuborildi (baholash ~30 s oladi).")
    else:
        test_sizib_chiqish()
        test_regressiya(b)

    if conn:
        conn.close()

    otdi = sum(1 for _n, ok, _d in _results if ok)
    jami = len(_results)
    print("\n" + "=" * 70)
    for n, ok, d in _results:
        if not ok:
            print(f"  YIQILDI: {n}" + (f" -- {d}" if d else ""))
    print(f"NATIJA: {otdi}/{jami} o'tdi")
    print("=" * 70)
    sys.exit(0 if otdi == jami else 1)


if __name__ == "__main__":
    main()
