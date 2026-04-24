"""
Pydantic 스키마 모듈
- FastAPI 요청(Request)과 응답(Response)의 데이터 형식을 정의한다.
- Pydantic은 타입 힌트를 보고 자동으로 데이터 유효성 검사를 해준다.
  예: int여야 하는데 문자열이 오면 자동으로 422 오류 반환
"""

from pydantic import BaseModel


# ─────────────────────────────────────────
# 인증 관련 스키마
# ─────────────────────────────────────────

class RegisterRequest(BaseModel):
    """회원가입 요청 바디"""
    username: str   # 로그인 아이디
    name: str       # 표시 이름
    email: str      # 이메일
    password: str   # 평문 비밀번호 (서버에서 해시 처리)


class LoginRequest(BaseModel):
    """로그인 요청 바디"""
    username: str
    password: str


class TokenResponse(BaseModel):
    """로그인 성공 시 반환하는 JWT 토큰 정보"""
    access_token: str   # JWT 문자열
    token_type: str     # 항상 "bearer"
    username: str       # 로그인한 유저 아이디
    name: str           # 로그인한 유저 이름


# ─────────────────────────────────────────
# 장소 추천 관련 스키마
# ─────────────────────────────────────────

class PlaceSearchRequest(BaseModel):
    """장소 추천 요청 바디"""
    location: str = ""             # 단일 위치 모드일 때 사용 (예: "강남역")
    purpose: str                   # 모임 목적 (예: "팀 회식")
    time_slot: str                 # 시간대 (예: "저녁 (17:00~21:00)")
    people_count: int              # 인원수
    locations: list[str] | None = None  # 다중 참여자 모드일 때 각 위치 리스트


class PlaceResult(BaseModel):
    """추천 결과 카드 한 장에 담길 장소 정보"""
    place_name: str          # 장소명
    category: str            # 카테고리 최말단 (예: "카페")
    address: str             # 도로명 또는 지번 주소
    distance: str            # 중심 좌표에서의 거리 (예: "42")
    place_url: str           # 카카오맵 URL
    reason: str              # GPT가 생성한 추천 이유
    tags: list[str] = []     # GPT가 생성한 특징 태그 (예: ["#조용한분위기", "#주차가능"])
    lat: float | None = None  # 위도 (지도 핀 표시용)
    lng: float | None = None  # 경도 (지도 핀 표시용)


class RecommendResponse(BaseModel):
    """장소 추천 API 응답"""
    places: list[PlaceResult]                    # 추천 장소 목록
    midpoint: str | None = None                  # 다중 참여자 모드일 때 중간지점 주소
    midpoint_lat: float | None = None            # 중간지점 위도
    midpoint_lng: float | None = None            # 중간지점 경도
    participant_coords: list[dict] | None = None  # 참여자 출발지 좌표 목록


# ─────────────────────────────────────────
# 즐겨찾기 관련 스키마
# ─────────────────────────────────────────

class FavoriteCreate(BaseModel):
    """즐겨찾기 추가 요청 바디"""
    place_name: str
    place_address: str
    place_url: str
    category: str


class MemoUpdate(BaseModel):
    """즐겨찾기 메모 수정 요청 바디"""
    memo: str


# ─────────────────────────────────────────
# 약속 관련 스키마
# ─────────────────────────────────────────

class AppointmentCreate(BaseModel):
    """약속 생성 요청 바디"""
    title: str          # 약속 이름 (예: "이번주 팀 회식")
    place_name: str     # 장소명
    place_address: str  # 장소 주소
    place_url: str      # 카카오맵 URL
    date: str = ""      # 날짜 (선택, 예: "2024-12-25")
    time: str = ""      # 시간 (선택, 예: "19:00")


class AppointmentRespondRequest(BaseModel):
    """약속 수락/거절 요청 바디"""
    action: str  # "수락" 또는 "거절"
