#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETL ISHONCHLILIGI — qayta urinish, checkpoint, HTTP va halol metrika
=====================================================================

NEGA BU MODUL BOR (o'lchangan, taxmin emas)
--------------------------------------------
2026-08-30 da `etl_run` ning 14 kunlik tahlili shuni ko'rsatdi:

    uzex     104 xato / 33 ok        xt-xarid   74 xato / 64 ok

Lekin 178 xatoning **154 tasi ETL xatosi emas**. Ular
`run_etl.close_stale_runs()` keyingi yurish boshida yopgan YETIM
`running` qatorlari: jarayon o'ldirilgan, qator yopilmay qolgan.
Faqat 22 tasi haqiqiy bola-jarayon nosozligi (0xC000013A).

Ya'ni ETL YIQILMAYDI — u **tugatishga ulgurmaydi**. Va tugatolmagani
uchun keyingi soatda NOLDAN boshlaydi va yana ulgurmaydi.

Uch tuzatish shu modulda:

  1. QAYTA BOSHLASH — `Checkpoint`. Uzilgan oqim qayerda to'xtaganini
     bazada saqlaydi.
  2. TASNIFLANGAN QAYTA URINISH — `Siyosat` + `tasnifla()`. Ilgari
     `except Exception` HAMMA narsani qayta urinardi, shu jumladan
     404 ni (hech qachon tuzalmaydi) — vaqt behuda ketardi.
  3. HALOL METRIKA — `Yurish`. Sanoqlar BAZAGA DARHOL yoziladi, oxirida
     emas. Jarayon o'ldirilsa ham o'lchov saqlanib qoladi.

ASOSIY TAMOYIL — O'LDIRISHNI USHLASHGA TAYANMAYMIZ
--------------------------------------------------
Windows'da `taskkill /F`, Modern Standby va kernel tashabbusidagi
o'chirishda Python HECH QANDAY kod bajarmaydi — `try/finally` ham,
signal ishlovchisi ham. Shuning uchun bu modul "chiroyli o'lish" ga
tayanmaydi: holat HAR QADAMDA bazaga yoziladi, ya'ni eng yomon holatda
bir necha yozuvlik ish yo'qoladi (va u ham IDEMPOTENT, qaytadan
bajarilsa dublikat bermaydi).

Signal ishlovchisi baribir bor, lekin u FAQAT BONUS: ushlash imkoni
bo'lgan holatlarda (Ctrl+C, SIGTERM) yurish darrov emas, joriy yozuvni
tugatib to'xtaydi.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import requests
    from requests.adapters import HTTPAdapter
except ImportError:                                          # pragma: no cover
    requests = None                                          # type: ignore
    HTTPAdapter = object                                     # type: ignore

try:
    import psycopg2
    from psycopg2.extras import Json
except ImportError:                                          # pragma: no cover
    psycopg2 = None                                          # type: ignore
    Json = None                                              # type: ignore


# =====================================================================
# 0) CHIQISHNI XAVFSIZ QILISH
# =====================================================================
def chiqishni_sozla() -> None:
    """stdout/stderr ni UTF-8 ga o'tkazadi, xatoni `replace` qiladi.

    O'LCHANGAN NUQSON (2026-08-30): `etl_uzex.py` ni to'g'ridan-to'g'ri
    konsoldan yurgizganda TENDER NOMINI chop etish paytida yiqilardi:

        UnicodeEncodeError: 'charmap' codec can't encode '\\u04b3'

    Windows konsoli cp1251, tender nomlari esa o'zbek kirill (ҳ) va
    boshqa belgilarni o'z ichiga oladi. Ya'ni CHOP ETISH butun ETLni
    o'ldirardi — jurnal yozuvi ish jarayonini yiqitgan.

    `run_etl.py` bolalarga `PYTHONIOENCODING=utf-8` beradi, shuning
    uchun rejalashtirilgan yurishda muammo ko'rinmasdi va shu sababli
    UZOQ VAQT payqalmadi. Aynan shu sinf `_tests/import_test.py` ni
    ham to'liq ishlamas holga keltirgan (u hech narsani tekshirmaydi).

    `errors="replace"` ATAYLAB: chop etib bo'lmaydigan belgi `?` ga
    aylanadi, lekin ISH TO'XTAMAYDI. Ma'lumot bazaga to'liq yoziladi —
    faqat konsol ko'rinishi kambag'allashadi.
    """
    for oqim in (sys.stdout, sys.stderr):
        try:
            oqim.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):         # pragma: no cover
            pass          # quvur yoki qayta yo'naltirilgan chiqish


# =====================================================================
# 1) XATO TASNIFI
# =====================================================================
#
# Qaysi xato qayta urinishdan TUZALADI, qaysisi YO'Q. Bu ro'yxat
# ATAYLAB QISQA va ATAYLAB OQ RO'YXAT (whitelist): notanish xato
# DOIMIY deb hisoblanadi.
#
# NEGA OQ RO'YXAT: teskarisi ("notanish -> qayta urin") aynan hozirgi
# `etl_tenders.rpc_call` xatti-harakati va u 404 ni ham to'rt marta
# urinib, har safar eksponensial kutib o'tirardi. Notanish xatoni
# qayta urinish — "balki o'zi tuzaladi" degan TAXMIN.

