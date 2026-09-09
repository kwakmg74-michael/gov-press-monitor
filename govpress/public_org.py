"""공공기관 보도자료 수집기.

지자체와 사정이 같다 — 전국 단위 통합 창구가 없어 기관마다 어댑터가
하나씩 필요하다. (ALIO는 경영정보 공시라 보도자료가 아니다.)

다만 지자체보다는 고르다. 상당수가 정부 표준 CMS를 써서, 페이지 넘김
파라미터가 `pageIndex` 계열로 몰린다.

공통 부분(받아 오기·TLS·중복 제거)은 `boards`에 있고, 여기에는
사이트별 파서와 `SITES`만 둔다.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from . import boards
from .boards import Site
from .models import PUBLIC, clean_text

CATEGORY = PUBLIC
PREFIX = "public"

# 분야 묶음. 대시보드 체크박스가 이 순서로 나뉜다.
GROUP_ORDER = ("부동산", "금융", "기타")


def _site(name, group, list_url, page_param, parser, **kw) -> Site:
    return Site(
        name=name,
        group=group,
        list_url=list_url,
        page_param=page_param,
        parser=parser,
        category=CATEGORY,
        prefix=PREFIX,
        **kw,
    )


def _re_uid(pattern: re.Pattern):
    """href나 onclick에서 정규식으로 글 번호를 뽑는 함수를 만든다."""

    def pick(anchor) -> str:
        return boards.script_uid(anchor, pattern)

    return pick


def _query(site: Site) -> dict[str, str]:
    """목록 주소에 붙은 파라미터. 상세 주소를 조립할 때 쓴다."""
    raw = parse_qs(urlparse(site.list_url).query)
    return {key: values[0] for key, values in raw.items() if values}


def _rows(
    html: str,
    site: Site,
    anchor_selector: str,
    uid_of,
    link_of,
    *,
    has_department: bool = False,
) -> list[dict]:
    """표 게시판 공통 처리.

    칸 구성이 사이트마다 달라서 자리를 고정하지 않는다. 날짜처럼 보이는
    칸을 뒤에서부터 찾고, 담당부서가 있는 게시판만 그 앞 칸을 읽는다.
    담당부서 칸이 없는 곳에서 앞 칸을 읽으면 제목이 부서로 들어간다.
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []

    for row in soup.select("table tbody tr"):
        anchor = row.select_one(anchor_selector)
        if not anchor:
            continue

        uid = uid_of(anchor)
        if not uid:
            continue

        cells = row.find_all("td")
        published, date_index = boards.find_date_cell(cells)
        if not published:
            continue

        department = ""
        if has_department and date_index > 0:
            department = boards.row_text(cells[date_index - 1])

        items.append(
            {
                "uid": uid,
                "title": boards.row_text(anchor),
                "link": link_of(anchor, uid),
                "department": department,
                "published_at": published,
            }
        )

    return items


# --- 금융감독원 --------------------------------------------------------------

_NTT_ID_RE = re.compile(r"nttId=(\d+)")


def parse_fss(html: str, site: Site) -> list[dict]:
    """금융감독원 보도자료.

    구조 (2026-09 확인):
        table.list-data tbody tr
          번호 / 제목(a) / 담당부서 / 등록일 / 첨부 / (빈) / 조회수

    상세 링크가 href에 그대로 있다. 다만 `pageIndex`가 붙어 오므로
    떼어 낸다 — 지금 몇 페이지를 보고 있었는지는 글의 주소가 아니다.
    """
    return _rows(
        html,
        site,
        'a[href*="view.do"]',
        _re_uid(_NTT_ID_RE),
        lambda a, uid: boards.keep_params(a.get("href", ""), site, ("nttId", "menuNo")),
        has_department=True,
    )


# --- 식품안전정보원 ----------------------------------------------------------

_FOODINFO_RE = re.compile(r"main\(\s*'V'\s*,\s*'(\d+)'")


def parse_foodinfo(html: str, site: Site) -> list[dict]:
    """식품안전정보원 보도자료.

    구조 (2026-09 확인):
        번호 / 제목(a) / 첨부 / 등록일 / 조회수 — 담당부서 칸이 없다.

    제목 링크가 `main('V', '415050', '<게시판ID>')`이라 href가 비어 있다.
    상세는 POST로 열리지만, 같은 파라미터를 주소에 실어 GET으로 요청해도
    서버가 받아 준다. 목록 주소에 이미 게시판·메뉴 번호가 다 붙어 있으므로
    그걸 그대로 물려주고 글 번호만 더한다.
    """
    query = _query(site)
    base = site.list_url.split("?")[0].replace("selectBoardList.do", "detailBBSArticle.do")

    def link(_anchor, uid: str) -> str:
        params = {**query, "nttId": uid}
        return base + "?" + "&".join(f"{k}={v}" for k, v in params.items())

    return _rows(
        html,
        site,
        'a[onclick*="main("]',
        _re_uid(_FOODINFO_RE),
        link,
    )


# --- 한국부동산원 ------------------------------------------------------------


