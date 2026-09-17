"""대시보드 렌더링 검증. 실제 korea.kr fixture로 만든 DB를 쓴다."""

from __future__ import annotations

import json
import re
from pathlib import Path

from govpress import agencies, dashboard, models, storage
from govpress.korea_kr import parse_list

FIXTURE = Path(__file__).parent / "fixtures" / "korea_list.html"


def build_db(tmp_path):
    db = tmp_path / "t.db"
    storage.save(parse_list(FIXTURE.read_text(encoding="utf-8")), db)
    return db


def read_tabs(html: str) -> list[dict]:
    payload = re.search(
        r'<script id="data" type="application/json">(.*?)</script>', html, re.S
    ).group(1)
    return json.loads(payload.replace("<\\/", "</"))


def render(tmp_path) -> str:
    return dashboard.render(build_db(tmp_path), tmp_path / "d.html").read_text(encoding="utf-8")


# --- 기본 ------------------------------------------------------------------

def test_대시보드가_생성된다(tmp_path):
    out = dashboard.render(build_db(tmp_path), tmp_path / "d.html")
    assert out.exists()
    assert "보도자료 모니터" in out.read_text(encoding="utf-8")


def test_외부_리소스를_불러오지_않는다(tmp_path):
    """오프라인/사내망에서도 파일 하나로 열려야 한다."""
    html = render(tmp_path)
    assert "<script src=" not in html
    assert '<link rel="stylesheet"' not in html


def test_링크가_새_탭으로_열린다(tmp_path):
    html = render(tmp_path)
    assert 'target="_blank"' in html
    assert 'rel="noopener noreferrer"' in html


# --- 탭 --------------------------------------------------------------------

def test_네_분류가_모두_탭으로_들어간다(tmp_path):
    """수집기가 없는 분류도 자리를 지켜야 나중에 붙일 곳이 보인다."""
    tabs = read_tabs(render(tmp_path))
    assert [t["category"] for t in tabs] == list(models.CATEGORIES)


def test_정부기관_탭에만_데이터가_있다(tmp_path):
    tabs = {t["category"]: t for t in read_tabs(render(tmp_path))}
    assert tabs["정부기관"]["count"] > 0
    for name in ("지자체", "공공기관", "연구소"):
        assert tabs[name]["count"] == 0
        assert tabs[name]["articles"] == []


def test_탭_숫자는_기사가_아니라_기관_수다(tmp_path):
    """기사 건수는 날마다 출렁인다. 탭에는 '몇 곳을 훑는지'를 보여 준다."""
    from govpress import agencies, local_gov, public_org, research

    tabs = {t["category"]: t for t in read_tabs(render(tmp_path))}
    assert tabs["정부기관"]["agencies"] == len(agencies.MINISTRIES)
    assert tabs["지자체"]["agencies"] == len(local_gov.agency_names())
    assert tabs["공공기관"]["agencies"] == len(public_org.agency_names())
    # 연구소는 긁지 않고 바로가기만 놓으므로, 세는 기준도 그 목록이다
    assert tabs["연구소"]["agencies"] == len(research.LINKS)

    # 기사가 하나도 없는 fixture에서도 기관 수는 그대로 나온다
    assert tabs["지자체"]["count"] == 0
    assert tabs["지자체"]["agencies"] > 0


def test_탭_배지에_곳_단위가_붙는다(tmp_path):
    html = render(tmp_path)
    assert "'곳</span>'" in html or "곳</span>" in html


def test_기사가_해당_탭에_담긴다(tmp_path):
    db = build_db(tmp_path)
    tabs = {t["category"]: t for t in read_tabs(render(tmp_path))}
    stored = [
        r for r in storage.list_articles(db) if not agencies.is_excluded(r["agency"])
    ]
    assert len(tabs["정부기관"]["articles"]) == len(stored)
    for article in tabs["정부기관"]["articles"]:
        assert article["link"].startswith("https://www.korea.kr/")
        assert article["published_at"] and article["agency"] and article["title"]


# --- 기관 체크박스 ----------------------------------------------------------

def government_tab(tmp_path) -> dict:
    return {t["category"]: t for t in read_tabs(render(tmp_path))}["정부기관"]


