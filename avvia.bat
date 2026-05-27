@echo off
echo ============================================================
echo   SCIOPERO TRENI - Avvio applicazione
echo ============================================================
echo.

:: Controlla dipendenze
where python >nul 2>&1
if errorlevel 1 (
    echo ERRORE: Python non trovato. Installare Python 3.10+
    pause & exit /b 1
)

where node >nul 2>&1
if errorlevel 1 (
    echo ERRORE: Node.js non trovato. Installare Node.js 18+
    echo Comando: winget install OpenJS.NodeJS.LTS
    pause & exit /b 1
)

:: Controlla database
if not exist "db\sciopero.db" (
    echo Database non trovato. Costruzione in corso...
    echo Questo richiede 2-5 minuti la prima volta.
    echo.
    cd etl
    pip install -r requirements.txt -q
    python build_db.py --skip-timetable
    cd ..
    echo.
)

:: Avvia backend
echo [1/2] Avvio backend API (porta 3001)...
start "Sciopero Treni - Backend" /min cmd /c "cd /d %~dp0backend && node dist/server.js"
timeout /t 2 /nobreak >nul

:: Avvia frontend
echo [2/2] Avvio frontend (porta 3000)...
start "Sciopero Treni - Frontend" /min cmd /c "cd /d %~dp0frontend && npm start"
timeout /t 3 /nobreak >nul

:: Apri browser
echo.
echo Apertura browser...
start http://localhost:3000

echo.
echo ============================================================
echo  App avviata!
echo  Backend:  http://localhost:3001
echo  Frontend: http://localhost:3000
echo.
echo  Per fermare: chiudi le finestre "Sciopero Treni"
echo ============================================================
