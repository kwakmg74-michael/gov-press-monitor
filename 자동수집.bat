@echo off
chcp 65001 > nul
cd /d "%~dp0"
setlocal

set "LOG=%~dp0수집기록.txt"
for /f "tokens=1-3 delims=-/ " %%a in ("%date%") do set "TODAY=%%a-%%b-%%c"

echo. >> "%LOG%"
echo ================================================== >> "%LOG%"
echo  %TODAY% %time:~0,5%  자동 수집 시작 >> "%LOG%"
echo ================================================== >> "%LOG%"

where python >nul 2>nul
if errorlevel 1 (
  echo  [!] 파이썬을 찾을 수 없습니다. >> "%LOG%"
  exit /b 1
)

echo. >> "%LOG%"
echo --- 정부기관 --- >> "%LOG%"
python -m govpress collect --days 7 >> "%LOG%" 2>&1

echo. >> "%LOG%"
echo --- 지자체 --- >> "%LOG%"
python -m govpress collect-local --pages 3 >> "%LOG%" 2>&1

echo. >> "%LOG%"
echo --- 공공기관 --- >> "%LOG%"
python -m govpress collect-public --pages 3 >> "%LOG%" 2>&1

echo. >> "%LOG%"
echo --- 연구소 --- >> "%LOG%"
python -m govpress collect-research --pages 3 >> "%LOG%" 2>&1

echo. >> "%LOG%"
echo --- 화면 만들기 --- >> "%LOG%"
python -m govpress dashboard >> "%LOG%" 2>&1
python -m govpress publish >> "%LOG%" 2>&1

echo. >> "%LOG%"
echo --- 인터넷에 올리기 --- >> "%LOG%"
where netlify >nul 2>nul
if errorlevel 1 (
  echo  netlify 명령이 없어 건너뜁니다. >> "%LOG%"
  echo  publish 폴더를 직접 올리시거나, 한 번만 설치하세요: >> "%LOG%"
  echo    npm install -g netlify-cli >> "%LOG%"
) else (
  call netlify deploy --prod --dir=publish >> "%LOG%" 2>&1
  if errorlevel 1 (
    echo  [!] 올리기 실패. 로그인이 풀렸을 수 있습니다: netlify login >> "%LOG%"
  )
)

echo. >> "%LOG%"
echo  %date% %time:~0,5%  끝 >> "%LOG%"

endlocal
exit /b 0
