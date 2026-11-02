@echo off
chcp 65001 >nul
title bge-m3 embeddings

REM === Настройки ===
set LLAMA_DIR=E:\llama
set MODEL=F:\kobold_model\bge-m3-Q8_0.gguf
REM 0 = только CPU (работа). С видеокартой — 99 (нужна CUDA/Vulkan-сборка llama.cpp)
set NGL=0
REM Потоки: число физических ядер
set THREADS=4
REM Текст целиком должен влезать в один батч: CTX = BATCH = UBATCH
set CTX=8192
set HOST=127.0.0.1
set PORT=8081

if not exist "%LLAMA_DIR%\llama-server.exe" (
    echo [ОШИБКА] Не найден llama-server.exe в %LLAMA_DIR%
    pause & exit /b 1
)
if not exist "%MODEL%" (
    echo [ОШИБКА] Не найден файл модели: %MODEL%
    pause & exit /b 1
)

echo ============================================
echo  Эмбеддинги bge-m3:  http://%HOST%:%PORT%/v1
echo  В .env:  EMB_BASE_URL=http://%HOST%:%PORT%/v1
echo  Для остановки: Ctrl+C
echo ============================================

cd /d "%LLAMA_DIR%"
llama-server.exe -m "%MODEL%" --embedding --pooling cls -ngl %NGL% -t %THREADS% -c %CTX% -b %CTX% -ub %CTX% -np 1 --no-mmap --host %HOST% --port %PORT%

echo.
echo Сервер остановлен. Код выхода: %errorlevel%
if "%errorlevel%"=="-1073741795" echo  - процессор не поддерживает инструкции этой сборки (AVX/AVX2^). Скачай сборку win-cpu-x64.
if "%errorlevel%"=="-1073741515" echo  - не хватает DLL: распакуй архив llama.cpp целиком; для CUDA-сборки нужны ещё cudart-DLL. Без видеокарты — сборка win-cpu-x64.
echo Причина обычно написана в строках выше (error / failed / out of memory^).
pause
