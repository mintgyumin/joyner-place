"""
약속 관리 로직 모듈
- create_appointment()      : 약속 생성 → 6자리 코드 반환
- join_appointment()        : 코드로 약속 참여
- accept_appointment()      : 약속 수락 (전원 수락 시 자동 확정)
- reject_appointment()      : 약속 거절
- get_appointment_detail()  : 약속 상세 정보 + 참여자 목록
- get_my_appointments()     : 내 약속 전체 목록
"""

import random
import string
from datetime import datetime
from database import get_conn


# ─────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────

def _generate_code() -> str:
    """6자리 대문자+숫자 코드를 무작위로 생성한다."""
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=6))


def _unique_code() -> str:
    """DB에 중복이 없는 6자리 코드를 생성한다 (최대 10회 시도)."""
    conn = get_conn()
    for _ in range(10):
        code = _generate_code()
        exists = conn.execute(
            "SELECT 1 FROM appointments WHERE id = ?", (code,)
        ).fetchone()
        if not exists:
            conn.close()
            return code
    conn.close()
    raise RuntimeError("약속 코드 생성에 실패했어요. 잠시 후 다시 시도해주세요.")


def _update_member_status(appointment_id: str, username: str, new_status: str) -> bool:
    """
    참여자 상태를 변경하고, 전원 수락 시 약속을 '확정'으로 바꾼다.

    Returns:
        True  : 상태 변경 성공
        False : 해당 참여자를 찾지 못함
    """
    conn = get_conn()
    cur = conn.execute(
        "UPDATE appointment_members SET status = ? WHERE appointment_id = ? AND username = ?",
        (new_status, appointment_id, username),
    )
    if cur.rowcount == 0:
        conn.close()
        return False

    # 수락 처리 후 전원 수락 여부 확인 → 약속 자동 확정
    if new_status == "수락":
        not_accepted = conn.execute(
            "SELECT COUNT(*) FROM appointment_members WHERE appointment_id = ? AND status != '수락'",
            (appointment_id,),
        ).fetchone()[0]
        if not_accepted == 0:
            conn.execute(
                "UPDATE appointments SET status = '확정' WHERE id = ?",
                (appointment_id,),
            )

    conn.commit()
    conn.close()
    return True


# ─────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────

def create_appointment(
    title: str,
    place_name: str,
    place_address: str,
    place_url: str,
    created_by: str,
    date: str = "",
    time: str = "",
) -> str:
    """
    약속을 생성하고 6자리 코드를 반환한다.
    만든 사람은 자동으로 '수락' 상태로 참여자에 추가된다.

    Args:
        date: 약속 날짜 (선택, 예: "2024-12-25")
        time: 약속 시간 (선택, 예: "19:00")

    Returns:
        6자리 약속 코드 (예: "AB12CD")
    """
    code = _unique_code()
    now = datetime.now().isoformat(timespec="seconds")

    conn = get_conn()
    conn.execute(
        """
        INSERT INTO appointments
            (id, title, place_name, place_address, place_url, created_by, created_at, status, date, time)
        VALUES (?, ?, ?, ?, ?, ?, ?, '대기중', ?, ?)
        """,
        (code, title, place_name, place_address, place_url, created_by, now, date, time),
    )
    # 만든 사람은 자동 수락 처리
    conn.execute(
        """
        INSERT INTO appointment_members (appointment_id, username, status, joined_at)
        VALUES (?, ?, '수락', ?)
        """,
        (code, created_by, now),
    )
    conn.commit()
    conn.close()
    return code


def join_appointment(appointment_id: str, username: str) -> bool:
    """
    약속 코드로 약속에 참여한다.

    Returns:
        True  : 참여 성공 (이미 참여 중인 경우도 True)
        False : 존재하지 않는 코드
    """
    conn = get_conn()

    apt = conn.execute(
        "SELECT id FROM appointments WHERE id = ?", (appointment_id,)
    ).fetchone()
    if apt is None:
        conn.close()
        return False

    # 이미 참여한 경우 중복 추가 없이 True 반환
    already = conn.execute(
        "SELECT 1 FROM appointment_members WHERE appointment_id = ? AND username = ?",
        (appointment_id, username),
    ).fetchone()
    if already:
        conn.close()
        return True

    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO appointment_members (appointment_id, username, status, joined_at)
        VALUES (?, ?, '대기중', ?)
        """,
        (appointment_id, username, now),
    )
    conn.commit()
    conn.close()
    return True


def accept_appointment(appointment_id: str, username: str) -> bool:
    """약속을 수락한다. 전원 수락 시 약속 상태가 '확정'으로 변경된다."""
    return _update_member_status(appointment_id, username, "수락")


def reject_appointment(appointment_id: str, username: str) -> bool:
    """약속을 거절한다."""
    return _update_member_status(appointment_id, username, "거절")


def get_appointment_detail(appointment_id: str) -> dict:
    """
    약속 상세 정보와 참여자 목록을 반환한다.

    Returns:
        약속 정보 dict (members 리스트 포함). 약속이 없으면 빈 dict 반환.
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM appointments WHERE id = ?", (appointment_id,)
    ).fetchone()
    if row is None:
        conn.close()
        return {}

    detail = dict(row)
    members = conn.execute(
        "SELECT * FROM appointment_members WHERE appointment_id = ? ORDER BY joined_at",
        (appointment_id,),
    ).fetchall()
    detail["members"] = [dict(m) for m in members]

    conn.close()
    return detail


def get_my_appointments(username: str) -> list:
    """
    내가 만들었거나 참여한 약속 전체 목록을 최신순으로 반환한다.
    각 row에는 내 참여 상태(my_status)가 포함된다.
    """
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT a.*, am.status AS my_status
        FROM appointments a
        JOIN appointment_members am
          ON a.id = am.appointment_id AND am.username = ?
        ORDER BY a.created_at DESC
        """,
        (username,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
