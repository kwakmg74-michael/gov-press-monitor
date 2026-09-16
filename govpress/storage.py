"""SQLite 저장소. (source, uid) 기준으로 중복을 막는다."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

from .models import Article

DEFAULT_DB = "articles.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    category      TEXT NOT NULL DEFAULT '정부기관',
    source        TEXT NOT NULL,
    uid           TEXT NOT NULL,
    agency        TEXT NOT NULL DEFAULT '',
    title         TEXT NOT NULL,
    link          TEXT NOT NULL,
    published_at  TEXT NOT NULL DEFAULT '',
    summary       TEXT NOT NULL DEFAULT '',
    collected_at  TEXT NOT NULL,
    UNIQUE (source, uid)
);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_agency ON articles (agency);
CREATE INDEX IF NOT EXISTS idx_articles_category ON articles (category);
"""


def _migrate_legacy(conn: sqlite3.Connection) -> bool:
    """구버전 articles 테이블이 있으면 옆으로 치워 둔다.

    0.1.x는 (agency, title, link, published_at, summary) 스키마를 썼고
    수집 품질도 신뢰할 수 없다(게시일이 전부 비어 있었다). 지우지는 않고
    `articles_legacy`로 이름만 바꿔 새 스키마가 깨끗하게 만들어지게 한다.
    """
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='articles'"
    ).fetchone()
    if not exists:
        return False

    columns = {row[1] for row in conn.execute("PRAGMA table_info(articles)")}
    if "uid" in columns:
        return False

    conn.execute("DROP TABLE IF EXISTS articles_legacy")
    conn.execute("ALTER TABLE articles RENAME TO articles_legacy")
    conn.commit()
    return True


def _ensure_category_column(conn: sqlite3.Connection) -> bool:
    """category 없이 만들어진 DB에 열을 덧붙인다.

    그 시점의 데이터는 전부 korea.kr(정부기관)이므로 그렇게 채운다.
    """
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='articles'"
    ).fetchone()
    if not exists:
        return False

    columns = {row[1] for row in conn.execute("PRAGMA table_info(articles)")}
    if "category" not in columns and "uid" in columns:
        conn.execute("ALTER TABLE articles ADD COLUMN category TEXT NOT NULL DEFAULT '정부기관'")
        conn.commit()
        return True
    return False


def connect(db_path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    _migrate_legacy(conn)
    _ensure_category_column(conn)
    conn.executescript(SCHEMA)
    return conn


def save(articles: Iterable[Article], db_path: str | Path = DEFAULT_DB) -> dict:
    """새 건수와 전체 건수를 돌려준다. 이미 있는 항목은 건드리지 않는다."""
    rows = [a.as_row() for a in articles if a.is_valid()]
    now = datetime.now().isoformat(timespec="seconds")

    conn = connect(db_path)
    try:
        before = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        conn.executemany(
            """
            INSERT OR IGNORE INTO articles
                (category, source, uid, agency, title, link,
                 published_at, summary, collected_at)
            VALUES
                (:category, :source, :uid, :agency, :title, :link,
                 :published_at, :summary, :collected_at)
            """,
            [dict(row, collected_at=now) for row in rows],
        )
        conn.commit()
        after = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    finally:
        conn.close()

    return {"submitted": len(rows), "new": after - before, "total": after}


def known_uids(
    sources: Iterable[str], db_path: str | Path = DEFAULT_DB
) -> set[tuple[str, str]]:
    """이미 저장해 둔 (출처, 글번호) 짝.

    목록에 날짜가 없는 게시판(KDI 등)은 글 하나하나를 열어 봐야 발간일을
    알 수 있다. 매번 다 열면 실례이므로, 이미 가진 글은 건너뛰려고 쓴다.
    """
    wanted = list(sources)
    if not wanted:
        return set()

    conn = connect(db_path)
    try:
        holes = ",".join("?" * len(wanted))
        rows = conn.execute(
            f"SELECT source, uid FROM articles WHERE source IN ({holes})", wanted
        ).fetchall()
    finally:
        conn.close()

    return {(row["source"], row["uid"]) for row in rows}


def list_articles(
    db_path: str | Path = DEFAULT_DB,
    limit: int | None = None,
    agency: str | None = None,
    category: str | None = None,
) -> list[dict]:
    query = (
        "SELECT category, source, uid, agency, title, link, "
        "published_at, summary, collected_at FROM articles"
    )
    params: list = []
    clauses: list[str] = []
    if agency:
        clauses.append("agency = ?")
        params.append(agency)
    if category:
        clauses.append("category = ?")
        params.append(category)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    # 같은 날짜 안에서는 출처의 게시 순서(uid가 클수록 최신)를 따른다.
    query += " ORDER BY published_at DESC, uid DESC, id DESC"
    if limit:
        query += " LIMIT ?"
        params.append(limit)

    conn = connect(db_path)
    try:
        return [dict(r) for r in conn.execute(query, params).fetchall()]
    finally:
        conn.close()


def agencies(db_path: str | Path = DEFAULT_DB) -> Sequence[tuple[str, int]]:
    conn = connect(db_path)
    try:
        return [
            (r["agency"], r["n"])
            for r in conn.execute(
                "SELECT agency, COUNT(*) AS n FROM articles "
                "WHERE agency != '' GROUP BY agency ORDER BY n DESC, agency"
            ).fetchall()
        ]
    finally:
        conn.close()


def stats(db_path: str | Path = DEFAULT_DB) -> dict:
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS total, "
            "COUNT(DISTINCT category) AS categories, "
            "COUNT(DISTINCT agency) AS agencies, "
            "MIN(published_at) AS first_day, "
            "MAX(published_at) AS last_day, "
            "MAX(collected_at) AS last_run "
            "FROM articles"
        ).fetchone()
        return dict(row)
    finally:
        conn.close()
