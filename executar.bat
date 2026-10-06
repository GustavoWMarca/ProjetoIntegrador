@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo O ambiente Python ainda nao foi criado.
    echo Consulte o arquivo README.md para realizar a preparacao inicial.
    pause
    exit /b 1
)

start "" "http://127.0.0.1:5000"
".venv\Scripts\python.exe" app.py
