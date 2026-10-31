@echo off
REM Faz o Ditado abrir sozinho sempre que o Windows ligar.
cd /d "%~dp0"
set "DITADO_DIR=%~dp0"
set "ATALHO=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Ditado.lnk"
powershell -NoProfile -Command "$d=$env:DITADO_DIR; $s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:ATALHO); $s.TargetPath=$d+'.venv\Scripts\pythonw.exe'; $s.Arguments=[char]34+$d+'ditado.py'+[char]34; $s.WorkingDirectory=$d; $s.Save()"
echo Ditado vai iniciar junto com o Windows.
echo Para desfazer, apague: %ATALHO%
pause