def parse_reb(html: str, site: Site) -> list[dict]:
    """한국부동산원 보도자료.

    구조 (2026-09 확인):
        번호 / 제목(a.nttInfoBtn) / 등록일 / 조회수 / 첨부 — 담당부서 없음.

    제목 링크가 `href="javascript:"`이고 글 번호는 `data-id`에 들어 있다.
    상세는 `selectNttInfo.do?mi=..&bbsId=..&nttSn=..`로 열린다.
    """
    query = _query(site)
    base = site.list_url.split("?")[0].replace("selectNttList.do", "selectNttInfo.do")

    def link(_anchor, uid: str) -> str:
        params = {**query, "nttSn": uid}
        return base + "?" + "&".join(f"{k}={v}" for k, v in params.items())

    return _rows(
        html,
        site,
        "a.nttInfoBtn[data-id]",
        lambda a: clean_text(a.get("data-id", "")),
        link,
    )


# --- 한국산업단지공단 --------------------------------------------------------

_KICOX_RE = re.compile(r"bbsArticleDet\('(\d+)'\)")


def parse_kicox(html: str, site: Site) -> list[dict]:
    """한국산업단지공단 보도자료.

    구조 (2026-09 확인):
        번호 / 제목(a) / 등록일 / 첨부 / 조회수 — 담당부서 없음.

    제목 링크가 `bbsArticleDet('49636')`이고, 상세는 목록 주소의 게시판
    번호를 그대로 쓴 `/boardDetail/1103?bbsSeq=49636`이다.
    """
    board_id = urlparse(site.list_url).path.rstrip("/").split("/")[-1]

    return _rows(
        html,
        site,
        'a[onclick*="bbsArticleDet"]',
        _re_uid(_KICOX_RE),
        lambda a, uid: urljoin(site.list_url, f"/boardDetail/{board_id}?bbsSeq={uid}"),
    )


# --- 한국소비자원 ------------------------------------------------------------

_KCA_NO_RE = re.compile(r"[?&]no=(\d+)")


def parse_kca(html: str, site: Site) -> list[dict]:
    """한국소비자원 보도자료.

    구조 (2026-09 확인):
        번호 / 제목(a) / 담당부서(td.b_write) / 등록일 / 조회수

    상세 링크가 `?menukey=4002&mode=view&no=...` 형태의 쿼리만 있는
    상대 주소다. 목록 주소에 이어 붙이면 그대로 열린다.
    """
    return _rows(
        html,
        site,
        'a[href*="mode=view"]',
        _re_uid(_KCA_NO_RE),
        lambda a, uid: urljoin(site.list_url, a.get("href", "")),
        has_department=True,
    )


# --- 서울주택도시개발공사 ----------------------------------------------------

_SH_RE = re.compile(r"getDetailView\('(\d+)'\)")


def parse_sh(html: str, site: Site) -> list[dict]:
    """서울주택도시개발공사(SH) 보도자료.

    구조 (2026-09 확인):
        번호 / 제목(a) / 부서명 / 등록일 / 조회수

    제목 링크가 `getDetailView('310068')`이고, 원래는 숨은 양식을 POST로
    보낸다. 그래도 같은 경로의 `view.do?seq=...`를 GET으로 요청하면 열린다.

    이 기관은 게시판이 둘(보도자료·해명자료)이라 `Site`도 둘이다.
    화면에는 기관 이름 하나로 나오고 결과는 합쳐진다.
    """
    base = site.list_url.rsplit("/", 1)[0]

    return _rows(
        html,
        site,
        'a[onclick*="getDetailView"]',
        _re_uid(_SH_RE),
        lambda a, uid: f"{base}/view.do?seq={uid}",
        has_department=True,
    )


# --- 사이트 목록 -------------------------------------------------------------
#
# 실제 목록 HTML을 확인하고 파서 테스트를 통과한 것만 넣는다.

SITES: tuple[Site, ...] = (
    _site(
        "한국부동산원",
        "부동산",
        "https://www.reb.or.kr/reb/na/ntt/selectNttList.do?mi=9565&bbsId=1154",
        "currPage",
        parse_reb,
    ),
    _site(
        "한국산업단지공단",
        "부동산",
        "https://www.kicox.or.kr/boardList/1103",
        "pageIndex",
        parse_kicox,
    ),
    _site(
        "서울주택도시개발공사",
        "부동산",
        "https://www.i-sh.co.kr/main/lay2/program/S1T532C1422/www/brd/m_139/list.do",
        "page",
        parse_sh,
        board="보도자료",
    ),
    _site(
        "서울주택도시개발공사",
        "부동산",
        "https://www.i-sh.co.kr/main/lay2/program/S1T532C1109/www/brd/m_612/list.do",
        "page",
        parse_sh,
        board="해명자료",
    ),
    _site(
        "금융감독원",
        "금융",
        "https://www.fss.or.kr/fss/bbs/B0000188/list.do?menuNo=200218",
        "pageIndex",
        parse_fss,
    ),
    _site(
        "식품안전정보원",
        "기타",
        "https://www.foodinfo.or.kr/portal/bbs/selectBoardList.do"
        "?bbsId=10000000000000000500&goMenuNo=9000001102"
        "&topMenuNo=9000001080&upperMenuNo=9000001101",
        "pageIndex",
        parse_foodinfo,
    ),
    _site(
        "한국소비자원",
        "기타",
        "https://www.kca.go.kr/home/sub.do?menukey=4002",
        "page",
        parse_kca,
    ),
)

# 목록에는 있지만 아직 게시판 구조를 확인하지 못한 곳.
PENDING: tuple[str, ...] = (
    "한국인터넷진흥원",
    "한국자산관리공사",
    "한국저작권보호원",
    "한국저작권위원회",
    "한국주택금융공사",
    "한국지식재산보호원",
    "한국토지주택공사",
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
