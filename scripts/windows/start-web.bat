@echo off
chcp 65001 >nul
title PPU: веб-интерфейс

REM 127.0.0.1 — только этот компьютер; 0.0.0.0 — доступно коллегам по сети
set HOST=127.0.0.1
set PORT=8000

set ROOT=%~dp0..\..
set PY=%ROOT%\venv\Scripts\python.exe
set PYTHONIOENCODING=utf-8

cd /d "%ROOT%"
if not exist data\index\meta.json (
    echo [ОШИБКА] Нет индекса data\index — сначала build-index.bat
    pause & exit /b 1
)

echo ============================================
echo  Проверка ППУ:  http://%HOST%:%PORT%
echo  Нужны: сервер эмбеддингов; для кнопки «Уточнить у LLM» — сервер судьи
echo  Для остановки: Ctrl+C
echo ============================================
"%PY%" -m ppu.web --host %HOST% --port %PORT%
pause
