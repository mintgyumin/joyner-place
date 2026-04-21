"""
즐겨찾기 관리 모듈
- add_favorite()    : 장소 즐겨찾기 추가
- remove_favorite() : 즐겨찾기 삭제
- get_favorites()   : 내 즐겨찾기 목록 (최신순)
- is_favorite()     : 이미 저장된 장소인지 확인
- update_memo()     : 저장된 장소에 메모 수정
"""

from datetime import datetime
from database import get_conn


def add_favorite(
    username: str,
    place_name: str,
    place_address: str,
    place_url: str,
    category: str,
) -> bool:
    """
    장소를 즐겨찾기에 추가한다.

    Returns:
        True  : 추가 성공
        False : 이미 저장된 장소 (중복)
    """
    conn = get_conn()

    already = conn.execute(
        "SELECT 1 FROM favorites WHERE username = ? AND place_name = ?",
        (username, place_name),
    ).fetchone()

    if already:
        conn.close()
        return False

    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO favorites
            (username, place_name, place_address, place_url, category, memo, saved_at)
        VALUES (?, ?, ?, ?, ?, '', ?)
        """,
        (username, place_name, place_address, place_url, category, now),
    )
    conn.commit()
    conn.close()
    return True


def remove_favorite(username: str, place_name: str) -> bool:
    """
    즐겨찾기에서 장소를 삭제한다.

    Returns:
        True  : 삭제 성공
        False : 해당 장소를 찾지 못함
    """
    conn = get_conn()
    cur = conn.execute(
        "DELETE FROM favorites WHERE username = ? AND place_name = ?",
        (username, place_name),
    )
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def get_favorites(username: str) -> list:
    """
    내 즐겨찾기 목록을 최신 저장순으로 반환한다.

    Returns:
        list of dict: [{"id", "place_name", "place_address", "place_url",
                        "category", "memo", "saved_at"}, ...]
    """
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT * FROM favorites
        WHERE username = ?
        ORDER BY saved_at DESC
        """,
        (username,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def is_favorite(username: str, place_name: str) -> bool:
    """해당 장소가 이미 즐겨찾기에 저장되어 있으면 True를 반환한다."""
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM favorites WHERE username = ? AND place_name = ?",
        (username, place_name),
    ).fetchone()
    conn.close()
    return row is not None


def update_memo(username: str, place_name: str, memo: str) -> bool:
    """
    즐겨찾기에 저장된 장소의 메모를 수정한다.

    Returns:
        True  : 수정 성공
        False : 해당 장소를 찾지 못함
    """
    conn = get_conn()
    cur = conn.execute(
        "UPDATE favorites SET memo = ? WHERE username = ? AND place_name = ?",
        (memo, username, place_name),
    )
    updated = cur.rowcount > 0
    conn.commit()
    conn.close()
    return updated
