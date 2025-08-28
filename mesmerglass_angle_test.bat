@echo off
setlocal ENABLEEXTENSIONS ENABLEDELAYEDEXPANSION
cd /d "%~dp0"

REM Force ANGLE (Direct3D) explicitly
set "QT_QPA_PLATFORM=windows"
set "QT_OPENGL=angle"

echo [MesmerGlass ANGLE Test]
echo Running: spiral-test for 5s using ANGLE (Direct3D)...

"%CD%\.venv\Scripts\python.exe" -m mesmerglass spiral-test --duration 5
set "EC=%ERRORLEVEL%"
echo Exit code: %EC%
echo (0=success, 77=GL unavailable, 1=unexpected error)
echo.
pause
endlocal
