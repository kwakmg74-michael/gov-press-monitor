"""연구소 파서 검증. 실제 목록 HTML을 저장한 fixture로 돌린다."""

from __future__ import annotations

from pathlib import Path

import pytest

from govpress import boards, research
from govpress.models import RESEARCH

FIXTURES = Path(__file__).parent / "fixtures"

CASES = {
    "국토연구원": "research_krihs.html",
    "건축공간연구원": "research_auri.html",
    "KB경영연구소": "research_kbfg.html",
    "한국법제연구원": "research_klri.html",
    "한국조세재정연구원": "research_kipf.html",
}

# KDI는 게시판마다 모양이 달라 따로 본다.
KDI_LIST = "research_kdi_list.html"
KDI_VIEW = "research_kdi_view.html"
KDI_FOCUS_VIEW = "research_kdi_focus_view.html"
KDI_ISSUE = "research_kdi_issue.html"
KDI_OUTLOOK = "research_kdi_outlook.html"


@pytest.fixture(scope="module")
def parsed():
    out = {}
    for name, fixture in CASES.items():
        site = research.find(name)
        html = (FIXTURES / fixture).read_text(encoding="utf-8")
        out[name] = boards.to_articles(site.parser(html, site), site)
    return out


# --- 공통 ------------------------------------------------------------------

@pytest.mark.parametrize("name", list(CASES))
def test_세_건씩_실사용_가능하게_파싱된다(parsed, name):
    articles = parsed[name]
    assert len(articles) == 3, f"{name} 파싱 건수가 다릅니다"
    assert all(a.is_valid() for a in articles)
    assert all(a.category == RESEARCH for a in articles)
    assert all(a.agency == name for a in articles)


@pytest.mark.parametrize("name", list(CASES))
def test_날짜가_ISO형식이다(parsed, name):
    for article in parsed[name]:
        assert len(article.published_at) == 10 and article.published_at[4] == "-"


@pytest.mark.parametrize("name", list(CASES))
def test_링크가_원문을_가리키고_페이지상태값은_없다(parsed, name):
    for article in parsed[name]:
        assert article.link.startswith("https://")
        assert "javascript" not in article.link
        assert "nPage" not in article.link, "보고 있던 페이지 번호가 링크에 남았습니다"
        assert "sch_text" not in article.link


@pytest.mark.parametrize("name", list(CASES))
def test_uid가_중복되지_않는다(parsed, name):
    uids = [a.uid for a in parsed[name]]
    assert len(uids) == len(set(uids))


# --- 국토연구원 --------------------------------------------------------------

def test_국토연구원_제목에_숨은_새글_라벨이_섞이지_않는다(parsed):
    """화면에는 안 보이지만 <span class="sr_only">새글</span>이 들어 있다."""
    for article in parsed["국토연구원"]:
        assert not article.title.startswith("새글")
        assert "새글" not in article.title


def test_국토연구원_작성부서를_읽는다(parsed):
    assert parsed["국토연구원"][0].summary == "지식홍보팀"
    assert parsed["국토연구원"][0].link.endswith("list_no=398617")


def test_국토연구원_분류칸을_제목으로_읽지_않는다(parsed):
    """번호 / 분류 / 제목 순서라, 자리를 잘못 세면 전부 '보도자료'가 된다."""
    titles = [a.title for a in parsed["국토연구원"]]
    assert "보도자료" not in titles
    assert len(set(titles)) == 3


# --- 건축공간연구원 ----------------------------------------------------------

def test_건축공간연구원_카드에서_제목을_뽑는다(parsed):
    articles = parsed["건축공간연구원"]
    assert articles[0].title == "국가 공공자산으로서 청사의 체계적 관리를 위한 법률 제정 연구"
    assert articles[0].summary == "김영현"


def test_건축공간연구원_연관키워드를_기사로_줍지_않는다(parsed):
    """카드 안에 #해시태그 링크가 여럿 있다. 그걸 제목으로 읽으면 안 된다."""
    for article in parsed["건축공간연구원"]:
        assert not article.title.startswith("#")
        assert "sch_type=K" not in article.link


def test_건축공간연구원_점찍힌_날짜를_읽는다(parsed):
    assert parsed["건축공간연구원"][0].published_at == "2026-06-30"


# --- KB경영연구소 ------------------------------------------------------------

def test_KB_카드에서_제목과_저자를_뽑는다(parsed):
    articles = parsed["KB경영연구소"]
    assert articles[0].title == "[KB지식비타민] 시간은 아껴 쓰는 것이 아니라 골라 쓰는 것"
    assert articles[0].summary == "방석훈"
    assert articles[0].link.endswith("reportView.do?reportId=2001360")


