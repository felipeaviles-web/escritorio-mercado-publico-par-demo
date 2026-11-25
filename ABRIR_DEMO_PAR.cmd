@echo off
setlocal
cd /d "%~dp0"
set "BUNDLED_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%BUNDLED_PYTHON%" (
  "%BUNDLED_PYTHON%" -X utf8 "%~dp0demo_par.py" --puerto 0
) else (
  where py.exe >nul 2>nul
  if not errorlevel 1 (
    py.exe -3 -X utf8 "%~dp0demo_par.py" --puerto 0
  ) else (
    python.exe -X utf8 "%~dp0demo_par.py" --puerto 0
  )
)
if errorlevel 1 pause
