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


# --- 한 곳이 넘어져도 나머지는 간다 -------------------------------------------
#
# 2026-09-28에 성남시 연결이 'access violation'으로 어긋났다. 구형 TLS로
# 붙는 곳은 가끔 이런다. 그 한 곳 때문에 나머지를 못 받으면 안 된다.

def _site(name, parser):
    from govpress import boards

    return boards.Site(
        name=name, group="서울", list_url=f"https://{name}.example/list",
        page_param="page", parser=parser, category="지자체", prefix="local",
    )


def _one(uid):
    def parse(html, site):
        return [{
            "uid": uid, "title": f"{site.name} 보도자료", "link": "https://x.example/1",
            "department": "", "published_at": "2026-09-28",
        }]
    return parse


def test_한_기관이_계속_실패해도_다음_기관으로_넘어간다(monkeypatch):
    from govpress import boards

    부른곳 = []

    def fake_fetch(site, page, session=None, timeout=25, known=None):
        부른곳.append(site.name)
        if site.name == "성남시":
            raise OSError("exception: access violation writing 0x48")
        return boards.to_articles(site.parser("", site), site)

    monkeypatch.setattr(boards, "fetch_page", fake_fetch)
    monkeypatch.setattr(boards.time, "sleep", lambda *_: None)

    sites = [_site("성남시", _one("1")), _site("용인시", _one("2"))]
    got = boards.collect(sites, pages=1)

    assert [a.agency for a in got] == ["용인시"], "넘어진 뒤 멈춰 버렸습니다"
    assert 부른곳.count("성남시") == 2, "새 연결로 한 번 더 해 보지 않았습니다"


def test_다시_해서_되면_그대로_받는다(monkeypatch):
    """연결이 한 번 어긋났을 뿐이면 두 번째에 붙는다."""
    from govpress import boards

    시도 = {"n": 0}

    def flaky(site, page, session=None, timeout=25, known=None):
        시도["n"] += 1
        if 시도["n"] == 1:
            raise OSError("Connection aborted.")
        return boards.to_articles(site.parser("", site), site)

    monkeypatch.setattr(boards, "fetch_page", flaky)
    monkeypatch.setattr(boards.time, "sleep", lambda *_: None)

    got = boards.collect([_site("성남시", _one("1"))], pages=1)
    assert [a.agency for a in got] == ["성남시"]


def test_다시_할_때는_쓰던_연결을_쓰지_않는다(monkeypatch):
    """끊긴 연결을 그대로 다시 쓰면 또 실패한다."""
    from govpress import boards

    세션 = []

    def fake(site, page, session=None, timeout=25, known=None):
        세션.append(session)
        raise OSError("Connection aborted.")

    monkeypatch.setattr(boards, "fetch_page", fake)
    monkeypatch.setattr(boards.time, "sleep", lambda *_: None)
    boards.collect([_site("성남시", _one("1"))], pages=1)

    assert 세션[0] is not None, "첫 시도는 쓰던 연결이어야 합니다"
    assert 세션[1] is None, "다시 할 때도 같은 연결을 썼습니다"


# --- 시간이 차면 손을 뗀다 -----------------------------------------------------
#
# 2026-09-30에 지자체 한 곳에서 물려 한 시간 반을 서 있었다. 작업 스케줄러가
# 1시간 만에 통째로 죽여서 화면 만들기와 올리기가 아예 실행되지 않았고,
# 보는 사람에게는 어제 화면이 그대로 남았다.
#
# 한 곳이 늦는 것보다 그날 갱신을 통째로 놓치는 편이 훨씬 나쁘다.

def test_시간이_차면_남은_기관을_건너뛴다(monkeypatch):
    from govpress import boards

    시계 = {"t": 0.0}
    monkeypatch.setattr(boards.time, "monotonic", lambda: 시계["t"])
    monkeypatch.setattr(boards.time, "sleep", lambda *_: None)

    def slow(site, page, session=None, timeout=None, known=None):
        시계["t"] += 60          # 기관마다 1분씩 먹는다고 치자
        return boards.to_articles(site.parser("", site), site)

    monkeypatch.setattr(boards, "fetch_page", slow)

    sites = [_site(f"기관{i}", _one(str(i))) for i in range(10)]
    알림 = []
    got = boards.collect(
        sites, pages=1, budget_seconds=180,
        on_progress=lambda *a: 알림.append(a),
    )

    assert len(got) == 3, f"3분치만 받아야 하는데 {len(got)}곳을 받았습니다"
    말 = " ".join(str(a) for a in 알림)
    assert "다음 차례로 미룹니다" in 말, "건너뛴 곳을 알리지 않았습니다"


def test_시간_상한을_끄면_끝까지_간다(monkeypatch):
    from govpress import boards

    def quick(site, page, session=None, timeout=None, known=None):
        return boards.to_articles(site.parser("", site), site)

    monkeypatch.setattr(boards, "fetch_page", quick)
    monkeypatch.setattr(boards.time, "sleep", lambda *_: None)

    sites = [_site(f"기관{i}", _one(str(i))) for i in range(5)]
    assert len(boards.collect(sites, pages=1, budget_seconds=0)) == 5


def test_받은_데까지는_들고_나온다(monkeypatch):
    """시간이 찼다고 그때까지 모은 것을 버리면 안 된다."""
    from govpress import boards

    시계 = {"t": 0.0}
    monkeypatch.setattr(boards.time, "monotonic", lambda: 시계["t"])
    monkeypatch.setattr(boards.time, "sleep", lambda *_: None)

    def slow(site, page, session=None, timeout=None, known=None):
        시계["t"] += 100
        return boards.to_articles(site.parser("", site), site)

    monkeypatch.setattr(boards, "fetch_page", slow)
    got = boards.collect(
        [_site("가", _one("1")), _site("나", _one("2"))], pages=1, budget_seconds=50
    )
    assert [a.agency for a in got] == ["가"]


def test_연결과_읽기_시간을_따로_잡는다():
    """숫자 하나로 주면 한 요청이 생각보다 오래 붙든다."""
    from govpress import boards

    assert isinstance(boards.TIMEOUT, tuple) and len(boards.TIMEOUT) == 2
    assert boards.TIMEOUT[0] <= 10
