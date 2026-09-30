@echo off
rem --- Scheduled collection. Runs three times a day.
rem --- Keep this file ASCII-only: cmd mis-seeks inside a UTF-8 batch
rem --- file under chcp 65001 and runs half a line as a command.
rem --- All the real work (and all the Korean) lives in govpress/daily.py.
chcp 65001 > nul
cd /d "%~dp0"
python -u -m govpress daily
exit /b %errorlevel%
