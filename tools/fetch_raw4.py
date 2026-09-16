"""한국행정연구원 마지막 시도.

이 사이트는 목록을 화면이 아니라 JSON으로 따로 받아 온다. 그런데 그
주소만 곧바로 두드리면 404가 난다. 브라우저는 먼저 목록 화면을 열어
접속 표시(쿠키)와 위조 방지 표를 받아 두고 그걸 얹어 보내기 때문일 수
있어, 이번에는 같은 순서로 해 본다.

    python tools\\fetch_raw4.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from govpress import boards  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "raw"
PAGE = "https://www.kipa.re.kr/html/kor/rsch/rsd/rschData.do"
BASE = "https://www.kipa.re.kr"
META = re.compile(r'<meta name="(_csrf|_csrf_header)" content="([^"]*)"')

BODY = {
    "currentPageNo": 1,
    "recordCountPerPage": 10,
    "pageSize": 10,
    "pageUnit": 10,
    "firstIndex": 0,
    "tpcClsfCdsArr": "",
    "pblsgYrCds": "",
    "clctCtgryCds": "",
    "srchWrd": "",
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    session = boards.legacy_session()

    page = session.get(PAGE, headers=boards.HEADERS, timeout=30)
    page.encoding = page.apparent_encoding or "utf-8"
    found = dict(META.findall(page.text))
    print(f"  목록화면 {page.status_code} · 쿠키 {len(session.cookies)}개 · 표 {found}")

    headers = dict(boards.HEADERS)
    headers.update(
        {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Referer": PAGE,
            "Origin": BASE,
            "X-Requested-With": "XMLHttpRequest",
            "X-srvcSiteCd": "kipa",
            "X-srvcMenuCode": "13001000000002025021902",
        }
    )
    name = found.get("_csrf_header")
    if name and found.get("_csrf"):
        headers[name] = found["_csrf"]

    for label, path in (
        ("연도목록", "/service/kor/rsch/rsd/selectRschYearList"),
        ("자료목록", "/service/kor/rsch/rsd/selectRschDataList"),
    ):
        body = {} if "Year" in path else BODY
        try:
            response = session.post(
                BASE + path, json=body, headers=headers, timeout=30
            )
        except Exception as exc:
            print(f"  {label} 실패: {type(exc).__name__} {str(exc)[:120]}")
            continue

        text = response.text
        print(f"  {label} {response.status_code} {len(text):,}자 · {text[:160]}")

        if response.ok and text.strip().startswith("{"):
            (OUT / f"kipa_{label}.txt").write_text(text, encoding="utf-8")
            try:
                result = json.loads(text).get("result") or {}
                rows = result.get("dataList") or []
                if rows:
                    print("    열쇠:", sorted(rows[0]))
                    print("    첫 건:", json.dumps(rows[0], ensure_ascii=False)[:600])
            except Exception as exc:
                print("    JSON 해석 실패:", exc)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
