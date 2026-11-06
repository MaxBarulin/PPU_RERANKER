@echo off
chcp 65001 >nul
title Qwen judge

REM === Настройки ===
set LLAMA_DIR=E:\llama
set MODEL=F:\models\Qwen3.6-35B-A3B-Q4_K_M.gguf
REM 0 = только CPU (работа). С видеокартой - 99
set NGL=0
REM Потоки: число физических ядер
set THREADS=8
REM Промпт судьи: правила ~480 токенов + новое ППУ и 4 кандидата целиком (тексты не
REM обрезаются, длинные ППУ - тысячи токенов) + ответ. 16384 - с запасом
set CTX=16384
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
echo  Рассуждения выключены (--reasoning off) - на CPU каждый токен дорог
echo  Для остановки: Ctrl+C
echo ============================================

cd /d "%LLAMA_DIR%"
REM -np 1: один слот, чтобы закэшированная постоянная часть промпта переиспользовалась
llama-server.exe -m "%MODEL%" -ngl %NGL% -t %THREADS% -c %CTX% -np 1 --reasoning off --no-mmap --host %HOST% --port %PORT%

echo.
echo Сервер остановлен. Код выхода: %errorlevel%
if "%errorlevel%"=="-1073741795" echo  - процессор не поддерживает инструкции этой сборки (AVX/AVX2^). Скачай сборку win-cpu-x64.
if "%errorlevel%"=="-1073741515" echo  - не хватает DLL: распакуй архив llama.cpp целиком; для CUDA-сборки нужны ещё cudart-DLL. Без видеокарты - сборка win-cpu-x64.
if "%errorlevel%"=="-1073741819" echo  - аварийное падение (access violation^). Если падает даже "llama-server.exe --version" - обнови Microsoft Visual C++ Redistributable x64 (старый msvcp140.dll^). Иначе - не хватило памяти: уменьши CTX (например, 4096^).
echo Причина обычно написана в строках выше (error / failed / out of memory^).
pause
