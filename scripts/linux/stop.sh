#!/usr/bin/env bash
# Остановка веба проверки ППУ (модели не трогает).
set -euo pipefail
cd "$(dirname "$0")/../.."
PIDFILE=logs/web.pid

# PID из файла может после перезагрузки достаться другому процессу — сверяем команду
if ! { [ -f "$PIDFILE" ] && ps -p "$(cat "$PIDFILE")" -o args= 2>/dev/null | grep -q "ppu.web"; }; then
  rm -f "$PIDFILE"
  echo "Веб не запущен."
  pgrep -af "ppu.web" && echo "↑ похоже на запущенные вручную — останови: kill <PID>" || true
  exit 0
fi
PID=$(cat "$PIDFILE")
kill "$PID"
for _ in $(seq 20); do kill -0 "$PID" 2>/dev/null || break; sleep 0.5; done
kill -0 "$PID" 2>/dev/null && kill -9 "$PID"
rm -f "$PIDFILE"
echo "Остановлен (PID $PID)."