def test_KB_조회수를_날짜로_읽지_않는다(parsed):
    """dd가 발행일과 조회수 두 개다. 자리로 세면 조회수를 날짜로 읽는다."""
    assert parsed["KB경영연구소"][0].published_at == "2026-08-31"


def test_KB는_게시판이_둘이어도_한_기관이다():
    names = research.agency_names()
    assert names.count("KB경영연구소") == 1
    assert [s.board for s in research.boards_of("KB경영연구소")] == [
        "연구보고서", "브랜드보고서",
    ]


# --- 한국법제연구원 ----------------------------------------------------------

def test_법제연구원_숨은_라벨을_걷어낸다(parsed):
    """각 칸 앞에 <em class="hidden">발행일:</em> 같은 라벨이 숨어 있다."""
    for article in parsed["한국법제연구원"]:
        assert "발행일" not in article.published_at
        assert not article.title.startswith("제목")
        assert "연구진" not in article.summary


def test_법제연구원_제목이_통째로_사라지지_않는다(parsed):
    """제목을 감싼 <a>에 class="new"가 붙어 있어, 링크째 읽으면 지워진다."""
    articles = parsed["한국법제연구원"]
    assert articles[0].title == "한국법제연구원 2025 연차보고서"
    assert all(len(a.title) > 5 for a in articles)


def test_법제연구원_new_뱃지가_제목에_남지_않는다(parsed):
    assert "[new]" not in parsed["한국법제연구원"][1].title


def test_법제연구원_상세주소를_경로로_만든다(parsed):
    assert parsed["한국법제연구원"][0].link == (
        "https://www.klri.re.kr/kor/publication/2384/view.do"
    )


# --- 한국조세재정연구원 ------------------------------------------------------

def test_조세재정연구원_발간월을_그_달_1일로_읽는다(parsed):
    """여기는 '2026-09'까지만 적는다. 날짜가 없으면 대시보드가 걸러 낸다."""
    articles = parsed["한국조세재정연구원"]
    assert articles[0].published_at == "2026-09-01"
    assert all(a.published_at.endswith("-01") for a in articles)


def test_조세재정연구원_저자를_읽는다(parsed):
    assert parsed["한국조세재정연구원"][0].summary == "박주철"


def test_조세재정연구원_라벨을_값으로_읽지_않는다(parsed):
    """칸마다 <strong>저자</strong><span>박주철</span> 꼴이다."""
    for article in parsed["한국조세재정연구원"]:
        assert article.summary not in ("저자", "발간월")
        assert not article.title.startswith("저자")


def test_조세재정연구원_상세주소를_GET용으로_만든다(parsed):
    assert parsed["한국조세재정연구원"][0].link == (
        "https://www.kipf.re.kr/kor/Publication/All/kiPublish/ALL/view.do"
        "?serialNo=527650"
    )


# --- 한국개발연구원(KDI) -----------------------------------------------------

def _kdi(board: str):
    return next(s for s in research.boards_of("한국개발연구원") if s.board == board)


def _parse(board: str, fixture: str):
    site = _kdi(board)
    html = (FIXTURES / fixture).read_text(encoding="utf-8")
    return site, boards.to_articles(site.parser(html, site), site)


def test_KDI_목록은_날짜를_비워_둔다():
    """이 목록에는 발간일이 아예 없다. 상세를 열어야 알 수 있다."""
    _, articles = _parse("연구보고서", KDI_LIST)
    assert len(articles) == 3
    assert all(a.published_at == "" for a in articles)
    assert all(a.title and a.link.startswith("https://") for a in articles)


def test_KDI_제목과_저자를_뽑고_상세주소를_만든다():
    _, articles = _parse("연구보고서", KDI_LIST)
    assert articles[0].title == "불평등에 관한 연구: 소득과 자산을 중심으로"
    assert articles[0].summary == "이승희"
    assert articles[0].link == (
        "https://www.kdi.re.kr/research/reportView?pub_no=19257"
    )


def test_KDI_연관주제_태그를_제목으로_읽지_않는다():
    """카드마다 #거시경제모형 같은 링크가 여럿 붙어 있다."""
    _, articles = _parse("연구보고서", KDI_LIST)
    for article in articles:
        assert not article.title.startswith("#")
        assert "topicList" not in article.link


