@echo off
REM Run Python script to generate manifest
C:\G\python.exe F:\standalone_manifest.py > F:\manifest_run.log 2>&1
echo Exit Code: %ERRORLEVEL% >> F:\manifest_run.log
type F:\manifest_run.log
