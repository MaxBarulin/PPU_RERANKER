@echo off
chcp 65001 >nul
title PPU: сборка индекса

REM Использование: build-index.bat "путь\к\реестру.xlsx"
REM Нужен запущенный сервер эмбеддингов (start-embeddings.bat).
REM Можно прервать и запустить снова — посчитанные эмбеддинги берутся из кэша.

set ROOT=%~dp0..\..
set PY=%ROOT%\venv\Scripts\python.exe
set PYTHONIOENCODING=utf-8

if "%~1"=="" (
    echo Использование: %~nx0 "F:\replicate\PPU\rrr\PPU.xlsx"
    pause & exit /b 1
)
if not exist "%~1" (
    echo [ОШИБКА] Не найден файл реестра: %~1
    pause & exit /b 1
)

cd /d "%ROOT%"
echo === 1/2 Нормализация реестра ===
"%PY%" -m ppu.prepare "%~1" --out data\registry_clean.jsonl > data\prepare_report.txt
if errorlevel 1 ( echo [ОШИБКА] prepare & pause & exit /b 1 )
type data\prepare_report.txt

echo.
echo === 2/2 Эмбеддинги и индекс ===
"%PY%" -m ppu.index data\registry_clean.jsonl --out data\index
if errorlevel 1 ( echo [ОШИБКА] index & pause & exit /b 1 )

echo.
echo Готово. Отчёт о данных: data\prepare_report.txt
echo Перезапусти веб (start-web.bat), чтобы он подхватил новый индекс.
pause
