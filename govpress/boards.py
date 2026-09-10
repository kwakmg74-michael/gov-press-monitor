"""게시판 수집기의 공통 뼈대.

지자체·공공기관·연구소는 통합 창구가 없어 사이트마다 어댑터가 하나씩
필요하다. 다만 필요한 일은 어디나 같다 — 목록 주소를 만들고, 받아 오고,
파서에 넘기고, `Article`로 바꾼다. 그 공통분모가 이 모듈이다.

분류별 모듈(`local_gov`, `public_org`, `research`)은 여기서 `Site`와
`collect`를 가져다 쓰고, **자기 파서와 사이트 목록만** 갖는다.

한 기관에 게시판이 여럿인 경우(KB경영연구소 3개, 서울주택도시개발공사 2개)는
`Site`를 여러 개 두고 `board`로 구분한다. 화면에는 기관 이름 하나로 나오고
결과는 합쳐진다 — `board`는 저장 열쇠를 겹치지 않게 하는 용도다.
"""

from __future__ import annotations

import re
import ssl
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

from .models import Article, clean_text, normalize_date

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}


# --- TLS 후퇴 ----------------------------------------------------------------
#
# 관공서 사이트에 붙을 때 걸리는 TLS 문제는 두 종류다. 둘 다 브라우저에서는
# 멀쩡히 열리기 때문에 "차단당했다"고 오해하기 쉽다.
#
# 1) 악수 실패 (SSLV3_ALERT_HANDSHAKE_FAILURE)
#    서버가 오래된 프로토콜·암호만 제시하는데, 요즘 OpenSSL은 기본값으로
#    그걸 거절한다. 우리 쪽이 받아들일 범위를 넓히면 붙는다.
#
# 2) 인증서 검증 실패 (CERTIFICATE_VERIFY_FAILED)
#    발급기관을 모르겠다는 뜻이다. 국내 정부 인증기관 루트가 윈도우에는
#    있지만 파이썬 번들(certifi)에는 없거나, 사무실 보안장비가 통신을
#    가로채 재서명하는 경우다. 검증을 끄는 대신 **운영체제 저장소**를
#    보게 하면 브라우저와 같은 기준으로 검증하게 된다.
#
# 그래서 순서는: 기본 → 구형TLS+OS저장소 → (그래도 안 되면) 검증 생략.
# 실패한 뒤에만 물러서고, 성공한 단계는 그 호스트에 대해서만 기억한다.
_LEGACY_TLS_HOSTS: set[str] = set()
_INSECURE_HOSTS: set[str] = set()
_session_cache: dict[str, requests.Session] = {}


def _os_trust_context() -> ssl.SSLContext:
    """운영체제 인증서 저장소를 쓰는 컨텍스트.

    truststore가 있으면 윈도우/macOS 저장소를 그대로 쓴다. 브라우저가
    신뢰하는 기관이면 여기서도 신뢰한다. 없으면 기본 번들로 물러선다.
    """
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return create_urllib3_context()


class _LegacyTLSAdapter(HTTPAdapter):
    """구형 TLS 서버용 어댑터. 인증서는 OS 저장소 기준으로 검증한다."""

    def __init__(self, verify: bool = True, **kwargs):
        self._verify = verify
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        context = _os_trust_context() if self._verify else create_urllib3_context()

        context.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
        context.set_ciphers("DEFAULT@SECLEVEL=1")
        try:
            context.minimum_version = ssl.TLSVersion.TLSv1
        except (AttributeError, ValueError):
            pass

        if not self._verify:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

        kwargs["ssl_context"] = context
        return super().init_poolmanager(*args, **kwargs)


def _make_session(key: str, verify: bool) -> requests.Session:
    if key not in _session_cache:
        session = requests.Session()
        session.mount("https://", _LegacyTLSAdapter(verify=verify))
        if not verify:
            session.verify = False
        _session_cache[key] = session
    return _session_cache[key]


def legacy_session() -> requests.Session:
    """구형 TLS + 운영체제 인증서 저장소."""
    return _make_session("legacy", verify=True)


def insecure_session() -> requests.Session:
    """마지막 수단. 인증서 검증을 건너뛴다."""
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    return _make_session("insecure", verify=False)


# --- 사이트 ------------------------------------------------------------------


