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
    from govpress import agencies, local_gov

    tabs = {t["category"]: t for t in read_tabs(render(tmp_path))}
    assert tabs["정부기관"]["agencies"] == len(agencies.MINISTRIES)
    assert tabs["지자체"]["agencies"] == len(local_gov.SITES)
    assert tabs["공공기관"]["agencies"] == 0
    assert tabs["연구소"]["agencies"] == 0

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
