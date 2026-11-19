@echo off
setlocal
cd /d "%~dp0"

if not exist libsodium.dll (
  echo Copy the official x64 libsodium.dll into this folder, next to rangeproof.py.
  echo See README_PDF_STUDIO.md for the download link.
  exit /b 1
)

if not exist .venv\Scripts\python.exe (
  py -3.12 -m venv .venv
  if errorlevel 1 exit /b 1
)

.venv\Scripts\python.exe -c "from pdf_studio import app" >nul 2>&1
if errorlevel 1 (
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 exit /b 1
)

echo Open http://127.0.0.1:8001 in your browser. Press Ctrl+C to stop.
.venv\Scripts\python.exe -m uvicorn pdf_studio:app --host 127.0.0.1 --port 8001 --no-access-log
