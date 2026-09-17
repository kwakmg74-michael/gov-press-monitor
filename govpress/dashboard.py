"""수집된 보도자료를 단일 HTML 대시보드로 렌더링한다.

외부 의존성이 없는 파일 하나로 떨어지므로, 더블클릭으로 열거나
사내 공유 폴더에 그대로 올려도 동작한다.

대시보드가 제공하는 것:
- 정부부처 체크박스 — 조직도 구분(부/처/청/위원회)별로 묶고 가나다순
- 검색 기간 YY.MM.DD ~ YY.MM.DD (+ 오늘/7일/30일 프리셋)
- 제목·요약·기관 검색어 (결과에서 하이라이트)
"""

from __future__ import annotations

import html
import json
from datetime import date, datetime
from pathlib import Path

from . import agencies, local_gov, models, public_org, research, storage


# 분류별 명단표를 가진 모듈. 정부기관은 코드표(agencies)라 따로 다룬다.
_MODULES = {
    models.LOCAL: local_gov,
    models.PUBLIC: public_org,
    models.RESEARCH: research,
}


def _unique(names: list[str]) -> list[str]:
    """순서를 지키면서 중복을 걸러 낸다."""
    seen: list[str] = []
    for name in names:
        if name not in seen:
            seen.append(name)
    return seen


def _dept_groups(rows, category: str) -> list[dict]:
    """한 분류 안에서 체크박스에 깔 기관 명단.

    정부기관은 코드표의 전체 명단을 항상 깔고 건수만 얹는다(없으면 0).
    수집된 기관만 보여 주면 그날 발표가 없던 부처는 고를 수 없게 되기 때문이다.
    다른 분류는 아직 명단표가 없으므로 데이터에 등장한 기관으로 만든다.
    """
    counts: dict[str, int] = {}
    for row in rows:
        name = row["agency"]
        if name:
            counts[name] = counts.get(name, 0) + 1

    buckets: dict[str, list[dict]] = {}
    order: list[str] = list(agencies.GROUP_ORDER)
    notes: dict[str, str] = {}

    module = _MODULES.get(category)
    if module is not None:
        # 지자체는 지역(서울/경기), 그 밖에는 분야로 묶는다.
        # 분야 목록에 이미 '기타'가 있을 수 있으므로 중복을 걸러 낸다 —
        # 그대로 두면 같은 묶음이 화면에 두 번 그려진다.
        order = _unique(list(module.GROUP_ORDER) + [agencies.OTHER_GROUP])
        for group, sites in module.sites_by_group():
            for site in sites:
                buckets.setdefault(group, []).append(
                    {
                        "name": site.name,
                        "count": counts.pop(site.name, 0),
                        "parent": "",
                        # 대표 기관(광역자치단체)이 그 묶음 맨 앞에 온다.
                        "rank": 0 if site.primary else 1,
                    }
                )

    if category == models.GOVERNMENT:
        notes = dict(agencies.GROUP_DESCRIPTIONS)
        for ministry in agencies.all_ministries():
            buckets.setdefault(ministry.group, []).append(
                {
                    "name": ministry.name,
                    "count": counts.pop(ministry.name, 0),
                    "parent": ministry.parent,
                }
            )

    # 명단표에 없는 기관(신설되었거나 아직 명단을 만들지 않은 분류)
    for name in sorted(counts):
        buckets.setdefault(agencies.OTHER_GROUP, []).append(
            {"name": name, "count": counts[name], "parent": ""}
        )

    # rank가 없으면 1로 봐서, 결국 이름순이 된다. 지자체만 광역을 0으로 올린다.
    groups = []
    for group in order:
        if group not in buckets:
            continue
        depts = sorted(buckets[group], key=lambda d: (d.get("rank", 1), d["name"]))
        for dept in depts:
            dept.pop("rank", None)
        groups.append({"group": group, "note": notes.get(group, ""), "depts": depts})
    return groups


