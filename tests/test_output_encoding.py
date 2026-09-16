"""화면에 내보내는 글자 때문에 수집이 멈추지 않아야 한다.

2026-09-16에 실제로 겪은 일이다. 자동 수집이 하루 세 번 돌면서 매번
첫 줄에서 죽고 있었는데, 화면은 예전 자료로 계속 다시 만들어지니
겉으로는 멀쩡해 보였다. 사흘치가 그대로 날아갔다.

원인은 안내문에 섞인 '—' 한 글자였다. 결과를 파일로 넘기면(`>> 수집기록.txt`)
윈도우 파이썬이 옛 한글 인코딩(cp949)으로 쓰려 드는데, 그 글자를 못 써서
UnicodeEncodeError로 프로그램이 통째로 멈춘다.
"""

from __future__ import annotations

import io

from govpress.__main__ import use_utf8

# 안내문에 실제로 들어 있는 글자들. cp949로는 '—'를 쓸 수 없다.
DASH = "수집 시작 — 전체 공공기관 · 최근 3페이지"


def _cp949_stream() -> io.TextIOWrapper:
    """결과를 파일로 넘겼을 때의 윈도우 기본 상태를 흉내 낸다."""
    return io.TextIOWrapper(io.BytesIO(), encoding="cp949")


def test_고치기_전이라면_정말로_터진다():
    """이 테스트가 무엇을 막고 있는지 분명히 해 둔다."""
    stream = _cp949_stream()
    try:
        stream.write(DASH)
        stream.flush()
    except UnicodeEncodeError:
        return
    raise AssertionError("cp949에서 '—'가 써졌습니다. 전제가 바뀌었는지 확인하세요")


def test_출력을_UTF8로_바꾸면_멈추지_않는다():
    stream = _cp949_stream()
    use_utf8(stream)
    stream.write(DASH)
    stream.flush()
    assert stream.encoding == "utf-8"


def test_바꿀_수_없는_스트림이어도_그냥_넘어간다():
    """파이프나 가짜 스트림을 만나 프로그램이 죽으면 본말전도다."""

    class 못바꿈:
        encoding = "cp949"

        def reconfigure(self, **kwargs):
            raise OSError("이 스트림은 못 바꿉니다")

    use_utf8(못바꿈(), None, object())  # 아무 일도 일어나지 않아야 한다


def test_읽을_수_없는_글자가_와도_멈추지_않는다():
    """errors='replace'까지 걸려 있어야 한다."""
    stream = _cp949_stream()
    use_utf8(stream)
    assert stream.errors == "replace"