#: HTTP holat kodlari — qayta urinishdan tuzalishi MUMKIN.
QAYTA_URINILADIGAN_KODLAR = frozenset({
    408,   # Request Timeout
    425,   # Too Early
    429,   # Too Many Requests — Retry-After hurmat qilinadi
    500, 502, 503, 504,
})

#: HTTP holat kodlari — qayta urinish FOYDASIZ. Ro'yxat to'liq emas;
#: bu yerda YO'Q bo'lgan 4xx ham doimiy deb qaraladi (yuqoridagi
#: oq ro'yxatga kirmagani uchun). Bu ro'yxat faqat XABAR uchun.
DOIMIY_KODLAR = frozenset({400, 401, 403, 404, 405, 409, 410, 422})


class ManbaXato(Exception):
    """Manba bilan bog'liq xato — qayta urinsa bo'ladimi, aytadi.

    `kutish` — manba O'ZI aytgan kutish vaqti (Retry-After). None
    bo'lsa siyosat bo'yicha eksponensial kutish ishlatiladi.
    """

    def __init__(self, xabar: str, *, qayta_urinsa: bool,
                 kutish: Optional[float] = None,
                 kod: Optional[int] = None) -> None:
        super().__init__(xabar)
        self.qayta_urinsa = qayta_urinsa
        self.kutish = kutish
        self.kod = kod


class YozuvXato(Exception):
    """BITTA yozuvning xatosi — butun yurishni to'xtatmaydi.

    Ataylab `ManbaXato` dan alohida: manba xatosi butun oqimga tegishli
    (masalan 503 — server tushgan), yozuv xatosi esa faqat o'sha
    yozuvga (buzuq JSON, yetishmagan maydon).
    """

    def __init__(self, xabar: str, *, yozuv_id: Any = None) -> None:
        super().__init__(xabar)
        self.yozuv_id = yozuv_id


def _retry_after(resp: Any) -> Optional[float]:
    """`Retry-After` sarlavhasini soniyaga o'giradi.

    Faqat SON shakli qo'llab-quvvatlanadi. HTTP-sana shakli ham
    standartda bor, lekin uni to'g'ri o'qish uchun server vaqti bilan
    bizning soat farqini bilish kerak — bilmaymiz, shuning uchun
    TAXMIN QILMAYMIZ va siyosat bo'yicha kutamiz.
    """
    try:
        xom = resp.headers.get("Retry-After")
    except AttributeError:
        return None
    if not xom:
        return None
    try:
        n = float(str(xom).strip())
    except (TypeError, ValueError):
        return None
    # Manba juda uzun kutish so'rasa ham soatlik jadvalni bloklamaymiz.
    return max(0.0, min(n, 300.0))


def tasnifla(exc: BaseException) -> ManbaXato:
    """Istisnoni `ManbaXato` ga aylantiradi: qayta urinsa bo'ladimi?

    KENG `except` EMAS: bu yerda istisno YUTILMAYDI, faqat TASNIFLANADI.
    Chaqiruvchi baribir uni ko'radi va hisobga oladi.
    """
    if isinstance(exc, ManbaXato):
        return exc

    if requests is not None:
        # Ulanish va o'qish timeoutlari — TARMOQ, qayta urinsa bo'ladi.
        if isinstance(exc, (requests.exceptions.ConnectTimeout,
                            requests.exceptions.ConnectionError)):
            return ManbaXato(f"ulanish xatosi: {str(exc)[:160]}", qayta_urinsa=True)
        if isinstance(exc, requests.exceptions.ReadTimeout):
            return ManbaXato(f"o'qish timeouti: {str(exc)[:160]}", qayta_urinsa=True)
        if isinstance(exc, requests.exceptions.Timeout):
            return ManbaXato(f"timeout: {str(exc)[:160]}", qayta_urinsa=True)

        if isinstance(exc, requests.exceptions.HTTPError):
            resp = getattr(exc, "response", None)
            kod = getattr(resp, "status_code", None)
            if kod in QAYTA_URINILADIGAN_KODLAR:
                return ManbaXato(f"HTTP {kod}", qayta_urinsa=True,
                                 kutish=_retry_after(resp), kod=kod)
            return ManbaXato(f"HTTP {kod} — doimiy", qayta_urinsa=False, kod=kod)

    # Buzuq JSON. Manba xato paytida HTML sahifa qaytarishi kuzatilgan
    # (proksi/balanser), shuning uchun bu O'TKINCHI deb qaraladi —
    # lekin urinishlar soni bilan CHEGARALANGAN, cheksiz emas.
    if isinstance(exc, (json.JSONDecodeError, ValueError)) and "JSON" in str(exc).upper():
        return ManbaXato(f"buzuq JSON: {str(exc)[:160]}", qayta_urinsa=True)

    # NOTANISH XATO -> DOIMIY. "Balki o'zi tuzalar" degan taxmin
    # qilinmaydi; xato matni saqlanadi va ko'rinadi.
    return ManbaXato(f"{type(exc).__name__}: {str(exc)[:160]}", qayta_urinsa=False)


