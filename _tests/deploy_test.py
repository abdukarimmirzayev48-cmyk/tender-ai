#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SINOV: JOYLASHTIRISH ARTEFAKTLARI
==================================

Joylashtirish fayllari kod bilan birga eskiradi va buni HECH NARSA
ko'rsatmaydi — ular faqat serverda ishlaydi. Bu to'plam ularni
repozitoriyada tekshiradi.

HAR TEKSHIRUV AYNAN BITTA TALABGA bog'langan (foydalanuvchi
mezonlari):

  1. Sir repozitoriyaga TUSHMASIN
  2. Ommaviy havolada `localhost` BO'LMASIN
  3. Serverni qayta yuklash hamma xizmatni TIKLASIN
  4. ETL kirgan seanssiz DAVOM ETSIN
  5. Zaxira BOR va tiklash SINALGAN
  6. Ishlab chiqarishga staging'siz joylashtirib BO'LMASIN

Ishga tushirish:
    .venv\\Scripts\\python.exe _tests\\deploy_test.py
    .venv\\Scripts\\python.exe _tests\\deploy_test.py --offline
"""
from __future__ import annotations

import argparse
import io
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import konsol  # noqa: E402
import rejim  # noqa: E402

konsol.sozla()

_natija = []
D = os.path.join(ROOT, "deploy")


def check(nom, ok, tafsilot=""):
    _natija.append((nom, ok, tafsilot))
    print(f"  [{'PASS' if ok else 'FAIL'}] {nom}" + (f" -- {tafsilot}" if tafsilot else ""))
    return ok


def bolim(t):
    print(f"\n--- {t} ---")


def oqi(*p):
    return io.open(os.path.join(D, *p), encoding="utf-8").read()


# =====================================================================
def test_tuzilma():
    bolim("1. Fayllar joyida")
    kerak = [
        ("systemd", "tenderai-api@.service"),
        ("systemd", "tenderai-etl@.service"),
        ("systemd", "tenderai-etl@.timer"),
        ("systemd", "tenderai-backup@.service"),
        ("systemd", "tenderai-backup@.timer"),
        ("systemd", "tenderai-restore-test@.service"),
        ("systemd", "tenderai-restore-test@.timer"),
        ("caddy", "Caddyfile"),
        ("bin", "deploy.sh"), ("bin", "rollback.sh"), ("bin", "backup.sh"),
        ("bin", "restore-test.sh"), ("bin", "health-check.sh"),
        ("bin", "bootstrap.sh"),
        ("env", "staging.env.example"), ("env", "production.env.example"),
    ]
    for p in kerak:
        check("/".join(p), os.path.exists(os.path.join(D, *p)))


def test_sirlar():
    bolim("2. SIR REPOZITORIYAGA TUSHMASIN")
    # `deploy/env/*.env` chetlatilganmi (namunalar esa kuzatiladi).
    gi = io.open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read()
    check("`deploy/env/*.env` chetlatilgan", "deploy/env/*.env" in gi)
    check("`*.env.example` istisno qilingan", "!deploy/env/*.env.example" in gi)

    r = subprocess.run(["git", "ls-files", "deploy/"], capture_output=True,
                       text=True, cwd=ROOT, encoding="utf-8", errors="replace")
    kuzatilgan = [f for f in r.stdout.split() if f]
    yomon = [f for f in kuzatilgan
             if f.endswith(".env") and not f.endswith(".env.example")]
    check("kuzatilgan `.env` fayli YO'Q", not yomon, str(yomon))

    # HAQIQIY qiymat naqshlari. Namunada `REPLACE` va bo'sh qiymatlar
    # bo'lishi KUTILGAN — ular sir emas.
    pats = {
        "anthropic": re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
        "telegram": re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_-]{33}\b"),
        "aws": re.compile(r"AKIA[0-9A-Z]{16}"),
        "shaxsiy_kalit": re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"),
        "dsn_parol": re.compile(r"password=(?!REPLACE)(?!$)\S{6,}"),
        "bcrypt": re.compile(r"\$2[aby]\$\d\d\$(?!REPLACE)[./A-Za-z0-9]{50,}"),
    }
    topildi = []
    for dirpath, _dn, fnames in os.walk(D):
        for fn in fnames:
            p = os.path.join(dirpath, fn)
            t = io.open(p, encoding="utf-8", errors="ignore").read()
            for nom, rx in pats.items():
                if rx.search(t):
                    topildi.append(f"{os.path.relpath(p, ROOT)} [{nom}]")
    check("`deploy/` da haqiqiy sir naqshi YO'Q", not topildi, str(topildi[:3]))

    # Sirlar FAYLDAN o'qilsin, birlik faylida YOZILMASIN.
    api = oqi("systemd", "tenderai-api@.service")
    check("sirlar `EnvironmentFile` dan", "EnvironmentFile=/etc/tenderai/" in api)
    check("birlik faylida parol/kalit YOZILMAGAN",
          not re.search(r"Environment=.*(PASSWORD|API_KEY|TOKEN|DSN)=", api))


def test_localhost():
    bolim("3. OMMAVIY HAVOLADA `localhost` BO'LMASIN")
    # ASOSIY nom 19-vazifada `APP_PUBLIC_URL` ga o'tdi va tanlash
    # mantig'i `api/ommaviy_url.py` ga ko'chdi (yagona manba).
    # BATAFSIL tekshiruv `_tests/ommaviy_url_test.py` da; bu yerda
    # joylashtirish ARTEFAKTLARI tekshiriladi.
    for muhit in ("production", "staging"):
        s = oqi("env", f"{muhit}.env.example")
        m = re.search(r"^APP_PUBLIC_URL=(.*)$", s, re.M)
        check(f"`APP_PUBLIC_URL` {muhit} namunasida bor", bool(m))
        if m:
            u = m.group(1).strip()
            check(f"{muhit} `APP_PUBLIC_URL` mahalliy EMAS",
                  "localhost" not in u and "127.0.0.1" not in u, u)
            check(f"{muhit} `APP_PUBLIC_URL` HTTPS", u.startswith("https://"), u)

    # KOD DARAJASIDA: `dev` dan boshqa muhitda mahalliy havola
    # yuborilmasin — va bu ISHGA TUSHISHDA tekshirilsin, yuborishda
    # emas: aks holda noto'g'ri sozlama soatlab ko'rinmasdi.
    src = io.open(os.path.join(ROOT, "api", "ommaviy_url.py"),
                  encoding="utf-8").read()
    check("`bazani_tekshir()` mavjud", "def bazani_tekshir" in src)
    check("`ishga_tushishda_tekshir()` mavjud",
          "def ishga_tushishda_tekshir" in src)
    nsrc = io.open(os.path.join(ROOT, "api", "notify.py"),
                   encoding="utf-8").read()
    check("`card_url()` yagona quruvchidan o'tadi",
          re.search(r"def card_url.*?ommaviy_url\.havola\(", nsrc, re.S)
          is not None)
    msrc = io.open(os.path.join(ROOT, "api", "main.py"),
                   encoding="utf-8").read()
    check("qo'rovul `lifespan` ga ulangan",
          "ommaviy_url.ishga_tushishda_tekshir()" in msrc)

    # QURILMA: mahalliy manzil frontend qurilmasiga ham singib
    # qolardi (o'lchangan: `localhost:8000` x1, `localhost:5173` x3).
    d = oqi("bin", "deploy.sh")
    check("joylashtirish qurilma NATIJASINI tekshiradi",
          "frontend/dist/assets" in d and "MAHALLIY manzil bor" in d)


def test_qayta_yuklash():
    bolim("4. SERVERNI QAYTA YUKLASH HAMMA XIZMATNI TIKLASIN")
    api = oqi("systemd", "tenderai-api@.service")
    check("API `Restart=always`", "Restart=always" in api)
    check("API `WantedBy=multi-user.target`", "WantedBy=multi-user.target" in api)
    # Cheksiz qayta urinish jurnalni to'ldirib sababni ko'mib tashlardi.
    check("qayta urinish CHEKLANGAN (`StartLimitBurst`)",
          "StartLimitBurst=" in api)
    check("to'xtatishda so'rov tugatiladi (`SIGINT` + timeout)",
          "KillSignal=SIGINT" in api and "TimeoutStopSec=" in api)

    for nom in ("etl", "backup", "restore-test"):
        t = oqi("systemd", f"tenderai-{nom}@.timer")
        check(f"`{nom}` timer `WantedBy=timers.target`",
              "WantedBy=timers.target" in t)


def test_etl_seanssiz():
    bolim("5. ETL KIRGAN SEANSSIZ DAVOM ETSIN")
    svc = oqi("systemd", "tenderai-etl@.service")
    tmr = oqi("systemd", "tenderai-etl@.timer")
    # systemd xizmati SEANSGA bog'liq emas — Windows Task Scheduler'da
    # `LogonType=Interactive` aynan shu sababdan yurishlarni o'ldirgan.
    check("`User=tenderai` (tizim foydalanuvchisi)", "User=tenderai" in svc)
    check("`Type=oneshot`", "Type=oneshot" in svc)
    # Mashina o'chgan bo'lsa — yoqilganda O'TKAZIB YUBORILGANI bajariladi.
    check("`Persistent=true` (o'tkazib yuborilgan yurish bajariladi)",
          "Persistent=true" in tmr)
    check("soatlik jadval", "OnCalendar=" in tmr)
    # Ikki muhit BIR VAQTDA manbaga urilmasin.
    check("tasodifiy kechikish bor", "RandomizedDelaySec=" in tmr)
    # ETL o'zi TOZA to'xtasin; systemd timeout — faqat oxirgi to'siq.
    check("vaqt byudjeti ILOVAGA beriladi (`--max-seconds`)",
          "--max-seconds" in svc)
    check("ETL da `Restart=no` (timer qayta uradi)", "Restart=no" in svc)


def test_zaxira():
    bolim("6. ZAXIRA BOR VA TIKLASH SINALGAN")
    b = oqi("bin", "backup.sh")
    check("`pg_dump` maxsus formatda", "--format=custom" in b)
    # Buzuq dump faqat tiklash paytida bilinardi — eng yomon paytda.
    check("dump OCHILISHI darhol tekshiriladi", "pg_restore --list" in b)
    check("buzuq dump O'CHIRILADI", "rm -f" in b and "OCHILMADI" in b)
    check("sha256 yoziladi", "sha256sum" in b)
    check("eski zaxiralar tozalanadi", "-mtime" in b)

    r = oqi("bin", "restore-test.sh")
    check("tiklash mashqi VAQTINCHALIK bazaga", "SINOV_BAZA=" in r)
    # Bu tekshiruv bo'lmasa mashq ishlab chiqarishni yo'q qilardi.
    check("ishlab chiqarish bazasi bilan ADASHMASLIK tekshiruvi",
          "BIR XIL" in r and "ASOSIY_BAZA" in r)
    check("sha256 tekshiriladi", "sha256sum -c" in r)
    check("tiklash VAQTI o'lchanadi (RTO)", "RTO" in r)
    check("jadval/qator soni tekshiriladi", "N_JADVAL" in r and "N_TENDER" in r)
    check("pgvector tiklanganmi tekshiriladi", "pg_extension" in r)
    check("vaqtinchalik baza TASHLANADI", "DROP DATABASE" in r)

    t = oqi("systemd", "tenderai-restore-test@.timer")
    check("tiklash mashqi JADVALDA (haftalik)", "OnCalendar=Sun" in t)


def test_staging_birinchi():
    bolim("7. ISHLAB CHIQARISHGA STAGING'SIZ JOYLASHTIRIB BO'LMASIN")
    d = oqi("bin", "deploy.sh")
    check("production uchun staging tasdig'i TALAB qilinadi",
          ".verified" in d and "staging tasdigi yoq" in d)
    check("AYNAN SHU ref tekshirilgani solishtiriladi",
          "BOSHQA ref tekshirilgan" in d)
    check("tasdiq staging MUVAFFAQIYATLI tugagach yoziladi",
          re.search(r'if \[ "\$MUHIT" = "staging" \].*?\.verified', d, re.S) is not None)

    check("`current` simvolik havola (atomar almashtirish)", "ln -sfn" in d)
    check("sog'liq tekshiruvi o'tmasa AVTOMATIK qaytariladi",
          "orqaga qaytarilmoqda" in d)
    check("migratsiya EGASI roli bilan", "XT_DB_DSN_OWNER" in d)
    check("frontend QURILADI (dev-server emas)",
          "npm run build" in d and "npm run dev" not in d)

    r = oqi("bin", "rollback.sh")
    check("qaytarish atomar (`ln -sfn`)", "ln -sfn" in r)
    # Avtomatik `down` skript ma'lumot yo'qotishning eng qisqa yo'li.
    check("baza migratsiyasi QAYTARILMAYDI va sababi yozilgan",
          "QAYTARILMAYDI" in r and "ATAYLAB" in r)
    check("qaytargandan keyin sog'liq tekshiriladi", "health-check.sh" in r)


def test_proksi():
    bolim("8. Teskari proksi va HTTPS")
    c = oqi("caddy", "Caddyfile")
    check("staging va production sayti bor",
          c.count("import umumiy") >= 2)
    check("HSTS TLS TERMINATORIDA", "Strict-Transport-Security" in c)
    check("proksi `/ready` ni so'raydi", "health_uri /ready" in c)
    check("frontend STATIK `dist` dan", "frontend/dist" in c)
    check("dev-server ISHLATILMAYDI", ":5173" not in c)
    check("API faqat 127.0.0.1 ga proksi", "reverse_proxy 127.0.0.1:" in c)
    check("staging YOPIQ (basic_auth)", "basic_auth" in c)

    api = oqi("systemd", "tenderai-api@.service")
    check("uvicorn faqat 127.0.0.1 ga bog'lanadi",
          "--host 127.0.0.1" in api and "0.0.0.0" not in api)
    check("proksi sarlavhalari yoqilgan", "--proxy-headers" in api)


def test_sogliq():
    bolim("9. Sog'liq / tayyorlik / ETL yangiligi")
    src = io.open(os.path.join(ROOT, "api", "main.py"), encoding="utf-8").read()
    check("`/health` (tiriklik) bor", '@app.get("/health")' in src)
    check("`/ready` (tayyorlik) bor", '@app.get("/ready")' in src)
    check("`/ready` OCHIQ (proksi token ushlamaydi)",
          '"/ready",' in src[src.index("PUBLIC_PATHS = {"):
                             src.index("PUBLIC_PATHS = {") + 900])
    # Tayyor emas bo'lsa 503 — proksi shu kodga qarab kutadi.
    check("tayyor bo'lmasa 503", "status_code = 503" in src)
    # Ochiq endpoint tafsilot SIZDIRMASLIGI kerak.
    blok = src[src.index('@app.get("/ready")'):]
    blok = blok[:blok.index("\n\n\n")]
    check("`/ready` javobida tafsilot YO'Q",
          'v["holat"]' in blok and '"muhit": APP_ENV' not in blok)
    check("`/freshness` (ETL yangiligi) bor", '@app.get("/freshness")' in src)

    h = oqi("bin", "health-check.sh")
    for nom, naqsh in (("tiriklik", "/health"), ("tayyorlik", "/ready"),
                       ("ETL yangiligi", "/freshness"), ("baza", "psql")):
        check(f"sog'liq skripti `{nom}` ni tekshiradi", naqsh in h)
    # ETL hali yurmagan bo'lishi NORMAL — joylashtirish to'xtamasin.
    check("ETL tekshiruvi joylashtirishni TO'XTATMAYDI", "OGOH" in h)


def test_jurnal():
    bolim("10. Tuzilmali jurnal")
    p = os.path.join(ROOT, "api", "jurnal.py")
    check("`api/jurnal.py` mavjud", os.path.exists(p))
    if not os.path.exists(p):
        return
    from api import jurnal
    check("JSON formatlovchi bor", hasattr(jurnal, "JsonFormatter"))
    check("so'rov identifikatori bor", hasattr(jurnal, "yangi_sorov_id"))

    # SIR NIQOBLANADI — nomi bo'yicha, mazmuni bo'yicha emas.
    n = jurnal.niqobla({"password": "sir", "api_key": "sir",
                        "ichki": {"token": "sir"}, "yol": "/tenders"})
    check("`password` niqoblandi", n["password"] == jurnal.NIQOB)
    check("`api_key` niqoblandi", n["api_key"] == jurnal.NIQOB)
    check("ichki `token` ham niqoblandi", n["ichki"]["token"] == jurnal.NIQOB)
    check("oddiy maydon TEGILMAYDI", n["yol"] == "/tenders")

    api_src = io.open(os.path.join(ROOT, "api", "main.py"), encoding="utf-8").read()
    check("jurnal ishga tushishda sozlanadi", "jurnal.sozla()" in api_src)
    check("so'rov identifikatori javobga qo'yiladi", "X-Request-Id" in api_src)
    # `/health` har daqiqa so'raladi — jurnalni to'ldirmasin.
    check("sog'liq so'rovlari jurnalni to'ldirmaydi", "shovqin" in api_src)

    svc = oqi("systemd", "tenderai-api@.service")
    check("jurnal `journald` ga", "StandardOutput=journal" in svc)
    check("uvicorn kirish jurnali O'CHIQ (ikki marta yozilmasin)",
          "--no-access-log" in svc)
    stg = oqi("env", "staging.env.example")
    check("`LOG_FORMAT=json` joylashtirishda", "LOG_FORMAT=json" in stg)


# =====================================================================
def test_url_qorovuli():
    bolim("11. `localhost` qo'rovuli — HAQIQIY xulq")
    import importlib
    eski_env = os.environ.get("APP_ENV")
    eski_url = os.environ.get("PUBLIC_BASE_URL")
    try:
        from api import notify

        os.environ["APP_ENV"] = "production"
        os.environ.pop("PUBLIC_BASE_URL", None)
        importlib.reload(notify)
        try:
            notify.card_url("http://localhost:5173", 42)
            check("production da mahalliy havola TO'XTATILADI", False,
                  "o'tib ketdi")
        except notify.NotifyError:
            check("production da mahalliy havola TO'XTATILADI", True)

        os.environ["PUBLIC_BASE_URL"] = "https://tender.example.uz"
        importlib.reload(notify)
        u = notify.card_url("http://localhost:5173", 42)
        check("bazadagi mahalliy qiymat MUHIT bilan almashtiriladi",
              u.startswith("https://tender.example.uz"), u)

        os.environ["APP_ENV"] = "dev"
        os.environ.pop("PUBLIC_BASE_URL", None)
        importlib.reload(notify)
        u = notify.card_url("http://localhost:5173", 42)
        check("`dev` da mahalliy havola RUXSAT (ishlab chiqish)",
              "localhost" in u, u)
    finally:
        if eski_env is None:
            os.environ.pop("APP_ENV", None)
        else:
            os.environ["APP_ENV"] = eski_env
        if eski_url is None:
            os.environ.pop("PUBLIC_BASE_URL", None)
        else:
            os.environ["PUBLIC_BASE_URL"] = eski_url
        from api import notify as n2
        importlib.reload(n2)


def test_muhit_fayli_shellda():
    """Muhit fayli SHELL bilan o'qilganda BUZILMASIN (B-1)."""
    bolim("13. MUHIT FAYLI — ikki parser, bitta fayl")

    # O'LCHANGAN NUQSON (2026-09-01). `XT_DB_DSN` TIRNOQSIZ edi va
    # bitta fayl IKKI XIL o'qilardi:
    #
    #   systemd `EnvironmentFile=`   butun qatorni oladi  -> TO'G'RI
    #   shell `. envfile`            birinchi bo'shliqda  -> BUZILADI
    #                                kesadi
    #
    # Ya'ni API xizmati to'g'ri DSN olardi, `backup.sh` /
    # `restore-test.sh` / `deploy.sh` esa `dbname=...` ni — user,
    # parol va host YO'QOLGAN holda. Qolgani shellda O'ZGARUVCHI
    # TAYINLASH bo'lib ketardi, ya'ni XATO HAM BERMASDI.
    #
    # Bu skriptlar hech qachon yurgizilmagani uchun payqalmagan.
    # SHELL XULQI `shlex` BILAN TAQLID QILINADI, `bash` CHAQIRILMAYDI.
    #
    # SABAB O'LCHANDI: Windows'da `subprocess` ["bash", ...] ni WSL
    # bash iga yuboradi (`C:\Windows\System32\bash.exe`), Git Bash
    # ga emas — va u yiqiladi. Ya'ni sinov MUHITGA bog'liq bo'lib
    # qolardi va CI da jimgina o'tib ketishi mumkin edi.
    #
    # `shlex` POSIX so'z ajratish qoidasini AYNAN bajaradi: agar
    # `VAR=qiymat` o'ng tomoni bir nechta so'zga bo'linsa, shell
    # faqat BIRINCHISINI tayinlaydi — qolgani yo'qoladi.
    import shlex

    def shellda(matn):
        """Muhit faylini SHELL qanday o'qisa, shunday o'qiydi."""
        out = {}
        for qator in matn.split(chr(10)):
            q = qator.strip()
            if not q or q.startswith("#") or "=" not in q:
                continue
            nom, _, xom = q.partition("=")
            if not nom.replace("_", "").isalnum():
                continue
            try:
                bolaklar = shlex.split(xom, posix=True)
            except ValueError:
                bolaklar = [xom]
            # Shell BIRINCHI so'zni tayinlaydi; qolgani boshqa
            # tayinlash yoki buyruq bo'lib ketadi.
            out[nom] = bolaklar[0] if bolaklar else ""
        return out

    for muhit in ("production", "staging"):
        d = shellda(oqi("env", f"{muhit}.env.example"))
        dsn = d.get("XT_DB_DSN", "")
        egasi = d.get("XT_DB_DSN_OWNER", "")
        url = d.get("APP_PUBLIC_URL", "")
        # DSN da user/parol/host BO'LISHI shart — kesilgan bo'lsa
        # faqat `dbname=...` qoladi.
        for qism in ("user=", "password=", "host="):
            check(f"{muhit}: shellda `{qism}` YO'QOLMADI", qism in dsn,
                  f"olingan: {dsn[:60]!r}")
        check(f"{muhit}: `XT_DB_DSN_OWNER` bor va to'liq",
              "user=" in egasi and "host=" in egasi,
              f"olingan: {egasi[:60]!r}")
        check(f"{muhit}: `APP_PUBLIC_URL` o'qildi", url.startswith("https://"),
              f"olingan: {url[:40]!r}")

    # TAQLIDNING O'ZI SINALADI. Aks holda `shellda()` har doim
    # to'liq qiymat qaytarsa ham sinov yashil bo'lardi.
    soxta = shellda('A=dbname=x user=y host=z' + chr(10)
                    + 'B="dbname=x user=y host=z"')
    check("taqlid TIRNOQSIZ qiymatni KESADI", soxta["A"] == "dbname=x",
          soxta["A"])
    check("taqlid TIRNOQLI qiymatni BUTUN qoldiradi",
          soxta["B"] == "dbname=x user=y host=z", soxta["B"])

    # `deploy.sh` va `restore-test.sh` AYNAN shu faylni SOURCE
    # qiladi — ya'ni yuqoridagi buzilish ularga TO'G'RIDAN-TO'G'RI
    # tegishli.
    for skript in ("deploy.sh", "restore-test.sh", "backup.sh"):
        src = oqi("bin", skript)
        check(f"`{skript}` muhit faylini source qiladi",
              '. "$ENVFILE"' in src)

    # MASHQ QILISH MUMKINMI: yo'l qotirilgan bo'lsa skriptni
    # serverdan tashqarida umuman yurgizib bo'lmaydi — aynan
    # shuning uchun ular hech qachon bajarilmagan edi.
    for skript in ("backup.sh", "restore-test.sh"):
        src = oqi("bin", skript)
        check(f"`{skript}` muhit yo'li ALMASHTIRILADI (mashq uchun)",
              "TENDERAI_ENVFILE" in src)