def test_부처가_구분별_가나다순으로_들어간다(tmp_path):
    groups = government_tab(tmp_path)["groups"]
    assert groups

    order = [agencies.GROUP_ORDER.index(g["group"]) for g in groups]
    assert order == sorted(order), "구분 순서가 어긋났습니다"

    for group in groups:
        names = [d["name"] for d in group["depts"]]
        assert names == sorted(names), f"{group['group']}가 가나다순이 아닙니다"


def test_지자체는_광역이_먼저_그다음_가나다순이다(tmp_path):
    tabs = {t["category"]: t for t in read_tabs(render(tmp_path))}
    groups = {g["group"]: [d["name"] for d in g["depts"]] for g in tabs[models.LOCAL]["groups"]}
    assert groups["서울"] == ["서울시", "강동구", "송파구"]
    assert groups["경기"] == ["경기도", "구리시", "성남시", "용인시", "하남시"]


def test_같은_묶음이_두_번_그려지지_않는다(tmp_path):
    """분야 목록에 이미 '기타'가 있는데 뒤에 또 붙이면 화면에 두 번 나온다."""
    for tab in read_tabs(render(tmp_path)):
        names = [g["group"] for g in tab["groups"]]
        assert len(names) == len(set(names)), f"{tab['category']} 탭에 중복 묶음: {names}"


def test_기관도_한_탭에_한_번만_나온다(tmp_path):
    for tab in read_tabs(render(tmp_path)):
        names = [d["name"] for g in tab["groups"] for d in g["depts"]]
        assert len(names) == len(set(names)), f"{tab['category']} 탭에 중복 기관: {names}"


def test_체크박스에_정렬용_필드가_새지_않는다(tmp_path):
    """rank는 정렬에만 쓰고 HTML로는 내보내지 않는다."""
    for tab in read_tabs(render(tmp_path)):
        for group in tab["groups"]:
            for dept in group["depts"]:
                assert set(dept) == {"name", "count", "parent"}


def test_보도자료가_없는_부처도_목록에_나온다(tmp_path):
    """수집된 기관만 보여 주면 그날 발표가 없던 부처는 고를 수 없게 된다."""
    listed = {d["name"] for g in government_tab(tmp_path)["groups"] for d in g["depts"]}
    assert set(agencies.MINISTRIES.values()) <= listed, "코드표 기관이 빠졌습니다"
    for name in ("통일부", "병무청", "원자력안전위원회", "국가보훈부"):
        assert name in listed


def test_기관_건수_합계가_기사_수와_같다(tmp_path):
    tab = government_tab(tmp_path)
    total = sum(d["count"] for g in tab["groups"] for d in g["depts"])
    assert total == len(tab["articles"])


def test_제외한_기관은_어디에도_나오지_않는다(tmp_path):
    tab = government_tab(tmp_path)
    listed = {d["name"] for g in tab["groups"] for d in g["depts"]}
    assert not (listed & agencies.EXCLUDED)
    assert not any(agencies.is_excluded(a["agency"]) for a in tab["articles"])


# --- UI 요소 ---------------------------------------------------------------

def test_기간_입력과_프리셋이_있다(tmp_path):
    html = render(tmp_path)
    assert 'id="from"' in html and 'id="to"' in html
    assert 'placeholder="YY.MM.DD"' in html
    for days in ("1", "7", "30", "0"):
        assert f'data-days="{days}"' in html


def test_검색어와_체크박스_UI가_있다(tmp_path):
    html = render(tmp_path)
    assert 'id="q"' in html
    assert 'id="depts"' in html
    assert 'id="checkAll"' in html and 'id="checkNone"' in html
    assert 'id="tabs"' in html


def test_부처_패널이_기본으로_펼쳐져_있다(tmp_path):
    assert 'id="deptBox" open' in render(tmp_path)


def test_기관_날짜_부서가_한_줄에_들어간다(tmp_path):
    """제목 아래 정보가 각각 줄을 차지하면 목록이 쓸데없이 길어진다."""
    html = render(tmp_path)
    assert 'class="meta-row"' in html
    assert 'class="lead"' not in html, "요약이 여전히 별도 문단으로 렌더됩니다"
    # 메타 행 안에 기관·날짜·부서가 순서대로 들어간다
    order = html.index('class="meta-row"')
    for cls in ('class="badge"', 'class="date"', 'class="dept"'):
        assert html.index(cls, order) > order


