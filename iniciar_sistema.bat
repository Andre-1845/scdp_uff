@echo off
title Sistema de Afastamentos SCDP - preparando...
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo ============================================================
  echo  O Python nao foi encontrado neste computador.
  echo  Siga o "Guia de instalacao" que veio junto com esta pasta
  echo  para instalar o Python primeiro. Depois, clique de novo
  echo  neste atalho.
  echo ============================================================
  echo.
  pause
  exit /b 1
)

if not exist venv (
  echo Preparando o sistema pela primeira vez, isso pode levar alguns minutos...
  echo Nao feche esta janela.
  python -m venv venv
  call venv\Scripts\activate.bat
  python -m pip install --upgrade pip -q
  pip install -r requirements.txt -q
) else (
  call venv\Scripts\activate.bat
)

if not exist .env (
  copy .env.example .env >nul
  echo.
  echo Um arquivo de configuracao (.env) foi criado agora, com os valores
  echo de exemplo. Veja o Guia de instalacao se precisar ajustar algo,
  echo como os e-mails da Secretaria.
  echo.
)

start "Sistema SCDP - Afastamentos - NAO FECHE esta janela enquanto estiver usando o sistema" cmd /k "venv\Scripts\python.exe app.py"
timeout /t 3 /nobreak >nul
start "" http://localhost:5000
exit
