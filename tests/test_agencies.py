from __future__ import annotations

import pytest

from govpress import agencies
from govpress.agencies import UnknownAgency, resolve, resolve_many


def test_코드표가_비어있지_않다():
    assert len(agencies.MINISTRIES) >= 50
    assert agencies.MINISTRIES["A00006"] == "국토교통부"
    assert agencies.MINISTRIES["C00003"] == "금융위원회"


def test_코드는_모두_고유하고_형식이_같다():
    names = list(agencies.MINISTRIES.values())
    assert len(names) == len(set(names)), "기관명이 중복됩니다"
    for code in agencies.MINISTRIES:
        assert len(code) == 6 and code[0] in "ABC" and code[1:].isdigit()


@pytest.mark.parametrize(
    "value,expected",
    [
        ("국토교통부", "A00006"),   # 정식 명칭
        ("국토부", "A00006"),       # 줄임말
        ("A00006", "A00006"),       # 코드
        ("a00006", "A00006"),       # 소문자 코드
        ("금융위", "C00003"),
        ("질병관리청", "B00023"),
        ("교육", "A00002"),         # 부분 일치 (후보가 하나뿐)
    ],
)
def test_이름_줄임말_코드를_모두_받는다(value, expected):
    assert resolve(value).code == expected


def test_후보가_여러개면_알려준다():
    with pytest.raises(UnknownAgency) as err:
        resolve("위원회")
    assert "여러 개" in str(err.value)


@pytest.mark.parametrize("value", ["", "  ", "국토교통부장관실", "존재하지않는부처"])
def test_찾을_수_없으면_에러(value):
    with pytest.raises(UnknownAgency):
        resolve(value)


def test_여러개를_한번에_해석하고_중복을_없앤다():
    result = resolve_many(["국토교통부", "국토부", "A00006", "금융위원회"])
    assert [m.code for m in result] == ["A00006", "C00003"]


def test_입력_순서를_유지한다():
    result = resolve_many(["금융위원회", "국토교통부"])
    assert [m.name for m in result] == ["금융위원회", "국토교통부"]


def test_조직도상_구분은_그대로_남는다():
    """보여 줄 때는 합치더라도 부와 처의 구분 자체는 유지한다."""
    assert resolve("국토교통부").kind == "부"
    assert resolve("법제처").kind == "처"
    assert resolve("산림청").kind == "청"
    assert resolve("공정거래위원회").kind == "위원회"


def test_부와_처는_한_묶음으로_보여_준다():
    assert resolve("국토교통부").group == "부·처"
    assert resolve("법제처").group == "부·처"
    assert resolve("산림청").group == "청"
    assert resolve("공정거래위원회").group == "위원회"
    assert resolve("감사원").group == "기타"


def test_전체_목록은_구분순_가나다순이다():
    listed = agencies.all_ministries()
    assert len(listed) == len(agencies.MINISTRIES)

    # 구분은 부·처·실 → 청 → 위원회 순으로 나온다
    groups = [m.group for m in listed]
    order = [agencies.GROUP_ORDER.index(g) for g in groups]
    assert order == sorted(order)

    # 같은 구분 안에서는 가나다순
    for group, items in agencies.grouped():
        names = [m.name for m in items]
        assert names == sorted(names), f"{group}가 가나다순이 아닙니다"


def test_구분별_기관_수가_조직도와_같다():
    """정부 조직도 기준: 부 19 + 처 6 = 25, 청 18, 위원회 8."""
    result = dict(agencies.grouped())
    assert len(result["부·처"]) == 25
    assert len(result["청"]) == 18
    assert len(result["위원회"]) == 8
    assert sum(len(v) for v in result.values()) == len(agencies.MINISTRIES)


def test_국무조정실은_목록에서_빠져_있다():
    assert "국무조정실" not in agencies.MINISTRIES.values()
    with pytest.raises(UnknownAgency):
        resolve("국무조정실")


def test_청은_소속_부가_지정되어_있다():
    for ministry in dict(agencies.grouped())["청"]:
        assert ministry.parent, f"{ministry.name}의 소속 부가 비어 있습니다"
        assert agencies.resolve(ministry.parent).kind == "부"


@pytest.mark.parametrize(
    "cheong,parent",
    [
        ("산림청", "농림축산식품부"),
        ("경찰청", "행정안전부"),
        ("국세청", "재정경제부"),
        ("행정중심복합도시건설청", "국토교통부"),
        ("해양경찰청", "해양수산부"),
        ("질병관리청", "보건복지부"),
        ("기상청", "기후에너지환경부"),
        ("우주항공청", "과학기술정보통신부"),
    ],
)
def test_외청의_소속_부(cheong, parent):
    assert agencies.parent_of(cheong) == parent


def test_첫_항목은_가나다_첫_기관이다():
    """정렬이 코드순으로 되돌아가면 잡힌다."""
    first_group, first_items = agencies.grouped()[0]
    assert first_group == "부·처"
    assert first_items[0].name == "고용노동부"


@pytest.mark.parametrize(
    "old,new",
    [
        ("특허청", "지식재산처"),
        ("통계청", "국가데이터처"),
        ("문화재청", "국가유산청"),
        ("산업통상자원부", "산업통상부"),
        ("여성가족부", "성평등가족부"),
        ("대통령비서실", "청와대"),
    ],
)
def test_바뀐_이름도_찾아_준다(old, new):
    """조직 개편 전 이름으로 입력해도 현재 기관을 찾는다."""
    assert resolve(old).name == new


def test_나뉜_기관은_어디로_갔는지_알려_준다():
    with pytest.raises(UnknownAgency) as err:
        resolve("기획재정부")
    message = str(err.value)
    assert "기획예산처" in message and "재정경제부" in message


@pytest.mark.parametrize(
    "name,group",
    [
        ("국토교통부", "부·처"),
        ("법제처", "부·처"),
        ("경찰청", "청"),
        ("금융위원회", "위원회"),
        ("서울특별시", "기타"),      # 코드표에 없는 기관
        ("", "기타"),
    ],
)
def test_기관명으로_구분을_찾는다(name, group):
    assert agencies.group_of(name) == group
