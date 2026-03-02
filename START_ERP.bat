@echo off
echo ============================================
echo   HSL Solutions ERP v3.0
echo ============================================
echo.
python -m pip install -r requirements.txt --quiet 2>nul
echo.
echo   Dashboard:     http://localhost:5000/admin
echo   Configurator:  http://localhost:5000/configurator
echo   Config Admin:  http://localhost:5000/configurator/admin
echo   Login: admin / admin123
echo.
python app.py
pause
