"""수집 옵션(부처·기간·검색어)이 실제 요청으로 옮겨지는지 확인한다."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from govpress import korea_kr
from govpress.agencies import resolve_many
from govpress.models import InvalidDate, parse_date_range, parse_user_date

FIXTURE = Path(__file__).parent / "fixtures" / "korea_list.html"


class FakeResponse:
    def __init__(self, text):
        self.text = text
        self.apparent_encoding = "utf-8"
        self.encoding = None

    def raise_for_status(self):
        return None


class FakeSession:
    """요청 파라미터를 기록하고, 첫 페이지에만 결과를 돌려준다."""

    def __init__(self, html):
        self.html = html
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(params)
        # 2페이지부터는 빈 목록 → 수집이 멈춘다
        return FakeResponse(self.html if params["pageIndex"] == 1 else "<html></html>")


@pytest.fixture
def html():
    return FIXTURE.read_text(encoding="utf-8")


# --- 날짜 입력 --------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("26.09.08", date(2026, 9, 8)),
        ("2026.09.08", date(2026, 9, 8)),
        ("2026-9-8", date(2026, 9, 8)),
        ("26/09/08", date(2026, 9, 8)),
        ("20260908", date(2026, 9, 8)),
        ("  26.09.08  ", date(2026, 9, 8)),
    ],
)
def test_사용자_날짜_형식을_받는다(raw, expected):
    assert parse_user_date(raw) == expected


@pytest.mark.parametrize("raw", ["", "26.13.01", "26.02.30", "어제", "2026", "9/8"])
def test_잘못된_날짜는_거절한다(raw):
    with pytest.raises(InvalidDate):
        parse_user_date(raw)


def test_기간이_뒤집혀도_바로잡는다():
    start, end = parse_date_range("26.09.08", "26.09.01")
    assert start == date(2026, 9, 1) and end == date(2026, 9, 8)


def test_한쪽만_주어도_된다():
    assert parse_date_range("26.09.01", None) == (date(2026, 9, 1), None)
    assert parse_date_range(None, None) == (None, None)


# --- 요청 파라미터 ----------------------------------------------------------

def test_기간과_검색어가_요청에_실린다(html):
    session = FakeSession(html)
    korea_kr.fetch_page(
        1, date(2026, 8, 1), date(2026, 9, 8), keyword="부동산", session=session
    )
    params = session.calls[0]
    assert params["startDate"] == "2026-08-01"
    assert params["endDate"] == "2026-09-08"
    assert params["srchWord"] == "부동산"


def test_부처를_지정하면_repCode가_실린다(html):
    session = FakeSession(html)
    korea_kr.fetch_page(1, date(2026, 9, 1), date(2026, 9, 8), rep_code="A00006", session=session)
    params = session.calls[0]
    assert params["repCode"] == "A00006"
    assert params["repCodeType"] == "정부부처"


def test_부처를_지정하지_않으면_repCode가_비어있다(html):
    session = FakeSession(html)
    korea_kr.fetch_page(1, date(2026, 9, 1), date(2026, 9, 8), session=session)
    assert session.calls[0]["repCode"] == ""
    assert session.calls[0]["repCodeType"] == ""


def test_부처별로_따로_요청한다(html, monkeypatch):
    session = FakeSession(html)
    monkeypatch.setattr(korea_kr.requests, "Session", lambda: session)
    monkeypatch.setattr(korea_kr.time, "sleep", lambda *_: None)

    korea_kr.collect(
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 8),
        ministries=resolve_many(["국토교통부", "금융위원회"]),
    )

    codes = {call["repCode"] for call in session.calls}
    assert codes == {"A00006", "C00003"}


def test_명시한_기간이_days보다_우선한다(html, monkeypatch):
    session = FakeSession(html)
    monkeypatch.setattr(korea_kr.requests, "Session", lambda: session)
    monkeypatch.setattr(korea_kr.time, "sleep", lambda *_: None)

    korea_kr.collect(days=7, start_date=date(2026, 1, 1), end_date=date(2026, 3, 1))

    assert session.calls[0]["startDate"] == "2026-01-01"
    assert session.calls[0]["endDate"] == "2026-03-01"


def test_기간이_뒤집혀_들어와도_수집된다(html, monkeypatch):
    session = FakeSession(html)
    monkeypatch.setattr(korea_kr.requests, "Session", lambda: session)
    monkeypatch.setattr(korea_kr.time, "sleep", lambda *_: None)

    articles = korea_kr.collect(start_date=date(2026, 3, 1), end_date=date(2026, 1, 1))

    assert session.calls[0]["startDate"] == "2026-01-01"
    assert articles


def test_중복된_기사는_한_번만_담긴다(html, monkeypatch):
    """부처를 여러 개 지정해도 같은 newsId는 하나로 합쳐진다."""
    session = FakeSession(html)
    monkeypatch.setattr(korea_kr.requests, "Session", lambda: session)
    monkeypatch.setattr(korea_kr.time, "sleep", lambda *_: None)

    articles = korea_kr.collect(
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 8),
        ministries=resolve_many(["국토교통부", "금융위원회"]),
    )
    uids = [a.uid for a in articles]
    assert len(uids) == len(set(uids))


def test_제외한_기관은_수집하지_않는다(html, monkeypatch):
    """목록에서 뺀 기관은 전 부처 훑기에서도 걸러져야 한다."""
    from govpress.agencies import EXCLUDED

    session = FakeSession(html)
    monkeypatch.setattr(korea_kr.requests, "Session", lambda: session)
    monkeypatch.setattr(korea_kr.time, "sleep", lambda *_: None)

    raw = korea_kr.parse_list(html)
    assert any(a.agency in EXCLUDED for a in raw), "fixture에 제외 대상 기사가 없어 검증 불가"

    articles = korea_kr.collect(start_date=date(2026, 9, 1), end_date=date(2026, 9, 8))
    assert not any(a.agency in EXCLUDED for a in articles)
    assert len(articles) == len([a for a in raw if a.agency not in EXCLUDED])