# --- 화면에 담는 범위 --------------------------------------------------------
#
# 화면 파일 하나에 전부 담는 구조라, 담는 양이 곧 여는 속도다.
# 휴대폰으로 여는 사람이 있으므로 여기를 느슨하게 두면 안 된다.

def test_오래된_것은_화면에서_뺀다():
    from datetime import date

    today = date(2026, 9, 17)
    rows = [
        {"published_at": "2026-09-01"},
        {"published_at": "2023-09-17"},  # 딱 경계 — 남는다
        {"published_at": "2023-09-16"},  # 하루 차이로 빠진다
        {"published_at": "2019-01-03"},
    ]
    kept = [r["published_at"] for r in dashboard.keep_recent(rows, today)]
    assert kept == ["2026-09-01", "2023-09-17"]


def test_날짜가_없으면_남겨_둔다():
    from datetime import date

    rows = [{"published_at": ""}, {"published_at": None}]
    assert len(dashboard.keep_recent(rows, date(2026, 9, 17))) == 2


def test_윤년_2월29일에도_날짜를_만들_수_있다():
    from datetime import date

    assert dashboard.cutoff_date(date(2028, 2, 29)) == "2025-02-28"


def test_긴_설명은_앞부분만_싣는다():
    """korea.kr 보도자료는 본문 전체가 딸려 온다. 평균 1,000자다."""
    body = "가" * 5000
    short = dashboard.shorten(body)
    assert len(short) == dashboard.SUMMARY_LIMIT + 1  # 말줄임표 한 글자
    assert short.endswith("…")


def test_짧은_설명은_그대로_둔다():
    """지자체·공공기관은 여기에 담당부서가 들어온다. 건드리면 안 된다."""
    assert dashboard.shorten("홍보담당관") == "홍보담당관"
    assert dashboard.shorten(None) == ""


def test_화면에_담는_기간을_적어_둔다(tmp_path):
    """보는 사람이 '왜 예전 게 없지' 하지 않도록."""
    assert f"최근 {dashboard.KEEP_YEARS}년치" in render(tmp_path)


def test_본문이_통째로_실리지_않는다(tmp_path):
    for tab in read_tabs(render(tmp_path)):
        for article in tab["articles"]:
            assert len(article["summary"]) <= dashboard.SUMMARY_LIMIT + 1


# --- 게시 폴더 --------------------------------------------------------------

def test_게시하면_첫화면과_검색차단과_지킬해제가_생긴다(tmp_path):
    out = dashboard.publish(build_db(tmp_path), tmp_path / "docs")
    assert (out / "index.html").exists()
    assert "Disallow: /" in (out / "robots.txt").read_text(encoding="utf-8")
    assert (out / ".nojekyll").exists(), "Jekyll이 파일을 빼먹을 수 있습니다"


def test_게시_폴더_이름은_docs다():
    """GitHub Pages가 'main 가지의 docs 폴더'를 사이트로 띄운다.

    이름을 바꾸면 친구들이 보던 주소가 그대로 죽는다.
    """
    assert dashboard.PUBLISH_DIR == "docs"


# --- 연구소: 목록 대신 바로가기 ------------------------------------------------
#
# 여섯 곳을 합쳐 한 달 22건이라 매일 훑을 칸이 아닌데, 게시판 구조는 제일
# 까다로웠다. 그래서 화면에서는 가는 길만 놓는다.

def _research_tab(tmp_path) -> dict:
    tabs = read_tabs(render(tmp_path))
    return next(t for t in tabs if t["category"] == models.RESEARCH)


def test_연구소는_기사_대신_바로가기를_담는다(tmp_path):
    tab = _research_tab(tmp_path)
    assert tab["kind"] == "links"
    assert tab["articles"] == []
    assert len(tab["links"]) >= 6


def test_바로가기마다_이름과_설명과_주소가_있다(tmp_path):
    for site in _research_tab(tmp_path)["links"]:
        assert site["name"] and site["note"] and site["group"]
        assert site["url"].startswith("https://")


