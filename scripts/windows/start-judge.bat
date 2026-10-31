@echo off
chcp 65001 >nul
title Qwen judge

REM === Настройки ===
set LLAMA_DIR=E:\llama
set MODEL=F:\models\Qwen3.6-35B-A3B-Q4_K_M.gguf
REM 0 = только CPU (работа). С видеокартой — 99
set NGL=0
REM Потоки: число физических ядер
set THREADS=8
REM Промпт судьи ~700 токенов + ответ ~50 — 4096 с запасом
set CTX=4096
set HOST=127.0.0.1
set PORT=8080

if not exist "%LLAMA_DIR%\llama-server.exe" (
    echo [ОШИБКА] Не найден llama-server.exe в %LLAMA_DIR%
    pause & exit /b 1
)
if not exist "%MODEL%" (
    echo [ОШИБКА] Не найден файл модели: %MODEL%
    pause & exit /b 1
)

echo ============================================
echo  LLM-судья:  http://%HOST%:%PORT%/v1
echo  В .env:  LLM_BASE_URL=http://%HOST%:%PORT%/v1
echo  Рассуждения выключены (--reasoning off) — на CPU каждый токен дорог
echo  Для остановки: Ctrl+C
echo ============================================

cd /d "%LLAMA_DIR%"
REM -np 1: один слот, чтобы закэшированная постоянная часть промпта переиспользовалась
llama-server.exe -m "%MODEL%" -ngl %NGL% -t %THREADS% -c %CTX% -np 1 --reasoning off --no-mmap --host %HOST% --port %PORT%

echo Сервер остановлен.
pause
