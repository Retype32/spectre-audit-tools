@echo off
rem Builds dist\Spectre.exe on Windows. Run it from the Spectre folder.
rem Needs Python 3.10 or newer (python.org installer) and an internet connection.
setlocal
cd /d "%~dp0"
set PY=py
where py >/dev/null 2>/dev/null || set PY=python

echo Installing build requirements...
%PY% -m pip install --upgrade -r requirements.txt pyinstaller || goto :error

echo Running the tests...
%PY% -m unittest discover -s tests -t . || goto :error

echo Building Spectre.exe...
%PY% -m PyInstaller --noconfirm --clean Spectre.spec || goto :error

echo.
echo Done: dist\Spectre.exe
echo Copy it to the shared Spectre folder together with local_settings.json.
endlocal
exit /b 0

:error
echo.
echo Build failed - see the messages above.
endlocal
exit /b 1
