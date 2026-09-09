"""지자체 파서 검증. 실제 목록 HTML을 저장한 fixture로 돌린다."""

from __future__ import annotations

from pathlib import Path

import pytest

from govpress import local_gov
from govpress.models import LOCAL

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# --- 서울시 ----------------------------------------------------------------

@pytest.fixture(scope="module")
def seoul_articles():
    site = local_gov.find("서울시")
    return local_gov.to_articles(local_gov.parse_seoul(load("local_seoul.html"), site), site)


def test_서울시_행을_모두_뽑는다(seoul_articles):
    assert len(seoul_articles) == 5


def test_서울시_항목이_실사용_가능하다(seoul_articles):
    """제목·링크·날짜·분류가 하나라도 비면 저장 단계에서 버려진다."""
    assert all(a.is_valid() for a in seoul_articles)


def test_서울시_분류와_기관명(seoul_articles):
    assert all(a.category == LOCAL for a in seoul_articles)
    assert all(a.agency == "서울시" for a in seoul_articles)


def test_서울시_링크가_실제_상세주소로_조립된다(seoul_articles):
    """목록 링크가 javascript:fnTbbsView('465874') 라서 그대로 쓰면 못 연다."""
    for article in seoul_articles:
        assert article.link.startswith(
            "https://www.seoul.go.kr/news/news_report.do?bbsNo=158&nttNo="
        )
        assert "javascript" not in article.link
    assert seoul_articles[0].link.endswith("nttNo=465874")


def test_서울시_날짜가_ISO형식이다(seoul_articles):
    for article in seoul_articles:
        assert len(article.published_at) == 10 and article.published_at[4] == "-"
    assert {a.published_at for a in seoul_articles} == {"2026-09-08", "2026-09-07"}


def test_서울시_제목에_파일있음_같은_군더더기가_붙지_않는다(seoul_articles):
    for article in seoul_articles:
        assert "파일있음" not in article.title


def test_서울시_담당부서가_비어도_버리지_않는다(seoul_articles):
    """부서가 빈 행(시장 동정 등)도 보도자료다."""
    empty = [a for a in seoul_articles if not a.summary]
    assert empty, "부서가 빈 행이 fixture에 없어 검증 불가"
    assert all(a.is_valid() for a in empty)


def test_서울시_uid가_중복되지_않는다(seoul_articles):
    uids = [a.uid for a in seoul_articles]
    assert len(uids) == len(set(uids))


def test_빈_HTML은_빈_결과를_준다():
    site = local_gov.find("서울시")
    assert local_gov.parse_seoul("<html><body><p>없음</p></body></html>", site) == []


# --- 목록 구성 --------------------------------------------------------------

def test_페이지_주소를_만든다():
    site = local_gov.find("서울시")
    assert site.page_url(2) == "https://www.seoul.go.kr/news/news_report.do?curPage=2"


def test_출처가_지자체마다_구분된다():
    """(source, uid)로 중복을 막으므로 지자체끼리 uid가 겹쳐도 안전하다."""
    sources = {site.source for site in local_gov.SITES}
    assert len(sources) == len(local_gov.SITES)
    assert all(s.startswith("local:") for s in sources)


def test_지역별로_묶인다():
    grouped = dict(local_gov.sites_by_region())
    assert "서울" in grouped
    assert "서울시" in [s.name for s in grouped["서울"]]
    assert local_gov.region_of("서울시") == "서울"


def test_지역_순서는_서울_다음_경기다():
    assert local_gov.REGION_ORDER == ("서울", "경기")


def test_아직_확인하지_않은_지자체는_목록에_넣지_않는다():
    """구조를 보지 않고 넣으면 빈 결과나 엉뚱한 링크를 알아채기 어렵다."""
    listed = {site.name for site in local_gov.SITES}
    assert not (listed & set(local_gov.PENDING))


# --- 표준 게시판 (송파구·구리시) ---------------------------------------------

@pytest.fixture(scope="module")
def songpa():
    site = local_gov.find("송파구")
    return local_gov.to_articles(site.parser(load("local_songpa.html"), site), site)


@pytest.fixture(scope="module")
def guri():
    site = local_gov.find("구리시")
    return local_gov.to_articles(site.parser(load("local_guri.html"), site), site)


def test_송파구_항목이_실사용_가능하다(songpa):
    assert len(songpa) == 3
    assert all(a.is_valid() for a in songpa)
    assert all(a.agency == "송파구" for a in songpa)


def test_송파구_제목에_라벨과_NEW가_붙지_않는다(songpa):
    """모바일용 숨은 라벨('제목')과 NEW 아이콘이 제목에 섞이면 안 된다."""
    for article in songpa:
        assert not article.title.startswith("제목")
        assert "NEW" not in article.title


def test_송파구_담당부서를_읽는다(songpa):
    assert songpa[0].summary == "홍보담당관"


def test_구리시는_파일칸이_끼어_있어도_담당부서를_찾는다(guri):
    """구리시는 번호/제목/파일/담당부서/작성일 5칸이다."""
    assert len(guri) == 3
    assert guri[0].summary == "건강증진과"
    assert all(a.is_valid() for a in guri)


@pytest.mark.parametrize("name", ["송파구", "구리시"])
def test_표준게시판_링크에서_페이지상태값을_떼어낸다(name, songpa, guri):
    articles = songpa if name == "송파구" else guri
    for article in articles:
        assert "nttNo=" in article.link
        assert "pageIndex" not in article.link
        assert "searchCnd" not in article.link
        assert article.link.startswith("https://")


def test_표준게시판_날짜가_ISO형식이다(songpa, guri):
    for article in songpa + guri:
        assert len(article.published_at) == 10 and article.published_at[4] == "-"


# --- 카드형 게시판 (하남시) --------------------------------------------------

@pytest.fixture(scope="module")
def hanam():
    site = local_gov.find("하남시")
    return local_gov.to_articles(site.parser(load("local_hanam.html"), site), site)


def test_하남시_카드형에서도_뽑아낸다(hanam):
    """하남시는 표가 아니라 카드가 줄지어 있는 형태다."""
    assert len(hanam) == 3
    assert all(a.is_valid() for a in hanam)
    assert all(a.agency == "하남시" for a in hanam)


def test_하남시_제목과_요약이_섞이지_않는다(hanam):
    for article in hanam:
        assert len(article.title) < 60, "요약이 제목에 딸려 들어왔습니다"
        assert not article.title.startswith("누구나")


def test_하남시_날짜(hanam):
    assert {a.published_at for a in hanam} == {"2026-09-08", "2026-09-07"}


# --- 전체 ------------------------------------------------------------------

def test_모든_지자체가_지역에_속한다():
    for site in local_gov.SITES:
        assert site.region in local_gov.REGION_ORDER


def test_지역이_둘로_나뉜다():
    grouped = dict(local_gov.sites_by_region())
    assert set(grouped) == {"서울", "경기"}
    assert {s.name for s in grouped["서울"]} == {"서울시", "송파구"}
    assert {s.name for s in grouped["경기"]} == {"구리시", "하남시"}
