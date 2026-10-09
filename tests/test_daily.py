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


def _govpress_calls(name) -> list[str]:
    줄 = [l.strip() for l in (ROOT / name).read_text(encoding="ascii").splitlines()]
    return [l for l in 줄 if "-m govpress " in l]


@pytest.mark.parametrize("name", BATS)
def test_배치파일은_파이썬만_부른다(name):
    """일이 배치와 파이썬으로 나뉘어 있으면 어느 쪽이 도는지 헷갈린다."""
    부른_것 = _govpress_calls(name)
    assert 부른_것, f"{name}이 govpress를 부르지 않습니다"
    for 줄 in 부른_것:
        assert 줄.startswith('"%PY%" -u -m govpress '), 줄


# --- 받기는 수집과 다른 판에서 해야 한다 ------------------------------------------
#
# 2026-10-09. 10월 8일 저녁에 올린 코드가 다음 날 아침 수집에 반영되지
# 않았다. 받기는 성공했는데 화면은 옛 코드로 그려졌다.
#
# 파이썬은 시작할 때 파일을 읽어 머리에 담는다. 돌고 있는 중에 git 이
# 디스크를 바꿔 놔도 이미 담아 둔 것은 안 바뀐다. 그래서 받기를 따로
# 떼어, 그 판이 끝나고 다음 판이 새 파일을 읽게 했다.

def test_받기와_수집은_따로_부른다():
    부른_것 = _govpress_calls("자동수집.bat")
    assert len(부른_것) == 2, 부른_것
    assert 부른_것[0].endswith("govpress sync")
    assert 부른_것[1].endswith("govpress daily --no-sync")


def test_받기가_수집보다_먼저다():
    """순서가 뒤집히면 받아 온 코드가 그 판에 쓰이지 않는다."""
    글 = (ROOT / "자동수집.bat").read_text(encoding="ascii")
    assert 글.index("govpress sync") < 글.index("govpress daily")


def test_왜_두_번_부르는지_파일_안에_적어_둔다(name="자동수집.bat"):
    """한 줄로 합치고 싶어지는 모양이다. 까닭이 곁에 있어야 한다."""
    글 = (ROOT / name).read_text(encoding="ascii")
    assert "Two python calls on purpose" in 글
    assert "already" in 글 and "running process" in 글


# --- PC마다 다른 파이썬 ---------------------------------------------------------
#
# 서버PC는 가상환경(D:\Server\Envs\press)의 파이썬을 쓰고, pc1은 PATH에
# 걸린 것을 그냥 쓴다. 배치 파일에 경로를 박아 두면 두 대가 같은 줄을
# 서로 다르게 고쳐 놓고 git 에서 매번 부딪힌다. 그래서 경로는 파일로
# 빼 두고, 그 파일은 git 이 쳐다보지 않게 한다.

@pytest.mark.parametrize("name", BATS)
def test_파이썬_경로를_파일에서_읽는다(name):
    글 = (ROOT / name).read_text(encoding="ascii")
    assert 'set "PY=python"' in 글                      # 적어 둔 것이 없으면 이것
    assert 'if exist "%~dp0python-path.txt"' in 글      # 있으면 그것
    assert 'set /p PY=<"%~dp0python-path.txt"' in 글


@pytest.mark.parametrize("name", BATS)
def test_경로에_빈칸이_있어도_된다(name):
    """Program Files 밑이면 따옴표가 없을 때 두 동강 난다."""
    assert '"%PY%" -u -m' in (ROOT / name).read_text(encoding="ascii")


@pytest.mark.parametrize("name", BATS)
def test_배치파일은_자기_폴더를_기준으로_찾는다(name):
    r"""작업 스케줄러가 부르면 현재 폴더가 C:\Windows\System32 다."""
    글 = (ROOT / name).read_text(encoding="ascii")
    assert 'cd /d "%~dp0"' in 글
    assert "python-path.txt" in 글 and "%~dp0python-path.txt" in 글


def test_파이썬_경로는_git에_담지_않는다():
    """담으면 서버가 올린 경로를 pc1이 받아 쓰게 된다."""
    assert "python-path.txt" in (ROOT / ".gitignore").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", BATS)
