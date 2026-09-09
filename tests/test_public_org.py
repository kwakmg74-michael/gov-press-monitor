"""공공기관 파서 검증. 실제 목록 HTML을 저장한 fixture로 돌린다."""

from __future__ import annotations

from pathlib import Path

import pytest

from govpress import boards, public_org
from govpress.models import PUBLIC

FIXTURES = Path(__file__).parent / "fixtures"

# 기관 이름 -> 저장해 둔 목록 HTML
CASES = {
    "금융감독원": "public_fss.html",
    "식품안전정보원": "public_foodinfo.html",
    "한국부동산원": "public_reb.html",
    "한국산업단지공단": "public_kicox.html",
    "한국소비자원": "public_kca.html",
    "서울주택도시개발공사": "public_sh.html",
}


@pytest.fixture(scope="module")
def parsed():
    out = {}
    for name, fixture in CASES.items():
        site = public_org.find(name)
        html = (FIXTURES / fixture).read_text(encoding="utf-8")
        out[name] = boards.to_articles(site.parser(html, site), site)
    return out


# --- 공통 ------------------------------------------------------------------

@pytest.mark.parametrize("name", list(CASES))
def test_세_건씩_실사용_가능하게_파싱된다(parsed, name):
    """제목·링크·날짜·분류가 하나라도 비면 저장 단계에서 버려진다."""
    articles = parsed[name]
    assert len(articles) == 3, f"{name} 파싱 건수가 다릅니다"
    assert all(a.is_valid() for a in articles)
    assert all(a.category == PUBLIC for a in articles)
    assert all(a.agency == name for a in articles)


@pytest.mark.parametrize("name", list(CASES))
def test_날짜가_ISO형식이다(parsed, name):
    for article in parsed[name]:
        assert len(article.published_at) == 10 and article.published_at[4] == "-"


@pytest.mark.parametrize("name", list(CASES))
def test_링크가_원문을_가리킨다(parsed, name):
    """javascript: 링크를 그대로 저장하면 나중에 열 수 없다."""
    for article in parsed[name]:
        assert article.link.startswith("https://")
        assert "javascript" not in article.link
        assert "#none" not in article.link


@pytest.mark.parametrize("name", list(CASES))
def test_uid가_중복되지_않는다(parsed, name):
    uids = [a.uid for a in parsed[name]]
    assert len(uids) == len(set(uids))


@pytest.mark.parametrize("name", list(CASES))
def test_제목에_라벨이나_NEW가_섞이지_않는다(parsed, name):
    """모바일용 숨은 라벨('제목', '등록일')과 새글 아이콘을 걷어내야 한다."""
    for article in parsed[name]:
        assert article.title
        assert not article.title.startswith(("제목", "번호"))
        assert "새글" not in article.title
        assert "NEW" not in article.title


# --- 기관별로 확인할 것 ------------------------------------------------------

def test_금융감독원_담당부서를_읽고_페이지상태값은_뗀다(parsed):
    articles = parsed["금융감독원"]
    assert articles[0].summary == "자본시장감독국"
    for article in articles:
        assert "nttId=" in article.link
        assert "pageIndex" not in article.link, "보고 있던 페이지 번호가 링크에 남았습니다"


def test_한국소비자원_담당부서를_읽는다(parsed):
    assert parsed["한국소비자원"][0].summary == "보험의료팀"
    assert parsed["한국소비자원"][0].link.endswith("no=1004558981")


@pytest.mark.parametrize(
    "name", ["식품안전정보원", "한국부동산원", "한국산업단지공단"]
)
def test_담당부서_칸이_없으면_비워_둔다(parsed, name):
    """부서 칸이 없는 게시판에서 날짜 앞 칸을 읽으면 제목이 부서로 들어간다."""
    for article in parsed[name]:
        assert article.summary == "", f"{name}에 엉뚱한 값이 부서로 들어왔습니다"


