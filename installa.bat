@echo off
echo ============================================================
echo   SCIOPERO TRENI - Installazione
echo ============================================================
echo.

:: Verifica Python
python --version >nul 2>&1
if errorlevel 1 (
    echo Installazione Python...
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
)

:: Verifica Node.js
node --version >nul 2>&1
if errorlevel 1 (
    echo Installazione Node.js...
    winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
    :: Ricarica PATH
    call refreshenv 2>nul || (
        echo Riavviare il terminale dopo l'installazione di Node.js
        pause & exit /b 1
    )
)

echo.
echo [1/4] Installazione dipendenze Python...
cd etl
pip install -r requirements.txt -q
if errorlevel 1 ( echo ERRORE pip install & pause & exit /b 1 )
cd ..

echo [2/4] Installazione dipendenze backend...
cd backend
call npm install --silent
if errorlevel 1 ( echo ERRORE npm install backend & pause & exit /b 1 )
call npm run build
if errorlevel 1 ( echo ERRORE build backend & pause & exit /b 1 )
cd ..

echo [3/4] Installazione dipendenze frontend...
cd frontend
call npm install --silent
if errorlevel 1 ( echo ERRORE npm install frontend & pause & exit /b 1 )
call npm run build
if errorlevel 1 ( echo ERRORE build frontend & pause & exit /b 1 )
cd ..

echo [4/4] Costruzione database...
cd etl
python build_db.py --skip-timetable
if errorlevel 1 ( echo ERRORE build_db & pause & exit /b 1 )
cd ..

echo.
echo ============================================================
echo  Installazione completata!
echo  Per avviare l'app: doppio click su avvia.bat
echo ============================================================
pause
