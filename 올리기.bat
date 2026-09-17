@echo off
chcp 65001 > nul
cd /d "%~dp0"
setlocal

rem 손으로 고친 것을 인터넷에 올린다.
rem
rem 쓰는 법 — 더블클릭하거나, 설명을 붙이려면:
rem     올리기.bat "연구소 목록 손봄"
rem
rem 자동수집.bat 과 다른 점: 저쪽은 새 보도자료를 모아 화면만 올리고,
rem 이쪽은 코드까지 함께 기록에 남긴다.

set "MSG=%~1"
if "%MSG%"=="" set "MSG=화면·설정 수정"

echo.
echo [1/4] 테스트
python -m pytest -q
if errorlevel 1 (
  echo.
  echo  [!] 테스트가 깨졌습니다. 올리지 않고 멈춥니다.
  echo      무엇이 틀렸는지 위에 나와 있습니다.
  pause
  exit /b 1
)

echo.
echo [2/4] 화면 만들기
python -m govpress publish
if errorlevel 1 (
  echo  [!] 화면을 만들지 못했습니다. 올리지 않고 멈춥니다.
  pause
  exit /b 1
)

echo.
echo [3/4] 바뀐 것
rem 담을 곳을 하나하나 적는다. 통째로 담으면 작업 중이던 것까지 딸려 간다.
git add govpress tests tools docs .gitignore 자동수집.bat 올리기.bat
git diff --cached --stat
git diff --cached --quiet
if not errorlevel 1 (
  echo  바뀐 내용이 없습니다. 올릴 것이 없네요.
  pause
  exit /b 0
)

echo.
echo [4/4] 올리기
git commit -m "%MSG%"
git push
if errorlevel 1 (
  echo.
  echo  [!] 올리기 실패. 인터넷이나 GitHub 로그인을 확인하세요.
  pause
  exit /b 1
)

echo.
echo  올렸습니다. 2~3분 뒤 화면에 반영됩니다:
echo    https://kwakmg74-michael.github.io/gov-press-monitor/
echo.
pause
exit /b 0
