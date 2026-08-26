@echo off
title Gerando o scdp-uff.exe...
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo O Python nao foi encontrado neste computador. Instale o Python
  echo primeiro ^(veja o Guia de instalacao, Passo 1^) e rode este arquivo
  echo de novo.
  echo.
  pause
  exit /b 1
)

if not exist venv (
  echo Preparando o ambiente pela primeira vez...
  python -m venv venv
)
call venv\Scripts\activate.bat

echo Instalando as pecas necessarias (isso roda so uma vez, pode levar
echo alguns minutos)...
python -m pip install --upgrade pip -q
pip install -r requirements.txt -q
pip install pyinstaller -q

echo.
echo Gerando o scdp-uff.exe, aguarde...
echo.
pyinstaller --noconfirm --onefile --name scdp-uff ^
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --add-data "forms_config.json;." ^
  app.py

if not exist dist\scdp-uff.exe (
  echo.
  echo Algo deu errado e o scdp-uff.exe nao foi gerado. Role a tela para
  echo cima e procure por uma linha que comece com "ERROR". Copie essa
  echo mensagem para pedir ajuda.
  echo.
  pause
  exit /b 1
)

copy /Y dist\scdp-uff.exe scdp-uff.exe >nul
rmdir /s /q build >nul 2>nul
del /q scdp-uff.spec >nul 2>nul

echo.
echo ============================================================
echo  Pronto! O arquivo scdp-uff.exe foi criado nesta pasta.
echo.
echo  A partir de agora, esse UNICO arquivo (scdp-uff.exe) e tudo o
echo  que voce precisa para rodar o sistema, em QUALQUER computador
echo  Windows - nem precisa ter Python instalado la. Copie o
echo  scdp-uff.exe para onde quiser (um pendrive, outro computador,
echo  a Area de Trabalho) e de dois cliques nele.
echo.
echo  Na pasta dist\ ficou uma copia extra, pode apagar se quiser -
echo  o arquivo que importa e o scdp-uff.exe que ficou aqui do lado
echo  deste script.
echo ============================================================
echo.
pause
