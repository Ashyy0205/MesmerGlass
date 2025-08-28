@echo off
setlocal ENABLEEXTENSIONS ENABLEDELAYEDEXPANSION
cd /d "%~dp0"

set "LOG=%CD%\gl_diag.txt"
echo [MesmerGlass GL Fix Launcher] > "%LOG%"
echo Working dir: %CD% >> "%LOG%"
echo. >> "%LOG%"

set "QT_QPA_PLATFORM=windows"
set "QT_OPENGL=desktop"
echo Trying desktop OpenGL... >> "%LOG%"
echo Launching MesmerLoom spiral-test for 5s (desktop)...
"%CD%\.venv\Scripts\python.exe" -m mesmerglass spiral-test --duration 5 >> "%LOG%" 2>&1
set "EXITCODE=%ERRORLEVEL%"
echo desktop exit=%EXITCODE% >> "%LOG%"

IF "%EXITCODE%"=="77" (
  echo Desktop unavailable (77). Retrying with ANGLE... >> "%LOG%"
  set "QT_OPENGL=angle"
  echo Launching MesmerLoom spiral-test for 5s (ANGLE)...
  "%CD%\.venv\Scripts\python.exe" -m mesmerglass spiral-test --duration 5 >> "%LOG%" 2>&1
  set "EXITCODE=%ERRORLEVEL%"
  echo angle exit=%EXITCODE% >> "%LOG%"
)

echo. >> "%LOG%"
echo Final exit code: %EXITCODE% >> "%LOG%"
echo (0=success, 77=GL unavailable, 1=unexpected error) >> "%LOG%"

type "%LOG%"
echo.
echo Log saved to: %LOG%
echo Press any key to close...
pause >nul
endlocal
