"""연구소 자료 수집기.

여기는 다른 분류와 성격이 조금 다르다. 연구기관이 내놓는 것은 보도자료보다
**발간물(연구보고서)** 쪽이 많아서, 목록도 게시판이 아니라 카드형인 곳이
있다. 그래도 우리가 뽑는 것은 같다 — 제목·날짜·원문 링크.

공통 부분(받아 오기·TLS·중복 제거)은 `boards`에 있고, 여기에는
사이트별 파서와 `SITES`만 둔다.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from . import boards
from .boards import Site
from .models import RESEARCH, normalize_date

CATEGORY = RESEARCH
PREFIX = "research"

# 분야 묶음. 대시보드 체크박스가 이 순서로 나뉜다.
GROUP_ORDER = ("부동산", "금융", "기타")


def _site(name, group, list_url, page_param, parser, **kw) -> Site:
    return Site(
        name=name,
        group=group or "기타",
        list_url=list_url,
        page_param=page_param,
        parser=parser,
        category=CATEGORY,
        prefix=PREFIX,
        **kw,
    )


# --- 국토연구원 --------------------------------------------------------------

_LIST_NO_RE = re.compile(r"list_no=(\d+)")


def parse_es_board(html: str, site: Site) -> list[dict]:
    """정부·연구기관 표준 게시판(`board.es` 계열).

    구조 (2026-09 확인, 국토연구원):
        table.tstyle_list tbody tr
          번호 / 분류 / 제목(a) / 작성자 / 등록일 / 조회수 / 첨부

    상세 링크가 href에 그대로 있다. 다만 `nPage`, `tag` 같은 페이지 상태가
    붙어 오므로 떼어 낸다. 제목 앞에는 화면에 안 보이는 '새글' 라벨이
    숨어 있어서, 그대로 읽으면 제목이 '새글 실제제목'이 된다.
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []

    for row in soup.select("table tbody tr"):
        anchor = row.select_one('a[href*="act=view"]')
        if not anchor:
            continue

        uid = boards.script_uid(anchor, _LIST_NO_RE)
        if not uid:
            continue

        cells = row.find_all("td")
        published, date_index = boards.find_date_cell(cells)
        if not published:
            continue

        items.append(
            {
                "uid": uid,
                "title": boards.row_text(anchor),
                "link": boards.keep_params(
                    anchor.get("href", ""), site, ("mid", "bid", "act", "list_no")
                ),
                "department": (
                    boards.row_text(cells[date_index - 1]) if date_index > 0 else ""
                ),
                "published_at": published,
            }
        )

    return items


# --- 건축공간연구원 ----------------------------------------------------------

_PUBLICATION_ID_RE = re.compile(r"publication_id=(\d+)")


def parse_publication_cards(html: str, site: Site) -> list[dict]:
    """발간물 카드 목록(`publication/list.es` 계열).

    구조 (2026-09 확인, 건축공간연구원):
        li
          a[href*=publication_id] > strong.title  제목
          span.category  보고서 종류
          span.date      발행일 (2026.06.30)
          span.writer    연구책임자

    표가 아니라 카드가 줄지어 있고, 카드 안에 연관 키워드 링크가 여럿
    들어 있다. 그래서 "카드 안의 첫 링크"가 아니라 **제목(strong.title)을
    가진 링크**를 기준으로 잡는다. 키워드 링크를 제목으로 주워 담으면
    목록이 해시태그로 채워진다.
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []

    for card in soup.select("li"):
        title_el = card.select_one("strong.title")
        if not title_el:
            continue

        anchor = title_el.find_parent("a")
        if not anchor:
            continue

        uid = boards.script_uid(anchor, _PUBLICATION_ID_RE)
        if not uid:
            continue

        published = normalize_date(boards.row_text(card.select_one("span.date")))
        if not published:
            continue

        items.append(
            {
                "uid": uid,
                "title": boards.row_text(title_el),
                "link": boards.keep_params(
                    anchor.get("href", ""),
                    site,
                    ("mid", "publication_id", "publication_type"),
                ),
                "department": boards.row_text(card.select_one("span.writer")),
                "published_at": published,
            }
        )

    return items


# --- KB경영연구소 ------------------------------------------------------------

_KB_ID_RE = re.compile(r"(?:reportId|vitaminId)=(\d+)")


def parse_kb_cards(html: str, site: Site) -> list[dict]:
    """KB경영연구소 발간물 목록.

    구조 (2026-09 확인):
        li > a[href*=View.do]
             span.kate  분류      h3  제목
             dl > dt  저자   dd  발행일   dd.hits  조회수

    날짜 칸을 자리로 세지 않고 `dd` 중 조회수(.hits)가 아닌 것을 고른다.
    글 번호는 게시판에 따라 `reportId` 또는 `vitaminId`로 이름이 다르다.
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []

    for card in soup.select("li"):
        title_el = card.select_one("h3")
        anchor = card.select_one('a[href*="View.do"]')
        if not (title_el and anchor):
            continue

        uid = boards.script_uid(anchor, _KB_ID_RE)
        if not uid:
            continue

        published = ""
        for dd in card.select("dl dd"):
            if "hits" in (dd.get("class") or []):
                continue
            published = normalize_date(boards.row_text(dd))
            if published:
                break
        if not published:
            continue

        items.append(
            {
                "uid": uid,
                "title": boards.row_text(title_el),
                "link": urljoin(site.list_url, anchor.get("href", "")),
                "department": boards.row_text(card.select_one("dl dt")),
                "published_at": published,
            }
        )

    return items


