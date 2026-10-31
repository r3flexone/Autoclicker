@echo off
rem Startet den Autoclicker per Doppelklick und richtet beim ersten Mal ein, was
rem dafuer fehlt: Python, die eigene Umgebung .venv und die Pakete aus
rem requirements.txt. Bei jedem weiteren Start wird nur geprueft, ob sich
rem requirements.txt geaendert hat - sonst geht es sofort los.
rem
rem Bewusst nur ASCII und CRLF: cmd liest eine Batch-Datei in der OEM-Codepage
rem (Umlaute kaemen als Zeichensalat an) und findet Sprungmarken in einer Datei
rem mit reinen LF-Zeilenenden nicht zuverlaessig. Beides haelt ein Test fest.
setlocal
cd /d "%~dp0"
title Autoclicker

rem Die eine Version, gegen die getestet wird - dieselbe wie in README und CI.
set "PY_VERSION=3.14"
set "HERE=%~dp0"
set "VENV_PY=.venv\Scripts\python.exe"
set "STAMP=.venv\requirements.installed"
set "FRESH="

rem Eine Umgebung, deren Python fehlt (Ordner von einem anderen PC kopiert,
rem Python deinstalliert), wird unten neu angelegt statt beim Start zu scheitern.
if exist "%VENV_PY%" "%VENV_PY%" -c "import sys" >nul 2>&1 && goto :packages

echo Der Autoclicker wird eingerichtet ...
call :find_python
if not defined BASE_PY call :install_python
if not defined BASE_PY goto :fail

echo.
echo Lege die Umgebung .venv an ...
"%BASE_PY%" -m venv --clear .venv || goto :fail
set "FRESH=1"

:packages
if exist "%STAMP%" fc /b requirements.txt "%STAMP%" >nul 2>&1 && goto :shortcut
echo.
echo Installiere die Pakete - beim ersten Mal dauert das einige Minuten ...
"%VENV_PY%" -m pip install --disable-pip-version-check -r requirements.txt || goto :fail
copy /y requirements.txt "%STAMP%" >nul

:shortcut
if defined FRESH call :offer_shortcut

"%VENV_PY%" main.py %*
set "CODE=%errorlevel%"
rem Endet der Autoclicker mit einem Fehler, bleibt das Fenster offen - sonst
rem schliesst es sich, bevor man die Meldung lesen kann.
if not "%CODE%"=="0" pause
exit /b %CODE%


:fail
echo.
echo Das Einrichten ist nicht durchgelaufen - die Meldung steht oben.
pause
exit /b 1


rem Sucht Python ohne PATH: ueber den Python-Launcher und an den Stellen, an die
rem die Installer von python.org es legen. Ein nacktes python ist unter Windows
rem oft nur der Verweis auf den Microsoft Store. Die Eingabe des Launchers kommt
rem aus nul: fragt er nach, ob er die Version nachladen soll, liest er ein Nein,
rem statt unsichtbar auf eine Taste zu warten.
:find_python
set "BASE_PY="
for /f "delims=" %%P in ('py -%PY_VERSION% -c "import sys; print(sys.executable)" ^<nul 2^>nul') do set "BASE_PY=%%P"
if defined BASE_PY exit /b 0
set "PY_DIGITS=%PY_VERSION:.=%"
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python%PY_DIGITS%\python.exe"
    "%LOCALAPPDATA%\Python\pythoncore-%PY_VERSION%-64\python.exe"
    "%ProgramFiles%\Python%PY_DIGITS%\python.exe"
) do if not defined BASE_PY if exist "%%~P" set "BASE_PY=%%~P"
exit /b 0


rem Installiert nur nach Rueckfrage, fuer den eigenen Benutzer - ohne
rem Administratorrechte. Ohne winget (sehr altes Windows 10) bleibt der Weg
rem ueber python.org.
:install_python
echo.
echo Python %PY_VERSION% ist auf diesem PC nicht installiert.
where winget >nul 2>&1 || goto :python_by_hand
set "ANSWER=j"
set /p "ANSWER=Jetzt ueber winget installieren? [J/n] "
if /i "%ANSWER:~0,1%"=="n" goto :python_by_hand
winget install --id Python.Python.%PY_VERSION% -e --source winget --scope user
call :find_python
if defined BASE_PY exit /b 0
:python_by_hand
echo.
echo Bitte Python %PY_VERSION% von https://www.python.org/downloads/ installieren
echo und danach start.bat noch einmal doppelklicken.
exit /b 0


rem Nur beim ersten Einrichten gefragt. Das Symbol schreibt tools\symbol.py nach
rem symbol\, die Pfade bekommt PowerShell ueber die Umgebung (HERE) - so stoert
rem kein Apostroph im Ordnernamen die Anfuehrungszeichen.
:offer_shortcut
echo.
set "ANSWER=j"
set /p "ANSWER=Verknuepfung auf dem Desktop anlegen? [J/n] "
if /i "%ANSWER:~0,1%"=="n" exit /b 0
"%VENV_PY%" tools\symbol.py >nul
powershell -NoProfile -Command "$link = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Autoclicker.lnk')); $link.TargetPath = Join-Path $env:HERE 'start.bat'; $link.WorkingDirectory = $env:HERE; $link.IconLocation = Join-Path $env:HERE 'symbol\autoclicker.ico'; $link.Save()" && echo Die Verknuepfung "Autoclicker" liegt jetzt auf dem Desktop.
exit /b 0
