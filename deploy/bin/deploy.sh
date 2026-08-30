#!/usr/bin/env bash
# =============================================================================
# Tender AI — joylashtirish (STAGING BIRINCHI)
# =============================================================================
#     deploy.sh staging    <git-ref>
#     deploy.sh production <git-ref>
#
# ISHLAB CHIQARISHGA TO'G'RIDAN-TO'G'RI JOYLASHTIRIB BO'LMAYDI: shu
# ref STAGING da tekshirilgan bo'lishi SHART. Tasdiq `.verified`
# faylida va uni shu skriptning O'ZI yozadi — staging joylashtiruvi
# sog'liq tekshiruvidan o'tgach.
#
# NEGA SIMVOLIK HAVOLA (`current`): orqaga qaytarish BITTA atomar
# amal bo'ladi (`ln -sfn`), ya'ni "qaytardim, lekin yarmi eski yarmi
# yangi" holati yuzaga kelmaydi.
#
# BU SKRIPTDA SIR YO'Q. Sirlar `/etc/tenderai/<muhit>.env` da va u
# repozitoriyaga tushmaydi.
# =============================================================================
set -euo pipefail

MUHIT="${1:?foydalanish: deploy.sh <staging|production> <git-ref>}"
REF="${2:?git ref (tag yoki commit) kerak}"

case "$MUHIT" in
    staging|production) ;;
    *) echo "Noma'lum muhit: $MUHIT"; exit 2 ;;
esac

ILDIZ="/opt/tenderai/${MUHIT}"
RELIZLAR="${ILDIZ}/releases"
JORIY="${ILDIZ}/current"
ENVFILE="/etc/tenderai/${MUHIT}.env"
REPO="${TENDERAI_REPO:-/opt/tenderai/repo.git}"

log()  { printf '[%s] %s\n' "$(date '+%F %T')" "$*"; }
xato() { printf '[%s] XATO: %s\n' "$(date '+%F %T')" "$*" >&2; exit 1; }

[ -f "$ENVFILE" ] || xato "muhit fayli yo'q: $ENVFILE"

# --- 1) ISHLAB CHIQARISH UCHUN STAGING TASDIQI SHART -------------------------
if [ "$MUHIT" = "production" ]; then
    TASDIQ="/opt/tenderai/staging/.verified"
    [ -f "$TASDIQ" ] || xato "staging tasdigi yoq ($TASDIQ). Avval: deploy.sh staging $REF"
    TASDIQLANGAN="$(cat "$TASDIQ")"
    if [ "$TASDIQLANGAN" != "$REF" ]; then
        xato "staging da BOSHQA ref tekshirilgan: '$TASDIQLANGAN' != '$REF'"
    fi
    log "staging tasdigi topildi: $REF"
fi

# --- 2) Yangi reliz katalogi -------------------------------------------------
STAMP="$(date +%Y%m%d-%H%M%S)"
TOZA_REF="$(printf '%s' "$REF" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-24)"
YANGI="${RELIZLAR}/${STAMP}-${TOZA_REF}"
mkdir -p "$YANGI" "${ILDIZ}/var/hf" "${ILDIZ}/var/cache"
log "reliz: $YANGI"

git --git-dir="$REPO" archive "$REF" | tar -x -C "$YANGI"

# --- 3) Python muhiti --------------------------------------------------------
log "python muhiti quriladi"
python3 -m venv "${YANGI}/.venv"
"${YANGI}/.venv/bin/pip" install --quiet --upgrade pip
"${YANGI}/.venv/bin/pip" install --quiet -r "${YANGI}/requirements-api.txt"

# --- 4) Frontend QURILADI (dev-server ISHLATILMAYDI) -------------------------
# Vite dev-server 0.0.0.0 ga boglanadi va uning zaifliklari bor
# (docs/xavfsizlik.md M-9). Joylashtirishda faqat statik qurilma.
log "frontend quriladi"
( cd "${YANGI}/frontend" && npm ci --silent && npm run build )
[ -d "${YANGI}/frontend/dist" ] || xato "frontend/dist yaratilmadi"

# --- 5) MIGRATSIYA — EGASI roli bilan ---------------------------------------
# Ilova roli (tai_app) da DDL huquqi ATAYLAB yoq.
set -a
# shellcheck disable=SC1090
. "$ENVFILE"
set +a
: "${XT_DB_DSN_OWNER:?migratsiya uchun XT_DB_DSN_OWNER kerak (env faylda)}"
log "migratsiya holati"
"${YANGI}/.venv/bin/python" "${YANGI}/migratsiya.py" --holat --dsn "$XT_DB_DSN_OWNER" || true
log "migratsiya qollanadi"
"${YANGI}/.venv/bin/python" "${YANGI}/migratsiya.py" --qolla --dsn "$XT_DB_DSN_OWNER"

# --- 6) ALMASHTIRISH (atomar) ------------------------------------------------
ESKI="$(readlink -f "$JORIY" 2>/dev/null || true)"
ln -sfn "$YANGI" "$JORIY"
log "current -> $YANGI"

# --- 7) Xizmatlar ------------------------------------------------------------
sudo systemctl restart "tenderai-api@${MUHIT}"
sudo systemctl enable --now "tenderai-etl@${MUHIT}.timer"          >/dev/null
sudo systemctl enable --now "tenderai-backup@${MUHIT}.timer"       >/dev/null
sudo systemctl enable --now "tenderai-restore-test@${MUHIT}.timer" >/dev/null

# --- 8) SOGLIQ TEKSHIRUVI — otmasa AVTOMATIK QAYTARILADI ---------------------
if ! "${YANGI}/deploy/bin/health-check.sh" "$MUHIT"; then
    log "sogliq tekshiruvi OTMADI — orqaga qaytarilmoqda"
    if [ -n "$ESKI" ] && [ -d "$ESKI" ]; then
        ln -sfn "$ESKI" "$JORIY"
        sudo systemctl restart "tenderai-api@${MUHIT}"
        xato "qaytarildi -> $ESKI"
    fi
    xato "qaytariladigan eski reliz yoq"
fi

# --- 9) STAGING muvaffaqiyatli -> TASDIQ yoziladi ---------------------------
if [ "$MUHIT" = "staging" ]; then
    printf '%s' "$REF" > "${ILDIZ}/.verified"
    log "staging tasdigi yozildi: $REF"
fi

# --- 10) Eski relizlar (oxirgi 5 tasi qoladi) -------------------------------
( cd "$RELIZLAR" && ls -1dt */ 2>/dev/null | tail -n +6 | xargs -r rm -rf )

log "TUGADI: ${MUHIT} <- ${REF}"
