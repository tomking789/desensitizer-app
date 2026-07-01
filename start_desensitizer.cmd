@echo off
setlocal
set "APP_DIR=%~dp0"

if exist "%APP_DIR%.python\python.exe" (
  "%APP_DIR%.python\python.exe" "%APP_DIR%app.py"
  goto :done
)

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%APP_DIR%app.py"
  goto :done
)

where python >nul 2>nul
if %errorlevel%==0 (
  python "%APP_DIR%app.py"
  goto :done
)

echo Cannot find Python runtime.
echo Install Python 3.10+ and run:
echo   python -m pip install -r requirements.txt
pause

:done
endlocal
