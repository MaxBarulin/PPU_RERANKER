#!/usr/bin/env bash
# Запуск веба проверки ППУ в фоне. Модели (эмбеддинги, LLM) уже работают на сервере.
#
#   scripts/linux/start.sh
#
# Первый запуск сам создаёт venv и .env. Порт и адрес — PPU_PORT / PPU_HOST
# в .env (по умолчанию 8010 и 0.0.0.0). База обновляется на странице /admin.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p logs data
PIDFILE=logs/web.pid

# PID из файла может после перезагрузки достаться другому процессу — сверяем команду
running() { [ -f "$PIDFILE" ] && ps -p "$(cat "$PIDFILE")" -o args= 2>/dev/null | grep -q "ppu.web"; }

env_get() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '\r' || true; }

if [ ! -x venv/bin/python ]; then
  echo "Первый запуск: создаю venv и ставлю зависимости…"
  python3 -m venv venv
  venv/bin/pip install -q --upgrade pip
  venv/bin/pip install -q -r requirements.txt
fi
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Создан .env из .env.example — проверь адреса моделей: nano .env"
fi

PORT=$(env_get PPU_PORT); PORT=${PORT:-8010}
HOST=$(env_get PPU_HOST); HOST=${HOST:-0.0.0.0}

if running; then
  echo "Уже запущен (PID $(cat "$PIDFILE")). Перезапуск: scripts/linux/stop.sh && scripts/linux/start.sh"
  exit 0
fi
if ss -Hltn "sport = :$PORT" 2>/dev/null | grep -q .; then
  echo "[ОШИБКА] Порт $PORT занят другой программой. Укажи свободный в .env: PPU_PORT=..."
  exit 1
fi

check() {
  if [ -z "$2" ]; then echo "  $1: не настроен"; return; fi
  if curl -fsS -m 5 "$2/models" >/dev/null 2>&1; then echo "  $1: OK  ($2)"
  else echo "  $1: НЕ ОТВЕЧАЕТ  ($2) — проверь, что сервер модели запущен"; fi
}
echo "Модели из .env:"
check "эмбеддинги" "$(env_get EMB_BASE_URL)"
check "LLM-судья " "$(env_get LLM_BASE_URL)"

nohup venv/bin/python -m ppu.web --host "$HOST" --port "$PORT" >> logs/web.log 2>&1 &
echo $! > "$PIDFILE"
sleep 3
if ! running; then
  echo "[ОШИБКА] Веб не запустился. Последние строки logs/web.log:"
  tail -20 logs/web.log
  rm -f "$PIDFILE"
  exit 1
fi

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo
echo "Работает (PID $(cat "$PIDFILE")):"
echo "  проверка ППУ:     http://${IP:-$(hostname)}:$PORT"
echo "  обновление базы:  http://${IP:-$(hostname)}:$PORT/admin"
echo "  лог:              tail -f logs/web.log"
echo "  остановить:       scripts/linux/stop.sh"
