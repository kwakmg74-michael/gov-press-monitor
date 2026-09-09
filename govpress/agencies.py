"""정부부처 코드표와 이름 해석.

korea.kr 보도자료 목록은 `repCode`로 기관을 서버에서 걸러 준다.
코드는 정책브리핑 '행정부처 바로가기'(/etc/ministry.do)에서 확인한 값이고,
기관명·구분·소속 관계는 정부 조직도를 기준으로 정리했다.

기관명은 korea.kr이 보도자료에 표기하는 이름을 그대로 쓴다.
조직도 명칭이 다른 경우(대통령비서실 ↔ 청와대)는 별칭으로 이어 두었다.
"""

from __future__ import annotations

from dataclasses import dataclass

# 목록에 보여 줄 구분과 순서.
# 부와 처는 쓰는 입장에서 굳이 나눌 이유가 없어 한 묶음으로 보여 준다
# (조직도상 구분은 Ministry.kind에 그대로 남아 있다).
GROUP_ORDER = ("부·처", "청", "위원회", "기타")
OTHER_GROUP = "기타"

KIND_TO_GROUP = {
    "부": "부·처",
    "처": "부·처",
    "청": "청",
    "위원회": "위원회",
    "기타": "기타",
}

GROUP_DESCRIPTIONS = {
    "부·처": "행정각부와 국무총리 소속 처",
    "청": "부 소속 외청",
    "위원회": "행정위원회",
    "기타": "대통령 직속 등",
}


@dataclass(frozen=True)
class Ministry:
    code: str
    name: str
    kind: str
    parent: str = ""  # 청의 소속 부, 처·위원회의 소속 기관

    @property
    def group(self) -> str:
        """목록에 보여 줄 묶음. 부와 처는 '부·처'로 합쳐진다."""
        return KIND_TO_GROUP.get(self.kind, OTHER_GROUP)

    @property
    def label(self) -> str:
        """소속까지 붙인 표시용 이름."""
        return f"{self.name} ({self.parent} 소속)" if self.parent else self.name


# (코드, 기관명, 구분, 소속) — 정부 조직도 순서
_REGISTRY: tuple[Ministry, ...] = (
    # --- 행정각부 19 ---
    Ministry("A00041", "재정경제부", "부"),
    Ministry("A00033", "과학기술정보통신부", "부"),
    Ministry("A00002", "교육부", "부"),
    Ministry("A00014", "외교부", "부"),
    Ministry("A00017", "통일부", "부"),
    Ministry("A00010", "법무부", "부"),
    Ministry("A00005", "국방부", "부"),
    Ministry("A00031", "행정안전부", "부"),
    Ministry("A00037", "국가보훈부", "부"),
    Ministry("A00009", "문화체육관광부", "부"),
    Ministry("A00008", "농림축산식품부", "부"),
    Ministry("A00015", "산업통상부", "부"),
    Ministry("A00012", "보건복지부", "부"),
    Ministry("A00019", "기후에너지환경부", "부"),
    Ministry("A00001", "고용노동부", "부"),
    Ministry("A00013", "성평등가족부", "부"),
    Ministry("A00006", "국토교통부", "부"),
    Ministry("A00023", "해양수산부", "부"),
    Ministry("A00032", "중소벤처기업부", "부"),
    # --- 국무총리 소속 처 6 ---
    Ministry("A00040", "기획예산처", "처", "국무총리"),
    Ministry("A00030", "인사혁신처", "처", "국무총리"),
    Ministry("A00011", "법제처", "처", "국무총리"),
    Ministry("A00027", "식품의약품안전처", "처", "국무총리"),
    Ministry("A00038", "국가데이터처", "처", "국무총리"),
    Ministry("A00039", "지식재산처", "처", "국무총리"),
    # --- 외청 18 (소속 부 표기) ---
    Ministry("B00004", "국세청", "청", "재정경제부"),
    Ministry("B00003", "관세청", "청", "재정경제부"),
    Ministry("B00013", "조달청", "청", "재정경제부"),
    Ministry("B00026", "우주항공청", "청", "과학기술정보통신부"),
    Ministry("B00024", "재외동포청", "청", "외교부"),
    Ministry("B00001", "검찰청", "청", "법무부"),
    Ministry("B00009", "병무청", "청", "국방부"),
    Ministry("B00008", "방위사업청", "청", "국방부"),
    Ministry("B00002", "경찰청", "청", "행정안전부"),
    Ministry("B00022", "소방청", "청", "행정안전부"),
    Ministry("B00025", "국가유산청", "청", "문화체육관광부"),
    Ministry("B00006", "농촌진흥청", "청", "농림축산식품부"),
    Ministry("B00010", "산림청", "청", "농림축산식품부"),
    Ministry("B00023", "질병관리청", "청", "보건복지부"),
    Ministry("B00005", "기상청", "청", "기후에너지환경부"),
    Ministry("B00018", "행정중심복합도시건설청", "청", "국토교통부"),
    Ministry("B00021", "새만금개발청", "청", "국토교통부"),
    Ministry("B00017", "해양경찰청", "청", "해양수산부"),
    # --- 위원회 8 ---
    Ministry("C00001", "공정거래위원회", "위원회", "국무총리"),
    Ministry("C00002", "국민권익위원회", "위원회", "국무총리"),
    Ministry("C00003", "금융위원회", "위원회", "국무총리"),
    Ministry("C00019", "개인정보보호위원회", "위원회", "국무총리"),
    Ministry("C00012", "원자력안전위원회", "위원회", "국무총리"),
    Ministry("C00005", "방송미디어통신위원회", "위원회", "대통령"),
    Ministry("C00015", "국가인권위원회", "위원회", "대통령"),
    Ministry("C00016", "중앙선거관리위원회", "위원회"),
    # --- 직속 기관 2 ---
    Ministry("C00022", "감사원", "기타", "대통령"),
    Ministry("A00016", "청와대", "기타", "대통령"),
)

