"""고시·공고 게시판 세 곳을 한 번 받아 본다. 긁을 수 있는 모양인지 보려고.

쓰는 법 — gov-press-monitor 폴더에서:

    python tools\\fetch_gosi.py

받은 HTML은 tests/fixtures/raw/ 에 남는다. 화면에 찍히는 것만 보여 주셔도
되고, 애매하면 그 파일을 보내 주셔도 된다.

보는 눈은 둘이다.

1) 긁히는가 — "줄처럼 보이는 것"이 여러 개면 그냥 긁을 수 있다. 길이는
   긴데 0이면 자바스크립트로 그리는 화면이라 다른 길을 찾아야 한다.

2) 쓸모가 있는가 — 이게 더 중요하다. 시보·도보는 주마다 한 권씩 내는
   관보라, 목록이 '제3300호 2026-10-15' 처럼 호수만 늘어서 있고 그 안의
   고시·공고는 PDF 안에 들어 있는 경우가 많다. 그러면 화면에 띄워도
   "이번 주 호가 나왔다"는 것밖에 알 수 없다. 아래 찍히는 줄이 호수인지
   개별 고시 제목인지를 봐야 한다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from govpress import boards  # noqa: E402

여기 = Path(__file__).resolve().parent.parent
받을곳 = 여기 / "tests" / "fixtures" / "raw"

# 주소 뒤의 #page=1#sdate=... 같은 토막은 브라우저 안에서만 쓰는 것이라
# 서버로 가지 않는다. 그래서 여기서는 뗀다.
대상 = [
    ("seoul_sibo", "서울시보",
     "https://www.seoul.go.kr/func/seoulsibo/list.do"),
    ("gg_dobo", "경기도보",
     "https://www.gg.go.kr/bbs/board.do?bsIdx=769&menuId=1786"),
    ("seongnam_sibo", "성남시보",
     "https://www.seongnam.go.kr/bbs010308"),
]

호수 = re.compile(r"제?\s*\d{3,5}\s*호")
고시말 = re.compile(r"고시|공고|지정|변경|결정|지구단위|도시계획|용도지역")
날짜 = re.compile(r"20\d{2}[.\-]\s?\d{1,2}[.\-]\s?\d{1,2}")


def main() -> int:
    받을곳.mkdir(parents=True, exist_ok=True)
    for 이름, 라벨, 주소 in 대상:
        print()
        print("=" * 64)
        print(f" {라벨}")
        print(f" {주소}")
        print("=" * 64)
        try:
            응답 = boards.get(주소)
        except Exception as exc:  # noqa: BLE001
            print(f"  [!] 못 받았습니다: {type(exc).__name__}: {exc}")
            continue

        글 = 응답.text
        (받을곳 / f"{이름}.html").write_text(글, encoding="utf-8")

        줄 = [l.strip() for l in re.sub(r"<[^>]+>", "\n", 글).splitlines()]
        줄 = [l for l in 줄 if 6 < len(l) < 120]
        보이는것 = [l for l in 줄 if 고시말.search(l) or 호수.search(l)]

        print(f"  응답 코드      : {응답.status_code}")
        print(f"  본문 길이      : {len(글):,}자")
        print(f"  <table> {글.count('<table')}개   <tr> {글.count('<tr'):,}개   "
              f"<a href> {글.count('<a '):,}개")
        print(f"  PDF 링크       : {글.lower().count('.pdf')}개")
        print(f"  호수처럼 보이는 줄 : {sum(1 for l in 줄 if 호수.search(l))}개")
        print(f"  날짜처럼 보이는 줄 : {sum(1 for l in 줄 if 날짜.search(l))}개")
        print(f"  줄처럼 보이는 것   : {len(보이는것)}개")
        for l in 보이는것[:10]:
            print(f"      · {l[:72]}")
        print(f"  받아 둔 파일   : tests/fixtures/raw/{이름}.html")

    print()
    print("끝. 위 내용을 그대로 보여 주세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
