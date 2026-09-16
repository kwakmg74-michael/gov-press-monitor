"""받아 둔 목록 HTML의 뼈대를 훑어본다. 파서를 쓰기 전 눈으로 보는 용도."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

RAW = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "raw"
DATE = re.compile(r"20\d\d[.\-/]\s?\d{1,2}[.\-/]\s?\d{1,2}")


def sig(el) -> str:
    name = el.name
    cls = ".".join(el.get("class") or [])
    eid = el.get("id") or ""
    out = name
    if eid:
        out += f"#{eid}"
    if cls:
        out += f".{cls}"
    return out


def path_of(el, depth=4) -> str:
    parts = []
    node = el
    for _ in range(depth):
        if node is None or node.name in ("[document]", "html"):
            break
        parts.append(sig(node))
        node = node.parent
    return " < ".join(parts)


def main(names):
    for name in names:
        html = (RAW / f"{name}.html").read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()

        print(f"\n{'='*70}\n{name}\n{'='*70}")

        # 날짜가 들어 있는 가장 작은 덩어리들을 모은다
        holders = {}
        for node in soup.find_all(string=DATE):
            parent = node.parent
            # 날짜를 품은 조상 중 링크를 함께 가진 첫 덩어리
            up = parent
            for _ in range(6):
                if up is None:
                    break
                if up.find("a"):
                    break
                up = up.parent
            if up is None:
                continue
            key = path_of(up, 3)
            holders.setdefault(key, []).append(up)

        for key, nodes in sorted(holders.items(), key=lambda kv: -len(kv[1]))[:4]:
            print(f"\n--- {len(nodes)}개  {key}")
            node = nodes[0]
            print("    " + node.get_text(" | ", strip=True)[:260])
            for a in node.find_all("a")[:4]:
                print(
                    f"    a href={a.get('href')!r:80.80} "
                    f"onclick={(a.get('onclick') or '')!r:50.50} "
                    f"text={a.get_text(' ', strip=True)[:50]!r}"
                )


if __name__ == "__main__":
    main(sys.argv[1:])
