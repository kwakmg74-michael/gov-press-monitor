"""한국행정연구원 조회조건 찾기.

접속은 됐는데 목록이 0건으로 온다. 이 사이트는 화면에서 연도와
보고서유형을 먼저 체크해 두고 그 값을 함께 보내는 구조라, 조건이
비면 아무것도 찾지 못한다. 어떤 조합을 보내야 하는지 몇 가지 시도해 본다.

    python tools\\fetch_raw5.py
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
LIST = "/service/kor/rsch/rsd/selectRschDataList"
YEARS = "/service/kor/rsch/rsd/selectRschYearList"


def headers_for() -> dict:
    head = dict(boards.HEADERS)
    head.update(
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
    return head


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    session = boards.legacy_session()
    head = headers_for()

    session.get(PAGE, headers=boards.HEADERS, timeout=30)

    # 화면이 쓰는 코드 목록 주소를 자바스크립트에서 찾아본다
    js = session.get(f"{BASE}/modules/baseModule.js", headers=boards.HEADERS, timeout=30)
    paths = sorted(set(re.findall(r"[\"'](/service/[A-Za-z0-9_/]+)[\"']", js.text)))
    print("  baseModule.js 안의 주소:", paths)

    years = session.post(BASE + YEARS, json={}, headers=head, timeout=30).json()
    year_values = [y["value"] for y in years["result"]["rschYearList"]][:3]
    print("  최근 연도:", year_values)

    year_param = "|".join(year_values) + "|"
    attempts = {
        "연도만": {"pblsgYrCds": year_param, "clctCtgryCds": ""},
        "유형만": {"pblsgYrCds": "", "clctCtgryCds": "12286|"},
        "연도+유형": {"pblsgYrCds": year_param, "clctCtgryCds": "12286|"},
        "연도+유형 없이 키워드": {"pblsgYrCds": "", "clctCtgryCds": "", "srchWrd": ""},
    }

    for label, extra in attempts.items():
        body = {
            "currentPageNo": 1,
            "recordCountPerPage": 10,
            "pageSize": 10,
            "pageUnit": 10,
            "firstIndex": 0,
            "tpcClsfCdsArr": "",
            "srchWrd": "",
            **extra,
        }
        data = session.post(BASE + LIST, json=body, headers=head, timeout=30).json()
        result = data.get("result") or {}
        rows = result.get("dataList") or []
        total = (result.get("paginationInfo") or {}).get("totalRecordCount")
        print(f"  {label:20} {len(rows)}건 (전체 {total})")

        if rows:
            (OUT / "kipa_list.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            print("    열쇠:", sorted(rows[0]))
            print("    첫 건:", json.dumps(rows[0], ensure_ascii=False)[:700])
            return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
