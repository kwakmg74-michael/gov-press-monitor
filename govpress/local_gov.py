"""지자체 보도자료 수집기.

정부부처와 달리 지자체는 통합 창구가 없다. 게시판 소프트웨어가 제각각이라
사이트마다 어댑터가 하나씩 필요하다. 그래서 이 모듈은

- 사이트별 파서 (`parse_seoul`, `parse_standard_board` ...)
- `SITES` : 검증이 끝난 지자체 목록 (여기에 한 줄 추가하면 확장된다)

두 가지로만 이루어져 있다. 받아 오기·TLS·중복 제거 같은 공통 부분은
`boards`에 있다.

새 지자체를 넣을 때는 실제 목록 HTML을 `tests/fixtures/local_*.html`로
저장하고 파서 테스트부터 만든다. 구조를 보지 않고 짐작해서 쓴 파서는
메뉴 링크를 기사로 주워 담는다.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from . import boards
from .boards import Site, tls_note  # noqa: F401  (기존 이름 유지)
from .models import LOCAL, clean_text, normalize_date

CATEGORY = LOCAL
PREFIX = "local"

# 지역 묶음. 대시보드 체크박스가 이 순서로 나뉜다.
REGION_ORDER = ("서울", "경기")
GROUP_ORDER = REGION_ORDER  # boards/대시보드에서 부르는 이름

_row_text = boards.row_text
_keep_params = boards.keep_params


def _site(name, region, list_url, page_param, parser, *, metro=False, **kw) -> Site:
    """지자체용 Site. 분류와 앞머리는 늘 같으므로 여기서 채운다."""
    return Site(
        name=name,
        group=region,
        list_url=list_url,
        page_param=page_param,
        parser=parser,
        category=CATEGORY,
        prefix=PREFIX,
        primary=metro,
        **kw,
    )


# --- 사이트별 파서 -----------------------------------------------------------


_SEOUL_NTT_RE = re.compile(r"fnTbbsView\('(\d+)'\)")
SEOUL_BBS_NO = "158"


def parse_seoul(html: str, site: Site) -> list[dict]:
    """서울시 보도자료.

    구조 (2026-09 확인):
        table.sib-lst-type-basic tbody tr
          td[0] 번호 / td[1] 제목(a) / td[2] 담당부서 / td[3] 등록일

    목록의 링크는 `javascript:fnTbbsView('465874')` 형태라 href를 그대로 쓸 수
    없다. nttNo를 뽑아 실제 상세 주소로 다시 만든다.
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []

    for row in soup.select("table.sib-lst-type-basic tbody tr"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        anchor = cells[1].find("a")
        if not anchor:
            continue

        match = _SEOUL_NTT_RE.search(anchor.get("href", "") or "")
        if not match:
            continue

        ntt_no = match.group(1)
        items.append(
            {
                "uid": ntt_no,
                "title": clean_text(anchor.get_text(" ", strip=True)),
                "link": (
                    "https://www.seoul.go.kr/news/news_report.do"
                    f"?bbsNo={SEOUL_BBS_NO}&nttNo={ntt_no}"
                ),
                "department": clean_text(cells[2].get_text(" ", strip=True)),
                "published_at": normalize_date(cells[3].get_text(strip=True)),
            }
        )

    return items






def _board_permalink(href: str, site: Site) -> str:
    """행정표준 게시판용 링크 정리."""
    return _keep_params(href, site, ("bbsNo", "nttNo", "key"))


def parse_standard_board(html: str, site: Site) -> list[dict]:
    """행정표준 게시판(`selectBbsNttList.do` 계열) 공통 파서.

    많은 시·군·구가 같은 게시판 소프트웨어를 쓴다.

        table tbody tr
          td[0] 번호 / td[1].p-subject 제목(a) / td[2] 주관부서 / td[-1] 작성일

    상세 링크가 `selectBbsNttView.do?...nttNo=...` 형태로 href에 들어 있어
    따로 조립할 필요는 없지만, 페이지 상태값이 잔뜩 붙어 오므로 정리한다.
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()

    for row in soup.select("table tbody tr"):
        anchor = row.select_one('a[href*="NttView.do"], a[href*="nttView.do"]')
        if not anchor:
            continue

        href = anchor.get("href", "") or ""
        uid_match = re.search(r"nttNo=(\d+)", href, flags=re.IGNORECASE)
        if not uid_match:
            continue
        uid = uid_match.group(1)

        title = _row_text(anchor)
        cells = row.find_all("td")

        # 칸 구성이 사이트마다 다르다(송파는 4칸, 구리는 '파일'이 끼어 5칸).
        # 날짜 칸을 먼저 찾고, 그 바로 앞 칸을 담당부서로 본다.
        published = ""
        date_index = -1
        for index in range(len(cells) - 1, -1, -1):
            published = normalize_date(_row_text(cells[index]))
            if published:
                date_index = index
                break

        department = ""
        if date_index > 0:
            candidate = cells[date_index - 1]
            if anchor not in candidate.find_all("a"):
                department = _row_text(candidate)

        if not title or not published or uid in seen:
            continue
        seen.add(uid)

        items.append(
            {
                "uid": uid,
                "title": title,
                "link": _board_permalink(href, site),
                "department": department,
                "published_at": published,
            }
        )

    return items


def parse_card_board(html: str, site: Site) -> list[dict]:
    """카드형 게시판(하남시 계열).

    표가 아니라 카드가 줄지어 있는 형태다.

        .cont_area > a[href*="selectBbsNttView.do"]
            span.post_title  -> 제목
            p                -> 요약
            span.post_data   -> 게시일
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()

    for anchor in soup.select('.cont_area a[href*="NttView.do"]'):
        href = anchor.get("href", "") or ""
        uid_match = re.search(r"nttNo=(\d+)", href, flags=re.IGNORECASE)
        if not uid_match:
            continue
        uid = uid_match.group(1)

        title = _row_text(anchor.select_one(".post_title"))
        published = normalize_date(_row_text(anchor.select_one(".post_data")))
        lead = anchor.find("p")
        summary = clean_text(lead.get_text(" ", strip=True)) if lead else ""

        if not title or not published or uid in seen:
            continue
        seen.add(uid)

        items.append(
            {
                "uid": uid,
                "title": title,
                "link": _board_permalink(href, site),
                "department": summary[:80],
                "published_at": published,
            }
        )

    return items


_SEONGNAM_UID_RE = re.compile(r"fn_move_form\('(\d+)'\)")


def parse_seongnam(html: str, site: Site) -> list[dict]:
    """성남시 새소식.

        table.board-table tbody tr
          td[0] 번호 / td[1].text-left 제목(a) / td[2] 작성부서 / td[3] 등록일

    목록 링크가 `fn_move_form('405200')` 이라 pstSn을 뽑아 조립한다.
    상세 주소는 `/bbs010101/{pstSn}` 형태로 깔끔하다.
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()

    base = site.list_url.split("?")[0].rstrip("/")

    for row in soup.select("table.board-table tbody tr"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        anchor = cells[1].find("a")
        if not anchor:
            continue

        match = _SEONGNAM_UID_RE.search(anchor.get("onclick", "") or "")
        if not match:
            continue
        uid = match.group(1)

        title = _row_text(anchor)
        published = normalize_date(_row_text(cells[3]))
        if not title or not published or uid in seen:
            continue
        seen.add(uid)

        items.append(
            {
                "uid": uid,
                "title": title,
                "link": f"{base}/{uid}",
                "department": _row_text(cells[2]),
                "published_at": published,
            }
        )

    return items


def parse_yongin(html: str, site: Site) -> list[dict]:
    """용인시 시정소식.

        div.t_list table tbody tr
          td[0] 번호 / td[1] 분류 / td[2].td_al 제목(a)
          td[3] 첨부 / td[4] 부서명 / td[5] 등록일 / td[6] 조회수

    상세 링크는 href에 그대로 들어 있고 `q_bbscttSn`이 고유 번호다.
    같은 목록 안에서도 글마다 q_bbsCode가 다르므로 링크를 통째로 정리해 둔다.
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()

    for row in soup.select("div.t_list table tbody tr"):
        anchor = row.select_one('a[href*="BD_selectBbs.do"]')
        if not anchor:
            continue

        href = anchor.get("href", "") or ""
        match = re.search(r"q_bbscttSn=(\w+)", href)
        if not match:
            continue
        uid = match.group(1)

        cells = row.find_all("td")
        title = _row_text(anchor)

        published = ""
        date_index = -1
        for index in range(len(cells) - 1, -1, -1):
            published = normalize_date(_row_text(cells[index]))
            if published:
                date_index = index
                break

        department = _row_text(cells[date_index - 1]) if date_index > 0 else ""

        if not title or not published or uid in seen:
            continue
        seen.add(uid)

        items.append(
            {
                "uid": uid,
                "title": title,
                "link": _keep_params(href, site, ("q_bbsCode", "q_clCode", "q_bbscttSn")),
                "department": department,
                "published_at": published,
            }
        )

    return items


def parse_gyeonggi(html: str, site: Site) -> list[dict]:
    """경기도 뉴스포털 보도자료.

        td.tit a.txtLink[href*="brief_gongbo_view.do"]  -> 제목
        td.dp                                           -> 담당부서
        td.date                                         -> 등록일

    링크에 `;jsessionid=...`가 붙어 오므로 떼어낸다. 세션이 끝나면
    무의미해지는 값이라 그대로 저장하면 나중에 링크가 지저분해진다.
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()

    for row in soup.select("tr"):
        anchor = row.select_one('a[href*="brief_gongbo_view.do"]')
        if not anchor:
            continue

        href = anchor.get("href", "") or ""
        match = re.search(r"number=(\d+)", href)
        if not match:
            continue
        uid = match.group(1)

        title = _row_text(anchor)
        published = normalize_date(_row_text(row.select_one("td.date")))
        department = _row_text(row.select_one("td.dp"))

        if not title or not published or uid in seen:
            continue
        seen.add(uid)

        items.append(
            {
                "uid": uid,
                "title": title,
                "link": _keep_params(href, site, ("BS_CODE", "number")),
                "department": department,
                "published_at": published,
            }
        )

    return items


def parse_gangdong(html: str, site: Site) -> list[dict]:
    """강동구 보도자료.

        div.table01 table tbody tr
          td[0] 번호 / td[1].tx-lt 제목(a) / td[2] 주관부서 / td[3] 등록일

    상세 주소가 `/web/newportal/press/15448`처럼 경로에 글 번호가 들어간다.
    쿼리 파라미터가 없어 링크를 손볼 것도 없다.
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()

    for row in soup.select("div.table01 table tbody tr"):
        anchor = row.select_one('a[href*="/press/"]')
        if not anchor:
            continue

        href = anchor.get("href", "") or ""
        uid = href.rstrip("/").rsplit("/", 1)[-1]
        if not uid.isdigit():
            continue

        cells = row.find_all("td")
        title = _row_text(anchor)

        published = ""
        date_index = -1
        for index in range(len(cells) - 1, -1, -1):
            published = normalize_date(_row_text(cells[index]))
            if published:
                date_index = index
                break

        department = _row_text(cells[date_index - 1]) if date_index > 0 else ""

        if not title or not published or uid in seen:
            continue
        seen.add(uid)

        items.append(
            {
                "uid": uid,
                "title": title,
                "link": urljoin(site.list_url, href),
                "department": department,
                "published_at": published,
            }
        )

    return items


# --- 사이트 목록 -------------------------------------------------------------
#
# 실제 목록 HTML을 확인하고 파서 테스트를 통과한 것만 넣는다.
# 확인 전인 지자체를 미리 넣어 두면, 수집은 도는데 결과가 비거나
# 엉뚱한 링크가 섞여 들어와도 알아채기 어렵다.

SITES: tuple[Site, ...] = (
    _site(
        name="서울시",
        region="서울",
        list_url="https://www.seoul.go.kr/news/news_report.do",
        page_param="curPage",
        parser=parse_seoul,
        metro=True,
    ),
    _site(
        name="강동구",
        region="서울",
        list_url="https://www.gangdong.go.kr/web/newportal/press/list",
        page_param="cp",
        parser=parse_gangdong,
    ),
    _site(
        name="송파구",
        region="서울",
        list_url="https://www.songpa.go.kr/www/selectBbsNttList.do?bbsNo=96&key=2781",
        page_param="pageIndex",
        parser=parse_standard_board,
    ),
    _site(
        name="경기도",
        region="경기",
        list_url="https://gnews.gg.go.kr/briefing/brief_gongbo.do",
        page_param="page",
        parser=parse_gyeonggi,
        metro=True,
    ),
    _site(
        name="구리시",
        region="경기",
        list_url="https://www.guri.go.kr/www/selectBbsNttList.do?bbsNo=42&key=393",
        page_param="pageIndex",
        parser=parse_standard_board,
    ),
    _site(
        name="성남시",
        region="경기",
        list_url="https://www.seongnam.go.kr/bbs010101",
        # 페이지 이동이 POST뿐이라 한 번에 받을 건수를 늘리는 쪽으로 간다.
        page_param="cntPerPage",
        page_mode="size",
        page_size=30,
        parser=parse_seongnam,
    ),
    _site(
        name="용인시",
        region="경기",
        list_url="https://www.yongin.go.kr/user/bbs/BD_selectBbsList.do?q_bbsCode=1001&q_clCode=1",
        page_param="q_currPage",
        parser=parse_yongin,
    ),
    _site(
        name="하남시",
        region="경기",
        list_url="https://www.hanam.go.kr/www/selectBbsNttList.do?bbsNo=1164&key=10221",
        page_param="pageIndex",
        parser=parse_card_board,
    ),
)

# 넣을 예정이지만 아직 목록 구조를 확인하지 못한 곳.
# 확인이 끝나는 대로 SITES로 옮긴다.
#
# 남양주시는 개발자도구 감지 페이지가 떠서 정상 목록을 받을 수 없었다.
PENDING: tuple[str, ...] = ()


def sites_by_region() -> list[tuple[str, list[Site]]]:
    """지역별로 묶고, 지역 안은 광역이 먼저 그다음 가나다순."""
    return boards.sites_by_group(SITES, REGION_ORDER)


def sites_by_group():
    """`sites_by_region`의 다른 이름. 대시보드는 분류마다 이 이름으로 부른다."""
    return sites_by_region()


def region_of(name: str) -> str:
    site = boards.find(SITES, name)
    return site.group if site else ""


def find(name: str) -> Site | None:
    return boards.find(SITES, name)


def boards_of(name: str) -> list[Site]:
    return boards.boards_of(SITES, name)


def agency_names() -> list[str]:
    """수집 대상 지자체 이름. 탭 숫자가 이 개수다."""
    return boards.agency_names(SITES)


def collect(sites=None, pages: int = 3, delay: float = 0.7, on_progress=None,
            known=None):
    """지자체 보도자료를 모은다. 대상을 안 주면 전체."""
    targets = list(sites) if sites else list(SITES)
    return boards.collect(
        targets, pages=pages, delay=delay, on_progress=on_progress, known=known
    )