def test_경로를_어떻게_적는지_파일_안에_적어_둔다(name):
    """따옴표를 치거나 뒤에 빈칸을 남기면 조용히 안 돈다."""
    글 = (ROOT / name).read_text(encoding="ascii")
    assert "python-path.txt (one line, no quotes, no trailing space)" in 글


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
    monkeypatch.setattr(cli.daily, "sync", lambda **k: True)
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

    monkeypatch.setattr(cli.daily, "sync", lambda **k: True)
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
    monkeypatch.setattr(cli.daily, "sync", lambda **k: True)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: 통과())
    monkeypatch.setattr(cli.daily, "push", lambda 것, 말, **k: 적힌말.append(말) or 0)

    assert cli.main(["release"]) == 0
    assert 적힌말 == ["코드 수정"]


def test_올릴_때_코드를_담는다():
    from govpress import __main__ as cli

    for 것 in ("govpress", "tests", "자동수집.bat", "올리기.bat", ".gitattributes"):
        assert 것 in cli.RELEASE_PATHS
    assert "." not in cli.RELEASE_PATHS
    assert "articles.db" not in cli.RELEASE_PATHS


# --- pc1은 화면을 올리지 않는다 ---------------------------------------------------
#
# 수집은 서버PC가 맡고 pc1은 코드를 고친다. 그래서 두 대의 articles.db 가
# 갈라진다 — 2026-10-05에 서버 10,809건, pc1 10,338건이었다.
#
# 예전처럼 올리기.bat 이 화면까지 다시 만들면, 코드 한 줄 고치려고 누른 것이
# pc1의 낡은 DB로 사이트를 471건 뒤로 되돌린다. 오류는 나지 않는다.

def test_손으로_올릴_때는_화면을_만들지_않는다(tmp_path, monkeypatch):
    from govpress import __main__ as cli

    class 통과:
        returncode = 0

    만들었나: list = []
    monkeypatch.setattr(cli.daily, "sync", lambda **k: True)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: 통과())
    monkeypatch.setattr(cli.dashboard, "publish",
                        lambda db, f: 만들었나.append(1) or tmp_path)
    monkeypatch.setattr(cli.daily, "push", lambda *a, **k: 0)

    assert cli.main(["release", "코드만"]) == 0
    assert not 만들었나


def test_화면_폴더는_코드와_함께_담지_않는다():
    """담으면 pc1에 남아 있던 낡은 docs 가 그대로 올라간다."""
    from govpress import __main__ as cli

    assert "docs" not in cli.RELEASE_PATHS


def test_화면은_누가_만드는지_알려_준다(tmp_path, monkeypatch, capsys):
    """'화면 만들기'가 사라졌는데 말이 없으면 빠진 줄 안다."""
    from govpress import __main__ as cli

    class 통과:
        returncode = 0

    monkeypatch.setattr(cli.daily, "sync", lambda **k: True)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: 통과())
    monkeypatch.setattr(cli.daily, "push", lambda *a, **k: 0)

    cli.main(["release", "코드만"])
    assert "서버PC가 다음 수집 때" in capsys.readouterr().out


# --- 두 대가 같은 저장소를 쓴다 -------------------------------------------------
#
# 2026-10-05부터 서버PC가 수집·발행을 맡고, pc1은 코드를 고쳐 올린다.
# 받아 두지 않고 올리면 나중에 올리는 쪽이 통째로 튕기는데, 수집은
# 성공했다고 적히니 겉으로는 멀쩡해 보인다. 9월에 두 달을 그렇게 보냈다.

def test_올리기_전에_먼저_받는다():
    git = 가짜git()
    assert daily.sync(git=git) is True
    assert git.부른것 == [["pull", "--rebase", "--autostash"]]


def test_담아_두지_않은_것은_잠깐_치워_둔다():
    """방금 만든 docs 가 그대로 있으면 받아 오다 막힌다."""
    git = 가짜git()
    daily.sync(git=git)
    assert "--autostash" in git.부른것[0]


