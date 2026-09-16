"""수집 결과의 공통 데이터 모델."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date

# 대시보드 상단 탭. 순서가 곧 탭 순서다.
CATEGORIES = ("정부기관", "지자체", "공공기관", "연구소")

GOVERNMENT = "정부기관"
LOCAL = "지자체"
PUBLIC = "공공기관"
RESEARCH = "연구소"

_DATE_RE = re.compile(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})")

# 사용자가 손으로 넣는 형식: 26.09.08 / 2026.09.08 / 2026-9-8 / 20260908
_USER_DATE_RE = re.compile(r"^\s*(\d{2}|\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})\s*$")
_COMPACT_DATE_RE = re.compile(r"^\s*(\d{4})(\d{2})(\d{2})\s*$")


class InvalidDate(ValueError):
    """날짜 형식을 알아볼 수 없을 때."""


def parse_user_date(value: str) -> date:
    """'26.09.08' 같은 사용자 입력을 date로 바꾼다.

    두 자리 연도는 2000년대로 해석한다(26 -> 2026).
    """
    text = str(value or "")

    match = _USER_DATE_RE.match(text) or _COMPACT_DATE_RE.match(text)
    if not match:
        raise InvalidDate(f"날짜 형식을 알 수 없습니다: '{value}' (예: 26.09.08 또는 2026-09-08)")

    year, month, day = match.groups()
    year_int = int(year)
    if len(year) == 2:
        year_int += 2000

    try:
        return date(year_int, int(month), int(day))
    except ValueError as exc:
        raise InvalidDate(f"존재하지 않는 날짜입니다: '{value}'") from exc


def parse_date_range(start: str | None, end: str | None) -> tuple[date | None, date | None]:
    """시작·종료를 함께 해석하고 뒤집힌 순서를 잡아 준다."""
    first = parse_user_date(start) if start else None
    last = parse_user_date(end) if end else None
    if first and last and first > last:
        first, last = last, first
    return first, last


def normalize_date(value: str | None) -> str:
    """'2026.09.08', '2026-9-8' 등을 'YYYY-MM-DD'로 정규화한다.

    두 자리 연도('26.09.15')는 그 칸이 **날짜 하나뿐일 때만** 받아 준다.
    본문에 섞인 '26.09.15'까지 날짜로 보면 엉뚱한 값을 줍게 되기 때문이다.
    경기주택도시공사처럼 목록에 연도를 두 자리로만 적는 곳이 있다.

    형식을 알 수 없으면 빈 문자열을 돌려준다. 절대 원본을 그대로 흘리지 않는다.
    """
    if not value:
        return ""
    text = str(value)

    m = _DATE_RE.search(text)
    if m:
        year, month, day = m.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"

    m = _USER_DATE_RE.match(text)
    if m:
        year, month, day = m.groups()
        return f"{int(year) + 2000}-{int(month):02d}-{int(day):02d}"

    return ""


def clean_text(value: str | None) -> str:
    """연속 공백/개행/non-breaking space를 한 칸으로 눌러 준다."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


@dataclass(frozen=True)
class Article:
    """보도자료 한 건.

    category: 대시보드 탭 (정부기관/지자체/공공기관/연구소).
    source: 어느 수집기가 가져왔는지 (korea.kr 등).
    uid: 출처 안에서 고유한 식별자(korea.kr은 newsId). 중복 제거의 기준.
    link: 원문으로 바로 이동할 수 있는 정규화된 permalink.
    """

    source: str
    uid: str
    agency: str
    title: str
    link: str
    published_at: str = ""
    summary: str = ""
    category: str = ""
    extra: dict = field(default_factory=dict, compare=False)

    def as_row(self) -> dict:
        row = asdict(self)
        row.pop("extra", None)
        return row

    def is_valid(self) -> bool:
        """제목·링크·날짜·분류가 모두 있어야 실사용 가능한 레코드로 본다."""
        return bool(
            self.title
            and self.link
            and self.published_at
            and self.uid
            and self.category in CATEGORIES
        )
