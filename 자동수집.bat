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

rem --- 인터넷에 올리기 ---
rem GitHub Pages는 main 가지의 docs 폴더를 그대로 사이트로 띄운다.
rem 그래서 "올리기"는 docs 폴더를 git에 밀어 넣는 일이 전부다.
rem docs 만 담는다 — 작업 중인 코드가 딸려 올라가면 안 된다.
echo. >> "%LOG%"
echo --- 인터넷에 올리기 --- >> "%LOG%"
where git >nul 2>nul
if errorlevel 1 (
  echo  [!] git 명령을 찾을 수 없어 건너뜁니다. >> "%LOG%"
) else (
  git add docs >> "%LOG%" 2>&1
  git diff --cached --quiet
  if errorlevel 1 (
    git commit -m "보도자료 화면 갱신 %TODAY% %time:~0,5%" >> "%LOG%" 2>&1
    git push >> "%LOG%" 2>&1
    if errorlevel 1 (
      echo  [!] 올리기 실패. 인터넷이나 GitHub 로그인을 확인하세요. >> "%LOG%"
    ) else (
      echo  올렸습니다: https://kwakmg74-michael.github.io/gov-press-monitor/ >> "%LOG%"
    )
  ) else (
    echo  바뀐 내용이 없어 올리지 않았습니다. >> "%LOG%"
  )
)

echo. >> "%LOG%"
echo  %date% %time:~0,5%  끝 >> "%LOG%"

endlocal
exit /b 0
