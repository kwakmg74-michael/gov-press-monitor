"""분양 공고 바로가기.

연구·업계 탭과 같은 결이다 — 글을 긁어 오지 않고 가는 길만 놓는다.

왜 긁지 않는가. 분양 공고는 보도자료와 쓰임이 다르다. 보도자료는 "무슨
일이 있었나"를 훑는 것이라 제목만 늘어놓아도 쓸모가 있지만, 공고는 결국
원문을 열어 평형·일정·자격을 봐야 한다. 제목만 베껴 와 봐야 한 번 더
누르게 할 뿐이다. 게다가 세 곳 다 공고가 뜨고 지는 주기가 제각각이라,
하루 세 번 훑어 모아 둘 까닭이 없다.

그래서 여기 주소는 홈페이지가 아니라 **공고 목록 화면**을 가리킨다.
연구·업계 쪽과 반대인데, 그쪽은 "그 기관이 뭘 내놓나"를 둘러보는 자리라
대문이 오래 가고, 이쪽은 "지금 뜬 공고가 뭔가"를 보러 가는 자리라 목록에
바로 닿아야 하기 때문이다. 대신 사이트가 개편되면 주소가 죽는다. 그때는
새 주소를 받아 여기만 고치면 된다.
"""

from __future__ import annotations

# 묶음 순서. 지금은 하나지만, 민간 분양이나 지자체 도시공사를 더하면
# 여기에 이름을 보태고 LINKS 의 group 만 맞춰 주면 된다.
LINK_GROUP_ORDER = ("공공분양",)

LINKS: tuple[dict[str, str], ...] = (
    {"name": "LH청약플러스", "group": "공공분양",
     "note": "한국토지주택공사 분양·임대 공고. 전국이 한자리에 모인다",
     "url": "https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancList.do?viewType=srch"},
    {"name": "LH 공지사항", "group": "공공분양",
     "note": "LH청약플러스 알려드려요 > 공지사항. 일정 변경·정정 공고가 여기 먼저 뜬다",
     "url": "https://apply.lh.or.kr/lhapply/apply/noti/an/list.do?slBbsKdCd=03&mi=1079"},
    {"name": "SH청약", "group": "공공분양",
     "note": "서울주택도시공사 주택분양 공고",
     "url": "https://www.i-sh.co.kr/app/lay2/program/S48T1581C1617/www/brd/m_244/list.do?multi_itm_seq=1"},
    {"name": "GH청약", "group": "공공분양",
     "note": "경기주택도시공사 분양·임대 공고",
     "url": "https://gh.or.kr/gh/announcement-of-salerental001.do"},
)
