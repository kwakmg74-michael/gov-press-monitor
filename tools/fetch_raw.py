"""새 게시판의 목록 HTML을 그대로 받아 둔다.

파서를 쓰려면 먼저 그 게시판이 실제로 어떤 모양인지 봐야 한다. 그런데
이 작업을 하는 쪽(클라우드)에서는 국내 기관 사이트가 막혀 있어서, 받아
오는 일만 사무실 PC에서 대신 한다.

    python tools\\fetch_raw.py

받은 파일은 tests/fixtures/raw/ 에 쌓인다. 파서를 다 만들고 나면 이
폴더는 지워도 된다 — 테스트에 쓰는 것은 여기서 3건만 추려 낸 파일이다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from govpress import boards  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "raw"

# 파일이름: 목록 주소
TARGETS: dict[str, str] = {
    # --- 공공기관 ---
    "kisa": "https://www.kisa.or.kr/402",
    "hf": "https://www.hf.go.kr/ko/sub05/sub05_04_05.do",
    "lh": "https://www.lh.or.kr/gallery.es?mid=a10502000000&bid=0003",
    "bok": (
        "https://www.bok.or.kr/portal/singl/newsData/list.do"
        "?menuNo=201263&pageIndex=1"
    ),
    "gh": "https://www.gh.or.kr/gh/press-release.do",
    # --- 연구소 ---
    "kipf": "https://www.kipf.re.kr/kor/Publication/All/kiPublish/ALL/list.do",
    "kipa": "https://www.kipa.re.kr/html/kor/rsch/rsd/rschData.do",
    "kdi_report": "https://www.kdi.re.kr/research/reportList",
    "kdi_focus": "https://www.kdi.re.kr/research/focusList",
    "kdi_economy": "https://www.kdi.re.kr/research/economy",
    "kdi_montrends": "https://www.kdi.re.kr/research/monTrends",
    "kdi_etc": "https://www.kdi.re.kr/research/etcReportList",
    "kdi_moncountry": "https://www.kdi.re.kr/research/monCountry",
    # --- 2페이지도 한 장씩. 페이지 넘기는 방식을 확인하려고 받는다 ---
    "kisa_p2": "https://www.kisa.or.kr/402?page=2",
    "hf_p2": (
        "https://www.hf.go.kr/ko/sub05/sub05_04_05.do"
        "?mode=list&articleLimit=10&article.offset=10"
    ),
    "lh_p2": "https://www.lh.or.kr/gallery.es?mid=a10502000000&bid=0003&nPage=2",
    "gh_p2": (
        "https://www.gh.or.kr/gh/press-release.do"
        "?mode=list&articleLimit=10&article.offset=10"
    ),
    "kipf_p2": (
        "https://www.kipf.re.kr/kor/Publication/All/kiPublish/ALL/list.do?pageIndex=2"
    ),
    "kipa_p2": "https://www.kipa.re.kr/html/kor/rsch/rsd/rschData.do?pageIndex=2",
    "kdi_report_p2": "https://www.kdi.re.kr/research/reportList?page=2",
}


def get(url: str) -> requests.Response:
    """boards.fetch_page 와 같은 3단계 후퇴를 쓴다."""
    try:
        return requests.get(url, headers=boards.HEADERS, timeout=30)
    except requests.exceptions.SSLError:
        try:
            return boards.legacy_session().get(url, headers=boards.HEADERS, timeout=30)
        except requests.exceptions.SSLError:
            return boards.insecure_session().get(url, headers=boards.HEADERS, timeout=30)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    failed = 0

    for name, url in TARGETS.items():
        try:
            response = get(url)
            response.raise_for_status()
        except Exception as exc:
            print(f"  {name:16} 실패: {exc}")
            failed += 1
            continue

        response.encoding = response.apparent_encoding or "utf-8"
        path = OUT / f"{name}.html"
        path.write_text(response.text, encoding="utf-8")
        print(f"  {name:16} {len(response.text):>8,}자  {path.name}")

    print(f"\n{len(TARGETS) - failed}/{len(TARGETS)}개 받음 → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
