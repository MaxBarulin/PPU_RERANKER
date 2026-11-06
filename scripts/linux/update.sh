#!/usr/bin/env bash
# Обновить код из git и перезапустить веб. Данные (data/, .env) не трогаются.
#
#   scripts/linux/update.sh            - текущая ветка
#   scripts/linux/update.sh <ветка>    - переключиться на ветку
set -euo pipefail
cd "$(dirname "$0")/../.."

PORT=$(grep -E '^PPU_PORT=' .env 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '\r' || true)
SCHEME=http; grep -qE '^PPU_SSL_CERT=.+' .env 2>/dev/null && SCHEME=https
# /api/info открыт без пароля и показывает, идёт ли сборка (-k: свой сертификат)
if curl -fsSk -m 3 "$SCHEME://127.0.0.1:${PORT:-8010}/api/info" 2>/dev/null \
   | grep -q '"rebuild":"running"'; then
  echo "[ВНИМАНИЕ] Сейчас идёт сборка индекса - перезапуск её прервёт (посчитанное останется в кэше)."
  read -r -p "Продолжить? [y/N] " ans
  [ "$ans" = "y" ] || exit 1
fi

if [ $# -ge 1 ]; then
  git fetch origin "$1"
  git checkout "$1"
fi
git pull --ff-only
[ -x venv/bin/python ] && venv/bin/pip install -q -r requirements.txt
scripts/linux/stop.sh
scripts/linux/start.sh
