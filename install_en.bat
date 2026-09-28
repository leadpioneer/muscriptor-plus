@rem = ASCII-only first line (the rest of this file is plain ASCII) ===========
@echo off
setlocal EnableExtensions
title MuScriptor Plus - Setup
cd /d "%~dp0"

echo.
echo  +==================================================+
echo  !        MuScriptor Plus - setup wizard            !
echo  +==================================================+
echo.

:: ---------- 1. Hardware assessment -----------------------------------------
echo [1/9] Assessing this computer (CPU, RAM, GPU)...
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
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "@((Get-CimInstance Win32_VideoController).Name) -match 'NVIDIA'"`) do if "%%I"=="True" set "GPU_NAME=NVIDIA (driver missing)"
:gpu_probed
if defined GPU_NAME set "DEVICE=cuda"

if not "%DEVICE%"=="cuda" goto :device_decided
set "RECOMMEND=medium"
if defined VRAM_MB if %VRAM_MB% LSS 4000 set "RECOMMEND=small"
if defined VRAM_MB if %VRAM_MB% GEQ 11000 set "RECOMMEND=large"
:device_decided
if not "%DEVICE%"=="cuda" if defined RAM_GB if %RAM_GB% LSS 8 set "VERDICT=Low-end machine"
if not "%DEVICE%"=="cuda" if not defined VERDICT set "VERDICT=Workhorse (CPU)"
if "%DEVICE%"=="cuda" if defined RAM_GB if %RAM_GB% GEQ 16 set "VERDICT=Gaming rig"
if "%DEVICE%"=="cuda" if not defined VERDICT set "VERDICT=Workhorse"

echo       CPU cores: %NUMBER_OF_PROCESSORS%
if defined RAM_GB   echo       RAM: %RAM_GB% GB
if defined GPU_NAME echo       GPU: %GPU_NAME%
if defined VRAM_MB  echo       VRAM: %VRAM_MB% MB
set "TORCH_NOTE=installing PyTorch with CUDA (cu128)"
if not "%DEVICE%"=="cuda" set "TORCH_NOTE=installing the CPU-only PyTorch build (no 2.5 GB CUDA download)"
echo       Verdict: %VERDICT%. %TORCH_NOTE%, recommended model: "%RECOMMEND%".
if "%DEVICE%"=="cuda" goto :gpu_probed2
echo       Transcription will be slower, but everything will work.
:gpu_probed2

:: ---------- 2. winget -------------------------------------------------------
echo [2/9] Checking winget (the wizard uses it to install what is missing)...
where winget >nul 2>nul
if not errorlevel 1 goto :winget_ok
echo   [X] winget not found - without it the wizard cannot install packages itself.
echo       Install "App Installer" from the Microsoft Store and run install_en.bat again.
goto :fail
:winget_ok
echo   [ok] winget is available.

:: ---------- 3. uv -----------------------------------------------------------
echo [3/9] Checking uv (Python dependency manager)...
where uv >nul 2>nul
if not errorlevel 1 goto :uv_ok
:uv_install
echo       uv not found. Installing via winget...
winget install --id=astral-sh.uv -e --accept-source-agreements --accept-package-agreements
call :refresh_path
:uv_check
where uv >nul 2>nul
if not errorlevel 1 goto :uv_ok
echo   [!] uv is still not visible.
choice /c 123 /n /m "  [1] Install via winget again   [2] I installed it myself - check again   [3] Quit"
if errorlevel 3 goto :fail
if errorlevel 2 (
    call :refresh_path
    goto :uv_check
)
goto :uv_install
:uv_ok
echo   [ok] uv found.

:: ---------- 4. Node.js (web UI build) ---------------------------------------
echo [4/9] Checking Node.js (needed to build the web UI)...
where node >nul 2>nul
if not errorlevel 1 goto :node_ok
:node_install
echo       Node.js not found. Installing the LTS version via winget...
winget install --id=OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
call :refresh_path
:node_check
where node >nul 2>nul
if not errorlevel 1 goto :node_ok
echo   [!] Node.js is still not visible.
choice /c 123 /n /m "  [1] Install via winget again   [2] I installed it myself - check again   [3] Quit"
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
    echo   [!] Node.js is outdated: version 22.19+ is required, found %NODE_MAJOR%.%NODE_MINOR%.
    echo       Update it from https://nodejs.org - otherwise the web UI build may fail.
)
echo   [ok] Node.js found.

:: ---------- 5. Python dependencies (torch variant depends on the hardware) --
echo [5/9] Installing Python dependencies...
set "SYNCARGS="
set "RUNSYNC="
if "%DEVICE%"=="cpu" (
    echo       CPU variant: uv sync --no-sources - PyTorch comes from PyPI ^(CPU build^).
    set "SYNCARGS=--no-sources"
    set "RUNSYNC=--no-sync"
) else (
    echo       GPU variant: uv sync - PyTorch with CUDA ^(cu128^) from the PyTorch index.
)
:: uv sync --no-sources rewrites uv.lock for the CPU resolution; the lockfile
:: must stay untouched for GPU machines, so it is restored after the install.
if "%DEVICE%"=="cpu" copy /y uv.lock "%TEMP%\muscriptor-uv.lock.bak" >nul
call uv sync %SYNCARGS%
set "SYNC_RC=%errorlevel%"
if "%DEVICE%"=="cpu" copy /y "%TEMP%\muscriptor-uv.lock.bak" uv.lock >nul
if not "%SYNC_RC%"=="0" goto :fail

echo       Checking PyTorch...
call uv run %RUNSYNC% python -c "import torch; print('       [ok] torch', torch.__version__, '| cuda:', torch.cuda.is_available())"
if errorlevel 1 (
    echo   [X] PyTorch does not import - the environment is broken. Please attach the output above to an issue.
    goto :fail
)

:: ---------- 6. Web UI build --------------------------------------------------
echo [6/9] Building the web UI...
if not exist "web\package.json" (
    echo   [X] The web\ folder is missing - clone the full repository.
    goto :fail
)
pushd web
call corepack pnpm install
if errorlevel 1 (popd & goto :fail)
call corepack pnpm run build
if errorlevel 1 (popd & goto :fail)
popd
echo   [ok] Web UI built (muscriptor\web_dist).

:: ---------- 7. Default model -------------------------------------------------
echo [7/9] Default model choice (can be changed later in the web UI):
echo         1) small  - for machines without a GPU / with a weak GPU
echo         2) medium - speed/accuracy trade-off (default)
echo         3) large  - most accurate, needs a GPU (~12 GB VRAM)
echo       Based on your hardware the wizard recommends: %RECOMMEND%
set "MODEL=%RECOMMEND%"
set /p MODEL_CHOICE="Your choice [1/2/3] (Enter = recommendation): "
if "%MODEL_CHOICE%"=="1" set "MODEL=small"
if "%MODEL_CHOICE%"=="2" set "MODEL=medium"
if "%MODEL_CHOICE%"=="3" set "MODEL=large"
> model.txt echo %MODEL%
echo   [ok] Saved: %MODEL% (model.txt file; delete it to go back to medium)

:: ---------- 8. HuggingFace: access to the model weights ----------------------
echo [8/9] Access to the model weights on HuggingFace.
echo       The weights are gated under the CC BY-NC 4.0 license. You need to (free):
echo         1. Register at https://huggingface.co
echo         2. Open the model page and click "Agree"/"Agree and access":
echo            https://huggingface.co/MuScriptor/muscriptor-%MODEL%
echo         3. Log in with a token on this machine.
set /p HF_ANSWER="Log in with a token now? [y/N]: "
if /i "%HF_ANSWER%"=="y" call uv run %RUNSYNC% hf auth login

:hf_check
echo       Checking access to MuScriptor/muscriptor-%MODEL%...
call uv run %RUNSYNC% python -c "from huggingface_hub import hf_hub_download; hf_hub_download('MuScriptor/muscriptor-%MODEL%', 'config.json'); print('       [ok] access to the weights confirmed')"
if not errorlevel 1 goto :hf_ok
echo   [!] No access yet. Check: the license is accepted on the model page
echo       (link above) and you are logged in - `uv run hf auth whoami`.
choice /c 123 /n /m "  [1] I accepted the license and logged in - check again   [2] Open the model page in the browser   [3] Quit"
if errorlevel 3 goto :fail
if errorlevel 2 start "" "https://huggingface.co/MuScriptor/muscriptor-%MODEL%"
goto :hf_check
:hf_ok

set /p DL_ANSWER="Download the %MODEL% weights now so the first start is fast? [y/N]: "
if /i not "%DL_ANSWER%"=="y" goto :dl_skip
call uv run %RUNSYNC% hf download "MuScriptor/muscriptor-%MODEL%"
if errorlevel 1 (
    echo   [!] The download failed. The weights will be fetched on the first server start.
)
:dl_skip

:: ---------- 9. Companion programs --------------------------------------------
echo [9/9] Companion programs (each one is mandatory - the wizard will not move on
echo       until the program is installed and detected).

set "ST_FF="
:ffmpeg_check
where ffmpeg >nul 2>nul
if not errorlevel 1 goto :ffmpeg_ok
echo   [!] ffmpeg not found - without it lead-vocal removal does not work.
choice /c 123 /n /m "  [1] Install via winget   [2] I installed it myself - check again   [3] Quit"
if errorlevel 3 goto :fail
if errorlevel 2 (
    call :refresh_path
    goto :ffmpeg_check
)
if not defined ST_FF winget install --id=Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
call :refresh_path
goto :ffmpeg_check
:ffmpeg_ok
set "ST_FF=found"
echo   [ok] ffmpeg found  ^(lead-vocal removal will work^)
:ffmpeg_done

set "ST_MS="
:mscore_loop
call :mscore_check
if not errorlevel 1 goto :mscore_ok
echo   [!] MuseScore 4 not found - without it the PDF sheet-music export does not work.
choice /c 1234 /n /m "  [1] Install via winget   [2] I installed it myself - check again   [3] Open the download page   [4] Quit"
if errorlevel 4 goto :fail
if errorlevel 3 (
    start "" "https://musescore.org/en/download"
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
echo   [ok] MuseScore found  ^(PDF/MusicXML sheet export will work^)
:mscore_done

set "ST_FS="
:fs_loop
call :fs_check
if not errorlevel 1 goto :fs_ok
echo   [!] FluidSynth not found in tools\fluidsynth - without it the WAV export does not work.
echo       Download the archive from the release page (the "fluidsynth-...-win10-x64-cpp11.zip"
echo       asset) and unpack its contents into the tools\fluidsynth\ folder of this project.
choice /c 123 /n /m "  [1] I unpacked it - check again   [2] Open the releases page   [3] Quit"
if errorlevel 3 goto :fail
if errorlevel 2 start "" "https://github.com/FluidSynth/fluidsynth/releases"
goto :fs_loop
:fs_ok
set "ST_FS=found"
echo   [ok] FluidSynth found in tools\fluidsynth  ^(WAV export will work^)
:fs_done

:: ---------- Summary ----------------------------------------------------------
> device.txt echo %DEVICE%
echo.
echo  ================ Setup finished ================
echo    Device:                %DEVICE% (device.txt; the server uses it)
if "%DEVICE%"=="cpu" (
    echo    PyTorch:               CPU-only build from PyPI ^(--no-sources^)
) else (
    echo    PyTorch:               CUDA ^(cu128^) from the PyTorch index
)
echo    Web UI:                built
echo    Default model:         %MODEL% (model.txt)
echo    HF weights access:     confirmed
echo    ffmpeg:                %ST_FF%
echo    MuseScore:             %ST_MS%
echo    FluidSynth:            %ST_FS%
echo.
echo    Start the server with:  start.bat
echo  ================================================
pause
exit /b 0

:: ---------- Subroutines ------------------------------------------------------

:: Re-read PATH from the registry so programs installed by winget in this very
:: window are found without restarting the console.
:refresh_path
set "SYS_PATH="
set "USR_PATH="
for /f "tokens=2,*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%B"
for /f "tokens=2,*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USR_PATH=%%B"
if defined SYS_PATH set "PATH=%SYS_PATH%"
if defined USR_PATH set "PATH=%PATH%;%USR_PATH%"
exit /b 0

:: MuseScore: fill MSCORE with the first path found; errorlevel 1 when absent.
:mscore_check
set "MSCORE="
if exist "%ProgramFiles%\MuseScore 4\bin\MuseScore4.exe" set "MSCORE=%ProgramFiles%\MuseScore 4\bin\MuseScore4.exe"
if not defined MSCORE if exist "%ProgramFiles(x86)%\MuseScore 4\bin\MuseScore4.exe" set "MSCORE=%ProgramFiles(x86)%\MuseScore 4\bin\MuseScore4.exe"
if not defined MSCORE if exist "%LOCALAPPDATA%\Programs\MuseScore 4\bin\MuseScore4.exe" set "MSCORE=%LOCALAPPDATA%\Programs\MuseScore 4\bin\MuseScore4.exe"
if not defined MSCORE exit /b 1
exit /b 0

:: FluidSynth: errorlevel 0 when tools\fluidsynth contains a fluidsynth.exe.
:fs_check
dir /b /s "tools\fluidsynth\*fluidsynth.exe" >nul 2>nul
exit /b %errorlevel%

:: Remember the Node version (called from for /f).
:node_ver
set "NODE_MAJOR=%1"
set "NODE_MINOR=%2"
exit /b 0

:fail
echo.
echo   [X] Setup aborted. Fix the problem above and run install_en.bat again -
echo       the steps that already succeeded will repeat in seconds.
pause
exit /b 1