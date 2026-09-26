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

:: ---------- 1. uv -----------------------------------------------------------
echo [1/7] Проверяю uv (менеджер Python-зависимостей)...
where uv >nul 2>nul
if errorlevel 1 (
    echo       uv не найден. Пробую установить через winget...
    winget install --id=astral-sh.uv -e --accept-source-agreements --accept-package-agreements
    where uv >nul 2>nul
    if errorlevel 1 (
        echo   [X] Не удалось установить uv автоматически.
        echo       Установите вручную: https://docs.astral.sh/uv/getting-started/installation/
        echo       (после установки откройте новое окно консоли и запустите install.bat снова)
        goto :fail
    )
)
echo   [ok] uv найден.

:: ---------- 2. pnpm (для сборки веб-интерфейса) ----------------------------
echo [2/7] Проверяю pnpm (сборка веб-интерфейса)...
where pnpm >nul 2>nul
if not errorlevel 1 goto :pnpm_ok
where corepack >nul 2>nul
if errorlevel 1 (
    echo   [!] corepack не найден — нужен Node.js. Установите Node
    echo       (https://nodejs.org) и запустите install.bat снова.
    echo       Пока пропускаю сборку веб-интерфейса.
    goto :pnpm_done
)
corepack enable pnpm >nul 2>nul
:pnpm_ok
echo   [ok] pnpm доступен.
:pnpm_done

:: ---------- 3. Python-зависимости ------------------------------------------
echo [3/7] Устанавливаю Python-зависимости (uv sync)...
echo       На Windows это также ставит PyTorch с поддержкой CUDA (cu128).
call uv sync
if errorlevel 1 goto :fail

:: ---------- 4. Сборка веб-интерфейса ---------------------------------------
echo [4/7] Собираю веб-интерфейс...
if not exist "web\package.json" (
    echo   [!] Папка web\ не найдена — пропускаю сборку.
    goto :web_done
)
pushd web
call corepack pnpm install
if errorlevel 1 popd & goto :web_fail
call corepack pnpm run build
if errorlevel 1 popd & goto :web_fail
popd
echo   [ok] Веб-интерфейс собран (muscriptor\web_dist).
goto :web_done
:web_fail
echo   [X] Сборка веб-интерфейса не удалась. Сервер заработает и без него,
echo       но UI будет недоступен. Проверьте Node/pnpm и запустите install.bat снова.
goto :fail
:web_done

:: ---------- 5. HuggingFace --------------------------------------------------
echo [5/7] Вход в HuggingFace.
echo       Веса модели закрыты лицензией CC BY-NC 4.0: сначала примите её на страницах
echo         https://huggingface.co/MuScriptor/muscriptor-medium  (кнопка Agree)
echo         https://huggingface.co/MuScriptor/muscriptor-large
echo       (доступ выдаётся автоматически после логина на сайте).
set /p HF_ANSWER="Настроить вход по токену сейчас? [y/N]: "
if /i "%HF_ANSWER%"=="y" (
    call uv run hf auth login
) else (
    echo   [-] Пропускаю. Не забудьте: uv run hf auth login
)

:: ---------- 6. Модель по умолчанию ------------------------------------------
echo [6/7] Выбор модели по умолчанию (потом можно менять прямо в веб-интерфейсе):
echo         1) small  — для машин без GPU
echo         2) medium — баланс скорости и точности (по умолчанию)
echo         3) large  — самая точная, нужен GPU (~12 ГБ VRAM)
set MODEL=medium
choice /c 123 /n /m "Ваш выбор [1/2/3]: "
if errorlevel 3 set MODEL=large
if errorlevel 2 set MODEL=medium
if errorlevel 1 set MODEL=small
> model.txt echo %MODEL%
echo   [ok] Сохранено: %MODEL% (файл model.txt; удалите его, чтобы вернуться к medium)

:: ---------- 7. MuseScore / FluidSynth ---------------------------------------
echo [7/7] Проверка сопутствующих программ.
set "MSCORE="
if exist "%ProgramFiles%\MuseScore 4\bin\MuseScore4.exe" set "MSCORE=%ProgramFiles%\MuseScore 4\bin\MuseScore4.exe"
if exist "%ProgramFiles(x86)%\MuseScore 4\bin\MuseScore4.exe" set "MSCORE=%ProgramFiles(x86)%\MuseScore 4\bin\MuseScore4.exe"
if exist "%LOCALAPPDATA%\Programs\MuseScore 4\bin\MuseScore4.exe" set "MSCORE=%LOCALAPPDATA%\Programs\MuseScore 4\bin\MuseScore4.exe"
if defined MSCORE (
    echo   [ok] MuseScore найден: %MSCORE%  (ноты в PDF будут работать)
) else (
    echo   [!] MuseScore 4 не найден — не будет скачивания нот в PDF.
    echo       Установите с https://musescore.org/ru/download и перезапустите install.bat.
)
dir /b /s "tools\fluidsynth\*fluidsynth.exe" >nul 2>nul
if not errorlevel 1 (
    echo   [ok] FluidSynth найден в tools\fluidsynth  (экспорт WAV будет работать)
) else (
    echo   [!] FluidSynth не найден в tools\fluidsynth — не будет экспорта WAV.
    echo       Скачайте https://github.com/FluidSynth/fluidsynth/releases
    echo       ^(asset "fluidsynth-...-win10-x64-cpp11.zip"^) и распакуйте в tools\fluidsynth\
)

echo.
echo  ══════════════════════════════════════════════════
echo   Готово! Запускайте сервер командой:  start.bat
echo  ══════════════════════════════════════════════════
pause
exit /b 0

:fail
echo.
echo   [X] Установка прервана из-за ошибки выше.
pause
exit /b 1
