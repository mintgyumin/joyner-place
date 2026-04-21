"""
FastAPI 백엔드 진입점 — JOYNER Place

엔드포인트 목록:
  POST /auth/register          회원가입
  POST /auth/login             로그인 → JWT 반환
  POST /recommend              장소 추천 (인증 필요)
  GET  /favorites              즐겨찾기 목록 조회 (인증 필요)
  POST /favorites              즐겨찾기 추가 (인증 필요)
  DELETE /favorites/{name}     즐겨찾기 삭제 (인증 필요)
  PUT  /favorites/{name}/memo  메모 수정 (인증 필요)
  POST /appointments           약속 생성 (인증 필요)
  GET  /appointments           내 약속 목록 (인증 필요)
  GET  /appointments/{id}      약속 상세 (인증 필요)
  POST /appointments/{id}/join 약속 참여 (인증 필요)
  POST /appointments/{id}/respond 약속 수락/거절 (인증 필요)
"""

from contextlib import asynccontextmanager
from urllib.parse import unquote

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from auth import authenticate_user, create_access_token, get_current_user, register_user
from database import init_db
from schemas import (
    AppointmentCreate,
    AppointmentRespondRequest,
    FavoriteCreate,
    LoginRequest,
    MemoUpdate,
    PlaceSearchRequest,
    RegisterRequest,
    RecommendResponse,
    TokenResponse,
)
from retrieval import run_recommendation_pipeline
import favorites as fav_module
import appointment as apt_module


# ─────────────────────────────────────────
# 앱 시작 훅 — DB 테이블 초기화
# ─────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 앱 시작 시 DB 테이블을 자동 생성한다."""
    init_db()
    yield  # yield 이후는 앱 종료 시 실행 (필요 시 정리 코드 추가)


# ─────────────────────────────────────────
# FastAPI 앱 생성
# ─────────────────────────────────────────

app = FastAPI(
    title="JOYNER Place API",
    description="AI 기반 장소 추천 서비스 백엔드",
    version="2.0.0",
    lifespan=lifespan,
)

# ── CORS 설정 ────────────────────────────────────────────────────
# Streamlit 프론트엔드(다른 포트)에서 이 API를 호출하려면 CORS 허용이 필요하다.
# allow_origins=["*"]는 개발 편의용 — 운영 환경에서는 특정 도메인으로 제한 권장
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # 모든 출처 허용
    allow_credentials=True,
    allow_methods=["*"],        # GET, POST, PUT, DELETE 등 모두 허용
    allow_headers=["*"],        # Authorization 헤더 포함 모두 허용
)


# ─────────────────────────────────────────
# 인증 엔드포인트
# ─────────────────────────────────────────

@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest):
    """
    새 계정을 만든다.
    아이디 중복 시 409 Conflict 반환.
    """
    try:
        register_user(req.username, req.name, req.email, req.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return {"message": "회원가입 완료"}


@app.post("/auth/login", response_model=TokenResponse)
def login(req: LoginRequest):
    """
    아이디·비밀번호로 로그인하고 JWT 토큰을 반환한다.
    실패 시 401 Unauthorized 반환.
    """
    user = authenticate_user(req.username, req.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 틀렸어요.",
        )

    token = create_access_token({"sub": user["username"], "name": user["name"]})
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        username=user["username"],
        name=user["name"],
    )


# ─────────────────────────────────────────
# 장소 추천 엔드포인트
# ─────────────────────────────────────────

