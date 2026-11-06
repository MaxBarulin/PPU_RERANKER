@echo off
chcp 65001 >nul
title PPU: веб-интерфейс

REM 127.0.0.1 - только этот компьютер; 0.0.0.0 - доступно коллегам по сети
set HOST=127.0.0.1
set PORT=8000

set ROOT=%~dp0..\..
set PY=%ROOT%\venv\Scripts\python.exe
set PYTHONIOENCODING=utf-8

cd /d "%ROOT%"
if not exist data\index\meta.json (
    echo Индекса ещё нет - загрузите реестр в браузере: http://%HOST%:%PORT%/admin
    echo.
)

echo ============================================
echo  Проверка ППУ:     http://%HOST%:%PORT%
echo  Обновление базы:  http://%HOST%:%PORT%/admin
echo  Нужны: сервер эмбеддингов; для кнопки «Уточнить у LLM» - сервер судьи
echo  Для остановки: Ctrl+C
echo ============================================
"%PY%" -m ppu.web --host %HOST% --port %PORT%
pause
