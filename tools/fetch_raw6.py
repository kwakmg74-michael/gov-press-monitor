"""KDI FOCUS 상세 화면 한 장만 더. 발간일이 어디에 적혀 있는지 보려고.

연구보고서 상세는 `div.tit_top > p`에 발간일이 있는데, FOCUS 쪽은
거기서 못 찾는다. 화면 구조가 다른 듯해 실제 HTML을 받아 본다.

    python tools\\fetch_raw6.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from govpress import boards  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "raw"

TARGETS = {
    "kdi_focus_view": "https://www.kdi.re.kr/research/focusView?pub_no=19239",
    "kdi_focus_view2": "https://www.kdi.re.kr/research/focusView?pub_no=18911",
    "kdi_etc_view": "https://www.kdi.re.kr/research/reportEtcView?pub_no=19254",
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    # 목록을 먼저 열어 둔다. 곧바로 상세부터 두드리면 막는 곳이 있다.
    session.get(
        "https://www.kdi.re.kr/research/focusList", headers=boards.HEADERS, timeout=30
    )

    for name, url in TARGETS.items():
        try:
            response = session.get(
                url,
                headers={**boards.HEADERS, "Referer": "https://www.kdi.re.kr/research/focusList"},
                timeout=30,
            )
            response.raise_for_status()
        except Exception as exc:
            print(f"  {name:18} 실패: {exc}")
            continue

        response.encoding = response.apparent_encoding or "utf-8"
        (OUT / f"{name}.html").write_text(response.text, encoding="utf-8")
        print(f"  {name:18} {len(response.text):>8,}자")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