# --- 한국법제연구원 ----------------------------------------------------------

_KLRI_RE = re.compile(r"publication_view\('(\d+)'\)")


def parse_klri_cards(html: str, site: Site) -> list[dict]:
    """한국법제연구원 발간물 목록.

    구조 (2026-09 확인):
        li
          p.title > a[onclick=publication_view('2384')] > strong  제목
          div.date > p[0] 발행일 / p[1] 연구진 / p[2] 쪽수

    두 가지를 조심해야 한다.

    - 각 칸 앞에 `<em class="hidden">발행일:</em>` 같은 라벨이 숨어 있다.
      그대로 읽으면 날짜가 "발행일:2026-07-01"이 된다.
    - 제목을 감싼 `<a>`에도 `class="new"`가 붙어 있다. 링크째로 읽으면
      군더더기 제거 규칙(`.new`)에 걸려 제목이 통째로 사라지므로,
      **안쪽 `strong`만** 읽는다.

    상세는 `/kor/publication/<번호>/view.do` 로 열린다.
    """
    soup = BeautifulSoup(html, "html.parser")
    base = site.list_url.rsplit("/", 1)[0]
    items: list[dict] = []

    for card in soup.select("li"):
        anchor = card.select_one('a[onclick*="publication_view"]')
        title_el = anchor.select_one("strong") if anchor else None
        if not (anchor and title_el):
            continue

        uid = boards.script_uid(anchor, _KLRI_RE)
        if not uid:
            continue

        dates = card.select("div.date p")
        published = normalize_date(boards.row_text(dates[0])) if dates else ""
        if not published:
            continue

        items.append(
            {
                "uid": uid,
                "title": boards.row_text(title_el),
                "link": f"{base}/{uid}/view.do",
                "department": boards.row_text(dates[1]) if len(dates) > 1 else "",
                "published_at": published,
            }
        )

    return items


# --- 사이트 목록 -------------------------------------------------------------
#
# 실제 목록 HTML을 확인하고 파서 테스트를 통과한 것만 넣는다.

SITES: tuple[Site, ...] = (
    _site(
        "KB경영연구소",
        "금융",
        "https://www.kbfg.com/kbresearch/report/reportList.do",
        "pageIndex",
        parse_kb_cards,
        board="연구보고서",
    ),
    _site(
        "KB경영연구소",
        "금융",
        "https://www.kbfg.com/kbresearch/brand/brandList.do",
        "pageIndex",
        parse_kb_cards,
        board="브랜드보고서",
    ),
    _site(
        "한국법제연구원",
        "기타",
        "https://www.klri.re.kr/kor/publication/list.do",
        "pageIndex",
        parse_klri_cards,
    ),
    _site(
        "국토연구원",
        "부동산",
        "https://www.krihs.re.kr/board.es?mid=a10607000000&bid=0008",
        "nPage",
        parse_es_board,
    ),
    _site(
        "건축공간연구원",
        "기타",
        "https://www.auri.re.kr/publication/list.es"
        "?mid=a10312000000&publication_type=research",
        "nPage",
        parse_publication_cards,
    ),
)

# 목록에는 있지만 아직 게시판 구조를 확인하지 못한 곳.
PENDING: tuple[str, ...] = (
    "한국조세재정연구원",
    "한국행정연구원",
    "한국개발연구원",
    "한국지식재산연구원",
)


def sites_by_group():
    return boards.sites_by_group(SITES, GROUP_ORDER)


def agency_names() -> list[str]:
    return boards.agency_names(SITES)


def find(name: str) -> Site | None:
    return boards.find(SITES, name)


def boards_of(name: str) -> list[Site]:
    return boards.boards_of(SITES, name)


def collect(sites=None, pages: int = 3, delay: float = 0.7, on_progress=None):
    targets = list(sites) if sites else list(SITES)
    return boards.collect(targets, pages=pages, delay=delay, on_progress=on_progress)
