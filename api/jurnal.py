"""
TUZILMALI JURNAL — mashina o'qiy oladigan log
==============================================

NEGA KERAK. Hozirgi chiqish erkin matn: `print()` va standart
`logging` formati. Bir mashinada bu o'qiladi, lekin joylashtirishda
uch narsa buziladi:

  1. `journalctl` yoki log yig'uvchi qatorni AJRATA olmaydi —
     "xato bormi" degan savolga `grep` bilan javob beriladi va u
     til/formatga bog'liq.
  2. So'rovni oxirigacha KUZATIB bo'lmaydi: bitta so'rovning
     qatorlarini bog'laydigan identifikator yo'q.
  3. Sirlar tasodifan tushib qolishi mumkin va buni hech narsa
     to'smaydi.

Bu modul uchalasini hal qiladi: JSON qator, so'rov identifikatori,
va NOMLARI SIR bo'lgan maydonlarni niqoblash.

FORMAT SOZLANADI, MAJBURLANMAYDI:
    LOG_FORMAT=json   -> bir qator = bir JSON obyekt (joylashtirish)
    LOG_FORMAT=text   -> odam o'qiydigan (ishlab chiqish, standart)
    LOG_LEVEL=INFO

`stdout` ga yoziladi — fayl aylantirish (`logrotate`) yoki
`journald` ning ishi, ilovaniki emas. Ilova faylni o'zi ochsa,
konteynerda va systemd ostida ikki xil xulq chiqardi.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import re
import sys
import uuid
from contextvars import ContextVar
from typing import Any, Dict, Optional

#: Joriy so'rov identifikatori. `ContextVar` — async xavfsiz:
#: bir vaqtda bir necha so'rov ishlaganda ular aralashmaydi.
sorov_id: ContextVar[str] = ContextVar("sorov_id", default="")

#: Nomida shu bo'laklar bor maydon QIYMATI jurnalga tushmaydi.
#: Ro'yxat NOM bo'yicha ishlaydi, mazmun bo'yicha emas — mazmun
#: bo'yicha topish ehtimolli, nom bo'yicha esa aniq.
SIR_NAQSH = re.compile(
    r"(password|parol|passwd|secret|token|api_?key|authorization|"
    r"cookie|dsn|csrf|service_?key|smtp_pass)", re.I)

NIQOB = "***"

#: Standart `LogRecord` maydonlari — ular JSON ga alohida
#: qo'shilmaydi (ular allaqachon boshqa nom bilan chiqadi).
_STANDART = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName", "asctime", "message",
}


def niqobla(d: Dict[str, Any]) -> Dict[str, Any]:
    """Sir nomli maydonlarni niqoblaydi (rekursiv)."""
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if SIR_NAQSH.search(str(k)):
            out[k] = NIQOB
        elif isinstance(v, dict):
            out[k] = niqobla(v)
        else:
            out[k] = v
    return out


class JsonFormatter(logging.Formatter):
    """Bir qator = bir JSON obyekt.

    `ensure_ascii=False` — o'zbek matni `\\uXXXX` ga aylanmasin:
    jurnal odam ham o'qiydigan narsa bo'lib qolsin.
    """

    def format(self, record: logging.LogRecord) -> str:
        q: Dict[str, Any] = {
            "vaqt": _dt.datetime.fromtimestamp(
                record.created, _dt.timezone.utc).isoformat(),
            "daraja": record.levelname,
            "jurnal": record.name,
            "xabar": record.getMessage(),
        }
        sid = sorov_id.get()
        if sid:
            q["sorov_id"] = sid
        if record.exc_info:
            q["istisno"] = self.formatException(record.exc_info)
        qoshimcha = {k: v for k, v in record.__dict__.items()
                     if k not in _STANDART and not k.startswith("_")}
        if qoshimcha:
            q.update(niqobla(qoshimcha))
        return json.dumps(niqobla(q), ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """Ishlab chiqish uchun — so'rov id si bilan."""

    def format(self, record: logging.LogRecord) -> str:
        sid = sorov_id.get()
        old = f"[{sid[:8]}] " if sid else ""
        base = (f"{self.formatTime(record, '%H:%M:%S')} "
                f"{record.levelname:<7} {record.name}: {old}"
                f"{record.getMessage()}")
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def sozla(format_: Optional[str] = None, daraja: Optional[str] = None) -> str:
    """Jurnalni sozlaydi. -> tanlangan format nomi.

    IDEMPOTENT: takroriy chaqiruv ishlovchilarni KO'PAYTIRMAYDI —
    aks holda har qator ikki marta chiqardi (bu `uvicorn --reload`
    da haqiqiy holat).
    """
    fmt = (format_ or os.environ.get("LOG_FORMAT", "text")).strip().lower()
    lvl = (daraja or os.environ.get("LOG_LEVEL", "INFO")).strip().upper()

    ildiz = logging.getLogger()
    for h in list(ildiz.handlers):
        ildiz.removeHandler(h)

    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())
    ildiz.addHandler(h)
    ildiz.setLevel(getattr(logging, lvl, logging.INFO))

    # uvicorn o'z ishlovchilarini qo'yadi va natijada qator IKKI
    # marta chiqadi. Ularni ildizga yo'naltiramiz.
    for nom in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(nom)
        lg.handlers = []
        lg.propagate = True
    return fmt


def yangi_sorov_id() -> str:
    """Yangi so'rov identifikatorini o'rnatadi va qaytaradi."""
    sid = uuid.uuid4().hex
    sorov_id.set(sid)
    return sid
