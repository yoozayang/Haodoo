@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "PY="

if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set "PY=%LocalAppData%\Programs\Python\Python311\python.exe"
if not defined PY if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PY where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"

if not defined PY (
  echo Python not found. Install Python 3.x first.
  exit /b 1
)

%PY% "%SCRIPT_DIR%rename_to_trad.py"
endlocal