def test_식품안전정보원_링크를_GET용으로_조립한다(parsed):
    """목록 링크가 main('V', ...) 함수 호출이라 주소를 새로 만들어야 한다."""
    link = parsed["식품안전정보원"][0].link
    assert "detailBBSArticle.do" in link
    assert "nttId=415050" in link
    assert "bbsId=10000000000000000500" in link


def test_한국부동산원_링크를_data_id로_조립한다(parsed):
    link = parsed["한국부동산원"][0].link
    assert "selectNttInfo.do" in link
    assert "nttSn=116832" in link
    assert "mi=9565" in link and "bbsId=1154" in link


def test_한국산업단지공단_링크가_게시판_번호를_따라간다(parsed):
    assert parsed["한국산업단지공단"][0].link == (
        "https://www.kicox.or.kr/boardDetail/1103?bbsSeq=49636"
    )


def test_SH_부서를_읽고_링크를_GET용으로_만든다(parsed):
    articles = parsed["서울주택도시개발공사"]
    assert articles[0].summary == "홍보부"
    assert articles[0].link.endswith("/m_139/view.do?seq=310068")


def test_SH_제목에_NEW_뱃지가_섞이지_않는다(parsed):
    """이 게시판은 새 글 앞에 <span class="icoNew">NEW</span>를 넣는다."""
    for article in parsed["서울주택도시개발공사"]:
        assert not article.title.startswith("NEW")


def test_SH는_한_기관에_게시판이_여럿이어도_한_곳으로_센다():
    """체크박스는 기관 단위로 하나만 나와야 한다."""
    names = public_org.agency_names()
    assert names.count("서울주택도시개발공사") == 1
    assert len(names) <= len(public_org.SITES)


def test_한국부동산원_점으로_끝나는_날짜도_읽는다(parsed):
    """이 게시판은 '2026.09.09.' 처럼 마침표로 끝난다."""
    assert parsed["한국부동산원"][0].published_at == "2026-09-09"


# --- 목록 구성 --------------------------------------------------------------

def test_빈_HTML은_빈_결과를_준다():
    for name in CASES:
        site = public_org.find(name)
        assert site.parser("<html><body><p>없음</p></body></html>", site) == []


def test_출처가_게시판마다_구분된다():
    """(source, uid)로 중복을 막으므로 기관끼리 uid가 겹쳐도 안전하다."""
    sources = {site.source for site in public_org.SITES}
    assert len(sources) == len(public_org.SITES)
    assert all(s.startswith("public:") for s in sources)


def test_지자체와_출처_앞머리가_겹치지_않는다():
    """분류가 달라도 같은 DB에 들어가므로 앞머리로 갈라 둔다."""
    from govpress import local_gov

    assert not (
        {s.source for s in public_org.SITES} & {s.source for s in local_gov.SITES}
    )


def test_분야별로_묶인다():
    grouped = dict((g, [s.name for s in sites]) for g, sites in public_org.sites_by_group())
    assert grouped["부동산"] == ["서울주택도시개발공사", "한국부동산원", "한국산업단지공단"]
    assert grouped["금융"] == ["금융감독원"]
    assert grouped["기타"] == ["식품안전정보원", "한국소비자원"]


def test_묶음_안은_가나다순이다():
    for group, sites in public_org.sites_by_group():
        names = [s.name for s in sites]
        assert names == sorted(names), f"{group}이 가나다순이 아닙니다"


def test_모든_기관이_묶음에_속한다():
    for site in public_org.SITES:
        assert site.group in public_org.GROUP_ORDER


def test_확인하지_않은_기관은_목록에_넣지_않는다():
    """구조를 보지 않고 넣으면 빈 결과나 엉뚱한 링크를 알아채기 어렵다."""
    listed = {site.name for site in public_org.SITES}
    assert not (listed & set(public_org.PENDING))


def test_페이지_주소를_만든다():
    assert public_org.find("한국소비자원").page_url(2) == (
        "https://www.kca.go.kr/home/sub.do?menukey=4002&page=2"
    )
    assert public_org.find("한국산업단지공단").page_url(2) == (
        "https://www.kicox.or.kr/boardList/1103?pageIndex=2"
    )
