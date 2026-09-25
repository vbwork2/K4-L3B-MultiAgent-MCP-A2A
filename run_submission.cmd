@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo Python environment not found at %PYTHON_EXE%.
    exit /b 1
)

"%PYTHON_EXE%" -m student_agent.cli validate-inputs
if errorlevel 1 exit /b 1

set /a ATTEMPT=0
set "RUN_MODE=fresh"
if /I "%~1"=="resume" set "RUN_MODE=resume"
:run_cases
set /a ATTEMPT+=1
if /I "%RUN_MODE%"=="fresh" (
    "%PYTHON_EXE%" -m student_agent.cli run --jobs 2
    set "RUN_MODE=resume"
) else (
    "%PYTHON_EXE%" -m student_agent.cli run --resume --jobs 2
)
if errorlevel 1 (
    if %ATTEMPT% GEQ 5 exit /b 1
    timeout /t 5 /nobreak >nul
    goto run_cases
)

"%PYTHON_EXE%" -m student_agent.cli validate
if errorlevel 1 exit /b 1

"%PYTHON_EXE%" -m student_agent.cli package --output dist/submission-v3.zip
if errorlevel 1 exit /b 1

echo Submission ready: dist\submission-v3.zip
endlocal
