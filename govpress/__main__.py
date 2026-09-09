"""명령줄 진입점.

    python -m govpress depts                              # 부처 코드표 보기
    python -m govpress collect --dept 국토교통부 금융위원회   # 특정 부처만 수집
    python -m govpress collect --from 26.08.01 --to 26.09.08 --keyword 부동산
    python -m govpress dashboard --open                   # 대시보드 생성
    python -m govpress run --dept 국토부 --days 30 --open   # 수집 + 대시보드
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
import webbrowser
from collections import defaultdict

from . import agencies, dashboard, korea_kr, local_gov, public_org, research, storage
from .models import InvalidDate, parse_date_range


def _resolve_targets(names):
    if not names:
        return []
    try:
        return agencies.resolve_many(names)
    except agencies.UnknownAgency as exc:
        print(f"오류: {exc}", file=sys.stderr)
        raise SystemExit(2)


def _resolve_period(args):
    try:
        return parse_date_range(getattr(args, "date_from", None), getattr(args, "date_to", None))
    except InvalidDate as exc:
        print(f"오류: {exc}", file=sys.stderr)
        raise SystemExit(2)


def _display_width(text: str) -> int:
    """한글·한자는 터미널에서 두 칸을 차지한다."""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(1, width - _display_width(text))


def _depts(_args) -> int:
    """구분별로 묶어 가나다순으로, 세 칸씩 나란히 보여 준다."""
    reverse_aliases = defaultdict(list)
    for short, full in agencies.ALIASES.items():
        reverse_aliases[full].append(short)

    def cell_of(ministry) -> str:
        # 청은 어느 부 소속인지가 곧 그 청을 찾는 단서다.
        if ministry.kind == "청":
            return f"{ministry.name} {ministry.code} · {ministry.parent}"
        return f"{ministry.name} {ministry.code}"

    for group, items in agencies.grouped():
        cells = [cell_of(m) for m in items]
        columns = 2 if group == "청" else 3
        width = max(_display_width(c) for c in cells) + 2

        note = agencies.GROUP_DESCRIPTIONS.get(group, "")
        print(f"\n[{group}] {len(items)}곳{' — ' + note if note else ''}")
        for row_start in range(0, len(cells), columns):
            row = cells[row_start : row_start + columns]
            print("  " + "".join(_pad(cell, width) for cell in row).rstrip())

    print(f"\n총 {len(agencies.MINISTRIES)}곳.")
    print("--dept 에는 이름·줄임말·코드 아무거나 쓸 수 있습니다. 예) --dept 국토교통부 국토부 A00006")

    shortcuts = sorted(reverse_aliases.items(), key=lambda item: item[0])
    alias_width = max(_display_width(", ".join(sorted(s))) for _, s in shortcuts) + 2
    print("\n[줄임말]")
    for full, shorts in shortcuts:
        print("  " + _pad(", ".join(sorted(shorts)), alias_width) + "→ " + full)
    return 0


def _show_sites(module, title: str) -> int:
    """수집 대상 목록. 한 기관에 게시판이 여럿이면 함께 보여 준다."""
    for group, sites in module.sites_by_group():
        print(f"\n[{group}] {len(sites)}곳")
        for site in sites:
            extra = module.boards_of(site.name) if hasattr(module, "boards_of") else [site]
            print(f"  {_pad(site.name, 14)}{site.list_url}")
            for other in extra[1:]:
                print(f"  {_pad('', 14)}{other.list_url}  ({other.board})")

    print(f"\n총 {len(module.agency_names())}곳 / 게시판 {len(module.SITES)}개.")
    if module.PENDING:
        print("\n[확인 대기] 목록 구조 확인 후 추가 예정")
        print("  " + ", ".join(module.PENDING))
    return 0


def _locals(_args) -> int:
    return _show_sites(local_gov, "지자체")


def _publics(_args) -> int:
    return _show_sites(public_org, "공공기관")


def _collect_sites(module, args, what: str) -> int:
    targets = None
    if args.only:
        targets = []
        for name in args.only:
            found = module.boards_of(name) if hasattr(module, "boards_of") else []
            if not found:
                site = module.find(name)
                found = [site] if site else []
            if not found:
                print(
                    f"오류: '{name}'는 아직 수집 대상이 아닙니다. "
                    f"`python -m govpress {what}s`로 목록을 확인하세요.",
                    file=sys.stderr,
                )
                return 2
            targets.extend(found)

    names = sorted({s.name for s in targets}) if targets else None
    scope = ", ".join(names) if names else f"전체 {what}"
    print(f"{what} 수집 시작 — {scope} · 최근 {args.pages}페이지")

    def progress(label, page, added, error, note=""):
        if error:
            print(f"  [{label}] {page}페이지 {error}", file=sys.stderr)
        elif added:
            print(f"  [{label}] {page}페이지 → {added}건{note}")

    articles = module.collect(sites=targets, pages=args.pages, on_progress=progress)
    if not articles:
        print("수집된 보도자료가 없습니다.", file=sys.stderr)
        return 1

    result = storage.save(articles, args.db)
    print(f"수집 {len(articles)}건 / 신규 저장 {result['new']}건 / DB 누적 {result['total']}건")
    return 0


def _collect_local(args) -> int:
    return _collect_sites(local_gov, args, "지자체")


def _collect_public(args) -> int:
    return _collect_sites(public_org, args, "공공기관")


def _labs(_args) -> int:
    return _show_sites(research, "연구소")


def _collect_research(args) -> int:
    return _collect_sites(research, args, "연구소")


def _collect(args) -> int:
    targets = _resolve_targets(args.dept)
    start, end = _resolve_period(args)

    scope = ", ".join(m.name for m in targets) if targets else "전 부처"
    if start and end:
        period = f"{start} ~ {end}"
    else:
        period = f"최근 {args.days}일"
    keyword_note = f" · 검색어 '{args.keyword}'" if args.keyword else ""
    print(f"korea.kr 수집 시작 — {scope} · {period}{keyword_note}")

    def progress(label, page, added, error):
        if error:
            print(f"  [{label}] {page}페이지 {error}", file=sys.stderr)
        elif added:
            print(f"  [{label}] {page}페이지 → {added}건")

    articles = korea_kr.collect(
        days=args.days,
        max_pages=args.max_pages,
        start_date=start,
        end_date=end,
        keyword=args.keyword,
        ministries=targets,
        on_progress=progress,
    )

    if not articles:
        print(
            "조건에 맞는 보도자료가 없습니다. 기간·검색어를 넓혀 보세요.",
            file=sys.stderr,
        )
        return 1

    result = storage.save(articles, args.db)
    print(f"수집 {len(articles)}건 / 신규 저장 {result['new']}건 / DB 누적 {result['total']}건")
    return 0


def _dashboard(args) -> int:
    info = storage.stats(args.db)
    if not info.get("total"):
        print("DB가 비어 있습니다. 먼저 `python -m govpress collect`를 실행하세요.", file=sys.stderr)
        return 1

    path = dashboard.render(args.db, args.output).resolve()
    print(f"대시보드 생성: {path}")
    if args.open:
        webbrowser.open(path.as_uri())
    return 0


def _add_collect_options(parser) -> None:
    parser.add_argument(
        "--dept",
        nargs="+",
        metavar="기관",
        help="수집할 정부부처. 이름·줄임말·코드 모두 가능하고 여러 개 나열할 수 있습니다.",
    )
    parser.add_argument("--days", type=int, default=7, help="최근 며칠분 (기본 7, --from/--to가 있으면 무시)")
    parser.add_argument("--from", dest="date_from", metavar="YY.MM.DD", help="검색 시작일")
    parser.add_argument("--to", dest="date_to", metavar="YY.MM.DD", help="검색 종료일")
    parser.add_argument("--keyword", default="", metavar="검색어", help="korea.kr 검색어")
    parser.add_argument("--max-pages", type=int, default=50)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="govpress", description="정부부처 보도자료 수집기")
    parser.add_argument("--db", default=storage.DEFAULT_DB, help="SQLite 파일 경로")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("depts", help="선택 가능한 정부부처 목록 보기")
    sub.add_parser("locals", help="선택 가능한 지자체 목록 보기")

    local = sub.add_parser("collect-local", help="지자체 보도자료 수집")
    local.add_argument("--city", "--only", dest="only", nargs="+", metavar="지자체",
                       help="수집할 지자체 (생략하면 전체)")
    local.add_argument("--pages", type=int, default=3, help="기관별로 받아올 페이지 수 (기본 3)")

    sub.add_parser("publics", help="선택 가능한 공공기관 목록 보기")
    sub.add_parser("labs", help="선택 가능한 연구소 목록 보기")
    lab = sub.add_parser("collect-research", help="연구소 자료 수집")
    lab.add_argument("--only", nargs="+", metavar="기관", help="수집할 기관 (생략하면 전체)")
    lab.add_argument("--pages", type=int, default=3, help="기관별로 받아올 페이지 수 (기본 3)")
    public = sub.add_parser("collect-public", help="공공기관 보도자료 수집")
    public.add_argument("--only", nargs="+", metavar="기관", help="수집할 기관 (생략하면 전체)")
    public.add_argument("--pages", type=int, default=3, help="기관별로 받아올 페이지 수 (기본 3)")

    collect = sub.add_parser("collect", help="korea.kr에서 보도자료 수집")
    _add_collect_options(collect)

    board = sub.add_parser("dashboard", help="대시보드 HTML 생성")
    board.add_argument("--output", default=dashboard.DEFAULT_OUTPUT)
    board.add_argument("--open", action="store_true", help="생성 후 브라우저로 열기")

    run = sub.add_parser("run", help="수집 후 대시보드까지 한 번에")
    _add_collect_options(run)
    run.add_argument("--output", default=dashboard.DEFAULT_OUTPUT)
    run.add_argument("--open", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "depts":
        return _depts(args)
    if args.command == "locals":
        return _locals(args)
    if args.command == "collect-local":
        return _collect_local(args)
    if args.command == "publics":
        return _publics(args)
    if args.command == "collect-public":
        return _collect_public(args)
    if args.command == "labs":
        return _labs(args)
    if args.command == "collect-research":
        return _collect_research(args)
    if args.command == "collect":
        return _collect(args)
    if args.command == "dashboard":
        return _dashboard(args)
    if args.command == "run":
        code = _collect(args)
        if code != 0:
            return code
        return _dashboard(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
