"""새로 붙인 곳이 실제로 받아지는지 한 줄씩 확인한다.

저장해 둔 HTML로는 잘 읽히는데 실제 수집에서 0건이 나오는 경우가 있다.
주소에 페이지 번호를 붙이면 사이트가 다르게 응답하거나, 접속 표시를
요구하는 식이다. 그 차이를 눈으로 보려는 용도다.

    python tools\\check_sites.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from govpress import boards, public_org, research  # noqa: E402

TARGETS = [
    ("공공기관", public_org, "한국은행"),
    ("공공기관", public_org, "한국토지주택공사"),
    ("연구소", research, "한국조세재정연구원"),
    ("연구소", research, "한국개발연구원"),
]


def main() -> int:
    print("지금 PC에 올라와 있는 목록")
    print("  공공기관:", ", ".join(public_org.agency_names()))
    print("  연구소  :", ", ".join(research.agency_names()))
    print()

    for what, module, name in TARGETS:
        sites = module.boards_of(name)
        if not sites:
            print(f"[{what}] {name} — 목록에 없습니다 (코드가 예전 것입니다)")
            continue

        for site in sites:
            for page in (1, 2):
                url = site.page_url(page)
                try:
                    articles = boards.fetch_page(site, page)
                except Exception as exc:
                    print(f"  {site.label:24} {page}쪽 실패: {type(exc).__name__} {exc}")
                    continue

                first = articles[0].title[:34] if articles else "-"
                print(f"  {site.label:24} {page}쪽 {len(articles):>3}건  {first}")
                print(f"     {url}")

                if site.single_request:
                    break
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
