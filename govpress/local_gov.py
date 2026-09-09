"""지자체 보도자료 수집기.

정부부처와 달리 지자체는 통합 창구가 없다. 게시판 소프트웨어가 제각각이라
사이트마다 어댑터가 하나씩 필요하다. 그래서 이 모듈은

- `Site`  : 지자체 하나의 목록 URL과 파서를 묶은 것
- `SITES` : 검증이 끝난 지자체 목록 (여기에 한 줄 추가하면 확장된다)

두 가지로만 이루어져 있다. 새 지자체를 넣을 때는 실제 목록 HTML을
`tests/fixtures/local_*.html`로 저장하고 파서 테스트부터 만든다.
구조를 보지 않고 짐작해서 쓴 파서는 메뉴 링크를 기사로 주워 담는다.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .models import LOCAL, Article, clean_text, normalize_date

CATEGORY = LOCAL

# 지역 묶음. 대시보드 체크박스가 이 순서로 나뉜다.
REGION_ORDER = ("서울", "경기")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}


@dataclass(frozen=True)
class Site:
    """지자체 한 곳.

    name       : 대시보드에 뜨는 이름 (예: 서울시)
    region     : 지역 묶음 (서울/경기)
    list_url   : 보도자료 목록 페이지
    page_param : 페이지 번호를 넘기는 쿼리 이름
    parser     : 목록 HTML -> list[dict] (title/uid/link/published_at/department)
    """

    name: str
    region: str
    list_url: str
    page_param: str
    parser: Callable[[str, "Site"], list[dict]] = field(repr=False)
    # "page": 파라미터에 페이지 번호를 넣는다 (대부분)
    # "size": 페이지 이동이 POST뿐이라, 대신 한 번에 몇 건을 받을지 지정한다 (성남시)
    page_mode: str = "page"
    page_size: int = 10

    @property
    def source(self) -> str:
        return f"local:{self.name}"

    @property
    def single_request(self) -> bool:
        """한 번의 요청으로 끝나는가."""
        return self.page_mode == "size"

    def page_url(self, page: int) -> str:
        joiner = "&" if "?" in self.list_url else "?"
        value = page * self.page_size if self.page_mode == "size" else page
        return f"{self.list_url}{joiner}{self.page_param}={value}"


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


def _row_text(cell) -> str:
    """모바일 라벨(.add-head)과 NEW 아이콘을 걷어낸 셀 텍스트.

    이 게시판은 좁은 화면용으로 각 칸 앞에 '번호', '제목' 같은 라벨을
    숨겨 넣어 둔다. 그대로 읽으면 제목이 '제목 실제제목'이 된다.
    """
    if cell is None:
        return ""
    clone = BeautifulSoup(str(cell), "html.parser")
    for junk in clone.select(
        ".add-head, .mobile-tit, .p-icon, .new, .hd-element, .bbsNewImage, img"
    ):
        junk.decompose()
    return clean_text(clone.get_text(" ", strip=True))


def _keep_params(href: str, site: Site, names: tuple[str, ...]) -> str:
    """상세 링크에서 필요한 파라미터만 남긴다.

    목록에서 딴 링크에는 페이지 번호, 검색 조건, 세션 아이디 같은
    "지금 이 순간"의 상태가 잔뜩 붙어 온다. 그대로 저장하면 나중에
    열었을 때 지저분하고, 세션 아이디는 아예 의미가 없어진다.
    """
    absolute = urljoin(site.list_url, href)
    base, _, query = absolute.partition("?")
    base = base.split(";")[0]  # ;jsessionid=... 제거

    keep = {}
    for chunk in query.split("&"):
        name, _, value = chunk.partition("=")
        if name in names and value:
            keep[name] = value
    if not keep:
        return absolute
    return base + "?" + "&".join(f"{k}={v}" for k, v in keep.items())


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
    Site(
        name="서울시",
        region="서울",
        list_url="https://www.seoul.go.kr/news/news_report.do",
        page_param="curPage",
        parser=parse_seoul,
    ),
    Site(
        name="강동구",
        region="서울",
        list_url="https://www.gangdong.go.kr/web/newportal/press/list",
        page_param="cp",
        parser=parse_gangdong,
    ),
    Site(
        name="송파구",
        region="서울",
        list_url="https://www.songpa.go.kr/www/selectBbsNttList.do?bbsNo=96&key=2781",
        page_param="pageIndex",
        parser=parse_standard_board,
    ),
    Site(
        name="경기도",
        region="경기",
        list_url="https://gnews.gg.go.kr/briefing/brief_gongbo.do",
        page_param="page",
        parser=parse_gyeonggi,
    ),
    Site(
        name="구리시",
        region="경기",
        list_url="https://www.guri.go.kr/www/selectBbsNttList.do?bbsNo=42&key=393",
        page_param="pageIndex",
        parser=parse_standard_board,
    ),
    Site(
        name="성남시",
        region="경기",
        list_url="https://www.seongnam.go.kr/bbs010101",
        # 페이지 이동이 POST뿐이라 한 번에 받을 건수를 늘리는 쪽으로 간다.
        page_param="cntPerPage",
        page_mode="size",
        page_size=30,
        parser=parse_seongnam,
    ),
    Site(
        name="용인시",
        region="경기",
        list_url="https://www.yongin.go.kr/user/bbs/BD_selectBbsList.do?q_bbsCode=1001&q_clCode=1",
        page_param="q_currPage",
        parser=parse_yongin,
    ),
    Site(
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
    """지역별로 묶고, 지역 안은 가나다순."""
    buckets: dict[str, list[Site]] = {}
    for site in SITES:
        buckets.setdefault(site.region, []).append(site)
    return [
        (region, sorted(buckets[region], key=lambda s: s.name))
        for region in REGION_ORDER
        if region in buckets
    ]


def region_of(name: str) -> str:
    for site in SITES:
        if site.name == name:
            return site.region
    return ""


def find(name: str) -> Site | None:
    for site in SITES:
        if site.name == name:
            return site
    return None


# --- 수집 -------------------------------------------------------------------


def to_articles(items: list[dict], site: Site) -> list[Article]:
    return [
        Article(
            category=CATEGORY,
            source=site.source,
            uid=str(item["uid"]),
            agency=site.name,
            title=item["title"],
            link=item["link"],
            published_at=item["published_at"],
            summary=item.get("department", ""),
        )
        for item in items
    ]


def fetch_page(site: Site, page: int, session=None, timeout: int = 25) -> list[Article]:
    client = session or requests
    response = client.get(site.page_url(page), headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return to_articles(site.parser(response.text, site), site)


def collect(
    sites=None,
    pages: int = 3,
    delay: float = 0.7,
    on_progress=None,
) -> list[Article]:
    """지자체 보도자료를 모은다.

    지자체 게시판은 기간 검색 파라미터가 제각각이라 서버에서 거르지 않고,
    최근 `pages`페이지를 받아 온 뒤 대시보드에서 기간으로 좁힌다.
    """
    targets = list(sites) if sites else list(SITES)
    collected: dict[tuple[str, str], Article] = {}
    session = requests.Session()

    for site in targets:
        # "size" 방식은 한 번의 요청에 원하는 만큼 담아 오므로 반복하지 않는다.
        # 그대로 두면 30건 → 60건 → 90건을 겹쳐 받아 같은 글을 계속 다시 읽는다.
        last_page = 1 if site.single_request else pages
        for page in range(1, last_page + 1):
            request_page = pages if site.single_request else page
            try:
                items = fetch_page(site, request_page, session=session)
            except Exception as exc:
                if on_progress:
                    on_progress(site.name, page, 0, f"실패: {exc}")
                break

            fresh = [a for a in items if (a.source, a.uid) not in collected]
            for article in fresh:
                collected[(article.source, article.uid)] = article

            if on_progress:
                on_progress(site.name, page, len(fresh), None)

            if not items or not fresh:
                break

            time.sleep(delay)

    return sorted(
        collected.values(),
        key=lambda a: (a.published_at, a.uid),
        reverse=True,
    )