def test_바로가기는_속페이지가_아니라_홈페이지로_간다(tmp_path):
    """게시판 주소는 개편 한 번에 죽는다. 홈페이지 주소가 오래 간다.

    한국어 페이지가 따로 있거나(쿠쉬먼앤드웨이크필드) 연구원이 본사와
    다른 주소를 쓰는 곳(주택금융연구원)만 예외로 한 칸 더 들어간다.
    """
    for site in _research_tab(tmp_path)["links"]:
        tail = site["url"].split("//", 1)[1].rstrip("/")
        assert "?" not in tail, f"{site['name']}에 검색 조건이 붙어 있습니다"
        assert tail.count("/") <= 2, f"{site['name']}이 너무 깊이 들어갑니다"


def test_바로가기도_묶음을_따른다(tmp_path):
    from govpress import research

    groups = {s["group"] for s in _research_tab(tmp_path)["links"]}
    assert groups <= set(research.LINK_GROUP_ORDER)


def test_바로가기가_묶음_순서대로_나온다(tmp_path):
    from govpress import research

    order = list(research.LINK_GROUP_ORDER)
    seen = [order.index(s["group"]) for s in _research_tab(tmp_path)["links"]]
    assert seen == sorted(seen), "묶음이 뒤섞여 나옵니다"


def test_한글_이름이_영문보다_먼저_온다(tmp_path):
    """국내 기관을 찾으러 오는 화면이다. KB·OECD가 위로 올라오면 안 된다."""
    links = [s for s in _research_tab(tmp_path)["links"] if s["group"] == "연구소"]
    korean = [i for i, s in enumerate(links) if s["name"][:1] >= "가"]
    latin = [i for i, s in enumerate(links) if s["name"][:1] < "가"]
    assert max(korean) < min(latin)


def test_탭_이름과_묶음_이름이_겹치지_않는다(tmp_path):
    """탭도 '연구소', 그 안의 묶음도 '연구소'면 무슨 말인지 알 수 없다."""
    tab = _research_tab(tmp_path)
    assert tab["label"] != tab["category"]
    assert tab["label"] not in {s["group"] for s in tab["links"]}


def test_같은_기관을_두_번_넣지_않는다(tmp_path):
    links = _research_tab(tmp_path)["links"]
    assert len({s["name"] for s in links}) == len(links)
    assert len({s["url"] for s in links}) == len(links)


def test_못_붙였던_기관도_바로가기에는_넣는다(tmp_path):
    """긁지 않으니 파서가 필요 없다. 한국행정연구원이 그런 경우다."""
    names = [s["name"] for s in _research_tab(tmp_path)["links"]]
    assert "한국행정연구원" in names


def test_탭_숫자가_바로가기_개수와_같다(tmp_path):
    tab = _research_tab(tmp_path)
    assert tab["agencies"] == len(tab["links"])


def test_수집기는_지우지_않고_남겨_둔다():
    """생각이 바뀌면 화면만 되돌리면 되도록."""
    from govpress import research

    assert len(research.SITES) >= 6


def test_화면에_없는_분류는_건수에_세지_않는다(tmp_path):
    """연구소를 화면에서 뺐으면 위쪽 '몇 건'에서도 빠져야 한다."""
    html_text = render(tmp_path)
    tabs = read_tabs(html_text)
    shown = sum(t["count"] for t in tabs)
    import re

    total = re.search(r"<b>([\d,]+)건</b>", html_text).group(1)
    assert int(total.replace(",", "")) == shown


def test_바로가기는_이름만_내놓는다(tmp_path):
    """마흔 곳이 넘는다. 설명까지 깔면 화면을 다 먹는다."""
    html_text = render(tmp_path)
    assert 'class="link-chip"' in html_text
    assert 'class="link-card"' not in html_text, "카드 방식이 남아 있습니다"


def test_설명은_풍선말로_남는다(tmp_path):
    """이름만 보이더라도 무엇을 내는 곳인지 알 길은 있어야 한다."""
    html_text = render(tmp_path)
    assert "site.note + ' — ' + domainOf(site.url)" in html_text
    assert "title=" in html_text
