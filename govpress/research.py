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


# --- 한국조세재정연구원 ------------------------------------------------------

_KIPF_RE = re.compile(r"fn_search_detail\('(\d+)'\)")


def parse_kipf_cards(html: str, site: Site) -> list[dict]:
    """한국조세재정연구원 연구발간자료.

    구조 (2026-09 확인):
        a.link[onclick=fn_search_detail('527650')]
          strong.tit  제목
          ul.list_ul > li  '저자 박주철' / '발간월 2026-09'

    여기는 **발간월까지만** 적는다(2026-09). 날짜가 없으면 대시보드가
    그 글을 걸러 내므로, 그 달의 1일로 본다. 목록이 발간 순서대로
    내려오니 같은 달 안의 앞뒤는 어차피 목록 순서가 말해 준다.

    상세는 원래 숨은 양식을 POST로 보내지만, 같은 주소에 `serialNo`를
    실어 GET으로 요청해도 열린다.
    """
    soup = BeautifulSoup(html, "html.parser")
    base = site.list_url.rsplit("/", 1)[0]
    items: list[dict] = []

    for anchor in soup.select('a[onclick*="fn_search_detail"]'):
        title_el = anchor.select_one("strong.tit")
        uid = boards.script_uid(anchor, _KIPF_RE)
        if not (title_el and uid):
            continue

        published, author = "", ""
        for row in anchor.select("ul.list_ul li"):
            label = boards.row_text(row.select_one("strong"))
            value = boards.row_text(row.select_one("span"))
            if label == "발간월":
                published = normalize_date(f"{value}-01")
            elif label == "저자":
                author = value
        if not published:
            continue

        items.append(
            {
                "uid": uid,
                "title": boards.row_text(title_el),
                "link": f"{base}/view.do?serialNo={uid}",
                "department": author,
                "published_at": published,
            }
        )

    return items


# --- 한국개발연구원(KDI) -----------------------------------------------------

_KDI_PUB_RE = re.compile(r"pub_no=(\d+)")
_KDI_PREVIEW_RE = re.compile(r"preView\?pub_no=(\d+)")


