@echo off
rem ======================================================================
rem  J.A.R.V.I.S. - pornire platforma (dublu-click pe acest fisier)
rem  Serverul ruleaza cat timp aceasta fereastra e deschisa.
rem  Inchide fereastra (sau Ctrl+C) ca sa opresti platforma.
rem ======================================================================
cd /d "%~dp0"
title J.A.R.V.I.S. - server platforma
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

if not exist "venv\Scripts\python.exe" (
    echo [!] Nu gasesc venv\Scripts\python.exe in %CD%
    echo     Creeaza mediul virtual si instaleaza: venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

"venv\Scripts\python.exe" backend\api\server.py --deschide
echo.
echo Serverul s-a oprit.
pause
