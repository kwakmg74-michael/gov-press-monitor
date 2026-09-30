"""하루치 한 판, 그리고 배치 파일이 한글을 담지 않는다는 약속.

2026-09-30 오후 5시, 검은 창에 이런 두 줄이 떴다.

    '어디서' is not recognized as an internal or external command

배치 파일에 적어 둔 한글 설명 한가운데였다. 자세한 사정은 govpress/daily.py
맨 위에 적어 뒀다. 여기서는 다시 그런 일이 없도록 못을 박는다.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from govpress import daily

ROOT = Path(__file__).resolve().parent.parent
BATS = ("자동수집.bat", "올리기.bat")


# --- 배치 파일에는 한글을 담지 않는다 -------------------------------------------

@pytest.mark.parametrize("name", BATS)
def test_배치파일에_한글이_없다(name):
    """한 자라도 있으면 cmd 의 바이트 셈이 어긋날 수 있다."""
    raw = (ROOT / name).read_bytes()
    샌_것 = sorted({b for b in raw if b > 127})
    assert not 샌_것, f"{name} 에 아스키가 아닌 바이트가 있습니다: {샌_것[:8]}"


@pytest.mark.parametrize("name", BATS)
def test_배치파일이_왜_이런지_적어_둔다(name):
    """설명이 없으면 다음 사람이 친절하게 한글 주석을 도로 넣는다."""
    글 = (ROOT / name).read_text(encoding="ascii")
    assert "ASCII-only" in 글


@pytest.mark.parametrize("name", BATS)
def test_배치파일은_파이썬만_부른다(name):
    """일이 배치와 파이썬으로 나뉘어 있으면 어느 쪽이 도는지 헷갈린다."""
    줄 = [l.strip() for l in (ROOT / name).read_text(encoding="ascii").splitlines()]
    한_일 = [l for l in 줄 if l and not l.startswith(("@", "rem", "chcp", "cd ", "exit", "pause"))]
    assert len(한_일) == 1, 한_일
    assert 한_일[0].startswith("python -u -m govpress ")


@pytest.mark.parametrize("name", BATS)
def test_윈도우_줄바꿈을_쓴다(name):
    """줄 끝이 LF 뿐이면 cmd 가 명령 끝에 눈에 안 보이는 글자를 붙여 읽는다."""
    raw = (ROOT / name).read_bytes()
    assert raw.count(b"\r\n") == raw.count(b"\n")


def test_자동수집은_daily를_부른다():
    assert "govpress daily" in (ROOT / "자동수집.bat").read_text(encoding="ascii")


def test_올리기는_release를_부르고_기다려_준다():
    글 = (ROOT / "올리기.bat").read_text(encoding="ascii")
    assert "govpress release %*" in 글
    # 더블클릭으로 여는 창이다. pause 가 없으면 결과를 읽기 전에 닫힌다.
    assert b"\r\npause\r\n" in (ROOT / "올리기.bat").read_bytes()


# --- 화면에도 보여 주고 기록에도 남긴다 ------------------------------------------

def test_양쪽에_똑같이_적는다():
    가, 나 = io.StringIO(), io.StringIO()
    daily.Tee(가, 나).write("안녕")
    assert 가.getvalue() == 나.getvalue() == "안녕"


def test_한_줄_적을_때마다_흘려_보낸다(tmp_path):
    """도중에 죽어도 어디까지 갔는지는 남아야 한다. 예전엔 8KB를 모았다가
    통째로 잃어서 '지자체 ---' 에서 끊긴 것처럼 보였다."""
    적힌 = tmp_path / "log.txt"
    with open(적힌, "w", encoding="utf-8") as fp:
        daily.Tee(fp).write("여기까지 왔다")
        assert 적힌.read_text(encoding="utf-8") == "여기까지 왔다"


def test_한쪽이_막혀도_다른_쪽엔_적는다():
    class 막힌쪽:
        def write(self, _):
            raise OSError("닫힘")

        def flush(self):
            raise OSError("닫힘")

    살아있는 = io.StringIO()
    daily.Tee(막힌쪽(), 살아있는).write("괜찮다")
    assert 살아있는.getvalue() == "괜찮다"


def test_화면이_아니라고_밝힌다():
    """isatty 가 없으면 색을 입히려는 쪽이 터진다."""
    assert daily.Tee(io.StringIO()).isatty() is False


# --- git 으로 올리기 ----------------------------------------------------------

class 가짜git:
    """`git diff --cached --quiet` 가 0이면 '바뀐 것 없음'이다."""

    def __init__(self, 바뀜=True, 터질곳=None):
        self.부른것: list[list[str]] = []
        self.바뀜 = 바뀜
        self.터질곳 = 터질곳 or {}

    def __call__(self, args, cwd):
        self.부른것.append(list(args))
        if args[0] in self.터질곳:
            return self.터질곳[args[0]], "망했습니다"
        if args[:1] == ["diff"]:
            return (1 if self.바뀜 else 0), ""
        return 0, ""

    def 한_일(self):
        return [a[0] for a in self.부른것]


def test_바뀐_것이_없으면_담지도_올리지도_않는다(capsys):
    git = 가짜git(바뀜=False)
    assert daily.push(["docs"], "그대로", git=git) == 0
    assert git.한_일() == ["add", "diff"]
    assert "바뀐 내용이 없어" in capsys.readouterr().out


def test_바뀌었으면_담고_올린다():
    git = 가짜git()
    assert daily.push(["docs"], "새 화면", git=git) == 0
    assert git.한_일() == ["add", "diff", "commit", "push"]


def test_담을_곳을_하나하나_적는다():
    """`git add .` 로 통째로 담으면 작업 중이던 것이 딸려 간다."""
    git = 가짜git()
    daily.push(["govpress", "docs"], "둘", git=git)
    assert git.부른것[0] == ["add", "govpress", "docs"]


def test_적어_준_말이_그대로_담긴다():
    git = 가짜git()
    daily.push(["docs"], "연구소 목록 손봄", git=git)
    assert ["commit", "-m", "연구소 목록 손봄"] in git.부른것


def test_담기지_않으면_올리지_않는다(capsys):
    git = 가짜git(터질곳={"commit": 1})
    assert daily.push(["docs"], "실패", git=git) == 1
    assert "push" not in git.한_일()
    assert "담아 두지 못했습니다" in capsys.readouterr().out


def test_올리다_실패하면_무엇을_볼지_알려_준다(capsys):
    assert daily.push(["docs"], "실패", git=가짜git(터질곳={"push": 1})) == 1
    assert "GitHub 로그인" in capsys.readouterr().out


def test_git이_아예_없으면_조용히_건너뛴다(capsys):
    """수집은 멀쩡히 됐다. 올리지 못했다고 실패로 칠 일은 아니다."""
    assert daily.push(["docs"], "없음", git=가짜git(터질곳={"add": 127})) == 0
    assert "건너뜁니다" in capsys.readouterr().out


def test_올린_주소를_알려_준다(capsys):
    daily.push(["docs"], "새 화면", git=가짜git())
    assert daily.SITE_URL in capsys.readouterr().out


# --- 한 판 --------------------------------------------------------------------

def test_기록은_프로그램_옆에_쌓인다():
    """바로가기로 실행하면 작업 폴더가 엉뚱한 곳이 된다. 그때도 같은 곳."""
    assert daily.project_root() == ROOT
    assert (daily.project_root() / "govpress").is_dir()


def test_기록_이름은_그대로_둔다():
    """이미 13만 줄이 쌓여 있다. 이름이 바뀌면 옛 기록이 끊긴다."""
    assert daily.LOG_NAME == "수집기록.txt"


def test_한_판의_머리글을_알아볼_수_있다(capsys):
    daily.banner("2026-09-30 17:00  자동 수집 시작")
    나온것 = capsys.readouterr().out
    assert "자동 수집 시작" in 나온것
    assert 나온것.count(daily.RULE) == 2


def test_한_판이_수집부터_올리기까지_이어진다(tmp_path, monkeypatch, capsys):
    """중간 한 곳이 자빠져도 나머지는 마저 돌아야 한다."""
    from govpress import __main__ as cli

    한_일: list[str] = []
    monkeypatch.setattr(cli, "_collect", lambda a: 한_일.append("정부기관"))
    monkeypatch.setattr(cli, "_collect_local", lambda a: 한_일.append("지자체"))
    monkeypatch.setattr(cli, "_collect_public",
                        lambda a: (_ for _ in ()).throw(RuntimeError("연결 끊김")))
    monkeypatch.setattr(cli.dashboard, "publish", lambda db, f: (한_일.append("화면"), tmp_path)[1])
    monkeypatch.setattr(cli.daily, "push", lambda *a, **k: 한_일.append("올리기") or 0)
    monkeypatch.setattr(cli.daily, "project_root", lambda: tmp_path)

    code = cli.main(["--db", str(tmp_path / "t.db"), "daily"])

    assert code == 0
    assert 한_일 == ["정부기관", "지자체", "화면", "올리기"]
    적힌 = (tmp_path / daily.LOG_NAME).read_text(encoding="utf-8")
    assert "자동 수집 시작" in 적힌
    assert "[!] 공공기관에서 멈췄습니다: 연결 끊김" in 적힌
    assert "끝 (" in 적힌


def test_기록은_덮어쓰지_않고_이어_붙인다(tmp_path, monkeypatch):
    from govpress import __main__ as cli

    for 이름 in ("_collect", "_collect_local", "_collect_public"):
        monkeypatch.setattr(cli, 이름, lambda a: 0)
    monkeypatch.setattr(cli.dashboard, "publish", lambda db, f: tmp_path)
    monkeypatch.setattr(cli.daily, "push", lambda *a, **k: 0)
    monkeypatch.setattr(cli.daily, "project_root", lambda: tmp_path)

    (tmp_path / daily.LOG_NAME).write_text("어제 것\n", encoding="utf-8")
    cli.main(["--db", str(tmp_path / "t.db"), "daily"])
    assert (tmp_path / daily.LOG_NAME).read_text(encoding="utf-8").startswith("어제 것\n")


def test_테스트가_깨지면_올리지_않는다(tmp_path, monkeypatch, capsys):
    from govpress import __main__ as cli

    class 깨짐:
        returncode = 1

    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: 깨짐())
    올린것: list = []
    monkeypatch.setattr(cli.daily, "push", lambda *a, **k: 올린것.append(1) or 0)

    assert cli.main(["release", "손본 것"]) == 1
    assert not 올린것
    assert "올리지 않고 멈춥니다" in capsys.readouterr().out


def test_할_말을_안_적으면_그냥_올린다(tmp_path, monkeypatch):
    from govpress import __main__ as cli

    class 통과:
        returncode = 0

    적힌말: list[str] = []
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: 통과())
    monkeypatch.setattr(cli.storage, "stats", lambda db: {"total": 10})
    monkeypatch.setattr(cli.dashboard, "publish", lambda db, f: tmp_path)
    monkeypatch.setattr(cli.daily, "push", lambda 것, 말, **k: 적힌말.append(말) or 0)

    assert cli.main(["release"]) == 0
    assert 적힌말 == ["화면·설정 수정"]


def test_올릴_때_코드와_화면을_함께_담는다():
    from govpress import __main__ as cli

    for 것 in ("govpress", "tests", "docs", "자동수집.bat", "올리기.bat"):
        assert 것 in cli.RELEASE_PATHS
    assert "." not in cli.RELEASE_PATHS
    assert "articles.db" not in cli.RELEASE_PATHS