@dataclass(frozen=True)
class Site:
    """게시판 하나.

    name       : 화면에 뜨는 기관 이름
    group      : 체크박스 묶음 (지자체는 지역, 그 밖에는 분야)
    list_url   : 목록 페이지
    page_param : 페이지 번호를 넘기는 쿼리 이름
    parser     : 목록 HTML -> list[dict] (title/uid/link/published_at/department)
    category   : 어느 탭에 담을지 (정부기관/지자체/공공기관/연구소)
    prefix     : 저장 열쇠 앞머리 (local / public / research)
    board      : 한 기관에 게시판이 여럿일 때의 구분. 화면에는 안 나온다.
    primary    : 묶음 안에서 맨 앞에 고정 (광역자치단체 등)
    """

    name: str
    group: str
    list_url: str
    page_param: str
    parser: Callable[[str, "Site"], list[dict]] = field(repr=False)
    category: str = ""
    prefix: str = "local"
    board: str = ""
    # "page": 파라미터에 페이지 번호를 넣는다 (대부분)
    # "size": 페이지 이동이 POST뿐이라, 대신 한 번에 몇 건을 받을지 지정한다
    page_mode: str = "page"
    page_size: int = 10
    primary: bool = False

    @property
    def source(self) -> str:
        """저장할 때 쓰는 출처 열쇠. 게시판마다 달라야 한다."""
        base = f"{self.prefix}:{self.name}"
        return f"{base}/{self.board}" if self.board else base

    @property
    def label(self) -> str:
        """진행 표시에 쓰는 이름. 게시판이 여럿이면 어느 쪽인지 밝힌다."""
        return f"{self.name}·{self.board}" if self.board else self.name

    @property
    def single_request(self) -> bool:
        """한 번의 요청으로 끝나는가."""
        return self.page_mode == "size"

    @property
    def sort_key(self) -> tuple[int, str]:
        """대표 기관이 먼저, 그다음 가나다순."""
        return (0 if self.primary else 1, self.name)

    def page_url(self, page: int) -> str:
        joiner = "&" if "?" in self.list_url else "?"
        value = page * self.page_size if self.page_mode == "size" else page
        return f"{self.list_url}{joiner}{self.page_param}={value}"


# --- 목록 다루기 --------------------------------------------------------------


def agency_names(sites) -> list[str]:
    """기관 이름 목록. 게시판이 여럿인 기관도 한 번만 센다."""
    seen: list[str] = []
    for site in sites:
        if site.name not in seen:
            seen.append(site.name)
    return seen


def sites_by_group(sites, group_order, other: str = "기타"):
    """묶음별로 나눈다. 묶음 안은 대표 기관이 먼저, 그다음 가나다순.

    같은 기관의 게시판이 여럿이면 첫 번째 것만 대표로 남긴다 — 체크박스는
    기관 단위로 하나만 나와야 하기 때문이다.
    """
    buckets: dict[str, list[Site]] = {}
    seen: set[str] = set()
    for site in sites:
        if site.name in seen:
            continue
        seen.add(site.name)
        buckets.setdefault(site.group or other, []).append(site)

    order = list(group_order)
    for group in buckets:
        if group not in order:
            order.append(group)

    return [
        (group, sorted(buckets[group], key=lambda s: s.sort_key))
        for group in order
        if group in buckets
    ]


def boards_of(sites, name: str) -> list[Site]:
    """한 기관의 게시판 전부."""
    return [site for site in sites if site.name == name]


def find(sites, name: str) -> Site | None:
    for site in sites:
        if site.name == name:
            return site
    return None


# --- 파서 도우미 --------------------------------------------------------------


def row_text(cell) -> str:
    """모바일 라벨(.add-head)과 NEW 아이콘을 걷어낸 셀 텍스트.

    많은 게시판이 좁은 화면용으로 각 칸 앞에 '번호', '제목' 같은 라벨을
    숨겨 넣어 둔다. 그대로 읽으면 제목이 '제목 실제제목'이 된다.
    """
    if cell is None:
        return ""
    clone = BeautifulSoup(str(cell), "html.parser")
    for junk in clone.select(
        ".add-head, .mobile-tit, .p-icon, .new, .hd-element, .bbsNewImage, "
        ".blind, .sound_only, .only-m, .sr-only, .sr_only, .hidden, "
        ".icoNew, i:empty, img"
    ):
        junk.decompose()
    return clean_text(clone.get_text(" ", strip=True))


def keep_params(href: str, site: Site, names: tuple[str, ...]) -> str:
    """상세 링크에서 필요한 파라미터만 남긴다.

    목록에서 딴 링크에는 페이지 번호, 검색 조건, 세션 아이디 같은
    "지금 이 순간"의 상태가 잔뜩 붙어 온다. 그대로 저장하면 나중에
    열었을 때 지저분하고, 세션 아이디는 아예 의미가 없어진다.
    """
    absolute = urljoin(site.list_url, href)
    base, _, query = absolute.partition("?")
    base = base.split(";")[0]  # ;jsessionid=... 제거

    keep = {}
    for chunk in query.split("&"):
        name, _, value = chunk.partition("=")
        if name in names and value:
            keep[name] = value
    if not keep:
        return absolute
    return base + "?" + "&".join(f"{k}={v}" for k, v in keep.items())