# =====================================================================
# 2) QAYTA URINISH SIYOSATI
# =====================================================================
@dataclass(frozen=True)
class Siyosat:
    """Eksponensial kutish + jitter + maksimal urinish.

    JITTER NEGA KERAK: bir vaqtda ikki oqim (TypeId=1 va TypeId=2)
    bir xil xatoga uchrasa, jittersiz ular AYNAN bir vaqtda qayta
    urinadi va manbaga to'lqin bo'lib uriladi. Jitter ularni tarqatadi.

    `jitter=0.0` — sinov uchun: kutish deterministik bo'ladi.
    """
    urinishlar: int = 4          # jami urinish (1 asosiy + 3 qayta)
    asos: float = 1.0            # birinchi kutish, sekund
    koeff: float = 2.0           # eksponensial koeffitsient
    max_kutish: float = 60.0     # bitta kutishning yuqori chegarasi
    jitter: float = 0.25         # ±25%

    def kutish(self, urinish: int, tavsiya: Optional[float] = None,
               rng: Optional[random.Random] = None) -> float:
        """`urinish`-chi muvaffaqiyatsizlikdan keyin necha sekund kutamiz.

        `tavsiya` — manba aytgan `Retry-After`. U BOR bo'lsa ustun
        turadi: manba o'z yukini bizdan yaxshiroq biladi. Lekin u ham
        `max_kutish` bilan chegaralanadi, aks holda bitta 429 soatlik
        jadvalni to'xtatib qo'yardi.
        """
        if urinish < 1:
            raise ValueError("urinish 1 dan kichik bo'lolmaydi")
        if tavsiya is not None:
            asosiy = min(float(tavsiya), self.max_kutish)
        else:
            asosiy = min(self.asos * (self.koeff ** (urinish - 1)), self.max_kutish)
        if self.jitter <= 0:
            return asosiy
        r = rng or random
        return max(0.0, asosiy * (1.0 + r.uniform(-self.jitter, self.jitter)))


#: Standart siyosat — manba hostlariga nisbatan ehtiyotkor.
STANDART_SIYOSAT = Siyosat()


def qayta_urin(ish: Callable[[], Any], *,
               siyosat: Siyosat = STANDART_SIYOSAT,
               nom: str = "so'rov",
               uxla: Callable[[float], None] = time.sleep,
               ogohlantir: Optional[Callable[[str], None]] = None,
               toxtash: Optional[Callable[[], bool]] = None,
               hisob: Optional[Callable[[], None]] = None) -> Any:
    """`ish()` ni tasniflangan qayta urinish bilan bajaradi.

    QOIDA:
      * qayta urinsa bo'ladigan xato -> kutib qayta urinamiz
      * doimiy xato                  -> DARHOL ko'tariladi (vaqt behuda
                                        ketmasin)
      * urinishlar tugadi            -> oxirgi xato ko'tariladi

    `hisob` — har QAYTA urinishda chaqiriladi (metrikadagi `retried`).
    `toxtash` — to'xtash so'ralgan bo'lsa (Ctrl+C, vaqt byudjeti)
    kutishni bo'lib chiqamiz: uzoq kutish o'rtasida osilib qolmaslik uchun.
    """
    oxirgi: Optional[ManbaXato] = None
    for urinish in range(1, siyosat.urinishlar + 1):
        try:
            return ish()
        except BaseException as e:                           # noqa: BLE001
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            xato = tasnifla(e)
            oxirgi = xato
            if not xato.qayta_urinsa:
                raise xato from e
            if urinish >= siyosat.urinishlar:
                break
            kut = siyosat.kutish(urinish, xato.kutish)
            if ogohlantir:
                ogohlantir(f"{nom}: urinish {urinish}/{siyosat.urinishlar} "
                           f"muvaffaqiyatsiz ({xato}); {kut:.1f}s kutamiz")
            if hisob:
                hisob()
            _uxla_boluvchi(kut, uxla, toxtash)
    assert oxirgi is not None
    raise ManbaXato(f"{siyosat.urinishlar} urinishdan keyin ham: {oxirgi}",
                    qayta_urinsa=False, kod=oxirgi.kod)


def _uxla_boluvchi(kut: float, uxla: Callable[[float], None],
                   toxtash: Optional[Callable[[], bool]]) -> None:
    """Uzun kutishni 0.5 s bo'laklarga bo'lib uxlaydi.

    NEGA: 60 sekund kutayotganda Ctrl+C bosilsa yoki vaqt byudjeti
    tugasa, javob 60 sekunddan keyin kelardi. Bo'lib uxlash to'xtash
    so'rovini TEZ ko'radi.
    """
    if toxtash is None or kut <= 0.5:
        uxla(kut)
        return
    qolgan = kut
    while qolgan > 0:
        if toxtash():
            return
        bolak = min(0.5, qolgan)
        uxla(bolak)
        qolgan -= bolak


