@echo off
setlocal ENABLEEXTENSIONS ENABLEDELAYEDEXPANSION
cd /d "%~dp0"

set "LOG1=%CD%\qt_diag_desktop.txt"
set "LOG2=%CD%\qt_diag_angle.txt"

echo [Qt Plugin Diagnostic] > "%LOG1%"
echo Working dir: %CD% >> "%LOG1%"
echo QT_OPENGL=desktop >> "%LOG1%"
echo. >> "%LOG1%"

set "QT_QPA_PLATFORM=windows"
set "QT_OPENGL=desktop"
set "QT_DEBUG_PLUGINS=1"

REM Minimal PyQt6 QOpenGLWidget creation (desktop)
"%CD%\.venv\Scripts\python.exe" -c "import sys;from PyQt6.QtWidgets import QApplication;from PyQt6.QtOpenGLWidgets import QOpenGLWidget;a=QApplication(sys.argv);w=QOpenGLWidget();print('QOpenGLWidget created (desktop)')" >> "%LOG1%" 2>&1
echo. >> "%LOG1%"
echo Running spiral-test (desktop)... >> "%LOG1%"
"%CD%\.venv\Scripts\python.exe" -m mesmerglass spiral-test --duration 2 >> "%LOG1%" 2>&1
echo desktop exit=%ERRORLEVEL% >> "%LOG1%"

echo [Qt Plugin Diagnostic] > "%LOG2%"
echo Working dir: %CD% >> "%LOG2%"
echo QT_OPENGL=angle >> "%LOG2%"
echo. >> "%LOG2%"

set "QT_OPENGL=angle"

REM Minimal PyQt6 QOpenGLWidget creation (ANGLE)
"%CD%\.venv\Scripts\python.exe" -c "import sys;from PyQt6.QtWidgets import QApplication;from PyQt6.QtOpenGLWidgets import QOpenGLWidget;a=QApplication(sys.argv);w=QOpenGLWidget();print('QOpenGLWidget created (ANGLE)')" >> "%LOG2%" 2>&1
echo. >> "%LOG2%"
echo Running spiral-test (ANGLE)... >> "%LOG2%"
"%CD%\.venv\Scripts\python.exe" -m mesmerglass spiral-test --duration 2 >> "%LOG2%" 2>&1
echo angle exit=%ERRORLEVEL% >> "%LOG2%"

echo.
echo Wrote logs:
echo   %LOG1%
echo   %LOG2%
echo Open them and share the last ~30 lines if still failing.
echo.
pause
endlocal
