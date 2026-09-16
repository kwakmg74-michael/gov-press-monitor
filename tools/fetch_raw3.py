"""한국행정연구원만 한 번 더. 목록을 JSON으로 POST해서 받아 온다.

앞서 인증서 검증에서 막혔다. 이번에는 운영체제 인증서 저장소를 쓰는
연결로 보낸다(다른 기관에서 이미 쓰고 있는 방법).

    python tools\\fetch_raw3.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from govpress import boards  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "raw"
URL = "https://www.kipa.re.kr/service/kor/rsch/rsd/selectRschDataList"
BODY = {
    "currentPageNo": 1,
    "recordCountPerPage": 10,
    "pageSize": 10,
    "pageUnit": 10,
    "tpcClsfCdsArr": "",
    "pblsgYrCds": "",
    "clctCtgryCds": "",
    "srchWrd": "",
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    headers = dict(boards.HEADERS)
    headers["Content-Type"] = "application/json"
    headers["Referer"] = "https://www.kipa.re.kr/html/kor/rsch/rsd/rschData.do"

    for label, extra in (
        ("맨몸", {}),
        ("헤더붙임", {"X-srvcSiteCd": "kor", "X-srvcMenuCode": "rschData"}),
    ):
        try:
            response = boards.legacy_session().post(
                URL, json=BODY, headers={**headers, **extra}, timeout=30
            )
        except Exception as exc:
            print(f"  {label:8} 실패: {type(exc).__name__} {str(exc)[:120]}")
            continue

        body = response.text
        print(f"  {label:8} {response.status_code} {len(body):,}자")
        print(f"           {body[:300]}")
        if response.ok and body.strip().startswith("{"):
            (OUT / "kipa_json.txt").write_text(body, encoding="utf-8")
            try:
                rows = (json.loads(body).get("result") or {}).get("dataList") or []
                if rows:
                    print("  첫 건 열쇠:", sorted(rows[0]))
                    print("  첫 건:", json.dumps(rows[0], ensure_ascii=False)[:500])
                    return 0
            except Exception as exc:
                print("  JSON 해석 실패:", exc)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
