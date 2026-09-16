"""2차 확인용. 목록이 자바스크립트로 채워지는 몇 곳만 따로 두드려 본다.

    python tools\\fetch_raw2.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from govpress import boards  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "raw"

GETS: dict[str, str] = {
    # 한국은행: 목록만 따로 그려 주는 조각
    "bok_cont": (
        "https://www.bok.or.kr/portal/singl/newsData/listCont.do"
        "?menuNo=201263&depth2=200038&depth3=201263&targetDepth=3"
        "&searchCnd=1&searchKwd=&sort=1&pageUnit=10&pageIndex=1"
    ),
    "bok_cont_p2": (
        "https://www.bok.or.kr/portal/singl/newsData/listCont.do"
        "?menuNo=201263&depth2=200038&depth3=201263&targetDepth=3"
        "&searchCnd=1&searchKwd=&sort=1&pageUnit=10&pageIndex=2"
    ),
    # KDI: 목록에 발간일이 없다. 상세에는 있는지 본다
    "kdi_view": "https://www.kdi.re.kr/research/reportView?pub_no=19257",
    "kdi_focus_view": "https://www.kdi.re.kr/research/focusView?pub_no=19243",
    "kdi_report_pg2": "https://www.kdi.re.kr/research/reportList?pg=2",
    # 한국조세재정연구원: 상세가 GET으로도 열리는지
    "kipf_view": (
        "https://www.kipf.re.kr/kor/Publication/All/kiPublish/ALL/view.do"
        "?serialNo=527650"
    ),
    # 한국행정연구원: 목록을 부르는 자바스크립트(헤더 값을 보려고)
    "kipa_axios_js": "https://www.kipa.re.kr/modules/axiosModule.js",
}

# 한국행정연구원 목록은 JSON을 POST로 받아 온다.
KIPA_URL = "https://www.kipa.re.kr/service/kor/rsch/rsd/selectRschDataList"
KIPA_BODY = {
    "currentPageNo": 1,
    "recordCountPerPage": 10,
    "pageSize": 10,
    "tpcClsfCdsArr": "",
    "pblsgYrCds": "",
    "clctCtgryCds": "",
    "srchWrd": "",
}


def save(name: str, text: str) -> None:
    path = OUT / f"{name}.html"
    path.write_text(text, encoding="utf-8")
    print(f"  {name:18} {len(text):>8,}자")


def get(url: str) -> requests.Response:
    try:
        return requests.get(url, headers=boards.HEADERS, timeout=30)
    except requests.exceptions.SSLError:
        return boards.legacy_session().get(url, headers=boards.HEADERS, timeout=30)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    for name, url in GETS.items():
        try:
            response = get(url)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or "utf-8"
            save(name, response.text)
        except Exception as exc:
            print(f"  {name:18} 실패: {exc}")

    # --- 한국행정연구원 ---
    print("\n한국행정연구원 JSON:")
    for label, extra in (
        ("맨몸", {}),
        ("헤더붙임", {"X-srvcSiteCd": "kor", "X-srvcMenuCode": "rschData"}),
    ):
        headers = dict(boards.HEADERS)
        headers["Content-Type"] = "application/json"
        headers["Referer"] = "https://www.kipa.re.kr/html/kor/rsch/rsd/rschData.do"
        headers.update(extra)
        try:
            response = requests.post(
                KIPA_URL, json=KIPA_BODY, headers=headers, timeout=30
            )
            body = response.text
            print(f"  {label:8} {response.status_code} {len(body):,}자 {body[:200]}")
            if response.ok:
                save("kipa_json", body)
                try:
                    data = json.loads(body)
                    result = (data.get("result") or {}).get("dataList") or []
                    if result:
                        print("  첫 건 열쇠:", sorted(result[0])[:40])
                except Exception:
                    pass
        except Exception as exc:
            print(f"  {label:8} 실패: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
