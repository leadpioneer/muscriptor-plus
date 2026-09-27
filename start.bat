@rem = ASCII-only first line (the rest is UTF-8, switched below) ============
@echo off
chcp 65001 >nul
setlocal EnableExtensions
title MuScriptor Plus
cd /d "%~dp0"

:: ---- Кодировка для Python-вывода (иначе cp1251 падает на не-ASCII) ----
set "PYTHONUTF8=1"

:: ---- FluidSynth из tools\ (экспорт WAV) — добавить в PATH, если есть ----
for /f "delims=" %%F in ('dir /b /s "tools\fluidsynth\*fluidsynth.exe" 2^>nul') do (
    for %%D in ("%%~dpF.") do set "FS_BIN=%%~fD"
)
if defined FS_BIN set "PATH=%FS_BIN%;%PATH%"

:: ---- ffmpeg (удаление ведущего вокала) — просто предупредить, если нет ----
where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo   [!] ffmpeg не найден в PATH — удаление ведущего вокала будет недоступно.
    echo       Установите: winget install Gyan.FFmpeg, затем откройте новую консоль.
)

:: ---- Модель по умолчанию: из model.txt, иначе medium --------------------
set "MODEL=medium"
if exist model.txt set /p MODEL=<model.txt
set "MODEL=%MODEL: =%"

:: ---- Проверка установки --------------------------------------------------
if not exist ".venv" (
    echo   [!] Виртуальное окружение не найдено. Сначала запустите install.bat.
    pause
    exit /b 1
)

:: ---- Если сервер уже работает — просто открываем браузер ----------------
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8222/health' -TimeoutSec 3; if ($r.StatusCode -eq 200) { exit 0 } } catch { exit 1 }" >nul 2>nul
if not errorlevel 1 (
    echo   [ok] Сервер уже запущен — открываю браузер.
    start "" "http://127.0.0.1:8222"
    exit /b 0
)

echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║      MuScriptor Plus — запуск сервера (%MODEL%)       ║
echo  ╚══════════════════════════════════════════════════╝
echo.
echo   Запускаю сервер на http://127.0.0.1:8222
echo   Первая загрузка модели может занять несколько минут...
echo   (окно можно закрыть — сервер остановится вместе с ним)
echo.

start "MuScriptor Plus server" /min cmd /c "chcp 65001 >nul & set PYTHONUTF8=1& uv run muscriptor serve --model %MODEL% --host 127.0.0.1 --port 8222 & pause"

echo   Жду, пока сервер поднимется...
powershell -NoProfile -Command "$deadline = (Get-Date).AddMinutes(5); while ((Get-Date) -lt $deadline) { try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8222/health' -TimeoutSec 3; if ($r.StatusCode -eq 200) { exit 0 } } catch {}; Start-Sleep -Seconds 3 }; exit 1" >nul 2>nul
if errorlevel 1 (
    echo   [X] Сервер не ответил за 5 минут. Посмотрите окно сервера — вероятно,
    echo       не выполнен вход в HuggingFace (см. install.bat, шаг 5).
    pause
    exit /b 1
)

echo   [ok] Сервер работает — открываю http://127.0.0.1:8222
start "" "http://127.0.0.1:8222"
echo.
echo   Это окно можно закрыть; чтобы остановить сервер — закройте
echo   свёрнутое окно "MuScriptor Plus server".
timeout /t 8 >nul
exit /b 0
