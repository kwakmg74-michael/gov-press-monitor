"""대한민국 정책브리핑(korea.kr) 통합 보도자료 수집기.

중앙부처는 각 부처 사이트를 따로 긁지 않는다.
정책브리핑이 전 부처 보도자료를 한 곳에 모아 제공하고,
제목·부처·게시일·원문 링크가 목록 단계에서 모두 채워지기 때문이다.

목록 페이지 구조 (2026-09 기준, 서버 렌더링):

    div.list_type > ul > li > a[href*="pressReleaseView.do?newsId="]
        span.text
            strong        -> 제목
            span.lead     -> 요약
            span.source
                span[0]   -> 게시일 (2026.09.08)
                span[1]   -> 부처명
"""

from __future__ import annotations

import re
import time
from datetime import date, timedelta
from typing import Iterable, Iterator
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from .agencies import is_excluded
from .models import GOVERNMENT, Article, clean_text, normalize_date

SOURCE = "korea.kr"
CATEGORY = GOVERNMENT
BASE_URL = "https://www.korea.kr"
LIST_URL = f"{BASE_URL}/briefing/pressReleaseList.do"
VIEW_URL = f"{BASE_URL}/briefing/pressReleaseView.do"

PAGE_SIZE = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}

_NEWS_ID_RE = re.compile(r"newsId=(\d+)")

# 요약이 제목을 그대로 반복하거나 안내 상투구만 남는 경우가 많다.
_BOILERPLATE_RES = [
    re.compile(r"^관련\s*보도자료(\s*내용)?입니다\.?"),
    re.compile(r"^자세한\s*내용은\s*첨부\s*파일을?\s*참고하?시?기?\s*바랍니다\.?"),
    re.compile(r"^붙임\s*파일\s*참고\.?"),
]
_LEAD_SEPARATORS = " -–—·…:|\"'“”‘’,"
_MIN_SUMMARY_LEN = 20


_MIN_TITLE_OVERLAP = 8
_TITLE_OVERLAP_RATIO = 0.7
_NOISE_RE = re.compile(r"[\s.,·…\-–—'\"“”‘’()\[\]「」『』]")


def _squash(text: str) -> str:
    """비교용으로 공백과 구두점을 걷어낸 문자열."""
    return _NOISE_RE.sub("", text)


def _strip_repeated_title(summary: str, title: str) -> str:
    """요약 앞에 붙은 제목 반복분을 떼어낸다.

    korea.kr의 lead는 대부분 '제목- 부제 - 본문 첫 문장…' 형태라
    그대로 두면 대시보드에서 제목이 두 번 보인다.

    목록의 제목에는 lead에 없는 꼬리표(예: '(9.8.화)')가 붙기도 하므로
    완전 일치가 아니라 '앞부분이 제목의 대부분과 겹치는지'로 판정한다.
    """
    if not summary or not title:
        return summary

    squashed_title = _squash(title)
    if len(squashed_title) < _MIN_TITLE_OVERLAP:
        return summary  # 제목이 너무 짧으면 우연히 겹칠 수 있다

    matched = 0
    consumed = 0
    for index, char in enumerate(summary):
        if matched >= len(squashed_title):
            break
        if not _squash(char):
            consumed = index + 1
            continue
        if char != squashed_title[matched]:
            break
        matched += 1
        consumed = index + 1

    threshold = max(_MIN_TITLE_OVERLAP, int(len(squashed_title) * _TITLE_OVERLAP_RATIO))
    if matched < threshold:
        return summary

    return summary[consumed:].lstrip(_LEAD_SEPARATORS).strip()


def clean_summary(summary: str, title: str) -> str:
    """제목 반복과 상투구를 걷어낸 요약. 남는 게 없으면 빈 문자열."""
    text = _strip_repeated_title(clean_text(summary), title).lstrip(_LEAD_SEPARATORS)
    for pattern in _BOILERPLATE_RES:
        text = pattern.sub("", text).lstrip(_LEAD_SEPARATORS)
    # '- -' 처럼 겹친 구분자를 하나로 눌러 준다.
    text = re.sub(r"\s*[-–—]\s*[-–—]+\s*", " - ", text).strip()
    if len(text) < _MIN_SUMMARY_LEN:
        return ""
    return text


def permalink(news_id: str) -> str:
    """쿼리 잡동사니를 뺀 안정적인 원문 링크."""
    return f"{VIEW_URL}?newsId={news_id}"


def _news_id_from_href(href: str) -> str:
    if not href:
        return ""
    qs = parse_qs(urlparse(href).query)
    if qs.get("newsId"):
        return qs["newsId"][0]
    m = _NEWS_ID_RE.search(href)
    return m.group(1) if m else ""


