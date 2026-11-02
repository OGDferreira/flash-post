@echo off
REM Gera o Ditado.exe (Windows). Precisa do Python 3.10+ instalado (python.org).
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
if not exist ".venv\Scripts\python.exe" (
  echo Criando ambiente Python...
  %PY% -m venv .venv || goto :erro
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller || goto :erro
".venv\Scripts\python.exe" build_exe.py || goto :erro
echo.
echo ============================================================
echo  Executavel gerado em: %~dp0dist\Ditado\Ditado.exe
echo  Copie a pasta dist\Ditado inteira para onde quiser.
echo  Na primeira vez que abrir, ele baixa o modelo de voz.
echo ============================================================
explorer "%~dp0dist\Ditado"
pause
exit /b 0
:erro
echo.
echo Falha ao gerar o executavel. Veja a mensagem de erro acima.
pause
exit /b 1
