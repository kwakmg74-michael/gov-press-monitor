from __future__ import annotations

from govpress import storage
from govpress.models import Article


def make(uid: str, agency: str = "교육부", day: str = "2026-09-08",
         category: str = "정부기관") -> Article:
    return Article(
        category=category,
        source="korea.kr",
        uid=uid,
        agency=agency,
        title=f"보도자료 제목 {uid}",
        link=f"https://www.korea.kr/briefing/pressReleaseView.do?newsId={uid}",
        published_at=day,
        summary="요약",
    )


def test_저장하고_다시_읽는다(tmp_path):
    db = tmp_path / "t.db"
    result = storage.save([make("1"), make("2")], db)
    assert result == {"submitted": 2, "new": 2, "total": 2}
    assert len(storage.list_articles(db)) == 2


def test_같은_uid는_중복_저장되지_않는다(tmp_path):
    db = tmp_path / "t.db"
    storage.save([make("1")], db)
    result = storage.save([make("1"), make("2")], db)
    assert result["new"] == 1
    assert result["total"] == 2


def test_날짜가_없는_항목은_저장하지_않는다(tmp_path):
    db = tmp_path / "t.db"
    broken = Article(
        category="정부기관", source="korea.kr", uid="9", agency="교육부",
        title="제목", link="https://example.com", published_at="",
    )
    assert storage.save([broken], db)["total"] == 0


def test_분류가_없으면_저장하지_않는다(tmp_path):
    """탭이 분류에 기대므로, 분류 없는 레코드는 들어오면 안 된다."""
    db = tmp_path / "t.db"
    no_category = Article(
        source="korea.kr", uid="9", agency="교육부", title="제목",
        link="https://example.com", published_at="2026-09-08",
    )
    assert storage.save([no_category], db)["total"] == 0

    wrong = Article(
        category="엉뚱한분류", source="korea.kr", uid="8", agency="교육부",
        title="제목", link="https://example.com", published_at="2026-09-08",
    )
    assert storage.save([wrong], db)["total"] == 0


def test_분류로_걸러_읽는다(tmp_path):
    db = tmp_path / "t.db"
    storage.save(
        [make("1"), make("2", category="지자체"), make("3", category="지자체")], db
    )
    assert len(storage.list_articles(db, category="지자체")) == 2
    assert len(storage.list_articles(db, category="정부기관")) == 1
    assert len(storage.list_articles(db)) == 3


def test_category_없는_DB에_열을_덧붙인다(tmp_path):
    """0.2.x DB로 계속 수집할 수 있어야 한다."""
    import sqlite3

    db = tmp_path / "old.db"
    old = sqlite3.connect(db)
    old.execute(
        "CREATE TABLE articles (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, "
        "uid TEXT NOT NULL, agency TEXT, title TEXT, link TEXT, published_at TEXT, "
        "summary TEXT, collected_at TEXT NOT NULL, UNIQUE(source, uid))"
    )
    old.execute(
        "INSERT INTO articles (source, uid, agency, title, link, published_at, summary, collected_at) "
        "VALUES ('korea.kr', '100', '교육부', '옛 기사', 'https://x', '2026-09-01', '', '2026-09-01T00:00:00')"
    )
    old.commit()
    old.close()

    rows = storage.list_articles(db)
    assert len(rows) == 1
    assert rows[0]["category"] == "정부기관", "기존 데이터는 정부기관으로 채워져야 한다"

    assert storage.save([make("200")], db)["new"] == 1


def test_최신순으로_정렬된다(tmp_path):
    db = tmp_path / "t.db"
    storage.save([make("1", day="2026-09-01"), make("2", day="2026-09-08")], db)
    rows = storage.list_articles(db)
    assert [r["uid"] for r in rows] == ["2", "1"]


def test_기관별_집계(tmp_path):
    db = tmp_path / "t.db"
    storage.save([make("1", "교육부"), make("2", "교육부"), make("3", "국토교통부")], db)
    assert storage.agencies(db)[0] == ("교육부", 2)


def test_기관_필터(tmp_path):
    db = tmp_path / "t.db"
    storage.save([make("1", "교육부"), make("2", "국토교통부")], db)
    rows = storage.list_articles(db, agency="국토교통부")
    assert len(rows) == 1 and rows[0]["agency"] == "국토교통부"


def test_같은_날짜면_uid_큰_것이_먼저_온다(tmp_path):
    """korea.kr은 newsId가 클수록 최신 글이다."""
    db = tmp_path / "t.db"
    storage.save([make("156780600"), make("156780900"), make("156780700")], db)
    assert [r["uid"] for r in storage.list_articles(db)] == [
        "156780900", "156780700", "156780600",
    ]


def test_구버전_DB를_만나도_깨지지_않는다(tmp_path):
    """0.1.x 스키마가 남아 있어도 새로 수집할 수 있어야 한다."""
    import sqlite3

    db = tmp_path / "legacy.db"
    old = sqlite3.connect(db)
    old.execute(
        "CREATE TABLE articles (id INTEGER PRIMARY KEY, agency TEXT, title TEXT, "
        "link TEXT UNIQUE, published_at TEXT, summary TEXT)"
    )
    old.execute(
        "INSERT INTO articles (agency, title, link, published_at, summary) "
        "VALUES ('교육부', '공지사항', 'https://x', '', '')"
    )
    old.commit()
    old.close()

    assert storage.save([make("1")], db)["total"] == 1
    rows = storage.list_articles(db)
    assert len(rows) == 1 and rows[0]["uid"] == "1"

    # 예전 데이터는 지우지 않고 옆으로 옮겨 둔다
    conn = sqlite3.connect(db)
    legacy = conn.execute("SELECT COUNT(*) FROM articles_legacy").fetchone()[0]
    conn.close()
    assert legacy == 1
