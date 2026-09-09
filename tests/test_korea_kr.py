"""실제 korea.kr 목록 페이지 HTML(fixture)로 파서를 검증한다."""

from __future__ import annotations

from pathlib import Path

import pytest

from govpress.korea_kr import SOURCE, parse_list, permalink
from govpress.models import normalize_date

FIXTURE = Path(__file__).parent / "fixtures" / "korea_list.html"


@pytest.fixture(scope="module")
def articles():
    return parse_list(FIXTURE.read_text(encoding="utf-8"))


def test_한_페이지에서_20건을_뽑는다(articles):
    assert len(articles) == 20


def test_모든_항목이_실사용_가능하다(articles):
    """예전 구현의 실패 지점: 날짜가 전부 비어 있었다."""
    invalid = [a for a in articles if not a.is_valid()]
    assert invalid == []


def test_날짜가_ISO형식이다(articles):
    for article in articles:
        assert len(article.published_at) == 10
        assert article.published_at[4] == "-" and article.published_at[7] == "-"


def test_부처명이_채워진다(articles):
    assert all(a.agency for a in articles)
    # 목록에는 여러 부처가 섞여 나온다 (통합 피드이므로)
    assert len({a.agency for a in articles}) > 1


def test_링크는_정규화된_permalink다(articles):
    for article in articles:
        assert article.link == permalink(article.uid)
        assert article.link.startswith("https://www.korea.kr/briefing/pressReleaseView.do?newsId=")
        assert "&" not in article.link  # 쿼리 잡동사니가 붙지 않는다


def test_uid가_중복되지_않는다(articles):
    uids = [a.uid for a in articles]
    assert len(uids) == len(set(uids))


def test_메뉴나_배너를_주워오지_않는다(articles):
    """예전 구현은 '보도자료', '공지사항' 같은 메뉴 링크를 기사로 저장했다."""
    menu_like = {"보도자료", "공지사항", "브리핑룸", "정책브리핑", "동정자료", "홍보자료"}
    assert not (menu_like & {a.title for a in articles})
    # 제목이 지나치게 짧은 메뉴 텍스트도 없어야 한다
    assert all(len(a.title) > 8 for a in articles)


def test_source가_표시된다(articles):
    assert all(a.source == SOURCE for a in articles)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026.09.08", "2026-09-08"),
        ("2026-9-8", "2026-09-08"),
        ("2026/09/08", "2026-09-08"),
        ("등록일 2026.09.08 오전", "2026-09-08"),
        ("", ""),
        (None, ""),
        ("날짜없음", ""),
    ],
)
def test_날짜_정규화(raw, expected):
    assert normalize_date(raw) == expected


def test_빈_HTML은_빈_결과를_준다():
    assert parse_list("<html><body><p>no list</p></body></html>") == []


# --- 요약 정리 ---------------------------------------------------------------

def test_요약이_제목을_반복하지_않는다(articles):
    for a in articles:
        if a.summary:
            assert not a.summary.startswith(a.title[:12]), a.summary[:60]


def test_상투구만_남는_요약은_비운다(articles):
    for a in articles:
        assert a.summary != "관련 보도자료입니다."
        assert "관련 보도자료입니다" not in a.summary[:20]


@pytest.mark.parametrize(
    "summary,title,expected",
    [
        ("학교안전법 시행령 개정안 통과- 부제와 본문이 이어지는 충분히 긴 문장입니다.",
         "학교안전법 시행령 개정안 통과",
         "부제와 본문이 이어지는 충분히 긴 문장입니다."),
        ("행복청, 「2차 이전」 지원 관련 보도자료입니다.", "행복청,「2차 이전」 지원", ""),
        ("짧음", "전혀 다른 제목", ""),
        ("", "제목", ""),
        # 제목 뒤에 목록에만 붙는 꼬리표가 있어도 앞부분이 겹치면 떼어낸다
        ("기후보건포럼 개최 안내- 본문 첫 문장이 여기서부터 이어집니다.",
         "기후보건포럼 개최 안내(9.8.화)",
         "본문 첫 문장이 여기서부터 이어집니다."),
        # 제목이 짧으면 우연한 겹침일 수 있으므로 건드리지 않는다
        ("제목과 무관하게 시작하는 충분히 긴 요약 문장입니다.", "제목",
         "제목과 무관하게 시작하는 충분히 긴 요약 문장입니다."),
        # 제목으로 시작하지 않으면 그대로 둔다
        ("전혀 다른 문장으로 시작하는 충분히 긴 요약입니다.", "국토교통부 보도자료 제목",
         "전혀 다른 문장으로 시작하는 충분히 긴 요약입니다."),
    ],
)
def test_요약_정리_규칙(summary, title, expected):
    from govpress.korea_kr import clean_summary
    assert clean_summary(summary, title) == expected


@pytest.mark.parametrize(
    "summary,title",
    [
        ("첨부파일 안내 제목입니다 자세한 내용은 첨부파일을 참고하시기 바랍니다.",
         "첨부파일 안내 제목입니다"),
        ("붙임파일 안내 제목입니다 붙임 파일 참고.", "붙임파일 안내 제목입니다"),
    ],
)
def test_안내_상투구만_남으면_요약을_비운다(summary, title):
    from govpress.korea_kr import clean_summary
    assert clean_summary(summary, title) == ""


def test_요약_앞에_따옴표나_겹친_하이픈이_남지_않는다(articles):
    for a in articles:
        if a.summary:
            assert a.summary[0] not in "\"'“”‘’-–—·… ,"
            assert " - - " not in a.summary
