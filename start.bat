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
echo == A instalar dependencias ^(a primeira vez demora^)
rem Our own packages are reinstalled from the checkout on every start: uv only rebuilds a
rem path package when its pyproject.toml changes, so a git pull would keep the old code.
uv sync --frozen --extra bundle --reinstall-package tabforge-api --reinstall-package tabforge-worker --reinstall-package tabforge-score
if errorlevel 1 goto :fail

uv run --frozen --no-sync python packaging\dev_start.py %ARGS%
if errorlevel 1 goto :fail
exit /b 0

:fail
echo.
echo O TabForge nao arrancou. Registos: %LOCALAPPDATA%\TabForge\logs
rem No pause in CI (GitHub Actions sets CI=true): it would wait for a key forever.
if not defined CI pause
exit /b 1