def parse_list(html: str) -> list[Article]:
    """목록 페이지 HTML에서 보도자료를 뽑아낸다. 네트워크를 타지 않는 순수 함수."""
    soup = BeautifulSoup(html, "html.parser")
    articles: list[Article] = []
    seen: set[str] = set()

    for anchor in soup.select('a[href*="pressReleaseView.do"]'):
        news_id = _news_id_from_href(anchor.get("href", ""))
        if not news_id or news_id in seen:
            continue

        title_el = anchor.select_one("strong")
        source_spans = anchor.select("span.source > span")

        title = clean_text(title_el.get_text(" ", strip=True) if title_el else "")
        published_at = normalize_date(source_spans[0].get_text(strip=True) if source_spans else "")
        agency = clean_text(source_spans[1].get_text(strip=True) if len(source_spans) > 1 else "")

        lead_el = anchor.select_one("span.lead")
        summary = clean_summary(lead_el.get_text(" ", strip=True) if lead_el else "", title)

        # 목록 항목이 아니라 배너/추천 링크인 경우 제목·날짜가 비어 있다. 버린다.
        if not title or not published_at:
            continue

        seen.add(news_id)
        articles.append(
            Article(
                category=CATEGORY,
                source=SOURCE,
                uid=news_id,
                agency=agency,
                title=title,
                link=permalink(news_id),
                published_at=published_at,
                summary=summary,
            )
        )

    return articles


def fetch_page(
    page: int,
    start_date: date,
    end_date: date,
    keyword: str = "",
    rep_code: str = "",
    session: requests.Session | None = None,
    timeout: int = 25,
) -> list[Article]:
    """한 페이지를 가져와 파싱한다.

    기간·검색어·기관은 모두 korea.kr이 서버에서 걸러 준다.
    받아 와서 버리는 것보다 훨씬 적게 요청하게 된다.
    """
    client = session or requests
    response = client.get(
        LIST_URL,
        params={
            "pageIndex": page,
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "srchWord": keyword or "",
            "repCode": rep_code or "",
            "repCodeType": "정부부처" if rep_code else "",
            "period": "",
        },
        headers=HEADERS,
        timeout=timeout,
    )
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return parse_list(response.text)


def _collect_one(
    start: date,
    end: date,
    keyword: str,
    ministry,
    max_pages: int,
    delay: float,
    session: requests.Session,
    on_progress,
) -> dict[str, Article]:
    """기관 하나(또는 전체)에 대해 페이지를 끝까지 넘긴다."""
    label = ministry.name if ministry else "전체"
    rep_code = ministry.code if ministry else ""
    found: dict[str, Article] = {}

    for page in range(1, max_pages + 1):
        try:
            items = fetch_page(
                page, start, end, keyword=keyword, rep_code=rep_code, session=session
            )
        except Exception as exc:  # 네트워크/일시 오류는 그 기관만 포기한다
            if on_progress:
                on_progress(label, page, 0, f"실패: {exc}")
            break

        fresh = [a for a in items if a.uid not in found]
        for article in fresh:
            found[article.uid] = article

        if on_progress:
            on_progress(label, page, len(fresh), None)

        # 새로 얻은 게 없으면 마지막 페이지를 지난 것으로 본다.
        if not items or not fresh:
            break

        time.sleep(delay)

    return found


def collect(
    days: int = 7,
    max_pages: int = 50,
    delay: float = 0.7,
    end_date: date | None = None,
    start_date: date | None = None,
    keyword: str = "",
    ministries=None,
    on_progress=None,
) -> list[Article]:
    """보도자료를 모은다.

    - 기간: `start_date`/`end_date`를 주면 그대로, 없으면 최근 `days`일.
    - `keyword`: korea.kr 검색어(제목·본문 대상).
    - `ministries`: `agencies.Ministry` 목록. 주면 기관별로 나눠 요청한다.
      비워 두면 전 부처를 한 번에 훑는다.
    """
    end = end_date or date.today()
    start = start_date or (end - timedelta(days=days - 1))
    if start > end:
        start, end = end, start

    targets = list(ministries) if ministries else [None]

    collected: dict[str, Article] = {}
    session = requests.Session()

    for ministry in targets:
        collected.update(
            _collect_one(start, end, keyword, ministry, max_pages, delay, session, on_progress)
        )

    return sorted(
        (a for a in collected.values() if not is_excluded(a.agency)),
        key=lambda a: (a.published_at, a.uid),
        reverse=True,
    )


def iter_valid(articles: Iterable[Article]) -> Iterator[Article]:
    for article in articles:
        if article.is_valid():
            yield article