def test_KDI_상세에서_발간일을_읽는다():
    html = (FIXTURES / KDI_VIEW).read_text(encoding="utf-8")
    assert research.kdi_detail_date(html) == "2025-12-31"


def test_KDI_FOCUS는_상세_틀이_달라도_발간일을_읽는다():
    """FOCUS는 div.top_bg-wrap, 연구보고서는 div.tit_top이다.

    한쪽만 보면 FOCUS 열 건이 통째로 버려진다 — 실제로 0건이 나왔었다.
    """
    html = (FIXTURES / KDI_FOCUS_VIEW).read_text(encoding="utf-8")
    assert research.kdi_detail_date(html) == "2026-07-27"


def test_KDI_발간일이_없으면_빈값을_준다():
    assert research.kdi_detail_date("<html><body><p>없음</p></body></html>") == ""


def test_KDI_날짜없는_글은_상세를_열어_채운다():
    """이미 가진 글은 열지 않는다 — 새 글에만 요청이 나가야 한다."""
    site = _kdi("연구보고서")
    items = site.parser((FIXTURES / KDI_LIST).read_text(encoding="utf-8"), site)
    opened: list[str] = []

    class _Fake:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            pass

        @property
        def apparent_encoding(self):
            return "utf-8"

    def fake_get(url, **kwargs):
        opened.append(url)
        return _Fake((FIXTURES / KDI_VIEW).read_text(encoding="utf-8"))

    known = {(site.source, items[0]["uid"]), (site.source, items[1]["uid"])}
    filled = boards.fill_missing_dates(
        items, site, known=known, session=type("S", (), {"get": staticmethod(fake_get)})
    )

    assert len(opened) == 1, "이미 가진 글까지 열었습니다"
    assert [f["uid"] for f in filled] == [items[2]["uid"]]
    assert filled[0]["published_at"] == "2025-12-31"


def test_KDI_한번에_여는_수를_묶는다():
    site = _kdi("연구보고서")
    items = site.parser((FIXTURES / KDI_LIST).read_text(encoding="utf-8"), site)
    assert boards.fill_missing_dates(items, site, known=set(), budget=0) == []


def test_KDI_정기간행물은_최신호_한_권만_준다():
    site, articles = _parse("경제동향", KDI_ISSUE)
    assert len(articles) == 1
    assert articles[0].title == "KDI 경제동향 2026. 9"
    assert articles[0].published_at == "2026-09-07"
    assert articles[0].uid == "20260907"
    assert articles[0].link.endswith("pub_no=19271")


def test_KDI_경제전망은_제목줄에_날짜가_붙어_있다():
    _, articles = _parse("경제전망", KDI_OUTLOOK)
    assert len(articles) == 1
    assert articles[0].published_at == "2026-08-19"
    assert "2026.08.19" not in articles[0].title


def test_KDI_정기간행물은_페이지를_넘기지_않는다():
    for board in ("경제전망", "경제동향", "나라경제"):
        site = _kdi(board)
        assert site.single_request
        assert site.page_url(3) == site.list_url


def test_KDI는_게시판이_여섯이어도_한_기관이다():
    assert research.agency_names().count("한국개발연구원") == 1
    assert len(research.boards_of("한국개발연구원")) == 6


# --- 목록 구성 --------------------------------------------------------------

def test_빈_HTML은_빈_결과를_준다():
    for name in CASES:
        site = research.find(name)
        assert site.parser("<html><body><p>없음</p></body></html>", site) == []


def test_출처가_다른_분류와_겹치지_않는다():
    from govpress import local_gov, public_org

    mine = {s.source for s in research.SITES}
    assert len(mine) == len(research.SITES)
    assert all(s.startswith("research:") for s in mine)
    assert not (mine & {s.source for s in public_org.SITES})
    assert not (mine & {s.source for s in local_gov.SITES})


def test_분야별로_묶인다():
    grouped = dict((g, [s.name for s in sites]) for g, sites in research.sites_by_group())
    assert grouped["부동산"] == ["국토연구원"]
    assert grouped["금융"] == ["KB경영연구소", "한국개발연구원", "한국조세재정연구원"]
    assert grouped["기타"] == ["건축공간연구원", "한국법제연구원"]


def test_확인하지_않은_기관은_목록에_넣지_않는다():
    listed = {site.name for site in research.SITES}
    assert not (listed & set(research.PENDING))


def test_페이지_주소를_만든다():
    assert research.find("국토연구원").page_url(2) == (
        "https://www.krihs.re.kr/board.es?mid=a10607000000&bid=0008&nPage=2"
    )