# =====================================================================
# 3) HTTP MIJOZ — pool, keep-alive, AJRATILGAN timeoutlar
# =====================================================================
#
# AUDIT TOPILMASI (2026-08-30): `etl_uzex.py` modul darajasidagi
# `requests.post/get` ni ishlatardi, ya'ni HAR SO'ROV uchun YANGI
# TCP+TLS qo'l berish. To'liq yurishda bu 623 ta ortiqcha handshake.
# `etl_tenders.py` va `etl_details.py` esa `requests.Session()`
# ishlatadi — bir xil manbaga ikki xil munosabat.
#
# Bundan tashqari ikkalasi ham `timeout=40` bergan, ya'ni BITTA son.
# `requests` uni ULANISH va O'QISH uchun bir xil qo'llaydi. Natijada
# tushgan host uchun ham 40 sekund kutardik, holbuki ulanish 5
# sekundda ma'lum bo'ladi. Endi ular AJRATILGAN.

#: (ulanish, o'qish) — sekundda.
STANDART_TIMEOUT: Tuple[float, float] = (8.0, 45.0)


def sessiya_yarat(*, pool: int = 8,
                  sarlavhalar: Optional[Dict[str, str]] = None) -> "requests.Session":
    """Keep-alive va ulanish poolli `requests.Session`.

    `max_retries=0` — ATAYLAB. urllib3 ning o'z retry mexanizmi
    xatolarni TASNIFLAMAYDI va bizning `retried` hisoblagichimizga
    ko'rinmaydi. Qayta urinish BITTA joyda — `qayta_urin()` da.
    Ikki qavat qayta urinish urinishlar sonini ko'paytirib yuborardi
    (4 x 3 = 12) va manbaga hurmatsizlik bo'lardi.
    """
    if requests is None:                                     # pragma: no cover
        raise RuntimeError("requests o'rnatilmagan")
    s = requests.Session()
    adapter = HTTPAdapter(pool_connections=pool, pool_maxsize=pool, max_retries=0)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    if sarlavhalar:
        s.headers.update(sarlavhalar)
    return s


def javob_json(resp: Any) -> Any:
    """HTTP javobini tekshirib JSON qaytaradi.

    `raise_for_status()` HTTPError ko'taradi, uni `tasnifla()` kod
    bo'yicha ajratadi. JSON buzuq bo'lsa ham ANIQ xato chiqadi —
    `None` qaytarilmaydi, chunki `None` chaqiruvchida "bo'sh natija"
    bilan aralashib ketardi.
    """
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError as e:
        matn = (resp.text or "")[:120].replace("\n", " ")
        raise ManbaXato(f"buzuq JSON (HTTP {resp.status_code}): {matn}",
                        qayta_urinsa=True, kod=resp.status_code) from e


# =====================================================================
# 4) TO'XTASH SO'ROVI — signal va vaqt byudjeti
# =====================================================================
class Toxtatgich:
    """To'xtash so'rovini bitta joyda yig'adi: signal + vaqt byudjeti.

    SIGNAL ISHLOVCHISI ISTISNO KO'TARMAYDI. Sabab: `KeyboardInterrupt`
    yozuvni saqlash o'rtasida kelsa tranzaksiya yarim qolardi.
    Bayroq qo'yiladi, halqa esa joriy yozuvni TUGATIB to'xtaydi.

    VAQT BYUDJETI NEGA KERAK (o'lchangan): uzex to'liq yurishi 12-20
    daqiqa, rejalashtiruvchi chegarasi esa 2 soat edi. Yurish o'z
    vaqtida TOZA to'xtamasa, uni Windows O'LDIRADI va checkpoint
    yozilmay qoladi. Byudjet o'lim o'rniga toza to'xtashni beradi.
    """

    def __init__(self, byudjet_sek: Optional[float] = None) -> None:
        self._bayroq = threading.Event()
        self._sabab: Optional[str] = None
        self._boshlandi = time.monotonic()
        self._byudjet = byudjet_sek if (byudjet_sek or 0) > 0 else None
        self._eski: Dict[int, Any] = {}

    # --- signal ---
    def signallarni_ulash(self) -> None:
        for nom in ("SIGINT", "SIGBREAK", "SIGTERM"):
            sig = getattr(signal, nom, None)
            if sig is None:
                continue
            try:
                self._eski[int(sig)] = signal.signal(sig, self._qabul)
            except (ValueError, OSError):
                pass            # asosiy oqim emas yoki platformada yo'q

    def _qabul(self, signum, frame) -> None:                 # noqa: ARG002
        self.sora("foydalanuvchi")

    # --- so'rov ---
    def sora(self, sabab: str) -> None:
        if self._sabab is None:
            self._sabab = sabab
        self._bayroq.set()

    def toxtaymi(self) -> bool:
        if self._bayroq.is_set():
            return True
        if self._byudjet is not None and self.otgan() >= self._byudjet:
            self.sora("vaqt_byudjeti")
            return True
        return False

    @property
    def sabab(self) -> Optional[str]:
        return self._sabab

    def otgan(self) -> float:
        return time.monotonic() - self._boshlandi

    def qolgan(self) -> Optional[float]:
        if self._byudjet is None:
            return None
        return max(0.0, self._byudjet - self.otgan())


