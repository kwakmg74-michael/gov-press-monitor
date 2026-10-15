"""시·도·구보 주소를 지자체 홈페이지에서 찾아 본다.

쓰는 법 — gov-press-monitor 폴더에서:

    python tools\\find_gazette.py

여덟 곳의 홈페이지를 한 번씩 열어, 메뉴에 걸린 "○○시보 / ○○구보" 링크를
그러모은다. 이미 아는 세 곳(서울·경기·성남)도 함께 찍어 보여 주므로,
맞게 찾고 있는지 눈으로 견줄 수 있다.

찾은 주소는 govpress/local_gov.py 의 GAZETTES 에 한 줄씩 보태면 된다.
없는 주소를 지어내느니 바로가기를 안 다는 쪽이 낫다 — 눌렀는데 엉뚱한
데로 가면 그게 더 나쁘다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from govpress import boards, local_gov  # noqa: E402

# 메뉴 글자가 이런 모양이면 관보로 본다. '시보수' 같은 말에 걸리지 않게
# 앞뒤를 묶어 둔다.
관보말 = re.compile(r"(시\s?보|도\s?보|구\s?보|군\s?보|공\s?보)$|^(시\s?보|도\s?보|구\s?보|군\s?보|공\s?보)")


def 홈(주소: str) -> str:
    조각 = urlsplit(주소)
    return f"{조각.scheme}://{조각.netloc}/"


def main() -> int:
    for site in local_gov.SITES:
        이미 = local_gov.GAZETTES.get(site.name)
        print()
        print("=" * 64)
        print(f" {site.name}" + (f"   (이미 앎: {이미['label']})" if 이미 else ""))
        뿌리 = 홈(site.list_url)
        print(f" {뿌리}")
        print("=" * 64)

        찾음: list[tuple[str, str]] = []
        for 열곳 in (뿌리, site.list_url):
            try:
                응답 = boards.get(열곳)
            except Exception as exc:  # noqa: BLE001
                print(f"  [!] {열곳} — {type(exc).__name__}: {exc}")
                continue

            for m in re.finditer(
                r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', 응답.text, re.S | re.I
            ):
                글 = re.sub(r"<[^>]+>", " ", m.group(2))
                글 = " ".join(글.split())
                if not 글 or len(글) > 14 or not 관보말.search(글):
                    continue
                h = m.group(1).strip()
                if h.startswith(("javascript", "#", "mailto")):
                    continue
                주소 = urljoin(열곳, h)
                if (글, 주소) not in 찾음:
                    찾음.append((글, 주소))
            if 찾음:
                break

        if not 찾음:
            print("  못 찾았습니다. 홈페이지 메뉴에 안 걸려 있을 수 있습니다.")
        for 글, 주소 in 찾음[:6]:
            print(f"  {글:12} {주소[:84]}")

    print()
    print("끝. 위 내용을 그대로 보여 주세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
