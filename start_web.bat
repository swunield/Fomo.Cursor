@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo Installing deps if needed...
python -m pip install -r requirements.txt -q
echo.
echo Starting FOMO Desk at http://127.0.0.1:8787
echo.
python app.py
pause
