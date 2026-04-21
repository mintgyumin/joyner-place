"""
SQLite DB 관리 모듈
- get_conn() : DB 연결 반환 (row → dict 접근 가능)
- init_db()  : 앱 시작 시 테이블 자동 생성
"""

import os
import sqlite3

# DB 파일 위치: 컨테이너 기준 /app/data/joyner_place.db
DB_PATH = "/app/data/joyner_place.db"


def get_conn() -> sqlite3.Connection:
    """DB 연결을 반환한다. row["컬럼명"] 형태로 접근할 수 있도록 설정."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 딕셔너리처럼 컬럼명으로 접근 가능
    return conn


def init_db():
    """앱 시작 시 한 번 호출 — 테이블이 없으면 자동 생성한다."""
    conn = get_conn()
    cur = conn.cursor()

    # ── 약속 테이블 ─────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id            TEXT PRIMARY KEY,      -- 6자리 약속 코드 (예: AB12CD)
            title         TEXT NOT NULL,         -- 약속 이름
            place_name    TEXT NOT NULL,         -- 장소명
            place_address TEXT,                  -- 장소 주소
            place_url     TEXT,                  -- 카카오맵 URL
            created_by    TEXT NOT NULL,         -- 만든 사람 아이디
            created_at    TEXT NOT NULL,         -- 생성 시각 (ISO 형식)
            status        TEXT DEFAULT '대기중', -- 대기중 / 확정
            date          TEXT DEFAULT '',       -- 약속 날짜 (선택, 예: 2024-12-25)
            time          TEXT DEFAULT ''        -- 약속 시간 (선택, 예: 19:00)
        )
    """)

    # ── 참여자 테이블 ───────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS appointment_members (
            appointment_id TEXT NOT NULL,         -- 약속 코드 (FK)
            username       TEXT NOT NULL,         -- 참여자 아이디
            status         TEXT DEFAULT '대기중', -- 대기중 / 수락 / 거절
            joined_at      TEXT NOT NULL,         -- 참여 시각 (ISO 형식)
            PRIMARY KEY (appointment_id, username),
            FOREIGN KEY (appointment_id) REFERENCES appointments(id)
        )
    """)

    # ── 즐겨찾기 테이블 ────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            id            INTEGER PRIMARY KEY AUTOINCREMENT, -- 자동 증가 ID
            username      TEXT NOT NULL,                     -- 사용자 아이디
            place_name    TEXT NOT NULL,                     -- 장소명
            place_address TEXT,                              -- 주소
            place_url     TEXT,                              -- 카카오맵 URL
            category      TEXT,                              -- 카테고리
            memo          TEXT DEFAULT '',                   -- 메모 (선택)
            saved_at      TEXT NOT NULL,                     -- 저장 시각 (ISO 형식)
            UNIQUE (username, place_name)                    -- 같은 사용자가 같은 장소 중복 저장 방지
        )
    """)

    conn.commit()
    conn.close()
