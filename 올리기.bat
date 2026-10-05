@echo off
rem --- Publish hand-made changes: pull, test, build, commit, push.
rem --- Usage:  drop a note in quotes, e.g.  olligi.bat "fixed the lab list"
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
"%PY%" -u -m govpress release %*
pause
exit /b %errorlevel%