def test_부딪히면_반쯤_걸친_채로_두지_않는다(capsys):
    git = 가짜git(터질곳={"pull": 1})
    assert daily.sync(git=git) is False
    assert ["rebase", "--abort"] in git.부른것
    assert "이번에는 올리지 않습니다" in capsys.readouterr().out


def test_git이_없으면_받기도_건너뛴다():
    assert daily.sync(git=가짜git(터질곳={"pull": 127})) is True


def test_받지_못하면_올리지_않는다(tmp_path, monkeypatch, capsys):
    from govpress import __main__ as cli

    for 이름 in ("_collect", "_collect_local", "_collect_public"):
        monkeypatch.setattr(cli, 이름, lambda a: 0)
    monkeypatch.setattr(cli.dashboard, "publish", lambda db, f: tmp_path)
    monkeypatch.setattr(cli.daily, "project_root", lambda: tmp_path)
    monkeypatch.setattr(cli.daily, "sync", lambda **k: False)
    올린것: list = []
    monkeypatch.setattr(cli.daily, "push", lambda *a, **k: 올린것.append(1) or 0)

    assert cli.main(["--db", str(tmp_path / "t.db"), "daily"]) == 1
    assert not 올린것
    # 그래도 화면은 만들어 둔다. 다음 차례에 저절로 올라간다.
    assert "화면 만들기" in (tmp_path / daily.LOG_NAME).read_text(encoding="utf-8")


def test_받기는_화면을_만들기_전에_한다(tmp_path, monkeypatch):
    """받은 뒤에 만들어야 남의 것 위에 내 화면이 얹힌다."""
    from govpress import __main__ as cli

    순서: list[str] = []
    for 이름 in ("_collect", "_collect_local", "_collect_public"):
        monkeypatch.setattr(cli, 이름, lambda a: 0)
    monkeypatch.setattr(cli.daily, "project_root", lambda: tmp_path)
    monkeypatch.setattr(cli.daily, "sync", lambda **k: 순서.append("받기") or True)
    monkeypatch.setattr(cli.dashboard, "publish",
                        lambda db, f: 순서.append("화면") or tmp_path)
    monkeypatch.setattr(cli.daily, "push", lambda *a, **k: 순서.append("올리기") or 0)

    cli.main(["--db", str(tmp_path / "t.db"), "daily"])
    assert 순서 == ["받기", "화면", "올리기"]


def test_이름이_없으면_무엇을_치라고_알려_준다(capsys):
    """서버PC가 여기서 멈췄다. git 이 내놓는 말이 영어라 알아보기 어려웠다."""
    def git(a, cwd):
        if a[:1] == ["diff"]:
            return 1, ""
        if a[0] == "commit":
            return 1, "*** Please tell me who you are.\nRun\n  git config --global user.email"
        return 0, ""

    assert daily.push(["docs"], "실패", git=git) == 1
    나온것 = capsys.readouterr().out
    assert "git config --global user.name" in 나온것
    assert "kwakmg74" not in 나온것  # 공개 저장소에 올라가는 코드다


def test_먼저_올린_사람이_있으면_그렇게_말해_준다(capsys):
    def git(a, cwd):
        if a[:1] == ["diff"]:
            return 1, ""
        if a[0] == "push":
            return 1, "! [rejected]  main -> main (non-fast-forward)"
        return 0, ""

    assert daily.push(["docs"], "늦었다", git=git) == 1
    assert "다른 PC가 먼저 올렸습니다" in capsys.readouterr().out


def test_올리기도_받기부터_한다(tmp_path, monkeypatch, capsys):
    """pc1에서 손으로 올릴 때도 마찬가지다."""
    from govpress import __main__ as cli

    순서: list[str] = []
    monkeypatch.setattr(cli.daily, "sync", lambda **k: 순서.append("받기") or True)
    monkeypatch.setattr(cli.subprocess, "run",
                        lambda *a, **k: 순서.append("테스트") or type("R", (), {"returncode": 0})())
    monkeypatch.setattr(cli.storage, "stats", lambda db: {"total": 10})
    monkeypatch.setattr(cli.daily, "push", lambda *a, **k: 순서.append("올리기") or 0)

    assert cli.main(["release", "손본 것"]) == 0
    assert 순서 == ["받기", "테스트", "올리기"]


