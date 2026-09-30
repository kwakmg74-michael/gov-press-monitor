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
#
# 3개월치를 메우고 나니 8천 건이 넘어, 200자로는 화면이 5.7MB가 됐다.
# 그중 3.2MB가 이 요약이다. 120자로 줄여 1.2MB를 덜었다. 검색이 닿는
# 범위가 그만큼 좁아지지만, 리드 문장은 대개 여기 안에 들어온다.
SUMMARY_LIMIT = 120

# 한 번에 그리는 줄 수.
#
# 거르지 않으면 정부기관 한 탭이 8천 줄이다. 그걸 통째로 그리면 화면이
# 멎은 것처럼 몇 초를 먹는다 — 파일이 무거운 것보다 이쪽이 더 답답하다.
# 처음 이만큼만 그리고, 더 보겠다면 그때 잇는다.
PAGE_ROWS = 300

# 아무 조건 없이 열었을 때 보여 주는 기간.
#
# 이건 '오늘 뭐 나왔나'를 훑는 화면이다. 석 달치를 통째로 펼쳐 놓으면
# 정작 어제 것을 찾기가 어렵다. 그래서 처음에는 최근 며칠만 깔고,
# 더 보겠다면 열흘씩 거슬러 올라간다.
#
# 다만 **검색어를 넣거나 기간을 직접 정하면 이 제한은 풀린다.** 안 그러면
# "1월부터 9월까지 수출입"을 찾았는데 9월 것만 나오는 꼴이 된다 —
# 실제로 그렇게 헤맨 적이 있다.
RECENT_DAYS = 10


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


# 목록을 긁지 않고 바로가기만 놓는 분류.
#
# 연구소는 여섯 곳을 합쳐 한 달 22건이라 매일 훑을 칸이 아닌데, 게시판
# 구조는 제일 까다로웠다. 들이는 품에 견줘 나오는 게 적어서 화면에서는
# 가는 길만 놓아 둔다. 수집기 자체는 `research.SITES`에 그대로 있다.
LINK_ONLY: dict[str, str] = {models.RESEARCH: "research"}

# 탭에 적는 이름. 저장할 때 쓰는 분류 이름과 화면에 적는 이름을 갈라 둔다.
#
# '연구소' 칸에 증권사·업계·협회가 함께 들어오면서, 탭 이름과 그 안의
# 묶음 이름이 둘 다 '연구소'가 되어 버렸다. 그래서 탭만 다르게 부른다.
TAB_LABELS: dict[str, str] = {models.RESEARCH: "연구·업계"}


def _link_tab(category: str) -> dict:
    """목록 대신 기관 바로가기만 담은 탭.

    검색·기간·기관 고르기는 이 탭에서 아무 일도 하지 않으므로 화면에서
    감춘다 — 눌러도 반응이 없는 칸이 하나 있으면 나머지 칸도 못 믿게 된다.
    """
    module = _MODULES[category]
    order = list(module.LINK_GROUP_ORDER)

    def place(link) -> tuple:
        group = order.index(link["group"]) if link["group"] in order else len(order)
        # 한글 이름을 먼저, 그다음 영문. 국내 기관을 찾으러 오는 화면이다.
        name = link["name"]
        return (group, 0 if name[:1] >= "가" else 1, name)

    return {
        "category": category,
        "label": TAB_LABELS.get(category, category),
        "kind": "links",
        "count": 0,
        "agencies": len(module.LINKS),
        "articles": [],
        "groups": [],
        "links": [dict(link) for link in sorted(module.LINKS, key=place)],
    }


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
        if category in LINK_ONLY:
            tabs.append(_link_tab(category))
            continue

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
                "label": TAB_LABELS.get(category, category),
                "kind": "list",
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

