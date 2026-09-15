@echo off
setlocal EnableExtensions
set "APP_DIR=%~dp0"
rem Usage: start_ai_engineer.cmd [port]. Existing services are never stopped.
set "APP_PORT=8000"
if not "%~1"=="" set "APP_PORT=%~1"
pushd "%APP_DIR%" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Cannot access application directory: "%APP_DIR%"
    pause
    exit /b 1
)

rem Optional: set QWEN_API_KEY in the current shell or configure it in the website settings.
rem Never place the API key directly in this file.
set "PYTHONPATH=%APP_DIR%"
set "FREECAD_CMD=D:\freecad\bin\FreeCADCmd.exe"
set "CCX_PATH=D:\freecad\bin\ccx.exe"

rem Prefer the app-local environment, then the parent project environment.
set "PYTHON_EXE=%APP_DIR%.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%APP_DIR%..\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

if /i "%PYTHON_EXE%"=="python" (
    where python >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python was not found. Install Python or create .venv.
        pause
        popd
        exit /b 1
    )
)

"%PYTHON_EXE%" -c "import uvicorn" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] uvicorn is not installed for: "%PYTHON_EXE%"
    echo Install dependencies with: "%PYTHON_EXE%" -m pip install -r "%APP_DIR%backend\requirements.txt"
    pause
    popd
    exit /b 1
)

echo AI Engineer: http://127.0.0.1:%APP_PORT%/ui/
rem Append a dot so the quoted Windows directory does not end with a backslash.
"%PYTHON_EXE%" -m uvicorn backend.app:app --app-dir "%APP_DIR%." --host 127.0.0.1 --port "%APP_PORT%"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] AI Engineer stopped with exit code %EXIT_CODE%.
    pause
)

popd
endlocal
exit /b %EXIT_CODE%
