"""
Pydantic 스키마 — Agent 백엔드
요청/응답 데이터 구조를 정의한다.
"""

from pydantic import BaseModel


# ─────────────────────────────────────────
# 인증
# ─────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    name: str
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    username: str
    name: str


# ─────────────────────────────────────────
# 장소 결과
# ─────────────────────────────────────────

class PlaceResult(BaseModel):
    """추천 결과 카드 한 장에 담길 장소 정보"""
    place_name: str
    category: str
    address: str
    distance: str
    place_url: str
    reason: str
    tags: list[str] = []
    lat: float | None = None
    lng: float | None = None


# ─────────────────────────────────────────
# 채팅 요청 / 응답
# ─────────────────────────────────────────

class ChatRequest(BaseModel):
    """사용자 채팅 입력"""
    message: str                        # 사용자가 입력한 자연어 메시지
    session_id: str | None = None       # 대화 세션 ID (없으면 새 세션)
    # 프론트엔드에서 유지하는 전체 대화 히스토리
    # 형식: [{"role": "user"|"assistant", "content": "..."}, ...]
    # 빈 리스트면 이전 대화 컨텍스트 없이 새로 시작
    conversation_history: list[dict] = []


class ChatResponse(BaseModel):
    """Agent 응답"""
    reply: str                                    # 자연어 설명
    complete: bool                                # 추천 완료 여부
    session_id: str | None = None                 # 이번 세션 ID
    recommendations: list[PlaceResult] | None = None  # 추천 장소 목록
    validation_result: dict | None = None         # 검증 결과
    tool_calls_log: list[dict] = []               # Agent가 실행한 도구 로그
    midpoint: str | None = None                   # 중간지점 주소
    midpoint_lat: float | None = None
    midpoint_lng: float | None = None
    participant_coords: list[dict] | None = None  # 참여자 출발지 좌표