# =====================================================================
# 5) BAZA YORDAMCHISI
# =====================================================================
def _ulan(dsn: Optional[str] = None):
    if psycopg2 is None:                                     # pragma: no cover
        raise RuntimeError("psycopg2 o'rnatilmagan")
    dsn = dsn or os.environ.get("XT_DB_DSN")
    if not dsn:
        raise RuntimeError("XT_DB_DSN o'rnatilmagan")
    conn = psycopg2.connect(dsn, connect_timeout=10)
    conn.autocommit = True
    return conn


class BazaYozuvchi:
    """Metrika va checkpoint uchun ALOHIDA, autocommit ulanish.

    NEGA ALOHIDA: asosiy ETL ulanishi yozuvlarni tranzaksiya ichida
    saqlaydi. Metrikani o'sha tranzaksiyaga qo'shsak, yozuv rollback
    bo'lganda O'LCHOV HAM YO'QOLARDI — ya'ni yiqilgan yozuv hech
    qayerda ko'rinmasdi. Bu aynan "jimgina yo'qolish" sinfi.

    BAZA XATOSI ETL NI TO'XTATMAYDI, lekin YASHIRILMAYDI ham: u
    sanaladi va yurish oxirida chiqariladi.
    """

    def __init__(self, dsn: Optional[str] = None) -> None:
        self._dsn = dsn
        self._conn = None
        self.baza_xatolari: List[str] = []

    def _c(self):
        if self._conn is None or getattr(self._conn, "closed", 1):
            self._conn = _ulan(self._dsn)
        return self._conn

    def bajar(self, sql: str, params: Sequence[Any] = ()) -> Optional[tuple]:
        """SQL bajaradi. Baza yetib bo'lmasa `None` va xato SANALADI."""
        try:
            with self._c().cursor() as cur:
                cur.execute(sql, params)
                if cur.description:
                    return cur.fetchone()
                return None
        except Exception as e:                               # noqa: BLE001
            # Ulanish uzilgan bo'lsa keyingi chaqiruvda qayta ulanamiz.
            try:
                if self._conn is not None:
                    self._conn.close()
            except Exception:                                # noqa: BLE001
                pass
            self._conn = None
            xabar = f"{type(e).__name__}: {str(e)[:140]}"
            self.baza_xatolari.append(xabar)
            print(f"    [!] baza yozuvi bajarilmadi: {xabar}", file=sys.stderr)
            return None

    def yop(self) -> None:
        try:
            if self._conn is not None:
                self._conn.close()
        except Exception:                                    # noqa: BLE001
            pass
        self._conn = None


# =====================================================================
# 6) CHECKPOINT
# =====================================================================
def ish_kaliti(idlar: Iterable[Any]) -> str:
    """Ish ro'yxatining barmoq izi.

    Ro'yxat o'zgarsa (yangi savdo qo'shilsa) kalit ham o'zgaradi va
    saqlangan `kursor` YAROQSIZ deb belgilanadi. Bu ATAYLAB qattiq:
    UzEx ro'yxatni "yangisi birinchi" tartibida beradi, ya'ni bitta
    yangi yozuv hammasini bir pozitsiya suradi va indeksga tayangan
    tiklash o'rtadagi yozuvni JIMGINA tashlab ketardi.
    """
    h = hashlib.sha256()
    for i in idlar:
        h.update(str(i).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:32]


@dataclass
class CheckpointHolat:
    kursor: int = 0
    jami: Optional[int] = None
    oxirgi_id: Optional[int] = None
    ish_kaliti: Optional[str] = None
    urinish: int = 0
    oxirgi_xato: Optional[str] = None
    keyingi_urinish_at: Optional[Any] = None
    holat: str = "ochiq"

    def dict(self) -> Dict[str, Any]:
        return {
            "kursor": self.kursor, "jami": self.jami,
            "oxirgi_id": self.oxirgi_id, "urinish": self.urinish,
            "holat": self.holat,
            "oxirgi_xato": (self.oxirgi_xato or "")[:200] or None,
        }


