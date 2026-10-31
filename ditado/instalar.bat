@echo off
REM Instala o Ditado (Windows). Precisa do Python 3.10+ instalado (python.org).
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% -m venv .venv || goto :erro
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :erro
echo.
echo Instalado! Baixando o modelo de voz na primeira execucao (pode levar alguns minutos)...
".venv\Scripts\python.exe" -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"
echo.
echo Pronto. Rode "iniciar.bat" para comecar.
pause
exit /b 0
:erro
echo Falha na instalacao. Verifique se o Python esta instalado e no PATH.
pause
exit /b 1
