@rem = ASCII-only first line (the rest is UTF-8, switched below) ============
@echo off
chcp 65001 >nul
setlocal EnableExtensions
title MuScriptor Plus — установка
cd /d "%~dp0"

echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║        MuScriptor Plus — мастер установки        ║
echo  ╚══════════════════════════════════════════════════╝
echo.

:: ---------- 1. Оценка железа ------------------------------------------------
echo [1/9] Оцениваю компьютер (CPU, RAM, GPU)...
set "RAM_GB="
set "GPU_NAME="
set "VRAM_MB="
set "DEVICE=cpu"
set "VERDICT="
set "RECOMMEND=small"

for /f %%I in ('powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB)"') do set "RAM_GB=%%I"

where nvidia-smi >nul 2>nul
if not errorlevel 1 (
    for /f "delims=" %%I in ('nvidia-smi --query-gpu^=name --format^=csv,noheader') do if not defined GPU_NAME set "GPU_NAME=%%I"
    for /f "delims=" %%I in ('nvidia-smi --query-gpu^=memory.total --format^=csv,noheader,nounits') do if not defined VRAM_MB set "VRAM_MB=%%I"
    goto :gpu_probed
)
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "@((Get-CimInstance Win32_VideoController).Name) -match 'NVIDIA'"`) do if "%%I"=="True" set "GPU_NAME=NVIDIA (без драйвера)"
:gpu_probed
if defined GPU_NAME set "DEVICE=cuda"

if not "%DEVICE%"=="cuda" goto :device_decided
set "RECOMMEND=medium"
if defined VRAM_MB if %VRAM_MB% LSS 4000 set "RECOMMEND=small"
if defined VRAM_MB if %VRAM_MB% GEQ 11000 set "RECOMMEND=large"
:device_decided
if not "%DEVICE%"=="cuda" if defined RAM_GB if %RAM_GB% LSS 8 set "VERDICT=Тапок"
if not "%DEVICE%"=="cuda" if not defined VERDICT set "VERDICT=Рабочая лошадка (CPU)"
if "%DEVICE%"=="cuda" if defined RAM_GB if %RAM_GB% GEQ 16 set "VERDICT=Игровая сборка"
if "%DEVICE%"=="cuda" if not defined VERDICT set "VERDICT=Рабочая лошадка"

echo       Ядер процессора: %NUMBER_OF_PROCESSORS%
if defined RAM_GB   echo       Оперативная память: %RAM_GB% ГБ
if defined GPU_NAME echo       GPU: %GPU_NAME%
if defined VRAM_MB  echo       Видеопамять: %VRAM_MB% МБ
set "TORCH_NOTE=Ставлю PyTorch с CUDA (cu128)"
if not "%DEVICE%"=="cuda" set "TORCH_NOTE=Ставлю CPU-вариант PyTorch (без 2,5 ГБ CUDA-загрузки)"
echo       Вердикт: %VERDICT%. %TORCH_NOTE%, рекомендую модель "%RECOMMEND%".
if "%DEVICE%"=="cuda" goto :gpu_probed2
echo       Транскрипция пойдёт медленнее, но всё заработает.
:gpu_probed2

:: ---------- 2. winget -------------------------------------------------------
echo [2/9] Проверяю winget (через него мастер ставит недостающее)...
where winget >nul 2>nul
if not errorlevel 1 goto :winget_ok
echo   [X] winget не найден — без него мастер не сможет устанавливать пакеты сам.
echo       Установите "App Installer" из Microsoft Store и запустите install.bat снова.
goto :fail
:winget_ok
echo   [ok] winget доступен.

:: ---------- 3. uv -----------------------------------------------------------
echo [3/9] Проверяю uv (менеджер Python-зависимостей)...
where uv >nul 2>nul
if not errorlevel 1 goto :uv_ok
:uv_install
echo       uv не найден. Устанавливаю через winget...
winget install --id=astral-sh.uv -e --accept-source-agreements --accept-package-agreements
call :refresh_path
:uv_check
where uv >nul 2>nul
if not errorlevel 1 goto :uv_ok
echo   [!] uv по-прежнему не виден.
choice /c 123 /n /m "  [1] Установить через winget ещё раз   [2] Я установил сам — проверить снова   [3] Выйти"
if errorlevel 3 goto :fail
if errorlevel 2 (
    call :refresh_path
    goto :uv_check
)
goto :uv_install
:uv_ok
echo   [ok] uv найден.

:: ---------- 4. Node.js (сборка веб-интерфейса) ------------------------------
echo [4/9] Проверяю Node.js (нужен для сборки веб-интерфейса)...
where node >nul 2>nul
if not errorlevel 1 goto :node_ok
:node_install
echo       Node.js не найден. Устанавливаю LTS-версию через winget...
winget install --id=OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
call :refresh_path
:node_check
where node >nul 2>nul
if not errorlevel 1 goto :node_ok
echo   [!] Node.js по-прежнему не виден.
choice /c 123 /n /m "  [1] Установить через winget ещё раз   [2] Я установил сам — проверить снова   [3] Выйти"
if errorlevel 3 goto :fail
if errorlevel 2 (
    call :refresh_path
    goto :node_check
)
goto :node_install
:node_ok
set "NODE_MAJOR=0"
set "NODE_MINOR=0"
for /f "tokens=1,2 delims=v. " %%I in ('node --version') do call :node_ver %%I %%J
set "NODE_OLD=0"
if %NODE_MAJOR% LSS 22 set "NODE_OLD=1"
if %NODE_MAJOR% EQU 22 if %NODE_MINOR% LSS 19 set "NODE_OLD=1"
if "%NODE_OLD%"=="1" (
    echo   [!] Node.js устарел: нужна версия 22.19+, найдена %NODE_MAJOR%.%NODE_MINOR%.
    echo       Обновите с https://nodejs.org — иначе сборка веб-интерфейса может упасть.
)
echo   [ok] Node.js найден.

:: ---------- 5. Python-зависимости (вариант torch зависит от железа) ---------
echo [5/9] Устанавливаю Python-зависимости...
set "SYNCARGS="
set "RUNSYNC="
if "%DEVICE%"=="cpu" (
    echo       CPU-вариант: uv sync --no-sources — PyTorch берётся с PyPI ^(CPU-сборка^).
    set "SYNCARGS=--no-sources"
    set "RUNSYNC=--no-sync"
) else (
    echo       GPU-вариант: uv sync — PyTorch с CUDA ^(cu128^) с индекса PyTorch.
)
:: uv sync --no-sources перезаписывает uv.lock под CPU-резолюцию; для GPU-машин
:: лок должен остаться прежним, поэтому после установки возвращаем его на место.
if "%DEVICE%"=="cpu" copy /y uv.lock "%TEMP%\muscriptor-uv.lock.bak" >nul
call uv sync %SYNCARGS%
set "SYNC_RC=%errorlevel%"
if "%DEVICE%"=="cpu" copy /y "%TEMP%\muscriptor-uv.lock.bak" uv.lock >nul
if not "%SYNC_RC%"=="0" goto :fail

echo       Проверяю PyTorch...
call uv run %RUNSYNC% python -c "import torch; print('       [ok] torch', torch.__version__, '| cuda:', torch.cuda.is_available())"
if errorlevel 1 (
    echo   [X] PyTorch не импортируется — окружение сломано. Покажите вывод выше в issue.
    goto :fail
)

:: ---------- 6. Сборка веб-интерфейса ----------------------------------------
echo [6/9] Собираю веб-интерфейс...
if not exist "web\package.json" (
    echo   [X] Папка web\ не найдена — клонируйте репозиторий целиком.
    goto :fail
)
pushd web
call corepack pnpm install
if errorlevel 1 (popd & goto :fail)
call corepack pnpm run build
if errorlevel 1 (popd & goto :fail)
popd
echo   [ok] Веб-интерфейс собран (muscriptor\web_dist).

:: ---------- 7. Модель по умолчанию ------------------------------------------
echo [7/9] Выбор модели по умолчанию (потом меняется в веб-интерфейсе):
echo         1) small  — для машин без GPU / со слабым GPU
echo         2) medium — баланс скорости и точности (по умолчанию)
echo         3) large  — самая точная, нужен GPU (~12 ГБ VRAM)
echo       По железу мастер рекомендует: %RECOMMEND%
set "MODEL=%RECOMMEND%"
set /p MODEL_CHOICE="Ваш выбор [1/2/3] (Enter = рекомендация): "
if "%MODEL_CHOICE%"=="1" set "MODEL=small"
if "%MODEL_CHOICE%"=="2" set "MODEL=medium"
if "%MODEL_CHOICE%"=="3" set "MODEL=large"
> model.txt echo %MODEL%
echo   [ok] Сохранено: %MODEL% (файл model.txt; удалите его, чтобы вернуться к medium)

:: ---------- 8. HuggingFace: доступ к весам ----------------------------------
echo [8/9] Доступ к весам модели на HuggingFace.
echo       Веса закрыты лицензией CC BY-NC 4.0. Нужно ^(бесплатно^):
echo         1. Зарегистрироваться на https://huggingface.co
echo         2. Открыть страницу модели и нажать "Agree"/"Agree and access":
echo            https://huggingface.co/MuScriptor/muscriptor-%MODEL%
echo         3. Войти по токену на этой машине.
set /p HF_ANSWER="Войти по токену сейчас? [y/N]: "
if /i "%HF_ANSWER%"=="y" call uv run %RUNSYNC% hf auth login

:hf_check
echo       Проверяю доступ к MuScriptor/muscriptor-%MODEL%...
call uv run %RUNSYNC% python -c "from huggingface_hub import hf_hub_download; hf_hub_download('MuScriptor/muscriptor-%MODEL%', 'config.json'); print('       [ok] доступ к весам подтверждён')"
if not errorlevel 1 goto :hf_ok
echo   [!] Доступа пока нет. Проверьте: лицензия принята на странице модели
echo       ^(ссылка выше^) и выполнен вход — `uv run hf auth whoami`.
choice /c 123 /n /m "  [1] Я принял лицензию и вошёл — проверить снова   [2] Открыть страницу модели в браузере   [3] Выйти"
if errorlevel 3 goto :fail
if errorlevel 2 start "" "https://huggingface.co/MuScriptor/muscriptor-%MODEL%"
goto :hf_check
:hf_ok

set /p DL_ANSWER="Скачать веса %MODEL% сейчас, чтобы первый запуск был быстрым? [y/N]: "
if /i not "%DL_ANSWER%"=="y" goto :dl_skip
call uv run %RUNSYNC% hf download "MuScriptor/muscriptor-%MODEL%"
if errorlevel 1 (
    echo   [!] Скачивание не удалось. Веса докачаются при первом запуске сервера.
)
:dl_skip

:: ---------- 9. Сопутствующие программы --------------------------------------
echo [9/9] Сопутствующие программы (каждая обязательна — мастер не пойдёт дальше,
echo       пока программа не установлена и не обнаружена).

set "ST_FF="
:ffmpeg_check
where ffmpeg >nul 2>nul
if not errorlevel 1 goto :ffmpeg_ok
echo   [!] ffmpeg не найден — без него не работает удаление ведущего вокала.
choice /c 123 /n /m "  [1] Установить через winget   [2] Я установил сам — проверить снова   [3] Выйти"
if errorlevel 3 goto :fail
if errorlevel 2 (
    call :refresh_path
    goto :ffmpeg_check
)
if not defined ST_FF winget install --id=Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
call :refresh_path
goto :ffmpeg_check
:ffmpeg_ok
set "ST_FF=найден"
echo   [ok] ffmpeg найден  ^(удаление ведущего вокала будет работать^)
:ffmpeg_done

set "ST_MS="
:mscore_loop
call :mscore_check
if not errorlevel 1 goto :mscore_ok
echo   [!] MuseScore 4 не найден — без него не работает экспорт нот в PDF.
choice /c 1234 /n /m "  [1] Установить через winget   [2] Я установил сам — проверить снова   [3] Открыть страницу скачивания   [4] Выйти"
if errorlevel 4 goto :fail
if errorlevel 3 (
    start "" "https://musescore.org/ru/download"
    goto :mscore_loop
)
if errorlevel 2 (
    call :refresh_path
    goto :mscore_loop
)
if not defined ST_MS winget install --id=MuseScore.MuseScore -e --accept-source-agreements --accept-package-agreements
call :refresh_path
goto :mscore_loop
:mscore_ok
set "ST_MS=%MSCORE%"
echo   [ok] MuseScore найден  ^(ноты в PDF/MusicXML будут работать^)
:mscore_done

set "ST_FS="
:fs_loop
call :fs_check
if not errorlevel 1 goto :fs_ok
echo   [!] FluidSynth не найден в tools\fluidsynth — без него не работает экспорт WAV.
echo       Скачайте архив с релиза (asset "fluidsynth-...-win10-x64-cpp11.zip") и
echo       распакуйте содержимое в папку tools\fluidsynth\ этого проекта.
choice /c 123 /n /m "  [1] Я распаковал — проверить снова   [2] Открыть страницу релизов   [3] Выйти"
if errorlevel 3 goto :fail
if errorlevel 2 start "" "https://github.com/FluidSynth/fluidsynth/releases"
goto :fs_loop
:fs_ok
set "ST_FS=найден"
echo   [ok] FluidSynth найден в tools\fluidsynth  ^(экспорт WAV будет работать^)
:fs_done

:: ---------- Итог ------------------------------------------------------------
> device.txt echo %DEVICE%
echo.
echo  ═════════════════════════ Установка завершена ═════════════════════════
echo    Устройство:            %DEVICE% (device.txt; сервер использует это)
if "%DEVICE%"=="cpu" (
    echo    PyTorch:               CPU-сборка с PyPI ^(--no-sources^)
) else (
    echo    PyTorch:               CUDA ^(cu128^) с индекса PyTorch
)
echo    Веб-интерфейс:         собран
echo    Модель по умолчанию:   %MODEL% (model.txt)
echo    Доступ к весам HF:     подтверждён
echo    ffmpeg:                %ST_FF%
echo    MuseScore:             %ST_MS%
echo    FluidSynth:            %ST_FS%
echo.
echo    Запускайте сервер командой:  start.bat
echo  ══════════════════════════════════════════════════════════════════════
pause
exit /b 0

:: ---------- Подпрограммы ----------------------------------------------------

:: Перечитать PATH из реестра, чтобы программы, установленные winget в этом же
:: окне, находились без перезапуска консоли.
:refresh_path
set "SYS_PATH="
set "USR_PATH="
for /f "tokens=2,*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%B"
for /f "tokens=2,*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USR_PATH=%%B"
if defined SYS_PATH set "PATH=%SYS_PATH%"
if defined USR_PATH set "PATH=%PATH%;%USR_PATH%"
exit /b 0

:: MuseScore: заполнить MSCORE первым найденным путём; errorlevel 1, если нет.
:mscore_check
set "MSCORE="
if exist "%ProgramFiles%\MuseScore 4\bin\MuseScore4.exe" set "MSCORE=%ProgramFiles%\MuseScore 4\bin\MuseScore4.exe"
if not defined MSCORE if exist "%ProgramFiles(x86)%\MuseScore 4\bin\MuseScore4.exe" set "MSCORE=%ProgramFiles(x86)%\MuseScore 4\bin\MuseScore4.exe"
if not defined MSCORE if exist "%LOCALAPPDATA%\Programs\MuseScore 4\bin\MuseScore4.exe" set "MSCORE=%LOCALAPPDATA%\Programs\MuseScore 4\bin\MuseScore4.exe"
if not defined MSCORE exit /b 1
exit /b 0

:: FluidSynth: errorlevel 0, если в tools\fluidsynth есть fluidsynth.exe.
:fs_check
dir /b /s "tools\fluidsynth\*fluidsynth.exe" >nul 2>nul
exit /b %errorlevel%

:: Запомнить версию Node (вызывается из for /f).
:node_ver
set "NODE_MAJOR=%1"
set "NODE_MINOR=%2"
exit /b 0

:fail
echo.
echo   [X] Установка прервана. Исправьте проблему выше и запустите install.bat снова —
echo       уже выполненные шаги мастер пройдёт повторно за секунды.
pause
exit /b 1