class Checkpoint:
    """Bitta ETL oqimining "qayerda to'xtadik" holati.

    OQIM = manba + reyestr/TypeId. Masalan `uzex` + `type=1`.
    Har oqim MUSTAQIL: TypeId=2 tugab, TypeId=1 uzilishi mumkin.
    """

    def __init__(self, yozuvchi: BazaYozuvchi, platform: str, oqim: str,
                 faol: bool = True) -> None:
        self.y = yozuvchi
        self.platform = platform
        self.oqim = oqim
        #: `faol=False` — `--dry-run` va `--no-checkpoint` uchun. Barcha
        #: amallar sukut bilan o'tkazib yuboriladi, chaqiruvchi esa
        #: har joyda `if` yozmaydi (unutilgan `if` — nuqson manbai).
        self.faol = faol
        self.holat = CheckpointHolat()
        self._oxirgi_yozuv = 0.0

    # ---- o'qish ----
    def yukla(self) -> CheckpointHolat:
        if not self.faol:
            return self.holat
        r = self.y.bajar(
            "SELECT kursor, jami, oxirgi_id, ish_kaliti, urinish, oxirgi_xato, "
            "       keyingi_urinish_at, holat "
            "FROM etl_checkpoint WHERE source_platform=%s AND oqim=%s",
            (self.platform, self.oqim))
        if r:
            self.holat = CheckpointHolat(
                kursor=r[0] or 0, jami=r[1], oxirgi_id=r[2], ish_kaliti=r[3],
                urinish=r[4] or 0, oxirgi_xato=r[5], keyingi_urinish_at=r[6],
                holat=r[7] or "ochiq")
        return self.holat

    def band_mi(self) -> Tuple[bool, Optional[str]]:
        """Backoff oynasi ichidamizmi? (manba yaqinda 429/503 bergan)

        Qaytadi: (band, sabab). Band bo'lsa oqimga TEGILMAYDI — bu
        manbaga nisbatan hurmat va bizning vaqtimizni tejash.
        """
        if not self.faol:
            return False, None
        r = self.y.bajar(
            "SELECT keyingi_urinish_at, "
            "       EXTRACT(EPOCH FROM (keyingi_urinish_at - now()))::int "
            "FROM etl_checkpoint "
            "WHERE source_platform=%s AND oqim=%s AND keyingi_urinish_at > now()",
            (self.platform, self.oqim))
        if r and r[0] is not None:
            return True, f"manba backoff oynasida — yana {r[1]}s"
        return False, None

    # ---- yozish ----
    def boshla(self, jami: int, kalit: str) -> int:
        """Oqimni ochadi va DAVOM ETILADIGAN indeksni qaytaradi.

        Kalit mos kelmasa 0 qaytadi — noto'g'ri joydan davom etishdan
        ko'ra boshidan boshlagan yaxshi. Kontent solishtiruvi baribir
        allaqachon saqlangan yozuvlarni o'tkazib yuboradi.
        """
        if not self.faol:
            return 0
        eski = self.yukla()
        davom = 0
        if (eski.ish_kaliti == kalit and eski.holat == "ochiq"
                and 0 < eski.kursor < jami):
            davom = eski.kursor
        self.y.bajar(
            "INSERT INTO etl_checkpoint "
            "  (source_platform, oqim, holat, kursor, jami, ish_kaliti, "
            "   boshlandi_at, yangilandi_at) "
            "VALUES (%s,%s,'ochiq',%s,%s,%s, now(), now()) "
            "ON CONFLICT (source_platform, oqim) DO UPDATE SET "
            "  holat='ochiq', kursor=EXCLUDED.kursor, jami=EXCLUDED.jami, "
            "  ish_kaliti=EXCLUDED.ish_kaliti, yangilandi_at=now(), "
            "  keyingi_urinish_at=NULL",
            (self.platform, self.oqim, davom, jami, kalit))
        self.holat.kursor = davom
        self.holat.jami = jami
        self.holat.ish_kaliti = kalit
        return davom

    def siljit(self, kursor: int, oxirgi_id: Optional[int] = None,
               majburan: bool = False, har_sek: float = 3.0) -> None:
        """Kursorni oldinga suradi (vaqt bo'yicha kamaytirilgan yozuv).

        HAR YOZUVDA BAZAGA YOZMAYMIZ: 623 ta yozuv uchun 623 ta
        ortiqcha UPDATE. `har_sek` sekundda bir marta yetarli —
        o'ldirishda yo'qoladigan ish shuncha sekundlik, va u
        IDEMPOTENT qayta bajariladi.
        """
        self.holat.kursor = kursor
        if oxirgi_id is not None:
            self.holat.oxirgi_id = int(oxirgi_id)
        if not self.faol:
            return
        hozir = time.monotonic()
        if not majburan and (hozir - self._oxirgi_yozuv) < har_sek:
            return
        self._oxirgi_yozuv = hozir
        self.y.bajar(
            "UPDATE etl_checkpoint SET kursor=%s, oxirgi_id=%s, yangilandi_at=now() "
            "WHERE source_platform=%s AND oqim=%s",
            (kursor, self.holat.oxirgi_id, self.platform, self.oqim))

    def xato_yoz(self, xabar: str, kutish_sek: Optional[float]) -> None:
        """Oqim darajasidagi xatoni va keyingi urinish vaqtini yozadi."""
        self.holat.urinish += 1
        self.holat.oxirgi_xato = xabar[:500]
        if not self.faol:
            return
        self.y.bajar(
            "UPDATE etl_checkpoint SET urinish=urinish+1, oxirgi_xato=%s, "
            "  keyingi_urinish_at = CASE WHEN %s::float IS NULL THEN NULL "
            "                            ELSE now() + (%s::float * interval '1 second') END, "
            "  yangilandi_at=now() "
            "WHERE source_platform=%s AND oqim=%s",
            (xabar[:500], kutish_sek, kutish_sek, self.platform, self.oqim))

    def tugat(self) -> None:
        """Oqim to'liq tugadi: kursor nolga, urinish nolga, xato tozalanadi.

        `keyingi_urinish_at=NULL` — CHECK talab qiladi ('tugadi' holati
        ochiq kutish vaqti bilan birga yashay olmaydi).
        """
        self.holat.holat = "tugadi"
        self.holat.kursor = 0
        self.holat.urinish = 0
        if not self.faol:
            return
        self.y.bajar(
            "UPDATE etl_checkpoint SET holat='tugadi', kursor=0, urinish=0, "
            "  oxirgi_xato=NULL, keyingi_urinish_at=NULL, yangilandi_at=now() "
            "WHERE source_platform=%s AND oqim=%s",
            (self.platform, self.oqim))


