@echo off
SETLOCAL

:: Get the directory where the script is located
for %%I in ("%~dp0") do set "DIR=%%~fI"

:: Change directory to the script location
cd /d "%DIR%"

:: Check if virtual environment exists
IF NOT EXIST "venv" (
    python3.11 -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt
) ELSE (
    venv\Scripts\activate
)

:: Start the updater
python updater.py

:: After updates, run the main program from the latest version
for /f "delims=" %%I in ('dir /b /ad /o-n "v*"') do (
    SET "VERSION_FOLDER=%%I"
    goto :found
)

:notfound
echo No version folder found!
exit /b

:found
cd "%VERSION_FOLDER%"
python gui.py

ENDLOCAL