def test_hujjat():
    bolim("12. Joylashtirish hujjati")
    p = os.path.join(ROOT, "docs", "deploy.md")
    check("`docs/deploy.md` mavjud", os.path.exists(p))
    if not os.path.exists(p):
        return
    d = io.open(p, encoding="utf-8").read()
    for nom, naqsh in (
            ("staging birinchi", "staging"),
            ("orqaga qaytarish", "rollback"),
            ("zaxira va tiklash", "restore-test"),
            ("sirlar", "/etc/tenderai/"),
            ("baza roli", "tai_app"),
            ("HTTPS", "Caddy"),
            ("tiklash mashqi natijasi", "RTO")):
        check(f"hujjatda `{nom}` bor", naqsh in d)


# =====================================================================
def main():
    ap = argparse.ArgumentParser(description="Joylashtirish sinovi")
    rejim.bayroqlar(ap)
    rejim.moslash(ap.parse_args())

    print("=" * 70)
    print("SINOV: JOYLASHTIRISH ARTEFAKTLARI")
    print("=" * 70)

    test_tuzilma()
    test_sirlar()
    test_localhost()
    test_qayta_yuklash()
    test_etl_seanssiz()
    test_zaxira()
    test_staging_birinchi()
    test_proksi()
    test_sogliq()
    test_jurnal()
    test_url_qorovuli()
    test_muhit_fayli_shellda()
    test_hujjat()

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
