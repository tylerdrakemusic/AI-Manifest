@echo off
REM Batch script to run manifest update and verify
echo === COMMAND 1: Update Manifest ===
echo C:\G\python.exe F:\.github\!!☾⛧security\update_manifest.py
echo.
C:\G\python.exe F:\.github\!!☾⛧security\update_manifest.py
echo.
echo === COMMAND 2: Verify Manifest ===
echo C:\G\python.exe F:\.github\!!☾⛧security\update_manifest.py --verify
echo.
C:\G\python.exe F:\.github\!!☾⛧security\update_manifest.py --verify
