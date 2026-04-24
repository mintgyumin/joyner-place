"""
FastAPI 앱 — JOYNER Place Agent 백엔드

[엔드포인트]
POST /chat        ← Agent 대화 (JWT 인증 필요)
POST /auth/login  ← 로그인 → JWT 발급
POST /auth/register ← 회원가입
GET  /auth/verify ← 토큰 유효성 확인
GET  /health      ← 서버 상태 확인

포트: 8001 (기존 backend 8000과 충돌 방지)
"""

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    register_user,
    _init_users_yaml,
)
from schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    ChatRequest,
    ChatResponse,
    PlaceResult,
)
from agent import JoynerAgent


# ─────────────────────────────────────────
# 앱 초기화
# ─────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작 시 users.yaml 초기화."""
    _init_users_yaml()
    print("[startup] Agent 백엔드 준비 완료 (포트 8001)")
    yield


app = FastAPI(
    title="JOYNER Place Agent API",
    description="OpenAI Function Calling 기반 장소 추천 Agent",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — 프론트엔드(Streamlit)에서 호출 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Agent 인스턴스 (싱글턴 — 세션 상태 유지)
_agent = JoynerAgent()


# ─────────────────────────────────────────
# 인증 엔드포인트
# ─────────────────────────────────────────

@app.post("/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    """아이디 + 비밀번호로 로그인하고 JWT를 반환한다."""
    user = authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않아요.",
        )
    token = create_access_token({"sub": user["username"], "name": user["name"]})
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        username=user["username"],
        name=user["name"],
    )


@app.post("/auth/register")
async def register(req: RegisterRequest):
    """새 계정을 등록한다."""
    try:
        register_user(req.username, req.name, req.email, req.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "회원가입이 완료되었습니다."}


@app.get("/auth/verify")
async def verify(current_user: dict = Depends(get_current_user)):
    """토큰이 유효한지 확인한다."""
    return {"valid": True, "username": current_user["username"], "name": current_user["name"]}


# ─────────────────────────────────────────
# Agent 채팅 엔드포인트
# ─────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, current_user: dict = Depends(get_current_user)):
    """
    사용자 메시지를 Agent에게 전달하고 추천 결과를 반환한다.

    - session_id 없으면 새로 생성
    - Agent가 도구를 선택해 순차 실행
    - 최대 3회 재시도 후 최종 결과 반환
    """
    # 세션 ID 관리
    session_id = req.session_id or str(uuid.uuid4())

    try:
        # conversation_history를 함께 전달해 이전 대화 컨텍스트를 GPT가 볼 수 있게 한다
        result = _agent.run(
            message=req.message,
            session_id=session_id,
            conversation_history=req.conversation_history,
        )
    except Exception as e:
        print(f"[오류] Agent 실행 실패: {e}")
        raise HTTPException(status_code=500, detail=f"Agent 실행 중 오류 발생: {str(e)}")

    # PlaceResult로 변환
    recommendations = None
    if result.get("recommendations"):
        recommendations = [
            PlaceResult(**r) if not isinstance(r, PlaceResult) else r
            for r in result["recommendations"]
        ]

    return ChatResponse(
        reply=result.get("reply", ""),
        complete=result.get("complete", True),
        session_id=session_id,
        recommendations=recommendations,
        validation_result=result.get("validation_result"),
        tool_calls_log=result.get("tool_calls_log", []),
        midpoint=result.get("midpoint"),
        midpoint_lat=result.get("midpoint_lat"),
        midpoint_lng=result.get("midpoint_lng"),
        participant_coords=result.get("participant_coords"),
    )


# ─────────────────────────────────────────
# 상태 확인
# ─────────────────────────────────────────

@app.get("/health")
async def health():
    """서버 상태 확인."""
    return {"status": "ok", "service": "joyner-agent", "port": 8001}