# =====================================================================
# 7) YURISH METRIKASI
# =====================================================================
class Yurish:
    """`etl_run` qatoriga metrikani DARHOL yozadi.

    Run ID ota-jarayondan `ETL_RUN_ID` muhit o'zgaruvchisi orqali
    keladi. NEGA MUHIT ORQALI, chiqishni parsing qilib emas: o'ldirilgan
    bola HECH NARSA CHOP ETMAYDI, ya'ni chiqishga tayangan metrika
    aynan biz o'lchamoqchi bo'lgan holatda yo'qolardi.

    Sanoqlar `col = col + n` bilan oshiriladi, ya'ni bir platformaning
    bir necha qadami (TypeId=2 va TypeId=1) BITTA qatorga yig'iladi.
    """

    def __init__(self, yozuvchi: BazaYozuvchi, run_id: Optional[int] = None,
                 puls_har_sek: float = 10.0) -> None:
        self.y = yozuvchi
        xom = run_id if run_id is not None else os.environ.get("ETL_RUN_ID")
        try:
            self.run_id: Optional[int] = int(xom) if xom not in (None, "") else None
        except (TypeError, ValueError):
            self.run_id = None
        self._puls_har = puls_har_sek
        self._oxirgi_puls = 0.0
        self.processed = self.succeeded = self.failed = 0
        self.retried = self.resumed = self.skipped = 0

    @property
    def faol(self) -> bool:
        return self.run_id is not None

    def puls(self, majburan: bool = False) -> None:
        """"Men tirikman" belgisi. Yetim qator yopilganda davomiylik
        SHUNDAN hisoblanadi."""
        if not self.faol:
            return
        hozir = time.monotonic()
        if not majburan and (hozir - self._oxirgi_puls) < self._puls_har:
            return
        self._oxirgi_puls = hozir
        self.y.bajar("UPDATE etl_run SET heartbeat_at=now() WHERE id=%s",
                     (self.run_id,))

    def oldinga(self, *, processed: int = 0, succeeded: int = 0, failed: int = 0,
                retried: int = 0, resumed: int = 0, skipped: int = 0,
                yoz: bool = True) -> None:
        """Sanoqlarni oshiradi. `yoz=False` — faqat xotirada (paket uchun)."""
        self.processed += processed
        self.succeeded += succeeded
        self.failed += failed
        self.retried += retried
        self.resumed += resumed
        self.skipped += skipped
        if not (yoz and self.faol):
            return
        if not any((processed, succeeded, failed, retried, resumed, skipped)):
            return
        self.y.bajar(
            "UPDATE etl_run SET processed=processed+%s, succeeded=succeeded+%s, "
            "  failed=failed+%s, retried=retried+%s, resumed=resumed+%s, "
            "  skipped=skipped+%s, heartbeat_at=now() WHERE id=%s",
            (processed, succeeded, failed, retried, resumed, skipped, self.run_id))
        self._oxirgi_puls = time.monotonic()

    def checkpoint_yoz(self, holat: Dict[str, Any]) -> None:
        if not self.faol or Json is None:
            return
        self.y.bajar("UPDATE etl_run SET checkpoint=%s WHERE id=%s",
                     (Json(holat), self.run_id))

    def sabab_yoz(self, sabab: str) -> None:
        """Tugash sababini yozadi (statusni ota-jarayon qo'yadi)."""
        if not self.faol:
            return
        self.y.bajar(
            "UPDATE etl_run SET terminal_reason=%s, heartbeat_at=now() WHERE id=%s",
            (sabab[:120], self.run_id))

    def xulosa(self) -> str:
        return (f"ko'rildi {self.processed}, yozildi {self.succeeded}, "
                f"yiqildi {self.failed}, o'tkazildi {self.skipped}, "
                f"tiklandi {self.resumed}, qayta urinish {self.retried}")


