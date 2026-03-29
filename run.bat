@echo off
echo ====================================================
echo   PharmaCost Intelligence - AI Financial Agent
echo ====================================================
echo.
echo Installing dependencies...
pip install -r requirements.txt
echo.
echo Starting server...
python app.py
pause
