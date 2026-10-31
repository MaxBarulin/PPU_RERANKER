@echo off
chcp 65001 >nul
title bge-reranker-v2-m3 Server

REM === Настройки (меняй здесь при необходимости) ===
set LLAMA_DIR=E:\llama
set MODEL=F:\kobold_model\bge-reranker-v2-m3-Q4_K_M.gguf
REM Дома есть CUDA: 99 = всё на GPU. На работе (только CPU) поставь 0
set NGL=99
REM Потоки CPU: на работе поставь число физических ядер
set THREADS=4
REM Пара «запрос + документ» должна целиком влезать в один батч:
REM CTX = BATCH = UBATCH. 8192 — максимум bge-reranker-v2-m3
set CTX=8192
set HOST=127.0.0.1
set PORT=8082

REM === Проверки ===
if not exist "%LLAMA_DIR%\llama-server.exe" (
    echo [ОШИБКА] Не найден llama-server.exe в %LLAMA_DIR%
    pause
    exit /b 1
)
if not exist "%MODEL%" (
    echo [ОШИБКА] Не найден файл модели:
    echo %MODEL%
    pause
    exit /b 1
)

echo ============================================
echo  Реранкер bge-reranker-v2-m3
echo  POST http://%HOST%:%PORT%/v1/rerank
echo  GPU layers: %NGL%   Context: %CTX%   Threads: %THREADS%
echo  Для остановки: Ctrl+C или закрой окно
echo ============================================
echo.

cd /d "%LLAMA_DIR%"
llama-server.exe -m "%MODEL%" --reranking -ngl %NGL% -t %THREADS% -c %CTX% -b %CTX% -ub %CTX% -np 1 --no-mmap --host %HOST% --port %PORT%

echo.
echo Сервер остановлен.
pause
