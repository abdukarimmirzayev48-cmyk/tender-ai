#!/bin/bash
# =============================================================================
# ETL cron wrapper (H bosqich) — soatlik avtomatik yangilash
# =============================================================================
# cron/launchd shu skriptni chaqiradi. Vazifasi:
#   - to'g'ri katalog, venv va DSN'ni o'rnatish (cron muhitida PATH bo'sh bo'ladi)
#   - bir vaqtда faqat BITTA yurish (lock — oldingisi tugamasa o'tkazib yuboriladi)
#   - logni faylga yozish
#
# DSN'ni bu yerда to'g'rilang yoki .env dan o'qing:
# =============================================================================
set -euo pipefail

DIR="/Users/a1234/Downloads/Birja"
VENV_PY="$DIR/.venv/bin/python"
LOG="$DIR/etl_cron.log"
LOCK="/tmp/birja_etl.lock.d"

# DSN — .env dan (parol bilan). Agar .env bo'lmasa, bu yerда qo'lда bering.
if [ -f "$DIR/.env" ]; then
    export XT_DB_DSN="$(grep -E '^XT_DB_DSN=' "$DIR/.env" | head -1 | cut -d= -f2-)"
fi

# Lock (macOS'да flock yo'q — mkdir atomar): oldingi yurish tugamagan bo'lsa o'tkazamiz
if ! mkdir "$LOCK" 2>/dev/null; then
    echo "[$(date '+%F %T')] oldingi yurish davom etmoqda — o'tkazib yuborildi" >> "$LOG"
    exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT

cd "$DIR"
echo "===== [$(date '+%F %T')] ETL boshlandi =====" >> "$LOG"
"$VENV_PY" run_etl.py >> "$LOG" 2>&1
echo "===== [$(date '+%F %T')] tugadi (exit $?) =====" >> "$LOG"
