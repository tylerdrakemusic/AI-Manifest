@echo off
setlocal enabledelayedexpansion

echo ====== COMMAND 1: Update Manifest ======
C:\G\python.exe F:\.github\!!☾⛧security\update_manifest.py
set EXIT1=!ERRORLEVEL!
echo.
echo ====== COMMAND 2: Verify Manifest ======
C:\G\python.exe F:\.github\!!☾⛧security\update_manifest.py --verify
set EXIT2=!ERRORLEVEL!
echo.
echo ====== EXIT STATUSES ======
echo Command 1 exit code: !EXIT1!
echo Command 2 exit code: !EXIT2!