def _roster_size(category: str) -> int:
    """그 분류에서 수집할 수 있는 기관이 몇 곳인지.

    탭에 보여 주는 숫자는 이 값이다. 기사 건수는 날마다 출렁이지만
    '몇 곳을 훑고 있는가'는 그 탭이 무엇을 덮는지 말해 준다.
    """
    if category == models.GOVERNMENT:
        return len(agencies.MINISTRIES)
    module = _MODULES.get(category)
    if module is not None:
        # 게시판이 아니라 기관을 센다. 한 기관에 게시판이 여럿이어도 한 곳이다.
        return len(module.agency_names())
    return 0


# 화면에 담는 기간. 이보다 오래된 것은 DB에 그대로 두고 화면에서만 뺀다.
KEEP_YEARS = 3

# 한 건에 딸린 설명을 이만큼만 싣는다.
#
# korea.kr에서 오는 정부기관 보도자료는 **본문 전체**가 딸려 온다 — 평균
# 1,000자, 긴 것은 1만 자가 넘는다. 그대로 실으면 화면 파일이 3MB를
# 넘어서(전체의 95%가 이 본문이다) 휴대폰에서 열기 버거워진다.
#
# 보도자료는 첫 문단에 누가·무엇을 했는지가 들어가므로, 목록에서 훑고
# 검색하는 데는 앞부분이면 족하다. 본문 전체는 제목을 눌러 원문에서 본다.
SUMMARY_LIMIT = 200


def cutoff_date(today: date | None = None) -> str:
    """이 날짜보다 오래된 것은 화면에 싣지 않는다.

    2월 29일이 있는 해를 빼면 존재하지 않는 날짜가 되므로 하루 물린다.
    """
    today = today or date.today()
    try:
        first = today.replace(year=today.year - KEEP_YEARS)
    except ValueError:  # 2월 29일
        first = today.replace(year=today.year - KEEP_YEARS, day=28)
    return first.isoformat()


def shorten(text: str | None, limit: int = SUMMARY_LIMIT) -> str:
    """긴 설명을 앞부분만 남긴다. 잘렸다는 것을 말줄임표로 알린다."""
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "…"


def keep_recent(rows, today: date | None = None) -> list:
    """최근 KEEP_YEARS년치만 남긴다. 날짜가 없는 건 남겨 둔다."""
    first = cutoff_date(today)
    return [r for r in rows if not r["published_at"] or r["published_at"] >= first]


def _tabs(db_path) -> list[dict]:
    """상단 탭 하나하나의 데이터. 아직 수집기가 없는 분류도 자리를 지킨다."""
    tabs = []
    for category in models.CATEGORIES:
        rows = keep_recent(
            [
                r
                for r in storage.list_articles(db_path, category=category)
                if not agencies.is_excluded(r["agency"])
            ]
        )
        tabs.append(
            {
                "category": category,
                "count": len(rows),
                "agencies": _roster_size(category),
                "articles": [
                    {
                        "title": r["title"],
                        "agency": r["agency"],
                        "link": r["link"],
                        "published_at": r["published_at"],
                        "summary": shorten(r["summary"]),
                    }
                    for r in rows
                ],
                "groups": _dept_groups(rows, category),
            }
        )
    return tabs


DEFAULT_OUTPUT = "dashboard.html"

# 게시용 폴더. GitHub Pages가 "main 가지의 docs 폴더"를 그대로 사이트로
# 띄워 주기 때문에 이 이름이어야 한다. 폴더 이름을 바꾸면 주소가 죽는다.
PUBLISH_DIR = "docs"

# 자동 수집이 도는 시각. 작업 스케줄러(자동수집_등록용.xml)와 맞춰 둔다.
# 한쪽만 고치면 화면에 적힌 안내와 실제 동작이 어긋난다.
UPDATE_TIMES = ("오전 10시", "오후 2시", "오후 5시")

# 검색엔진에 뜨지 않게 한다. 사무실에서 돌려 보는 자료 모음이지
# 인터넷에서 찾아지라고 만든 페이지가 아니다.
_ROBOTS = "User-agent: *\nDisallow: /\n"

_TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>보도자료 모니터</title>
<style>
  :root {
    --bg: #f7f7f5;
    --surface: #ffffff;
    --sunken: #efeeea;
    --border: #e4e2dd;
    --text: #1f1e1c;
    --muted: #6b6862;
    --accent: #b4552d;
    --accent-soft: #f2e6e0;
    --danger: #b03434;
    --focus: #2f6f9f;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --bg: #191817;
      --surface: #232120;
      --sunken: #1f1d1c;
      --border: #38352f;
      --text: #eceae6;
      --muted: #a39e95;
      --accent: #e08a5f;
      --accent-soft: #33261f;
      --danger: #e08080;
      --focus: #7bb6e0;
    }
  }
  :root[data-theme="dark"] {
    --bg: #191817;
    --surface: #232120;
    --sunken: #1f1d1c;
    --border: #38352f;
    --text: #eceae6;
    --muted: #a39e95;
    --accent: #e08a5f;
    --accent-soft: #33261f;
    --danger: #e08080;
    --focus: #7bb6e0;
  }

  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: "Pretendard", -apple-system, BlinkMacSystemFont, "Segoe UI",
                 "Malgun Gothic", "Apple SD Gothic Neo", sans-serif;
    line-height: 1.55;
    -webkit-font-smoothing: antialiased;
  }
  .wrap { max-width: 980px; margin: 0 auto; padding: 32px 20px 80px; }

  header {
    margin-bottom: 20px;
    display: flex; justify-content: space-between;
    align-items: flex-start; gap: 16px; flex-wrap: wrap;
  }
  .head-right {
    display: flex; flex-direction: column;
    align-items: flex-end; gap: 7px;
    text-align: right;
    flex-shrink: 0;  /* 가운데 요약이 길어도 안내 문구가 눌리지 않게 */
  }
  .auto-note {
    font-size: 12px; color: var(--muted);
    margin: 0; line-height: 1.5;
  }
  .auto-note b { color: var(--text); font-weight: 600; }
  /* 담는 기간 안내. 요약 옆에 작게 붙인다 */
  .keep-note {
    display: inline-block; margin-left: 4px;
    padding: 1px 7px; border-radius: 999px;
    border: 1px solid var(--line);
    font-size: 11.5px; color: var(--muted); cursor: help;
  }
  #refresh { font-size: 12.5px; padding: 6px 12px; }
  #refresh:hover { border-color: var(--accent); color: var(--accent); }
  /* 좁은 화면에서는 아래로 흐르게 두고 왼쪽 정렬로 되돌린다 */
  @media (max-width: 620px) {
    .head-right { align-items: flex-start; text-align: left; }
  }
  h1 { font-size: 22px; margin: 0 0 6px; letter-spacing: -0.01em; }
  .meta { color: var(--muted); font-size: 13px; margin: 0; }
  .meta b { color: var(--text); font-weight: 600; }

  .tabs {
    display: flex; gap: 2px; flex-wrap: wrap;
    border-bottom: 1px solid var(--border);
    margin-bottom: 12px;
  }
  .tab {
    font: inherit; font-size: 14px; font-weight: 600;
    padding: 9px 14px;
    border: none; border-bottom: 2px solid transparent;
    border-radius: 8px 8px 0 0;
    background: none; color: var(--muted);
    cursor: pointer;
    margin-bottom: -1px;
  }
  .tab:hover { color: var(--text); background: var(--sunken); border-color: transparent; }
  .tab[aria-selected="true"] {
    color: var(--accent); border-bottom-color: var(--accent);
  }
  .tab .n {
    font-size: 11.5px; font-weight: 400; margin-left: 5px;
    color: var(--muted); font-variant-numeric: tabular-nums;
  }
  .tab.empty-tab { color: var(--muted); opacity: 0.6; }

  .panel {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 10px;
  }
  .field { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .field + .field { margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border); }
  .label {
    font-size: 12px; font-weight: 700; color: var(--muted);
    letter-spacing: 0.03em; min-width: 62px;
  }

  input[type="search"], input[type="text"] {
    font: inherit; font-size: 14px;
    padding: 8px 12px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--bg);
    color: var(--text);
  }
  input[type="search"] { flex: 1 1 280px; min-width: 0; }
  input.date { width: 122px; text-align: center; font-variant-numeric: tabular-nums; }
  input.date.invalid { border-color: var(--danger); color: var(--danger); }
  .tilde { color: var(--muted); }

  button {
    font: inherit; font-size: 13px;
    padding: 7px 12px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--bg);
    color: var(--text);
    cursor: pointer;
  }
  button:hover { border-color: var(--accent); color: var(--accent); }
  button.link {
    border: none; background: none; padding: 4px 6px;
    color: var(--muted); text-decoration: underline; text-underline-offset: 3px;
  }
  button.link:hover { color: var(--accent); }

  input:focus-visible, button:focus-visible, a:focus-visible, summary:focus-visible {
    outline: 2px solid var(--focus); outline-offset: 2px;
  }

  details.depts { margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border); }
  details.depts > summary {
    cursor: pointer; list-style: none;
    display: flex; align-items: center; gap: 8px;
    font-size: 12px; font-weight: 700; color: var(--muted); letter-spacing: 0.03em;
  }
  details.depts > summary::-webkit-details-marker { display: none; }
  details.depts > summary::before { content: "▸"; font-size: 11px; }
  details.depts[open] > summary::before { content: "▾"; }
  .dept-summary { font-weight: 400; color: var(--text); }
  .dept-actions { margin-left: auto; display: flex; gap: 2px; }

  /* 높이를 제한하지 않는다. 스크롤바가 생기면 오히려 훑기 불편하다. */
  .dept-scroll { margin-top: 8px; }
  .group + .group { margin-top: 10px; }
  .group-label {
    font-size: 11.5px; font-weight: 700; color: var(--muted);
    letter-spacing: 0.04em;
    padding: 0 0 4px 2px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 4px;
  }
  .group-label .n { font-weight: 400; }

  /* 격자로 깔아야 이름이 세로로 줄이 맞아서 눈으로 훑기 좋다. */
  .chips {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(196px, 1fr));
    gap: 1px 4px;
  }
  .chip {
    display: flex; align-items: center; gap: 7px;
    font-size: 13px; line-height: 1.35;
    padding: 3px 8px;
    border: 1px solid transparent;
    border-radius: 7px;
    cursor: pointer;
    user-select: none;
    min-width: 0;
  }
  .chip:hover { background: var(--sunken); }
  .chip input { accent-color: var(--accent); margin: 0; flex: none; }
  .chip .nm { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .chip .n {
    margin-left: auto; flex: none;
    color: var(--muted); font-size: 11.5px;
    font-variant-numeric: tabular-nums;
  }
  .chip:has(input:checked) {
    background: var(--accent-soft);
    border-color: var(--accent);
    color: var(--accent);
    font-weight: 600;
  }
  .chip:has(input:checked) .n { color: var(--accent); }
  .chip.zero { color: var(--muted); }
  .chip.zero .n { opacity: 0.55; }

  .count { font-size: 13px; color: var(--muted); padding: 4px 2px 12px; }

  ol.list { list-style: none; margin: 0; padding: 0; }
  .day {
    font-size: 12px; font-weight: 700; letter-spacing: 0.04em;
    color: var(--muted);
    padding: 16px 2px 6px;
  }
  .item {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 11px 14px;
    margin-bottom: 6px;
  }
  .item:hover { border-color: var(--accent); }
  .item a.title {
    color: var(--text); text-decoration: none;
    font-size: 15.5px; font-weight: 600; letter-spacing: -0.005em;
    line-height: 1.4;
    display: block; margin-bottom: 4px;
  }
  .item a.title:hover { color: var(--accent); text-decoration: underline; text-underline-offset: 3px; }
  .item a.title::after { content: " ↗"; color: var(--muted); font-weight: 400; }
  /* 기관·날짜·부서를 한 줄에 둔다. 각각 줄을 차지하면 목록이 길어지기만 한다. */
  .meta-row {
    display: flex; align-items: center; gap: 9px;
    min-width: 0;
  }
  .badge {
    flex: none;
    font-size: 11.5px; font-weight: 600;
    color: var(--accent); background: var(--accent-soft);
    padding: 2px 8px; border-radius: 999px;
  }
  .date {
    flex: none;
    font-size: 12px; color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  .dept {
    font-size: 12.5px; color: var(--muted);
    min-width: 0;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  mark { background: var(--accent-soft); color: inherit; padding: 0 1px; border-radius: 2px; }
  .empty { padding: 48px 8px; text-align: center; color: var(--muted); }
  footer { margin-top: 40px; font-size: 12px; color: var(--muted); }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>보도자료 모니터</h1>
    <p class="meta">
      <b>__TOTAL__건</b> · __AGENCY_COUNT__개 기관 · __RANGE__
      <span class="keep-note" title="더 오래된 자료도 모아 두었지만, 화면이 무거워지지 않도록 최근 것만 싣습니다.">최근 __KEEP_YEARS__년치</span>
      <br>마지막 수집 __LAST_RUN__ <span id="sourceNote"></span>
    </p>
    <div class="head-right">
      <p class="auto-note"><b>__UPDATE_TIMES__</b>에<br>자동으로 업데이트됩니다</p>
      <button id="refresh" type="button"
              title="이 페이지를 다시 불러옵니다. 마지막 수집 이후 새로 올라온 것이 있으면 반영됩니다.">
        새로고침
      </button>
    </div>
  </header>

  <nav class="tabs" id="tabs" role="tablist"></nav>

  <div class="panel">
    <div class="field">
      <span class="label">검색어</span>
      <input type="search" id="q" placeholder="제목·요약·기관에서 찾기 (예: 부동산, 재개발)" autocomplete="off">
    </div>

    <div class="field">
      <span class="label">기간</span>
      <input type="text" class="date" id="from" placeholder="YY.MM.DD" autocomplete="off" inputmode="numeric">
      <span class="tilde">~</span>
      <input type="text" class="date" id="to" placeholder="YY.MM.DD" autocomplete="off" inputmode="numeric">
      <button type="button" data-days="1">오늘</button>
      <button type="button" data-days="7">7일</button>
      <button type="button" data-days="30">30일</button>
      <button type="button" data-days="0">전체</button>
    </div>

    <details class="depts" id="deptBox" open>
      <summary>
        <span id="deptTitle">정부부처</span> <span class="dept-summary" id="deptSummary">전체</span>
        <span class="dept-actions">
          <button type="button" class="link" id="checkAll">전체선택</button>
          <button type="button" class="link" id="checkNone">해제</button>
        </span>
      </summary>
      <div class="dept-scroll" id="depts"></div>
    </details>
  </div>

  <div class="count" id="count"></div>
  <ol class="list" id="list"></ol>

  <footer>제목을 누르면 해당 보도자료 원문이 새 탭에서 열립니다.</footer>
</div>

<script id="data" type="application/json">__DATA__</script>
<script>
(function () {
  /* 데이터는 분류(탭)별로 나뉘어 들어온다:
     [{category, count, articles: [...], groups: [{group, note, depts:[...]}]}] */
  var TABS = JSON.parse(document.getElementById('data').textContent);

  var SOURCE_NOTES = {
    '정부기관': '· 출처 대한민국 정책브리핑(korea.kr)'
  };

  var tabsEl = document.getElementById('tabs');
  var listEl = document.getElementById('list');
  var countEl = document.getElementById('count');
  var qEl = document.getElementById('q');
  var fromEl = document.getElementById('from');
  var toEl = document.getElementById('to');
  var deptsEl = document.getElementById('depts');
  var deptTitleEl = document.getElementById('deptTitle');
  var deptSummaryEl = document.getElementById('deptSummary');
  var sourceNoteEl = document.getElementById('sourceNote');

  // 이 화면은 만들어 둔 파일이라, 수집이 새로 돌았는지 보려면 다시 받아야 한다.
  // 버튼이 수집을 시키는 것은 아니다 - 올라와 있는 최신 화면을 가져올 뿐이다.
  document.getElementById('refresh').addEventListener('click', function () {
    this.textContent = '불러오는 중...';
    this.disabled = true;
    location.reload();
  });
  var panelEl = document.querySelector('.panel');

  var active = 0;

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  /* ---------- 탭 ---------- */

  TABS.forEach(function (tab, i) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'tab' + (tab.agencies ? '' : ' empty-tab');
    btn.setAttribute('role', 'tab');
    btn.setAttribute('aria-selected', i === 0 ? 'true' : 'false');
    btn.innerHTML = esc(tab.category) + '<span class="n">' + tab.agencies + '곳</span>';
    btn.addEventListener('click', function () { selectTab(i); });
    tabsEl.appendChild(btn);
  });

  function selectTab(i) {
    active = i;
    [].forEach.call(tabsEl.children, function (btn, n) {
      btn.setAttribute('aria-selected', n === i ? 'true' : 'false');
    });
    var tab = TABS[i];
    deptTitleEl.textContent = tab.category === '정부기관' ? '정부부처' : '기관';
    sourceNoteEl.textContent = SOURCE_NOTES[tab.category] || '';
    panelEl.hidden = !tab.count;
    buildDepts(tab);
    render();
  }

  /* ---------- 기관 체크박스 ---------- */

  var deptCounts = {};

  function buildDepts(tab) {
    deptsEl.innerHTML = '';
    deptCounts = {};
    var index = 0;

    tab.groups.forEach(function (group) {
      group.depts.forEach(function (d) { deptCounts[d.name] = d.count; });

      var section = document.createElement('div');
      section.className = 'group';

      /* 묶음이 하나뿐이면 제목이 오히려 군더더기다. */
      if (tab.groups.length > 1) {
        var heading = document.createElement('div');
        heading.className = 'group-label';
        heading.innerHTML = esc(group.group) + ' <span class="n">' + group.depts.length + '곳'
          + (group.note ? ' · ' + esc(group.note) : '') + '</span>';
        section.appendChild(heading);
      }

      var grid = document.createElement('div');
      grid.className = 'chips';
      group.depts.forEach(function (dept) {
        var id = 'dept' + (index++);
        var label = document.createElement('label');
        label.className = dept.count ? 'chip' : 'chip zero';
        label.htmlFor = id;
        label.title = dept.parent ? dept.name + ' — ' + dept.parent + ' 소속' : dept.name;
        label.innerHTML = '<input type="checkbox" id="' + id + '" value="' + esc(dept.name) + '">'
          + '<span class="nm">' + esc(dept.name) + '</span>'
          + '<span class="n">' + dept.count + '</span>';
        grid.appendChild(label);
      });
      section.appendChild(grid);
      deptsEl.appendChild(section);
    });
  }

  function checkedDepts() {
    return [].slice.call(deptsEl.querySelectorAll('input:checked')).map(function (c) { return c.value; });
  }

  function setAll(checked) {
    [].forEach.call(deptsEl.querySelectorAll('input'), function (c) { c.checked = checked; });
    render();
  }

  document.getElementById('checkAll').addEventListener('click', function (e) {
    e.preventDefault(); setAll(true);
  });
  document.getElementById('checkNone').addEventListener('click', function (e) {
    e.preventDefault(); setAll(false);
  });
  deptsEl.addEventListener('change', render);

  /* ---------- 날짜 ---------- */

  /* 'YY.MM.DD' / 'YYYY-MM-DD' / '20260908' 을 'YYYY-MM-DD'로. 못 읽으면 null. */
  function parseDate(text) {
    var s = String(text || '').trim();
    if (!s) return '';
    var m = s.match(/^(\d{2}|\d{4})[.\-\/](\d{1,2})[.\-\/](\d{1,2})$/)
         || s.match(/^(\d{4})(\d{2})(\d{2})$/);
    if (!m) return null;
    var y = m[1].length === 2 ? 2000 + parseInt(m[1], 10) : parseInt(m[1], 10);
    var mo = parseInt(m[2], 10), d = parseInt(m[3], 10);
    if (mo < 1 || mo > 12 || d < 1 || d > 31) return null;
    return y + '-' + String(mo).padStart(2, '0') + '-' + String(d).padStart(2, '0');
  }

  function toISO(dateObj) {
    return dateObj.getFullYear() + '-'
      + String(dateObj.getMonth() + 1).padStart(2, '0') + '-'
      + String(dateObj.getDate()).padStart(2, '0');
  }

  function fmt(iso) { return iso.slice(2).replace(/-/g, '.'); }

  [].forEach.call(document.querySelectorAll('button[data-days]'), function (btn) {
    btn.addEventListener('click', function () {
      var days = parseInt(btn.dataset.days, 10);
      if (!days) { fromEl.value = ''; toEl.value = ''; }
      else {
        var end = new Date();
        var start = new Date();
        start.setDate(start.getDate() - (days - 1));
        fromEl.value = fmt(toISO(start));
        toEl.value = fmt(toISO(end));
      }
      render();
    });
  });

  /* ---------- 목록 ---------- */

  function highlight(text, term) {
    var safe = esc(text);
    if (!term) return safe;
    var pattern = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return safe.replace(new RegExp(pattern, 'gi'), function (m) { return '<mark>' + m + '</mark>'; });
  }

  function weekday(iso) {
    var names = ['일', '월', '화', '수', '목', '금', '토'];
    var d = new Date(iso + 'T00:00:00');
    return isNaN(d) ? '' : ' (' + names[d.getDay()] + ')';
  }

  function render() {
    var tab = TABS[active];
    var articles = tab.articles;

    if (!articles.length) {
      countEl.textContent = '';
      listEl.innerHTML = '<li class="empty">' + esc(tab.category)
        + ' 수집기는 아직 준비되지 않았습니다.</li>';
      return;
    }

    var term = qEl.value.trim();
    var lower = term.toLowerCase();

    var from = parseDate(fromEl.value);
    var to = parseDate(toEl.value);
    fromEl.classList.toggle('invalid', from === null);
    toEl.classList.toggle('invalid', to === null);
    if (from === null) from = '';
    if (to === null) to = '';
    if (from && to && from > to) { var swap = from; from = to; to = swap; }

    var picked = checkedDepts();
    var pickedSet = {};
    picked.forEach(function (n) { pickedSet[n] = true; });

    deptSummaryEl.textContent = picked.length
      ? (picked.length <= 3 ? picked.join(', ') : picked.length + '곳 선택')
      : '전체';

    var rows = articles.filter(function (a) {
      if (picked.length && !pickedSet[a.agency]) return false;
      if (from && a.published_at < from) return false;
      if (to && a.published_at > to) return false;
      if (!lower) return true;
      return (a.title + ' ' + a.summary + ' ' + a.agency).toLowerCase().indexOf(lower) !== -1;
    });

    countEl.textContent = rows.length
      ? rows.length + '건 표시 중 (' + esc(tab.category) + ' 전체 ' + articles.length + '건)'
      : '';

    if (!rows.length) {
      var hint = picked.length && picked.every(function (n) { return !deptCounts[n]; })
        ? '선택한 기관은 아직 수집된 보도자료가 없습니다. <br>수집할 때 --dept 로 지정하거나 기간을 넓혀 보세요.'
        : '조건에 맞는 보도자료가 없습니다.';
      listEl.innerHTML = '<li class="empty">' + hint + '</li>';
      return;
    }

    var out = '';
    var currentDay = null;
    rows.forEach(function (a) {
      if (a.published_at !== currentDay) {
        currentDay = a.published_at;
        out += '<li class="day">' + esc(currentDay) + weekday(currentDay) + '</li>';
      }
      out += '<li class="item">'
        + '<a class="title" href="' + esc(a.link) + '" target="_blank" rel="noopener noreferrer">'
        + highlight(a.title, term) + '</a>'
        + '<div class="meta-row">'
        + '<span class="badge">' + highlight(a.agency, term) + '</span>'
        + '<span class="date">' + esc(a.published_at) + '</span>'
        + (a.summary ? '<span class="dept" title="' + esc(a.summary) + '">'
             + highlight(a.summary, term) + '</span>' : '')
        + '</div>'
        + '</li>';
    });
    listEl.innerHTML = out;
  }

  [qEl, fromEl, toEl].forEach(function (el) { el.addEventListener('input', render); });

  /* 데이터가 있는 첫 탭을 연다. */
  var firstWithData = TABS.findIndex(function (t) { return t.count > 0; });
  selectTab(firstWithData >= 0 ? firstWithData : 0);
})();
</script>
</script>
</body>
</html>
"""


def render(db_path: str = storage.DEFAULT_DB, output: str | Path = DEFAULT_OUTPUT) -> Path:
    """DB를 읽어 대시보드 HTML 파일을 만든다. 만들어진 경로를 돌려준다."""
    tabs = _tabs(db_path)
    info = dict(storage.stats(db_path))

    every = [a for tab in tabs for a in tab["articles"]]
    total = len(every)
    agency_count = len({a["agency"] for a in every if a["agency"]})
    days = [a["published_at"] for a in every if a["published_at"]]
    date_range = "-"
    if days:
        first_day, last_day = min(days), max(days)
        date_range = first_day if first_day == last_day else f"{first_day} ~ {last_day}"

    last_run = info.get("last_run") or ""
    last_run = last_run.replace("T", " ") if last_run else datetime.now().strftime("%Y-%m-%d %H:%M")

    document = (
        _TEMPLATE.replace("__TOTAL__", f"{total:,}")
        .replace("__AGENCY_COUNT__", str(agency_count))
        .replace("__RANGE__", html.escape(date_range))
        .replace("__LAST_RUN__", html.escape(last_run))
        .replace("__UPDATE_TIMES__", html.escape(", ".join(UPDATE_TIMES)))
        .replace("__KEEP_YEARS__", str(KEEP_YEARS))
        .replace("__DATA__", json.dumps(tabs, ensure_ascii=False).replace("</", "<\\/"))
    )

    path = Path(output)
    path.write_text(document, encoding="utf-8")
    return path


def publish(db_path, folder=PUBLISH_DIR) -> Path:
    """인터넷에 올릴 폴더를 만든다.

    웹 호스팅은 폴더를 통째로 받고 `index.html`을 첫 화면으로 연다.
    그래서 대시보드를 그 이름으로 넣어 준다 — 파일 하나짜리 사이트다.

    이렇게 올려 두면 보는 사람은 설치할 게 없다. 주소만 열면 되고,
    기관을 추가해도 다음 수집·게시 때 저절로 반영된다.

    지금은 GitHub Pages로 띄운다. 이 폴더를 git에 올리면 그대로 사이트가
    된다 — 따로 올리는 도구도, 계정 한도도 없다.

    `.nojekyll`을 같이 둔다. GitHub Pages는 기본적으로 Jekyll이라는 도구를
    한 번 거치는데, 그게 밑줄로 시작하는 파일을 빼먹는다. 지금은 해당
    사항이 없지만, 들어가는 파일이 늘었을 때 조용히 빠지는 편이 더 나쁘다.
    """
    out = Path(folder)
    out.mkdir(parents=True, exist_ok=True)

    render(db_path, out / "index.html")
    (out / "robots.txt").write_text(_ROBOTS, encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return out
