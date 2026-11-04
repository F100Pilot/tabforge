@echo off
rem TabForge a partir do codigo fonte (Windows). Atualiza, prepara o que faltar e arranca.
rem Uso: start.bat            abre a aplicacao
rem      start.bat --smoke    autoteste sem janela (resultado em %LOCALAPPDATA%\TabForge\logs)
setlocal
cd /d "%~dp0"

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

echo == A atualizar o codigo
git pull --ff-only
if errorlevel 1 echo Aviso: git pull falhou; continua com a versao local.

cd apps\desktop
echo == A instalar dependencias ^(a primeira vez demora^)
uv sync --frozen --extra bundle
if errorlevel 1 goto :fail

uv run --frozen --no-sync python packaging\dev_start.py %*
if errorlevel 1 goto :fail
exit /b 0

:fail
echo.
echo O TabForge nao arrancou. Registos: %LOCALAPPDATA%\TabForge\logs
rem No pause in CI (GitHub Actions sets CI=true): it would wait for a key forever.
if not defined CI pause
exit /b 1