def find_date_cell(cells) -> tuple[str, int]:
    """뒤에서부터 날짜처럼 보이는 칸을 찾는다.

    칸 구성이 사이트마다 다르다(송파는 4칸, 구리는 '파일'이 끼어 5칸).
    자리를 고정하면 한 곳만 달라도 엉뚱한 값을 읽으므로, 날짜를 먼저
    찾고 그 앞 칸을 담당부서로 본다.
    """
    for index in range(len(cells) - 1, -1, -1):
        published = normalize_date(row_text(cells[index]))
        if published:
            return published, index
    return "", -1


def script_uid(anchor, pattern: re.Pattern) -> str:
    """href나 onclick에 든 `fnView('12345')` 류에서 번호를 뽑는다."""
    for attr in ("href", "onclick"):
        match = pattern.search(anchor.get(attr, "") or "")
        if match:
            return match.group(1)
    return ""


# --- 수집 -------------------------------------------------------------------


def to_articles(items: list[dict], site: Site) -> list[Article]:
    return [
        Article(
            category=site.category,
            source=site.source,
            uid=str(item["uid"]),
            agency=site.name,
            title=item["title"],
            link=item["link"],
            published_at=item["published_at"],
            summary=item.get("department", ""),
        )
        for item in items
    ]


def fetch_page(site: Site, page: int, session=None, timeout: int = 25) -> list[Article]:
    """한 페이지를 받아 파싱한다.

    TLS 악수에 실패하면 구형 설정으로 한 번 더 시도한다. 그 호스트는
    기억해 두어, 다음부터는 곧바로 구형 설정으로 붙는다.
    """
    url = site.page_url(page)
    host = urlparse(url).hostname or ""

    if host in _INSECURE_HOSTS:
        response = insecure_session().get(url, headers=HEADERS, timeout=timeout)
    elif host in _LEGACY_TLS_HOSTS:
        response = legacy_session().get(url, headers=HEADERS, timeout=timeout)
    else:
        client = session or requests
        try:
            response = client.get(url, headers=HEADERS, timeout=timeout)
        except requests.exceptions.SSLError:
            _LEGACY_TLS_HOSTS.add(host)
            try:
                response = legacy_session().get(url, headers=HEADERS, timeout=timeout)
            except requests.exceptions.SSLError:
                _INSECURE_HOSTS.add(host)
                response = insecure_session().get(url, headers=HEADERS, timeout=timeout)

    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return to_articles(site.parser(response.text, site), site)


def tls_note(site: Site) -> str:
    """이 사이트에 어떤 연결을 쓰고 있는지. 진행 표시에 붙인다."""
    host = urlparse(site.list_url).hostname or ""
    if host in _INSECURE_HOSTS:
        return " (인증서 검증 생략)"
    if host in _LEGACY_TLS_HOSTS:
        return " (구형 TLS)"
    return ""


def collect(
    sites,
    pages: int = 3,
    delay: float = 0.7,
    on_progress=None,
) -> list[Article]:
    """보도자료를 모은다.

    이 게시판들은 기간 검색 파라미터가 제각각이라 서버에서 거르지 않고,
    최근 `pages`페이지를 받아 온 뒤 대시보드에서 기간으로 좁힌다.
    """
    collected: dict[tuple[str, str], Article] = {}
    session = requests.Session()

    for site in sites:
        # "size" 방식은 한 번의 요청에 원하는 만큼 담아 오므로 반복하지 않는다.
        # 그대로 두면 30건 → 60건 → 90건을 겹쳐 받아 같은 글을 계속 다시 읽는다.
        last_page = 1 if site.single_request else pages
        for page in range(1, last_page + 1):
            request_page = pages if site.single_request else page
            try:
                items = fetch_page(site, request_page, session=session)
            except Exception as exc:
                if on_progress:
                    on_progress(site.label, page, 0, f"실패: {exc}", "")
                break

            fresh = [a for a in items if (a.source, a.uid) not in collected]
            for article in fresh:
                collected[(article.source, article.uid)] = article

            if on_progress:
                on_progress(site.label, page, len(fresh), None, tls_note(site))

            if not items or not fresh:
                break

            time.sleep(delay)

    return sorted(
        collected.values(),
        key=lambda a: (a.published_at, a.uid),
        reverse=True,
    )
