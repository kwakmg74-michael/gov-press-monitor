@echo off
rem --- Scheduled collection. Runs on the server PC.
rem --- Two python calls on purpose. The first one pulls new code;
rem --- the second one runs WITH it. A pull made inside an already
rem --- running process cannot change the modules it has loaded, so
rem --- the new code used to take effect only one run later.
rem --- Keep this file ASCII-only: cmd mis-seeks inside a UTF-8 batch
rem --- file under chcp 65001 and runs half a line as a command.
rem --- All the real work (and all the Korean) lives in govpress/daily.py.
rem --- Python: each PC writes its own interpreter path into
rem --- python-path.txt (one line, no quotes, no trailing space).
rem --- That file is git-ignored, so the two PCs never clash over it.
chcp 65001 > nul
cd /d "%~dp0"
set "PY=python"
if exist "%~dp0python-path.txt" set /p PY=<"%~dp0python-path.txt"
"%PY%" -u -m govpress sync
"%PY%" -u -m govpress daily --no-sync
exit /b %errorlevel%
