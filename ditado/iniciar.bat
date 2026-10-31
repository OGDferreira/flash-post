@echo off
REM Inicia o Ditado em segundo plano (sem janela). Icone aparece na bandeja.
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" "%~dp0ditado.py"