def test_받지_못하면_테스트도_돌리지_않는다(monkeypatch, capsys):
    from govpress import __main__ as cli

    돈것: list = []
    monkeypatch.setattr(cli.daily, "sync", lambda **k: False)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: 돈것.append(1))

    assert cli.main(["release"]) == 1
    assert not 돈것


# --- govpress sync ------------------------------------------------------------

def test_받기만_하는_명령이_있다(tmp_path, monkeypatch, capsys):
    from govpress import __main__ as cli

    받았나: list = []
    monkeypatch.setattr(cli.daily, "project_root", lambda: tmp_path)
    monkeypatch.setattr(cli.daily, "sync", lambda **k: 받았나.append(1) or True)
    모은것: list = []
    monkeypatch.setattr(cli, "_collect", lambda a: 모은것.append(1))

    assert cli.main(["sync"]) == 0
    assert 받았나 == [1]
    assert not 모은것, "받기만 해야 하는데 수집까지 했습니다"


def test_받기도_기록에_남는다(tmp_path, monkeypatch):
    """창을 안 보고 있었어도 나중에 읽을 수 있어야 한다."""
    from govpress import __main__ as cli

    monkeypatch.setattr(cli.daily, "project_root", lambda: tmp_path)
    monkeypatch.setattr(cli.daily, "sync", lambda **k: True)
    cli.main(["sync"])

    적힌 = (tmp_path / daily.LOG_NAME).read_text(encoding="utf-8")
    assert "자동 수집 시작" in 적힌
    assert "다른 PC가 올린 것 받기" in 적힌


def test_못_받으면_받기가_실패로_끝난다(tmp_path, monkeypatch):
    from govpress import __main__ as cli

    monkeypatch.setattr(cli.daily, "project_root", lambda: tmp_path)
    monkeypatch.setattr(cli.daily, "sync", lambda **k: False)
    assert cli.main(["sync"]) == 1


def test_앞에서_받았으면_다시_받지_않는다(tmp_path, monkeypatch):
    """두 번 받으면 느리기만 한 게 아니라 머리글이 두 번 찍힌다."""
    from govpress import __main__ as cli

    for 이름 in ("_collect", "_collect_local", "_collect_public"):
        monkeypatch.setattr(cli, 이름, lambda a: 0)
    monkeypatch.setattr(cli.dashboard, "publish", lambda db, f: tmp_path)
    monkeypatch.setattr(cli.daily, "project_root", lambda: tmp_path)
    monkeypatch.setattr(cli.daily, "push", lambda *a, **k: 0)
    받았나: list = []
    monkeypatch.setattr(cli.daily, "sync", lambda **k: 받았나.append(1) or True)

    assert cli.main(["--db", str(tmp_path / "t.db"), "daily", "--no-sync"]) == 0
    assert not 받았나

    적힌 = (tmp_path / daily.LOG_NAME).read_text(encoding="utf-8")
    assert 적힌.count("자동 수집 시작") == 0, "머리글은 앞 단계(sync)가 찍는다"
    assert "화면 만들기" in 적힌


def test_손으로_daily만_부르면_그때는_받는다(tmp_path, monkeypatch):
    """자동수집.bat 을 거치지 않는 길도 막히면 안 된다."""
    from govpress import __main__ as cli

    for 이름 in ("_collect", "_collect_local", "_collect_public"):
        monkeypatch.setattr(cli, 이름, lambda a: 0)
    monkeypatch.setattr(cli.dashboard, "publish", lambda db, f: tmp_path)
    monkeypatch.setattr(cli.daily, "project_root", lambda: tmp_path)
    monkeypatch.setattr(cli.daily, "push", lambda *a, **k: 0)
    받았나: list = []
    monkeypatch.setattr(cli.daily, "sync", lambda **k: 받았나.append(1) or True)

    assert cli.main(["--db", str(tmp_path / "t.db"), "daily"]) == 0
    assert 받았나 == [1]
    적힌 = (tmp_path / daily.LOG_NAME).read_text(encoding="utf-8")
    assert 적힌.count("자동 수집 시작") == 1