# =====================================================================
# 8) USTMA-UST YURISHDAN HIMOYA — baza maslahat qulfi
# =====================================================================
#
# Task Scheduler ning `MultipleInstances=IgnoreNew` FAQAT BITTA vazifa
# ichida ishlaydi. O'lchangan (etl_cron.log, 2026-08-30):
#
#     01:00:02  ETL boshlandi
#     01:02:14  RAG boshlandi      <- boshqa vazifa, bir xil bazaga
#     01:30:02  RAG boshlandi
#
# Ikki vazifa bir platformani bir vaqtda yig'sa manbaga so'rov tezligi
# IKKI BAROBAR bo'ladi — bu rate-limitni hurmat qilmaslik. Baza qulfi
# vazifa chegarasidan o'tadi va shuni to'sadi.
#
# `pg_try_advisory_lock` ATAYLAB `pg_advisory_lock` emas: kutmaymiz.
# Kutish soatlik jadvalda navbat hosil qilardi.

def qulf_kaliti(nom: str) -> int:
    """Matndan 63-bitli barqaror kalit."""
    h = hashlib.sha256(nom.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big") & 0x7FFF_FFFF_FFFF_FFFF


class Qulf:
    """Seans darajasidagi maslahat qulfi. Ulanish uzilsa O'ZI bo'shaydi.

    Jarayon o'ldirilganda ham qulf qolib ketmaydi: PostgreSQL uni
    seans tugashi bilan bo'shatadi. Fayl qulfida bu kafolat YO'Q —
    aynan shuning uchun bu yerda baza qulfi tanlangan.
    """

    def __init__(self, nom: str, dsn: Optional[str] = None) -> None:
        self.nom = nom
        self.kalit = qulf_kaliti(nom)
        self._dsn = dsn
        self._conn = None
        self.olindi = False

    def ol(self) -> bool:
        try:
            self._conn = _ulan(self._dsn)
            with self._conn.cursor() as cur:
                cur.execute("SELECT pg_try_advisory_lock(%s)", (self.kalit,))
                self.olindi = bool(cur.fetchone()[0])
        except Exception as e:                               # noqa: BLE001
            # Baza yetib bo'lmasa qulf QO'YILMAYDI va ish DAVOM ETADI:
            # qulf — himoya vositasi, ETL ning sharti emas. Lekin bu
            # jimgina bo'lmaydi.
            print(f"[!] qulf olinmadi (baza): {str(e)[:120]}", file=sys.stderr)
            self.olindi = True
        if not self.olindi:
            self.qoyver()
        return self.olindi

    def qoyver(self) -> None:
        try:
            if self._conn is not None:
                if self.olindi:
                    with self._conn.cursor() as cur:
                        cur.execute("SELECT pg_advisory_unlock(%s)", (self.kalit,))
                self._conn.close()
        except Exception:                                    # noqa: BLE001
            pass
        self._conn = None

    def __enter__(self) -> "Qulf":
        self.ol()
        return self

    def __exit__(self, *a) -> None:
        self.qoyver()


# =====================================================================
# 9) INKREMENTAL — nima o'zgargan?
# =====================================================================
def _tenglar(a: Any, b: Any) -> bool:
    """Ikki qiymat MAZMUNAN teng-mi?

    SONLAR ALOHIDA TAQQOSLANADI. Manba JSON da bir xil maydon goh `100`,
    goh `100.0` bo'lib keladi (`cost` da o'lchangan). Faqat `str()`
    bilan taqqoslaganda bu FARQ bo'lib ko'rinardi va o'zgarmagan savdo
    har soat qayta olinardi — ya'ni inkremental JIMGINA ishlamay
    qo'yardi va buni hech narsa ko'rsatmasdi.
    """
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return str(a) == str(b)


def ozgardimi(eski: Optional[Dict[str, Any]], yangi: Dict[str, Any],
              maydonlar: Sequence[str]) -> bool:
    """Manbadagi qator saqlanganidan farq qiladimi?

    BU — TIKLASHNING HAQIQIY MEXANIZMI. Indeksga tayanmaydi, shuning
    uchun ro'yxat qayta tartiblansa ham to'g'ri ishlaydi: oldingi
    yurishda saqlangan yozuv keyingi yurishda O'ZIDAN-O'ZI
    o'tkazib yuboriladi.

    `eski` None yoki bo'sh bo'lsa (bizda yo'q, yoki `raw_json` buzuq)
    -> YANGI, albatta olinadi. Ya'ni buzilish o'z-o'zini tuzatadi.
    """
    if not eski:
        return True
    for m in maydonlar:
        if not _tenglar(eski.get(m), yangi.get(m)):
            return True
    return False


def json_yukla(xom: Any) -> Dict[str, Any]:
    """Bazadagi `raw_json` ni dict ga o'giradi. Buzuq bo'lsa bo'sh dict.

    Buzuq `raw_json` — bu YOZUVNI QAYTA OLISH sababi, xato emas:
    bo'sh dict `ozgardimi()` ga "yangi" deb ko'rinadi va yozuv
    yangilanadi. Ya'ni buzilish O'Z-O'ZINI tuzatadi.
    """
    if isinstance(xom, dict):
        return xom
    if not xom:
        return {}
    try:
        v = json.loads(xom)
        return v if isinstance(v, dict) else {}
    except (TypeError, ValueError):
        return {}
