@echo off
setlocal
chcp 65001 >nul
set "APP_DIR=%~dp0"
set "DESENSITIZER_SCRIPT_DIR=%APP_DIR%"
set "LAUNCH_RELEASE=JABzAGMAcgBpAHAAdABEAGkAcgAgAD0AIAAkAGUAbgB2ADoARABFAFMARQBOAFMASQBUAEkAWgBFAFIAXwBTAEMAUgBJAFAAVABfAEQASQBSAAoAaQBmACAAKAAtAG4AbwB0ACAAJABzAGMAcgBpAHAAdABEAGkAcgApACAAewAgAGUAeABpAHQAIAAxACAAfQAKACQAcgBvAG8AdAAgAD0AIABSAGUAcwBvAGwAdgBlAC0AUABhAHQAaAAgAC0ATABpAHQAZQByAGEAbABQAGEAdABoACAAKABKAG8AaQBuAC0AUABhAHQAaAAgACQAcwBjAHIAaQBwAHQARABpAHIAIAAnAC4ALgAnACkACgAkAGUAeABlACAAPQAgAEoAbwBpAG4ALQBQAGEAdABoACAAJAByAG8AbwB0ACAAJwAsZzBXRI2ZZTGBT2XlXXdRXAAsZzBXRI2ZZTGBT2XlXXdRLgBlAHgAZQAnAAoAaQBmACAAKABUAGUAcwB0AC0AUABhAHQAaAAgAC0ATABpAHQAZQByAGEAbABQAGEAdABoACAAJABlAHgAZQApACAAewAKACAAIAAgACAAUwB0AGEAcgB0AC0AUAByAG8AYwBlAHMAcwAgAC0ARgBpAGwAZQBQAGEAdABoACAAJABlAHgAZQAKACAAIAAgACAAZQB4AGkAdAAgADAACgB9AAoAZQB4AGkAdAAgADEA"
set "CODEX_PY=C:\Users\tomking\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand "%LAUNCH_RELEASE%" >nul 2>nul
if not errorlevel 1 goto :done

if not exist "%APP_DIR%app.py" (
  echo Cannot find app.py in:
  echo   "%APP_DIR%"
  pause
  goto :done
)

if exist "%APP_DIR%.python\python.exe" (
  "%APP_DIR%.python\python.exe" "%APP_DIR%app.py"
  goto :check_error
)

if exist "%CODEX_PY%" (
  "%CODEX_PY%" -c "from tkinter import Tk; root=Tk(); root.withdraw(); root.destroy()" >nul 2>nul
  if not errorlevel 1 (
    "%CODEX_PY%" "%APP_DIR%app.py"
    goto :check_error
  )
)

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%APP_DIR%app.py"
  goto :check_error
)

where python >nul 2>nul
if %errorlevel%==0 (
  python "%APP_DIR%app.py"
  goto :check_error
)

echo Cannot find Python runtime.
echo Install Python 3.10+ and run:
echo   python -m pip install -r requirements.txt
pause
goto :done

:check_error
if errorlevel 1 (
  echo.
  echo Program failed to start. Error code: %errorlevel%
  echo If the message above mentions a missing module, install dependencies or use the bundled runtime.
  pause
)

:done
endlocal