# 서비스 문의를 받을 곳.
#
# GitHub Pages에는 서버가 없어서 페이지 혼자서는 메일을 못 보낸다. 그래서
# 폼 내용을 받아 메일로 넘겨 주는 곳(web3forms.com)을 하나 거친다.
#
# 이 열쇠는 감출 것이 아니다 — 어차피 페이지 소스에 실려 나가고, 그쪽에서도
# 공개용으로 발급해 준다. 열쇠로 할 수 있는 일은 **아래 주소로 메일을 보내는
# 것뿐**이라, 새어 나가도 남의 손에 들어갈 것이 없다. 대신 받는 주소가
# 페이지에 드러나지 않아서 스팸 수집을 피할 수 있다.
#
# 열쇠를 비워 두면 문의 버튼이 아예 나오지 않는다 — 눌러도 아무 일이
# 없는 버튼을 내놓느니 없는 편이 낫다.
INQUIRY_KEY = "e527548b-8026-4e73-8e9a-b371e1510902"
INQUIRY_ENDPOINT = "https://api.web3forms.com/submit"

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
  /* hidden 을 붙인 것은 무조건 감춘다.
     브라우저 기본 규칙(display:none)보다 우리가 쓴 .stale{display:flex}가
     세서, 감췄다고 생각한 것이 그대로 보이는 일이 있었다. */
  [hidden] { display: none !important; }

  /* 화면이 낡았을 때 위에 뜨는 띠 */
  .stale {
    position: sticky; top: 0; z-index: 20;
    display: flex; align-items: center; justify-content: center;
    gap: 12px; flex-wrap: wrap;
    padding: 10px 16px;
    background: var(--accent); color: #fff;
    font-size: 13.5px; line-height: 1.5;
  }
  .stale b { font-weight: 700; }
  .stale button {
    flex: none; font-size: 13px; padding: 5px 14px;
    background: #fff; border-color: #fff; color: var(--accent);
    font-weight: 700;
  }
  .stale button:hover { background: var(--accent-soft); }

  #searchBtn {
    flex: none; font-size: 13px; padding: 8px 18px; font-weight: 600;
    border-color: var(--accent); color: var(--accent);
  }
  #searchBtn:hover { background: var(--accent-soft); }
  #resetBtn { flex: none; font-size: 13px; padding: 8px 14px; }

  .head-buttons { display: flex; gap: 6px; }
  #refresh, #askBtn { font-size: 12.5px; padding: 6px 12px; }
  #refresh:hover, #askBtn:hover { border-color: var(--accent); color: var(--accent); }

  /* --- 서비스 문의 --- */
  #askBox {
    width: min(460px, calc(100vw - 32px));
    padding: 0; border: 1px solid var(--border); border-radius: 12px;
    background: var(--surface); color: var(--text);
  }
  #askBox::backdrop { background: rgba(0, 0, 0, 0.45); }
  #askForm { display: flex; flex-direction: column; padding: 22px 22px 18px; }
  #askForm h2 { margin: 0 0 4px; font-size: 17px; letter-spacing: -0.01em; }
  .ask-lead { margin: 0 0 16px; font-size: 13px; color: var(--muted); line-height: 1.6; }
  #askForm label {
    font-size: 12px; font-weight: 700; color: var(--muted);
    margin-bottom: 5px;
  }
  #askForm input[type="text"], #askForm input[type="email"], #askForm textarea {
    font: inherit; font-size: 14px;
    width: 100%; box-sizing: border-box;
    padding: 9px 11px; margin-bottom: 14px;
    border: 1px solid var(--border); border-radius: 8px;
    background: var(--bg); color: var(--text);
  }
  #askForm textarea { resize: vertical; line-height: 1.6; }
  /* 봇 미끼. 화면에서 지우되 읽어 주는 프로그램에도 안 걸리게 한다. */
  #askForm .hp { position: absolute; left: -9999px; opacity: 0; }
  .ask-msg { margin: 0 0 12px; font-size: 13px; min-height: 19px; line-height: 1.5; }
  .ask-msg.bad { color: var(--danger); }
  .ask-msg.good { color: var(--accent); }
  .ask-buttons { display: flex; justify-content: flex-end; gap: 8px; }
  .ask-buttons button { font-size: 13.5px; padding: 8px 18px; }
  #askSend { border-color: var(--accent); color: var(--accent); font-weight: 600; }
  #askSend:hover { background: var(--accent-soft); }
  #askSend[disabled] { opacity: 0.5; cursor: default; }
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
  .group + .group { margin-top: 20px; }
  /* 묶음 제목. 어느 탭에서든 이 줄이 "여기서부터 다른 묶음"이라는
     유일한 표시라, 작게 두면 목록이 한 덩어리로 읽힌다. */
  .group-label {
    font-size: 15px; font-weight: 800; color: var(--text);
    letter-spacing: -0.01em;
    padding: 0 0 6px 2px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 8px;
  }
  /* 옆에 붙는 개수와 설명은 작고 흐리게 — 제목이 묻히면 안 된다. */
  .group-label .n { font-size: 12px; font-weight: 500; color: var(--muted); }

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
  .more-wrap { padding: 14px 2px 4px; text-align: center; }
  #moreBtn { font-size: 13.5px; padding: 9px 26px; }
  #moreBtn:hover { border-color: var(--accent); color: var(--accent); }

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

  /* 목록 대신 바로가기만 놓는 탭(연구·업계) */
  .links-note {
    font-size: 13px; color: var(--muted);
    padding: 4px 2px 14px; line-height: 1.6;
  }
  /* 묶음 사이를 충분히 띄운다. 이름만 늘어놓다 보니 어디서 갈리는지가
     여백으로만 보인다 — 빠듯하면 마흔 곳이 한 덩어리로 읽힌다. */
  .links > .group-label {
    margin-top: 34px; padding-top: 4px; padding-bottom: 8px;
  }
  .links > .group-label:first-child { margin-top: 4px; }
  /* 이름만 죽 늘어놓는다. 마흔 곳이 넘어서 카드로 깔면 화면을 다 먹는다.
     설명과 주소는 마우스를 올리면 나오는 풍선말로 옮겼다.

     칸 너비를 같게 맞춘 격자로 깐다. 이름 길이대로 흘려 놓으면 줄마다
     끝이 들쭉날쭉해서 눈이 어지럽다. 같은 자리에서 시작하면 훑기 쉽다. */
  .link-chips {
    display: grid; gap: 10px 10px;
    grid-template-columns: repeat(auto-fill, minmax(215px, 1fr));
    margin-bottom: 4px;
  }
  .link-chip {
    display: flex; align-items: center; gap: 8px;
    text-decoration: none;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 9px 13px;
    font-size: 13.5px; color: var(--text);
    min-width: 0;
  }
  .link-chip:hover { border-color: var(--accent); color: var(--accent); }
  /* 이름이 칸보다 길면 잘라 낸다. 전체 이름은 풍선말에 그대로 있다. */
  .link-chip .t {
    flex: 1; min-width: 0;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .link-chip .go { flex: none; color: var(--muted); font-size: 11px; }
  .link-chip:hover .go { color: var(--accent); }
  mark { background: var(--accent-soft); color: inherit; padding: 0 1px; border-radius: 2px; }
  .empty { padding: 48px 8px; text-align: center; color: var(--muted); }
  footer { margin-top: 40px; font-size: 12px; color: var(--muted); }
</style>
</head>
<body>
<div class="stale" id="staleBar" hidden>
  <span>새 보도자료가 올라왔습니다. 보고 계신 화면은 <b id="staleWhen"></b> 기준입니다.</span>
  <button type="button" id="staleReload">최신으로 보기</button>
</div>
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
      <div class="head-buttons">
        <button id="refresh" type="button"
                title="이 페이지를 다시 불러옵니다. 마지막 수집 이후 새로 올라온 것이 있으면 반영됩니다.">
          새로고침
        </button>
        <button id="askBtn" type="button" hidden
                title="빠진 기관, 잘못 나오는 자료, 있었으면 하는 기능을 알려 주세요.">
          서비스 문의
        </button>
      </div>
    </div>
  </header>

  <nav class="tabs" id="tabs" role="tablist"></nav>

  <div class="panel">
    <div class="field">
      <span class="label">검색어</span>
      <input type="search" id="q" placeholder="제목·요약·기관에서 찾기 (예: 부동산, 재개발)" autocomplete="off">
      <button type="button" id="searchBtn">검색</button>
      <button type="button" id="resetBtn" class="ghost"
              title="검색어·기간·기관 선택을 모두 비웁니다.">초기화</button>
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
  <div class="more-wrap" id="moreWrap" hidden>
    <button type="button" id="moreBtn"></button>
  </div>

  <p class="links-note" id="linksNote" hidden></p>
  <div class="links" id="links" hidden></div>

  <footer id="footNote">제목을 누르면 해당 보도자료 원문이 새 탭에서 열립니다.</footer>

  <dialog id="askBox">
    <form id="askForm" method="dialog">
      <h2>서비스 문의</h2>
      <p class="ask-lead">빠진 기관, 잘못 나오는 자료, 있었으면 하는 기능 — 무엇이든 좋습니다.</p>

      <label for="askTitle">제목</label>
      <input type="text" id="askTitle" name="제목" maxlength="100" required
             placeholder="예: 서울시 자치구를 더 넣어 주세요">

      <label for="askBody">내용</label>
      <textarea id="askBody" name="내용" rows="6" maxlength="2000" required
                placeholder="어떤 점이 불편하신지, 무엇이 있었으면 하는지 적어 주세요."></textarea>

      <label for="askMail">회신 이메일</label>
      <input type="email" id="askMail" name="회신이메일" maxlength="120" required
             placeholder="답을 받으실 주소">

      <!-- 봇이 자동으로 채우는 미끼. 사람 눈에는 안 보인다. -->
      <input type="checkbox" name="botcheck" class="hp" tabindex="-1" autocomplete="off">

      <p class="ask-msg" id="askMsg" role="status" aria-live="polite"></p>

      <div class="ask-buttons">
        <button type="button" id="askCancel" class="ghost">닫기</button>
        <button type="submit" id="askSend">보내기</button>
      </div>
    </form>
  </dialog>
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
  /*
    그냥 location.reload()를 하면 브라우저가 가지고 있던 예전 화면을 그대로
    다시 내놓는 일이 있다. 주소 끝에 지금 시각을 붙여 아예 다른 주소로
    가게 해서, 반드시 새로 받아 오게 한다.
  */
  function reloadFresh() {
    location.replace(location.pathname + '?t=' + Date.now());
  }

  document.getElementById('refresh').addEventListener('click', function () {
    this.textContent = '불러오는 중...';
    this.disabled = true;
    reloadFresh();
  });

  /* ---------- 화면이 낡았는지 ---------- */
  /*
    이 화면은 만들어질 때의 내용을 그대로 담은 파일 하나다. 탭을 열어 둔
    채로 며칠이 지나도 저절로 바뀌지 않아서, 옛날 목록을 최신인 줄 알고
    보게 된다. 실제로 그런 일이 있었다 — 닷새 전 화면을 보고 "업데이트가
    안 된다"고 여기신 것이다.

    그래서 곁에 둔 작은 표식 파일(stamp.txt)만 이따금 확인한다. 거기 적힌
    수집 시각이 이 화면의 것과 다르면 새 자료가 올라온 것이다.
    5MB짜리 화면을 다시 받는 대신 스무 글자만 받아 본다.
  */
  var MY_STAMP = '__LAST_RUN__';
  var staleBar = document.getElementById('staleBar');

  function checkStale() {
    /* 파일을 직접 열어 본 경우(file://)에는 확인할 방법이 없다 */
    if (location.protocol === 'file:' || !window.fetch) return;

    fetch('stamp.txt?t=' + Date.now(), { cache: 'no-store' })
      .then(function (res) { return res.ok ? res.text() : null; })
      .then(function (text) {
        if (!text) return;
        if (text.trim() !== MY_STAMP.trim()) {
          document.getElementById('staleWhen').textContent = MY_STAMP;
          staleBar.hidden = false;
        }
      })
      .catch(function () { /* 인터넷이 끊겼거나 표식이 없다. 조용히 넘어간다 */ });
  }

  document.getElementById('staleReload').addEventListener('click', reloadFresh);

  /* 탭으로 돌아올 때와 30분마다 확인한다 */
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) checkStale();
  });
  setInterval(checkStale, 30 * 60 * 1000);
  checkStale();
  var panelEl = document.querySelector('.panel');
  var moreWrapEl = document.getElementById('moreWrap');
  var moreBtnEl = document.getElementById('moreBtn');

  /* 지금 몇 줄까지 그려 두었는지. 조건이 바뀌면 처음으로 되돌린다. */
  var PAGE_ROWS = __PAGE_ROWS__;
  var shown = PAGE_ROWS;

  /* 아무 조건 없이 열었을 때 보여 주는 기간(일). '더 보기'로 늘어난다. */
  var RECENT_DAYS = __RECENT_DAYS__;
  var recentDays = RECENT_DAYS;
  var moreMode = '';
  var linksEl = document.getElementById('links');
  var linksNoteEl = document.getElementById('linksNote');
  var footNoteEl = document.getElementById('footNote');

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
    btn.innerHTML = esc(tab.label || tab.category) + '<span class="n">' + tab.agencies + '곳</span>';
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

    /* 바로가기만 있는 탭에서는 검색·기간·기관 칸을 통째로 감춘다.
       눌러도 아무 일이 없는 칸이 하나 있으면 나머지 칸도 못 믿게 된다. */
    var linksOnly = tab.kind === 'links';
    panelEl.hidden = linksOnly || !tab.count;
    countEl.hidden = linksOnly;
    listEl.hidden = linksOnly;
    /* 바로가기 탭에서는 '더 보기'도 할 일이 없다. 이 탭은 render()를
       거치지 않고 빠져나가므로 여기서 직접 감춰야 한다. */
    if (linksOnly) moreWrapEl.hidden = true;
    linksEl.hidden = !linksOnly;
    linksNoteEl.hidden = !linksOnly;
    footNoteEl.textContent = linksOnly
      ? '기관을 누르면 그 기관 홈페이지가 새 탭에서 열립니다.'
      : '제목을 누르면 해당 보도자료 원문이 새 탭에서 열립니다.';

    if (linksOnly) {
      drawLinks(tab);
      return;
    }

    buildDepts(tab);
    renderFromTop();
  }

  /* ---------- 바로가기 ---------- */

  function drawLinks(tab) {
    linksNoteEl.textContent =
      '연구보고서는 한 달에 스무 건 남짓이라 모아 두기보다 바로 찾아가는 편이 낫습니다. '
      + '기관 홈페이지가 새 탭에서 열립니다.';

    var groups = [];
    (tab.links || []).forEach(function (site) {
      var found = groups.filter(function (g) { return g.name === site.group; })[0];
      if (!found) { found = { name: site.group, sites: [] }; groups.push(found); }
      found.sites.push(site);
    });

    linksEl.innerHTML = groups.map(function (group) {
      var chips = group.sites.map(function (site) {
        /* 이름만 내놓고, 설명과 주소는 풍선말로 넘긴다. */
        var tip = site.note + ' — ' + domainOf(site.url);
        return '<a class="link-chip" href="' + esc(site.url) + '"'
          + ' target="_blank" rel="noopener noreferrer"'
          + ' title="' + esc(site.name) + ' — ' + esc(tip) + '">'
          + '<span class="t">' + esc(site.name) + '</span>'
          + '<span class="go">↗</span></a>';
      }).join('');

      /* 묶음이 하나뿐이면 제목이 오히려 군더더기다. 목록 탭과 같은 규칙. */
      var heading = groups.length > 1
        ? '<div class="group-label">' + esc(group.name)
            + ' <span class="n">' + group.sites.length + '곳</span></div>'
        : '';
      return heading + '<div class="link-chips">' + chips + '</div>';
    }).join('');
  }

  /* 주소에서 www. 를 뗀 도메인. 어디로 가는지 미리 보여 준다. */
  function domainOf(url) {
    return String(url).replace(/^https?:\/\//, '').replace(/^www\./, '').replace(/\/.*$/, '');
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
    renderFromTop();
  }

  document.getElementById('checkAll').addEventListener('click', function (e) {
    e.preventDefault(); setAll(true);
  });
  document.getElementById('checkNone').addEventListener('click', function (e) {
    e.preventDefault(); setAll(false);
  });
  deptsEl.addEventListener('change', renderFromTop);

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

  /* n일 전 날짜. 오늘이 0이다. */
  function daysAgo(n) {
    var d = new Date();
    d.setDate(d.getDate() - n);
    return toISO(d);
  }

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
      renderFromTop();
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

    /*
       검색어도 기간도 없으면 '오늘 뭐 나왔나'를 보러 온 것이다. 그때만
       최근 며칠로 자른다. 검색을 시작하면 제한을 풀어야 한다 — 안 그러면
       "1월부터 9월까지 수출입"을 찾았는데 최근 것만 나온다.
    */
    var browsing = !lower && !from && !to;
    var since = browsing ? daysAgo(recentDays - 1) : '';

    var rows = articles.filter(function (a) {
      if (picked.length && !pickedSet[a.agency]) return false;
      if (since && a.published_at < since) return false;
      if (from && a.published_at < from) return false;
      if (to && a.published_at > to) return false;
      if (!lower) return true;
      return (a.title + ' ' + a.summary + ' ' + a.agency).toLowerCase().indexOf(lower) !== -1;
    });

    /* 최근 며칠로 자르느라 빠진 것이 있는가 */
    var olderLeft = 0;
    if (since) {
      olderLeft = articles.filter(function (a) {
        if (picked.length && !pickedSet[a.agency]) return false;
        return a.published_at < since;
      }).length;
    }

    var scope = since ? '최근 ' + recentDays + '일 · ' : '';
    countEl.textContent = rows.length
      ? scope
        + (rows.length > shown
            ? shown.toLocaleString() + '건 보이는 중 · 조건에 맞는 것 '
              + rows.length.toLocaleString() + '건'
            : rows.length.toLocaleString() + '건')
        + ' (' + esc(tab.category) + ' 전체 ' + articles.length.toLocaleString() + '건)'
      : '';

    if (!rows.length) {
      var hint = picked.length && picked.every(function (n) { return !deptCounts[n]; })
        ? '선택한 기관은 아직 수집된 보도자료가 없습니다. <br>수집할 때 --dept 로 지정하거나 기간을 넓혀 보세요.'
        : '조건에 맞는 보도자료가 없습니다.';
      listEl.innerHTML = '<li class="empty">' + hint + '</li>';
      return;
    }

    /*
       거르지 않으면 정부기관 한 탭이 8천 줄이다. 통째로 그리면 화면이
       몇 초 멎는다. 앞에서부터 shown개만 그리고 나머지는 '더 보기'로 잇는다.
    */
    /*
       '더 보기'가 하는 일이 상황에 따라 다르다.

       - 최근 며칠만 깔아 둔 상태면 → 열흘 더 거슬러 올라간다
       - 이미 다 펼쳐졌는데 줄 수가 많아 잘렸으면 → 줄을 더 그린다
    */
    moreMode = '';
    if (rows.length > shown) {
      moreMode = 'rows';
      moreBtnEl.textContent = '더 보기 (남은 '
        + (rows.length - shown).toLocaleString() + '건)';
    } else if (olderLeft) {
      moreMode = 'days';
      moreBtnEl.textContent = '이전 ' + RECENT_DAYS + '일 더 보기 (예전 것 '
        + olderLeft.toLocaleString() + '건)';
    }
    moreWrapEl.hidden = !moreMode;

    rows = rows.slice(0, shown);

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

  /* 조건이 달라지면 다시 앞에서부터 보여 준다. 스무 번 '더 보기'를 누른
     상태로 검색어를 바꾸면, 엉뚱하게 많은 줄을 그리게 된다. */
  function renderFromTop() {
    shown = PAGE_ROWS;
    recentDays = RECENT_DAYS;
    render();
  }

  moreBtnEl.addEventListener('click', function () {
    if (moreMode === 'days') {
      recentDays += RECENT_DAYS;
    } else {
      shown += PAGE_ROWS;
    }
    render();
    /* 이어 붙인 첫 줄이 눈에 들어오게 */
    moreWrapEl.scrollIntoView({ block: 'nearest' });
  });

  /* 치는 대로 바로 걸러 준다. 버튼을 누를 필요는 없다. */
  [qEl, fromEl, toEl].forEach(function (el) {
    el.addEventListener('input', renderFromTop);
  });

  /*
    그래도 '검색' 버튼을 둔다. 치는 대로 걸러지는 줄 모르면 "누를 데가
    없네" 하고 멈추게 되고, 날짜를 한 글자씩 칠 때는 중간중간 결과가
    튀어서 제대로 걸린 건지 헷갈린다. 버튼과 엔터가 "이제 됐다"는
    매듭이 되어 준다.

    '초기화'는 진짜로 하는 일이 있다 — 검색어·기간·기관을 한 번에 비운다.
    지금까지는 기관만 '해제'로 풀 수 있었다.
  */
  document.getElementById('searchBtn').addEventListener('click', function () {
    renderFromTop();
    qEl.blur();  /* 휴대폰 자판을 내려 결과가 바로 보이게 */
  });

  qEl.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); renderFromTop(); qEl.blur(); }
  });

  document.getElementById('resetBtn').addEventListener('click', function () {
    qEl.value = '';
    fromEl.value = '';
    toEl.value = '';
    fromEl.classList.remove('invalid');
    toEl.classList.remove('invalid');
    setAll(true);   /* 기관은 '전체 선택'이 아무것도 안 거른 상태다 */
    qEl.focus();
  });

  /* ---------- 서비스 문의 ---------- */
  /*
    GitHub Pages에는 서버가 없어서 페이지 혼자서는 메일을 못 보낸다.
    폼 내용을 받아 메일로 넘겨 주는 곳을 하나 거친다.

    열쇠가 비어 있으면 버튼을 아예 내놓지 않는다 — 눌러도 아무 일이
    없는 버튼은 없느니만 못하다.
  */
  var ASK_KEY = '__INQUIRY_KEY__';
  var ASK_URL = '__INQUIRY_ENDPOINT__';

  var askBtn = document.getElementById('askBtn');
  var askBox = document.getElementById('askBox');
  var askForm = document.getElementById('askForm');
  var askMsg = document.getElementById('askMsg');
  var askSend = document.getElementById('askSend');

  if (ASK_KEY && askBox && typeof askBox.showModal === 'function') {
    askBtn.hidden = false;

    askBtn.addEventListener('click', function () {
      say('', '');
      askSend.disabled = false;
      askBox.showModal();
      document.getElementById('askTitle').focus();
    });

    document.getElementById('askCancel').addEventListener('click', function () {
      askBox.close();
    });

    /* 바깥을 눌러도 닫힌다. */
    askBox.addEventListener('click', function (e) {
      if (e.target === askBox) askBox.close();
    });

    askForm.addEventListener('submit', function (e) {
      e.preventDefault();  /* method="dialog"라 두면 그냥 닫혀 버린다 */
      send();
    });
  }

  function say(text, kind) {
    askMsg.textContent = text;
    askMsg.className = 'ask-msg' + (kind ? ' ' + kind : '');
  }

  function send() {
    var title = document.getElementById('askTitle').value.trim();
    var body = document.getElementById('askBody').value.trim();
    var mail = document.getElementById('askMail').value.trim();

    if (!title || !body || !mail) { say('빈 칸을 채워 주세요.', 'bad'); return; }
    if (mail.indexOf('@') < 1) { say('회신 이메일을 다시 봐 주세요.', 'bad'); return; }

    askSend.disabled = true;
    say('보내는 중…', '');

    fetch(ASK_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify({
        access_key: ASK_KEY,
        subject: '[보도자료 모니터] ' + title,
        from_name: '보도자료 모니터',
        /* 받은 메일에서 바로 '답장'을 누르면 이 주소로 가게 한다 */
        replyto: mail,
        제목: title,
        내용: body,
        회신이메일: mail,
        botcheck: askForm.botcheck.checked
      })
    }).then(function (res) {
      return res.json().catch(function () { return { success: res.ok }; });
    }).then(function (data) {
      if (data && data.success) {
        say('보냈습니다. 읽고 회신드리겠습니다.', 'good');
        askForm.reset();
        setTimeout(function () { askBox.close(); }, 1600);
      } else {
        askSend.disabled = false;
        say('보내지 못했습니다. 잠시 뒤 다시 시도해 주세요.', 'bad');
      }
    }).catch(function () {
      askSend.disabled = false;
      say('보내지 못했습니다. 인터넷 연결을 확인해 주세요.', 'bad');
    });
  }

  /* 데이터가 있는 첫 탭을 연다. */
  var firstWithData = TABS.findIndex(function (t) { return t.count > 0; });
  selectTab(firstWithData >= 0 ? firstWithData : 0);
})();
</script>
</script>
</body>
</html>
"""


# 게시 폴더에 같이 두는 아주 작은 파일. 안에는 마지막 수집 시각 한 줄뿐이다.
#
# 화면은 만들어질 때의 내용을 그대로 담은 파일 하나라, 탭을 열어 둔 채로
# 며칠이 지나도 저절로 바뀌지 않는다. 그래서 이 파일만 이따금 확인해
# 시각이 달라졌으면 "새 자료가 있다"고 알려 준다. 5MB짜리 화면을 다시
# 받아 보는 대신 스무 글자만 받아 보는 셈이다.
STAMP_FILE = "stamp.txt"


def last_run_at(db_path) -> str:
    """마지막으로 수집한 시각. 화면과 stamp 파일이 같은 값을 쓴다."""
    stamp = (storage.stats(db_path) or {}).get("last_run") or ""
    if stamp:
        return stamp.replace("T", " ")
    return datetime.now().strftime("%Y-%m-%d %H:%M")


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

    last_run = last_run_at(db_path)

    document = (
        _TEMPLATE.replace("__TOTAL__", f"{total:,}")
        .replace("__AGENCY_COUNT__", str(agency_count))
        .replace("__RANGE__", html.escape(date_range))
        .replace("__LAST_RUN__", html.escape(last_run))
        .replace("__UPDATE_TIMES__", html.escape(", ".join(UPDATE_TIMES)))
        .replace("__KEEP_YEARS__", str(KEEP_YEARS))
        .replace("__PAGE_ROWS__", str(PAGE_ROWS))
        .replace("__RECENT_DAYS__", str(RECENT_DAYS))
        .replace("__INQUIRY_KEY__", html.escape(INQUIRY_KEY))
        .replace("__INQUIRY_ENDPOINT__", html.escape(INQUIRY_ENDPOINT))
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
    # 화면이 낡았는지 알아보는 데 쓰는 표식. 내용은 마지막 수집 시각뿐이다.
    (out / STAMP_FILE).write_text(last_run_at(db_path), encoding="utf-8")
    return out
