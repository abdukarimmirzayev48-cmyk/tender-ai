#!/usr/bin/env bash
# =============================================================================
# Tender AI — joylashtirishdan keyingi sogliq tekshiruvi
# =============================================================================
#     health-check.sh <staging|production>
#
# TORT TEKSHIRUV va ular BOSHQA-BOSHQA narsani olchaydi:
#
#   1. TIRIKLIK   /health    — jarayon javob beryaptimi
#   2. TAYYORLIK  /ready     — baza + migratsiya (503 = tayyor emas)
#   3. ETL        /freshness — malumot qancha eski
#   4. BAZA       togridan-togri SQL
#
# Ularni bittaga qoshish "tirik = ishlayapti" degan yolgon berardi:
# jarayon kotarilgan, lekin migratsiya qollanmagan holat HAQIQIY va
# u faqat 2-tekshiruvda korinadi.
#
# ETL tekshiruvi joylashtirishni TOXTATMAYDI — yangi joylashtirishda
# ETL hali yurmagan bolishi normal. U OGOHLANTIRISH beradi.
# =============================================================================
set -uo pipefail

MUHIT="${1:?foydalanish: health-check.sh <staging|production>}"
# Yo'l almashtirilishi mumkin — mashq uchun (B-1 dagi bilan bir xil
# sabab: qotirilgan yo'l skriptni serverdan tashqarida yurgizib
# bo'lmaydigan qiladi).
ENVFILE="${TENDERAI_ENVFILE:-/etc/tenderai/${MUHIT}.env}"
[ -f "$ENVFILE" ] || { echo "muhit fayli yoq: $ENVFILE"; exit 2; }

set -a
# shellcheck disable=SC1090
. "$ENVFILE"
set +a

PORT="${API_PORT:-8000}"
BASE="http://127.0.0.1:${PORT}"
# Soatlik timer + tasodifiy kechikish + yurish vaqti -> 3 soat.
ETL_MAX_AGE="${HEALTH_ETL_MAX_AGE_SEC:-10800}"

ok=0
xato=0
belgi() {
    if [ "$1" = "0" ]; then
        echo "  [OK  ] $2"; ok=$((ok + 1))
    else
        echo "  [XATO] $2"; xato=$((xato + 1))
    fi
}

# --- 1) TIRIKLIK. Xizmat kotarilishi uchun 60 s kutiladi. -------------------
kod=""
for _ in $(seq 1 30); do
    kod="$(curl -fsS -o /dev/null -w '%{http_code}' --max-time 5 \
           "${BASE}/health" 2>/dev/null || true)"
    [ "$kod" = "200" ] && break
    sleep 2
done
[ "$kod" = "200" ]
belgi $? "tiriklik /health (kod=${kod:-yoq})"

# --- 2) TAYYORLIK ------------------------------------------------------------
TMP="$(mktemp)"
javob="$(curl -sS -o "$TMP" -w '%{http_code}' --max-time 10 \
         "${BASE}/ready" 2>/dev/null || echo 000)"
tayyor="$(grep -o '"tayyor": *true' "$TMP" 2>/dev/null || true)"
holatlar="$(tr -d '\n' < "$TMP" 2>/dev/null | cut -c1-200)"
rm -f "$TMP"
[ "$javob" = "200" ] && [ -n "$tayyor" ]
belgi $? "tayyorlik /ready (kod=$javob)"
[ -n "$holatlar" ] && echo "         $holatlar"

# --- 3) ETL YANGILIGI (OGOHLANTIRISH, toxtatmaydi) --------------------------
# `/freshness` kirish talab qiladi. Service kaliti bolsa ishlatamiz;
# bolmasa OLCHANMADI deb aytamiz — nol deb hisoblamaymiz.
yosh=""
if [ -n "${ERP_SERVICE_KEY:-}" ]; then
    yosh="$(curl -fsS --max-time 15 -H "X-Service-Key: ${ERP_SERVICE_KEY}" \
            "${BASE}/freshness" 2>/dev/null \
            | grep -o '"overall_age_sec": *[0-9]*' | grep -o '[0-9]*' || true)"
fi
if [ -z "$yosh" ]; then
    echo "  [i   ] ETL yangiligi OLCHANMADI (service kaliti yoq yoki hali yurmagan)"
elif [ "$yosh" -gt "$ETL_MAX_AGE" ]; then
    echo "  [OGOH] ETL ${yosh}s oldin yurgan (chegara ${ETL_MAX_AGE}s)"
else
    belgi 0 "ETL yangiligi ${yosh}s"
fi

# --- 4) BAZA -----------------------------------------------------------------
if command -v psql >/dev/null 2>&1; then
    psql "$XT_DB_DSN" -Atqc 'SELECT 1' >/dev/null 2>&1
    belgi $? "baza ulanishi"
else
    echo "  [i   ] psql yoq — baza togridan-togri tekshirilmadi"
fi

echo "  ---- OK: $ok   XATO: $xato ----"
[ "$xato" -eq 0 ]
