@echo off
rem TabForge a partir do codigo fonte (Windows). Atualiza para o ultimo commit do main,
rem prepara o que faltar e arranca.
rem Uso: start.bat            abre a aplicacao
rem      start.bat --smoke    autoteste sem janela (resultado em %LOCALAPPDATA%\TabForge\logs)
setlocal

rem cmd.exe reads a running .bat from disk line by line: if git pull changed this file
rem mid-run, it would execute half-lines. Run from a temporary copy instead.
if /i not "%~1"=="--relaunched" (
  copy /y "%~f0" "%TEMP%\tabforge-start.bat" >nul
  if errorlevel 1 goto :fail
  call "%TEMP%\tabforge-start.bat" --relaunched "%~dp0" %*
  exit /b %errorlevel%
)
set "REPO=%~2"
set "ARGS=%3 %4 %5 %6 %7 %8 %9"
cd /d "%REPO%"
if errorlevel 1 goto :fail

rem OneDrive syncs and locks the thousands of files of the Python environment ("Access is
rem denied" on updates): stop with the fix. A label, not a ( ) block: the path may hold ")".
echo "%REPO%" | findstr /i "OneDrive" >nul
if not errorlevel 1 goto :onedrive

where git >nul 2>nul
if errorlevel 1 (
  echo Falta o Git para Windows: https://git-scm.com/download/win
  goto :fail
)

where uv >nul 2>nul
if errorlevel 1 (
  echo A instalar o uv ^(gestor de Python, uma vez^)...
  powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  if errorlevel 1 goto :fail
  set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)

rem In CI the checkout is the commit under test: no branch switch, no pull.
if defined CI goto :deps

echo == A atualizar o codigo ^(main^)
git fetch origin
if errorlevel 1 (
  echo Aviso: sem ligacao ao GitHub; continua com a versao local.
  goto :deps
)
for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD') do set "BRANCH=%%b"
if /i not "%BRANCH%"=="main" (
  rem Only once main has this launcher (after the desktop work is merged).
  git cat-file -e origin/main:start.bat 2>nul
  if not errorlevel 1 (
    echo == A mudar do ramo %BRANCH% para main
    git checkout main
    if errorlevel 1 echo Aviso: nao foi possivel mudar para main; continua em %BRANCH%.
  )
)
git pull --ff-only
if errorlevel 1 echo Aviso: git pull falhou; continua com a versao local.

:deps
cd apps\desktop
rem Always a uv-managed Python: the Microsoft Store Python redirects %LOCALAPPDATA% to a private
rem folder, so the data folder it creates is invisible to PostgreSQL (and to the user). uv
rem recreates a .venv that was made with another Python.
set "UV_MANAGED_PYTHON=1"
echo == A instalar dependencias ^(a primeira vez demora^)
rem Our own packages are reinstalled from the checkout on every start: uv only rebuilds a
rem path package when its pyproject.toml changes, so a git pull would keep the old code.
set "SYNC=uv sync --frozen --extra bundle --reinstall-package tabforge-api --reinstall-package tabforge-worker --reinstall-package tabforge-score"
%SYNC%
if not errorlevel 1 goto :run
rem A .venv that uv cannot use any more ("Failed to query Python interpreter ... Access is
rem denied": python.exe blocked or quarantined by security software, or a half-deleted venv)
rem is thrown away and built again once; the data in %LOCALAPPDATA%\TabForge is not touched.
echo == O ambiente Python nao respondeu; a cria-lo de novo
rmdir /s /q .venv 2>nul
%SYNC%
if errorlevel 1 goto :venv

:run

uv run --frozen --no-sync python packaging\dev_start.py %ARGS%
if errorlevel 1 goto :fail
exit /b 0

:venv
echo.
echo Nao foi possivel preparar o ambiente Python em %CD%\.venv
echo  1. Feche o TabForge e termine no Gestor de Tarefas os python.exe e postgres.exe.
echo  2. Corra o start.bat outra vez.
echo  3. Se repetir: Seguranca do Windows - Protecao contra virus e ameacas - Historico de
echo     protecao. Se o python.exe aparecer bloqueado, so a TI pode autoriza-lo.
goto :fail

:onedrive
echo.
echo O TabForge esta dentro do OneDrive: "%REPO%"
echo O OneDrive bloqueia os ficheiros do ambiente Python e as atualizacoes falham.
echo Feche o TabForge e instale-o fora do OneDrive, numa linha de comandos:
echo     cd /d C:\
echo     git clone https://github.com/F100Pilot/tabforge.git
echo     C:\tabforge\start.bat
echo As tabs ficam em %LOCALAPPDATA%\TabForge e nao se perdem.
goto :fail

:fail
echo.
echo O TabForge nao arrancou. Registos: %LOCALAPPDATA%\TabForge\logs
rem No pause in CI (GitHub Actions sets CI=true): it would wait for a key forever.
if not defined CI pause
exit /b 1