_BY_CODE: dict[str, Ministry] = {m.code: m for m in _REGISTRY}
_BY_NAME: dict[str, Ministry] = {m.name: m for m in _REGISTRY}

# code -> 기관명 (하위 호환)
MINISTRIES: dict[str, str] = {m.code: m.name for m in _REGISTRY}

# 흔히 쓰는 줄임말과, 조직도·옛 명칭
ALIASES = {
    "국토부": "국토교통부",
    "행안부": "행정안전부",
    "복지부": "보건복지부",
    "산업부": "산업통상부",
    "산업통상자원부": "산업통상부",
    "과기부": "과학기술정보통신부",
    "과기정통부": "과학기술정보통신부",
    "중기부": "중소벤처기업부",
    "노동부": "고용노동부",
    "환경부": "기후에너지환경부",
    "해수부": "해양수산부",
    "농식품부": "농림축산식품부",
    "문체부": "문화체육관광부",
    "여가부": "성평등가족부",
    "여성가족부": "성평등가족부",
    "보훈부": "국가보훈부",
    "금융위": "금융위원회",
    "공정위": "공정거래위원회",
    "권익위": "국민권익위원회",
    "방미통위": "방송미디어통신위원회",
    "방통위": "방송미디어통신위원회",
    "인권위": "국가인권위원회",
    "선관위": "중앙선거관리위원회",
    "개인정보위": "개인정보보호위원회",
    "원안위": "원자력안전위원회",
    "식약처": "식품의약품안전처",
    "특허청": "지식재산처",
    "통계청": "국가데이터처",
    "문화재청": "국가유산청",
    "행복청": "행정중심복합도시건설청",
    "대통령비서실": "청와대",
}


# 조직 개편으로 사라졌거나 여러 기관으로 나뉜 이름은 그냥 "없다"고 하지 않고
# 어디로 갔는지 알려 준다.
SPLIT_NOTES = {
    "기획재정부": "기획재정부는 기획예산처와 재정경제부로 나뉘었습니다.",
    "기재부": "기획재정부는 기획예산처와 재정경제부로 나뉘었습니다.",
    "행정자치부": "행정자치부는 행정안전부로 바뀌었습니다.",
    "미래창조과학부": "미래창조과학부는 과학기술정보통신부로 바뀌었습니다.",
}


# 목록에서 뺀 기관. 코드표에서 지우는 것만으로는 부족하다 —
# 전 부처를 훑을 때 기사가 딸려 들어와 '기타'로 다시 나타나기 때문에
# 수집과 표시 양쪽에서 걸러야 한다.
EXCLUDED = frozenset({"국무조정실"})


def is_excluded(name: str) -> bool:
    return name in EXCLUDED


class UnknownAgency(ValueError):
    """코드표에서 찾을 수 없는 기관 이름."""


def sort_key(ministry: Ministry) -> tuple:
    """구분 순, 그 안에서 기관명 가나다순."""
    return (GROUP_ORDER.index(ministry.group), ministry.name)


def all_ministries() -> list[Ministry]:
    """구분 순 · 가나다순으로 정렬된 전체 목록."""
    return sorted(_REGISTRY, key=sort_key)


def group_of(name: str) -> str:
    """기관명으로 구분을 찾는다. 코드표에 없으면 '기타'."""
    ministry = _BY_NAME.get(name)
    return ministry.group if ministry else OTHER_GROUP


def parent_of(name: str) -> str:
    """기관명으로 소속 기관을 찾는다. 없으면 빈 문자열."""
    ministry = _BY_NAME.get(name)
    return ministry.parent if ministry else ""


def grouped() -> list[tuple[str, list[Ministry]]]:
    """구분별로 묶고, 각 구분 안은 가나다순."""
    buckets: dict[str, list[Ministry]] = {}
    for ministry in _REGISTRY:
        buckets.setdefault(ministry.group, []).append(ministry)
    return [
        (group, sorted(buckets[group], key=lambda m: m.name))
        for group in GROUP_ORDER
        if group in buckets
    ]


def resolve(value: str) -> Ministry:
    """기관명·줄임말·코드 중 무엇을 주더라도 Ministry로 바꿔 준다.

    부분 일치도 허용하되, 후보가 둘 이상이면 모호하다고 알려 준다.
    """
    text = (value or "").strip()
    if not text:
        raise UnknownAgency("기관 이름이 비어 있습니다.")

    if text.upper() in _BY_CODE:
        return _BY_CODE[text.upper()]

    if text in SPLIT_NOTES:
        raise UnknownAgency(f"{SPLIT_NOTES[text]} 후속 기관 이름으로 지정하세요.")

    name = ALIASES.get(text, text)
    if name in _BY_NAME:
        return _BY_NAME[name]

    matches = [n for n in _BY_NAME if text in n]
    if len(matches) == 1:
        return _BY_NAME[matches[0]]
    if len(matches) > 1:
        raise UnknownAgency(
            f"'{value}'에 해당하는 기관이 여러 개입니다: {', '.join(sorted(matches))}"
        )

    raise UnknownAgency(
        f"'{value}'를 기관 코드표에서 찾을 수 없습니다. "
        "`python -m govpress depts`로 전체 목록을 확인하세요."
    )


def resolve_many(values) -> list[Ministry]:
    """중복은 걷어내고 입력 순서를 유지한다."""
    seen: set[str] = set()
    result: list[Ministry] = []
    for value in values or []:
        ministry = resolve(value)
        if ministry.code not in seen:
            seen.add(ministry.code)
            result.append(ministry)
    return result