def parse_kdi_list(html: str, site: Site) -> list[dict]:
    """KDI 발간물 목록(연구보고서·KDI FOCUS·기타보고서).

    구조 (2026-09 확인):
        li
          a[href*=View?pub_no=]
            div.rpt_tit > b(종류) + strong(제목)
          div.rpt_other > p > span(저자) span(쪽수)

    **목록에 발간일이 없다.** 제목·저자·쪽수만 적혀 있다. 날짜가 없으면
    저장 단계에서 버려지므로, 여기서는 날짜를 비워 두고 `detail_date`가
    새 글만 하나씩 열어 채우게 한다(`boards.fill_missing_dates`).
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []

    for card in soup.select("li"):
        anchor = card.select_one('a[href*="pub_no="]')
        title_el = card.select_one("div.rpt_tit strong")
        if not (anchor and title_el):
            continue

        uid = boards.script_uid(anchor, _KDI_PUB_RE)
        if not uid:
            continue

        author = card.select_one("div.rpt_other p span")
        items.append(
            {
                "uid": uid,
                "title": boards.row_text(title_el),
                "link": urljoin(site.list_url, anchor.get("href", "")),
                "department": boards.row_text(author),
                "published_at": "",  # 상세에서 채운다
            }
        )

    return items


# 상세 화면이 게시판마다 다르다. 발간일이 있는 자리를 순서대로 짚어 본다.
_KDI_DATE_SELECTORS = (
    "div.tit_top p",                  # 연구보고서·기타보고서
    "div.top_bg-wrap strong.title span",  # KDI FOCUS
)


def kdi_detail_date(html: str) -> str:
    """KDI 상세에서 발간일을 읽는다.

    같은 기관인데도 화면 틀이 둘이다. 연구보고서는 `div.tit_top`,
    KDI FOCUS는 `div.top_bg-wrap`에 제목과 발간일이 들어 있다.

    자리를 하나만 보면 FOCUS 쪽은 날짜를 못 찾아 **열 건이 통째로
    버려진다** — 실제로 그렇게 0건이 나왔다. 그래서 둘 다 짚어 본다.
    화면 아래쪽 '추천 발간물'에도 날짜가 많아서, 아무 날짜나 줍지 않고
    제목 옆자리만 본다.
    """
    soup = BeautifulSoup(html, "html.parser")
    for selector in _KDI_DATE_SELECTORS:
        published = normalize_date(boards.row_text(soup.select_one(selector)))
        if published:
            return published
    return ""


def parse_kdi_issue(html: str, site: Site) -> list[dict]:
    """KDI 정기간행물(경제전망·경제동향·나라경제).

    이쪽은 목록이 아니라 **최신호 한 권을 바로 펼쳐 보여 주는 화면**이다.
    연도·월을 골라야 지난 호로 갈 수 있으니 페이지를 넘길 것도 없다.
    그래서 한 번 받아 그 호 하나만 집어낸다.

    구조가 두 갈래다 (2026-09 확인):
        div.post-top > div.tit (제목) + div.tit-info > div.date (발간일)
        div.page_top-wrap > h2 (제목) > p (발간일)       ← 경제전망

    호마다 발간일이 다르므로 발간일을 글 번호로 쓴다. 같은 호를 두 번
    저장하는 일이 없고, 새 호가 나오면 새 글로 들어온다.
    """
    soup = BeautifulSoup(html, "html.parser")

    top = soup.select_one("div.post-top")
    if top:
        title = boards.row_text(top.select_one("div.tit"))
        published = normalize_date(boards.row_text(top.select_one("div.tit-info .date")))
    else:
        heading = soup.select_one(".page_top-wrap h2")
        if not heading:
            return []
        date_el = heading.select_one("p")
        published = normalize_date(boards.row_text(date_el))
        if date_el:
            date_el.decompose()
        title = boards.row_text(heading)

    if not (title and published):
        return []

    # '원문 미리보기' 버튼에 이 호의 번호가 들어 있다. 아래쪽 추천 목록에도
    # pub_no가 잔뜩 있으므로, 미리보기 주소만 골라 본다.
    preview = _KDI_PREVIEW_RE.search(html)
    link = f"{site.list_url}?pub_no={preview.group(1)}" if preview else site.list_url

    return [
        {
            "uid": published.replace("-", ""),
            "title": title,
            "link": link,
            "department": "",
            "published_at": published,
        }
    ]


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
    _site(
        "한국조세재정연구원",
        "금융",
        "https://www.kipf.re.kr/kor/Publication/All/kiPublish/ALL/list.do",
        "pageIndex",
        parse_kipf_cards,
    ),
    _site(
        "한국개발연구원",
        "금융",
        "https://www.kdi.re.kr/research/reportList",
        "pg",
        parse_kdi_list,
        board="연구보고서",
        detail_date=kdi_detail_date,
    ),
    _site(
        "한국개발연구원",
        "금융",
        "https://www.kdi.re.kr/research/focusList",
        "pg",
        parse_kdi_list,
        board="KDI FOCUS",
        detail_date=kdi_detail_date,
    ),
    _site(
        "한국개발연구원",
        "금융",
        "https://www.kdi.re.kr/research/etcReportList",
        "pg",
        parse_kdi_list,
        board="기타보고서",
        detail_date=kdi_detail_date,
    ),
    _site(
        "한국개발연구원",
        "금융",
        "https://www.kdi.re.kr/research/economy",
        "pg",
        parse_kdi_issue,
        board="경제전망",
        page_mode="single",
    ),
    _site(
        "한국개발연구원",
        "금융",
        "https://www.kdi.re.kr/research/monTrends",
        "pg",
        parse_kdi_issue,
        board="경제동향",
        page_mode="single",
    ),
    _site(
        "한국개발연구원",
        "금융",
        "https://www.kdi.re.kr/research/monCountry",
        "pg",
        parse_kdi_issue,
        board="나라경제",
        page_mode="single",
    ),
)

# 목록에는 있지만 아직 게시판 구조를 확인하지 못한 곳.
PENDING: tuple[str, ...] = ("한국행정연구원",)


# --- 바로가기 ----------------------------------------------------------------
#
# 화면에서는 연구소를 **긁어 오지 않고 바로가기로만** 보여 준다.
#
# 이유는 셋이다.
#
# - 양이 적다. 여섯 곳을 합쳐 한 달 22건, 하루 0.7건이다. 정부기관이
#   한 달 357건인 것과 견주면 매일 들여다볼 칸이 아니다. 두 달 넘게
#   새 글이 없는 곳도 있다.
# - 품이 제일 많이 든다. 발간일을 목록에 안 적는 곳(KDI)은 글을 하나씩
#   열어 봐야 했고, 어떤 곳(한국행정연구원)은 끝내 못 붙였다.
# - 성격이 다르다. 보도자료는 놓치면 안 되는 소식이지만 연구보고서는
#   필요할 때 찾아보는 자료다. 쌓아 두는 값어치가 크지 않다.
#
# 위의 수집기(`SITES`)는 지우지 않고 남겨 둔다. 돌리면 그대로 동작하고,
# 생각이 바뀌면 화면만 되돌리면 된다.
#
# 긁지 않으니 파서가 필요 없다 — 그래서 끝내 못 붙였던 한국행정연구원도
# 여기서는 그냥 한 줄이다.

# 바로가기 묶음 순서. 위의 GROUP_ORDER(수집기용)와는 별개다.
LINK_GROUP_ORDER = ("연구소", "증권사", "업계", "협회")

LINKS: tuple[dict[str, str], ...] = (
    # --- 연구소 : 국책 ---
    {"name": "국토연구원", "group": "연구소",
     "note": "국토·주택·도시 정책 연구. 부동산 시장 진단이 자주 나온다",
     "url": "https://www.krihs.re.kr"},
    {"name": "한국개발연구원(KDI)", "group": "연구소",
     "note": "거시경제 전망과 정책 연구. 경제동향은 매월 나온다",
     "url": "https://www.kdi.re.kr"},
    {"name": "건축공간연구원", "group": "연구소",
     "note": "건축·도시공간 제도 연구",
     "url": "https://www.auri.re.kr"},
    {"name": "한국조세재정연구원", "group": "연구소",
     "note": "조세·재정 정책 연구. 부동산 세제가 여기서 다뤄진다",
     "url": "https://www.kipf.re.kr"},
    {"name": "한국법제연구원", "group": "연구소",
     "note": "법령 해설과 입법 연구",
     "url": "https://www.klri.re.kr"},
    {"name": "한국행정연구원", "group": "연구소",
     "note": "행정 제도와 정부 운영 연구",
     "url": "https://www.kipa.re.kr"},
    {"name": "산업연구원(KIET)", "group": "연구소",
     "note": "산업 구조와 업종별 전망",
     "url": "https://www.kiet.re.kr"},
    {"name": "대외경제정책연구원(KIEP)", "group": "연구소",
     "note": "세계경제와 통상 정책 연구",
     "url": "https://www.kiep.go.kr"},
    {"name": "자본시장연구원(KCMI)", "group": "연구소",
     "note": "자본시장 제도와 금융산업 연구",
     "url": "https://www.kcmi.re.kr"},
    {"name": "보험연구원", "group": "연구소",
     "note": "보험 산업과 제도 연구",
     "url": "https://www.kiri.or.kr"},
    {"name": "국제금융센터(KCIF)", "group": "연구소",
     "note": "국제 금융시장 동향을 수시로 전한다",
     "url": "https://www.kcif.or.kr"},
    # --- 연구소 : 국회 ---
    {"name": "국회예산정책처", "group": "연구소",
     "note": "국회의 재정 분석 기관. 예산·세제 추계",
     "url": "https://www.nabo.go.kr"},
    {"name": "국회입법조사처", "group": "연구소",
     "note": "국회의 입법 조사 기관. 현안 분석 보고서",
     "url": "https://www.nars.go.kr"},
    {"name": "국회미래연구원", "group": "연구소",
     "note": "중장기 미래 전략 연구",
     "url": "https://www.nafi.re.kr"},
    # --- 연구소 : 주택·건설 ---
    {"name": "주택산업연구원", "group": "연구소",
     "note": "주택 공급과 시장 전망. 업계 쪽 시각이 담긴다",
     "url": "https://www.khi.re.kr"},
    {"name": "주택금융연구원", "group": "연구소",
     "note": "주택금융공사 부설. 주택담보대출·주택연금 분석",
     "url": "https://researcher.hf.go.kr/researcher/index.do"},
    {"name": "대한건설정책연구원", "group": "연구소",
     "note": "건설 산업과 제도 연구",
     "url": "https://www.ricon.re.kr"},
    # --- 연구소 : 금융지주 ---
    {"name": "KB경영연구소", "group": "연구소",
     "note": "부동산·금융 시장 보고서. 민간이라 시각이 다르다",
     "url": "https://www.kbfg.com"},
    {"name": "하나금융연구소", "group": "연구소",
     "note": "가계금융과 부동산 시장 분석",
     "url": "https://www.hanaif.re.kr"},
    {"name": "우리금융경영연구소", "group": "연구소",
     "note": "금융·경제 동향 분석",
     "url": "https://www.wfri.re.kr"},
    {"name": "IBK기업은행 경제연구소", "group": "연구소",
     "note": "중소기업과 경제 동향 분석",
     "url": "https://research.ibk.co.kr"},
    # --- 연구소 : 국제기구 ---
    {"name": "국제통화기금(IMF)", "group": "연구소",
     "note": "세계경제 전망과 한국 연례협의 보고서 (영문)",
     "url": "https://www.imf.org"},
    {"name": "OECD", "group": "연구소",
     "note": "회원국 경제 조사와 통계. 한국 경제보고서 (영문)",
     "url": "https://www.oecd.org"},

    # --- 증권사 ---
    {"name": "NH투자증권", "group": "증권사",
     "note": "리서치센터 보고서. 시장 전망과 산업 분석",
     "url": "https://www.nhsec.com"},
    {"name": "삼성증권", "group": "증권사",
     "note": "리서치센터 보고서. 시장 전망과 산업 분석",
     "url": "https://www.samsungpop.com"},
    {"name": "신한투자증권", "group": "증권사",
     "note": "리서치센터 보고서. 시장 전망과 산업 분석",
     "url": "https://www.shinhansec.com"},
    {"name": "키움증권", "group": "증권사",
     "note": "리서치센터 보고서. 시장 전망과 산업 분석",
     "url": "https://www1.kiwoom.com"},
    {"name": "대신증권", "group": "증권사",
     "note": "리서치센터 보고서. 시장 전망과 산업 분석",
     "url": "https://www.creontrade.com"},
    {"name": "교보증권", "group": "증권사",
     "note": "리서치센터 보고서. 시장 전망과 산업 분석",
     "url": "https://www.iprovest.com"},
    {"name": "IBK투자증권", "group": "증권사",
     "note": "리서치센터 보고서. 시장 전망과 산업 분석",
     "url": "https://www.ibks.com"},
    # --- 업계 ---
    {"name": "CBRE코리아", "group": "업계",
     "note": "글로벌 상업용 부동산 서비스. 오피스·물류 시장 보고서",
     "url": "https://www.cbrekorea.com"},
    {"name": "세빌스 코리아", "group": "업계",
     "note": "글로벌 상업용 부동산 서비스. 오피스 임대 동향",
     "url": "https://www.savills.co.kr"},
    {"name": "쿠쉬먼앤드웨이크필드", "group": "업계",
     "note": "글로벌 상업용 부동산 서비스. 시장 보고서",
     "url": "https://www.cushmanwakefield.com/ko-kr/south-korea"},
    {"name": "이지스자산운용", "group": "업계",
     "note": "부동산 자산운용. 오피스·물류 시장 보고서",
     "url": "https://www.igisam.com"},
    {"name": "젠스타메이트", "group": "업계",
     "note": "국내 상업용 부동산 종합 서비스. 시장 자료",
     "url": "https://www.genstarmate.com"},
    {"name": "알투코리아(R2 KOREA)", "group": "업계",
     "note": "부동산 조사·컨설팅",
     "url": "https://www.r2korea.kr"},
    {"name": "알스퀘어(RSQUARE)", "group": "업계",
     "note": "상업용 부동산 중개·데이터. 오피스 시장 리포트",
     "url": "https://www.rsquare.co.kr"},
    {"name": "부동산플래닛", "group": "업계",
     "note": "실거래 데이터 분석 서비스",
     "url": "https://www.bdsplanet.com"},
    {"name": "삼일회계법인(PwC)", "group": "업계",
     "note": "회계·자문. 산업별 보고서",
     "url": "https://www.pwc.com/kr"},
    {"name": "삼정회계법인(KPMG)", "group": "업계",
     "note": "회계·자문. 산업별 보고서",
     "url": "https://kpmg.com/kr"},

    # --- 협회 ---
    {"name": "금융투자협회", "group": "협회",
     "note": "증권·자산운용 업계 협회. 통계와 공시 자료",
     "url": "https://www.kofia.or.kr"},
    {"name": "전국은행연합회", "group": "협회",
     "note": "은행 업계 협회. 금리·수수료 공시",
     "url": "https://www.kfb.or.kr"},
    {"name": "한국경제인협회", "group": "협회",
     "note": "경제단체(옛 전경련). 기업·경제 조사 보고서",
     "url": "https://www.fki.or.kr"},
)


def sites_by_group():
    return boards.sites_by_group(SITES, GROUP_ORDER)


def agency_names() -> list[str]:
    return boards.agency_names(SITES)


def find(name: str) -> Site | None:
    return boards.find(SITES, name)


def boards_of(name: str) -> list[Site]:
    return boards.boards_of(SITES, name)


def collect(sites=None, pages: int = 3, delay: float = 0.7, on_progress=None,
            known=None):
    targets = list(sites) if sites else list(SITES)
    return boards.collect(
        targets, pages=pages, delay=delay, on_progress=on_progress, known=known
    )
