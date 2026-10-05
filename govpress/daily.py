"""하루 세 번 도는 자동 수집. 예전에는 자동수집.bat 이 하던 일이다.

왜 옮겼는가 — 2026-09-30 오후 5시 수집을 지켜보다가 검은 창에 이런 두
줄이 떴다.

    '어디서' is not recognized as an internal or external command
    '◆그때' is not recognized as an internal or external command

배치 파일에 적어 둔 한글 설명(rem) 한가운데다. cmd 는 배치 파일을 한 줄
실행할 때마다 "몇 번째 바이트까지 읽었는지"를 적어 두고 되돌아오는데,
`chcp 65001` 로 글자 규칙을 바꿔 놓은 채 한글(한 자에 3바이트)이 섞여
있으면 그 셈이 어긋난다. 그러면 줄 한가운데로 되돌아와, 설명글의 뒷토막을
명령인 줄 알고 실행하려 든다.

이번에 건너뛴 것이 설명뿐이라 수집은 멀쩡히 끝났다. 다음에도 그러리란
보장이 없다 — 어긋나는 자리는 파일을 한 줄 고칠 때마다 달라지고, 하필
`python ... collect` 줄을 물면 그날 수집이 통째로 빠진다. 조용히.

그래서 배치 파일에서 한글을 전부 걷어내고 하던 일을 이리로 옮겼다. 이제
자동수집.bat 은 이 파일을 부르는 네 줄이 전부다. 한글이 한 자도 없으면
어긋날 바이트도 없다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

LOG_NAME = "수집기록.txt"
RULE = "=" * 50
SITE_URL = "https://kwakmg74-michael.github.io/gov-press-monitor/"


def project_root() -> Path:
    """govpress 폴더를 담고 있는 폴더. 어디서 불러도 같은 곳을 가리킨다."""
    return Path(__file__).resolve().parent.parent


class Tee:
    """화면에도 보여 주고 기록에도 남긴다.

    `>> 수집기록.txt` 로 넘기면 창에는 아무것도 안 보여서, 도는 중인지
    멈춘 것인지 알 수가 없었다. 둘 다 한다.
    """

    def __init__(self, *streams):
        self._streams = streams

    def write(self, text: str) -> int:
        for stream in self._streams:
            try:
                stream.write(text)
                stream.flush()  # 죽더라도 어디까지 갔는지는 남아야 한다
            except Exception:
                pass
        return len(text)

    def flush(self) -> None:
        for stream in self._streams:
            try:
                stream.flush()
            except Exception:
                pass

    def isatty(self) -> bool:
        return False


def banner(text: str) -> None:
    print()
    print(RULE)
    print(f" {text}")
    print(RULE)


def run_git(args: list[str], cwd) -> tuple[int, str]:
    """git 한 번. 돌아온 값과 말을 그대로 돌려준다."""
    try:
        done = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return 127, "git 명령을 찾을 수 없습니다."
    return done.returncode, (done.stdout + done.stderr).strip()


def sync(cwd=None, git=run_git) -> bool:
    """올리기 전에 상대방이 올린 것을 먼저 받아 둔다.

    2026-10-05부터 두 대가 같은 저장소를 쓴다. 서버PC는 하루 세 번 수집해
    화면을 올리고, pc1은 코드를 고쳐 올린다. 받아 두지 않으면 나중에
    올리는 쪽이 `rejected (non-fast-forward)` 로 통째로 튕긴다 — 그런데
    수집은 성공했다고 적히니, 겉으로는 멀쩡해 보인다.

    --autostash 는 아직 담지 않은 것(방금 만든 docs 같은)을 잠깐 치웠다가
    도로 꺼내 준다. 부딪히면 반쯤 걸친 상태로 두지 않고 되돌린다.
    """
    cwd = Path(cwd or project_root())
    code, said = git(["pull", "--rebase", "--autostash"], cwd)
    if code == 127:  # git이 없으면 어차피 올리지도 못한다
        return True
    if said:
        print(said)
    if code == 0:
        return True

    git(["rebase", "--abort"], cwd)
    print("  [!] 다른 PC가 올린 것과 부딪혔습니다. 이번에는 올리지 않습니다.")
    print("      수집한 자료는 그대로 있습니다. 손으로 `git pull` 한 번 해 주세요.")
    return False


def push(paths, message: str, cwd=None, git=run_git) -> int:
    """담을 것만 담아 올린다.

    `git add .` 로 통째로 담으면 작업 중이던 것까지 딸려 올라간다.
    담을 곳을 하나하나 적는 까닭이다.
    """
    cwd = Path(cwd or project_root())

    code, said = git(["add", *paths], cwd)
    if code == 127:
        print(f"  [!] {said} 올리기를 건너뜁니다.")
        return 0
    if said:
        print(said)

    # 돌아온 값이 0이면 담긴 것과 지금이 같다 — 바뀐 것이 없다.
    if git(["diff", "--cached", "--quiet"], cwd)[0] == 0:
        print("  바뀐 내용이 없어 올리지 않았습니다.")
        return 0

    code, said = git(["commit", "-m", message], cwd)
    if said:
        print(said)
    if code:
        print("  [!] 담아 두지 못했습니다.")
        # 2026-10-04에 서버PC가 여기서 멈췄다. 수집은 다 됐는데 화면만
        # 그대로였다. git 이 내놓는 말이 영어라 알아보기 어려웠다.
        if "who you are" in said or "user.email" in said:
            print('      이 PC의 git에 "누가 올리는지"가 설정돼 있지 않습니다.')
            print("      아무 폴더에서나 한 번만 치면 계속 유지됩니다:")
            print('        git config --global user.name "이름"')
            print('        git config --global user.email "메일주소"')
        return 1

    code, said = git(["push"], cwd)
    if said:
        print(said)
    if code:
        if "non-fast-forward" in said or "rejected" in said:
            print("      다른 PC가 먼저 올렸습니다. `git pull --rebase` 뒤에 다시 해 주세요.")
        else:
            print("  [!] 올리기 실패. 인터넷이나 GitHub 로그인을 확인하세요.")
        return 1

    print(f"  올렸습니다: {SITE_URL}")
    return 0