@app.post("/recommend", response_model=RecommendResponse)
def recommend(
    req: PlaceSearchRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    AI 장소 추천 파이프라인을 실행한다.
    (카카오 검색 → 임베딩 → FAISS → GPT 추천 이유)
    실패 시 400 Bad Request 반환.
    """
    try:
        return run_recommendation_pipeline(req)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ─────────────────────────────────────────
# 즐겨찾기 엔드포인트
# ─────────────────────────────────────────

@app.get("/favorites")
def list_favorites(current_user: dict = Depends(get_current_user)):
    """내 즐겨찾기 전체 목록을 반환한다."""
    return fav_module.get_favorites(current_user["username"])


@app.post("/favorites", status_code=status.HTTP_201_CREATED)
def add_favorite(
    req: FavoriteCreate,
    current_user: dict = Depends(get_current_user),
):
    """장소를 즐겨찾기에 추가한다. 이미 저장된 경우 409 반환."""
    added = fav_module.add_favorite(
        username=current_user["username"],
        place_name=req.place_name,
        place_address=req.place_address,
        place_url=req.place_url,
        category=req.category,
    )
    if not added:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 저장된 장소예요.")
    return {"message": "즐겨찾기 추가 완료"}


@app.delete("/favorites/{place_name}")
def delete_favorite(
    place_name: str,
    current_user: dict = Depends(get_current_user),
):
    """
    즐겨찾기에서 장소를 삭제한다.
    place_name은 URL 인코딩된 상태로 전달되며, FastAPI가 자동으로 디코딩한다.
    한국어 장소명 처리: unquote로 이중 인코딩 방지.
    """
    decoded_name = unquote(place_name)
    deleted = fav_module.remove_favorite(current_user["username"], decoded_name)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="즐겨찾기에 없는 장소예요.")
    return {"message": "즐겨찾기 삭제 완료"}


@app.put("/favorites/{place_name}/memo")
def update_memo(
    place_name: str,
    req: MemoUpdate,
    current_user: dict = Depends(get_current_user),
):
    """즐겨찾기에 저장된 장소의 메모를 수정한다."""
    decoded_name = unquote(place_name)
    updated = fav_module.update_memo(current_user["username"], decoded_name, req.memo)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="즐겨찾기에 없는 장소예요.")
    return {"message": "메모 수정 완료"}


# ─────────────────────────────────────────
# 약속 엔드포인트
# ─────────────────────────────────────────

@app.post("/appointments", status_code=status.HTTP_201_CREATED)
def create_appointment(
    req: AppointmentCreate,
    current_user: dict = Depends(get_current_user),
):
    """약속을 생성하고 6자리 코드를 반환한다."""
    code = apt_module.create_appointment(
        title=req.title,
        place_name=req.place_name,
        place_address=req.place_address,
        place_url=req.place_url,
        created_by=current_user["username"],
        date=req.date,
        time=req.time,
    )
    return {"code": code}


@app.get("/appointments")
def list_appointments(current_user: dict = Depends(get_current_user)):
    """내가 만들었거나 참여한 약속 전체 목록을 반환한다."""
    return apt_module.get_my_appointments(current_user["username"])


@app.get("/appointments/{apt_id}")
def get_appointment(
    apt_id: str,
    current_user: dict = Depends(get_current_user),
):
    """약속 상세 정보와 참여자 목록을 반환한다."""
    detail = apt_module.get_appointment_detail(apt_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="존재하지 않는 약속 코드예요.")
    return detail


@app.post("/appointments/{apt_id}/join")
def join_appointment(
    apt_id: str,
    current_user: dict = Depends(get_current_user),
):
    """약속 코드로 약속에 참여한다. 잘못된 코드면 404 반환."""
    ok = apt_module.join_appointment(apt_id, current_user["username"])
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="존재하지 않는 약속 코드예요.")
    return {"message": "약속 참여 완료"}


@app.post("/appointments/{apt_id}/respond")
def respond_appointment(
    apt_id: str,
    req: AppointmentRespondRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    약속을 수락하거나 거절한다.
    req.action은 "수락" 또는 "거절"이어야 한다.
    """
    if req.action == "수락":
        ok = apt_module.accept_appointment(apt_id, current_user["username"])
    elif req.action == "거절":
        ok = apt_module.reject_appointment(apt_id, current_user["username"])
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="action은 '수락' 또는 '거절'만 가능해요.",
        )

    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="참여 정보를 찾을 수 없어요.")
    return {"message": f"약속 {req.action} 완료"}
