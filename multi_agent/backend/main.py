"""
FastAPI 앱 — JOYNER Place Multi-Agent 백엔드 (포트 8003)

[엔드포인트]
POST /chat          ← Multi-Agent 파이프라인 실행 (JWT 인증)
POST /auth/login    ← 로그인 → JWT 발급
POST /auth/register ← 회원가입
GET  /auth/verify   ← 토큰 유효성 확인
GET  /health        ← 서버 상태 확인
"""

import json
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

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
    AgentLogEntry,
)
from orchestrator import MultiAgentOrchestrator

_DATA_DIR = Path(os.getenv("DATA_DIR", os.path.dirname(os.path.abspath(__file__))))


@asynccontextmanager
async def lifespan(app: FastAPI):
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _init_users_yaml()
    print("[startup] Multi-Agent 백엔드 준비 완료 (포트 8003)")
    yield


app = FastAPI(
    title="JOYNER Place Multi-Agent API",
    description="Multi-Agent 파이프라인 기반 장소 추천 (LocationAgent → SearchAgent → RecommendAgent → ValidationAgent)",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_orchestrator = MultiAgentOrchestrator()


# ─────────────────────────────────────────
# 인증
# ─────────────────────────────────────────

@app.post("/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest):
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
    try:
        register_user(req.username, req.name, req.email, req.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "회원가입이 완료되었습니다."}


@app.get("/auth/verify")
async def verify(current_user: dict = Depends(get_current_user)):
    return {"valid": True, "username": current_user["username"], "name": current_user["name"]}


# ─────────────────────────────────────────
# Multi-Agent 채팅
# ─────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, current_user: dict = Depends(get_current_user)):
    """
    Multi-Agent 파이프라인을 실행하고 추천 결과를 반환한다.
    LocationAgent → SearchAgent → RecommendAgent → ValidationAgent
    """
    session_id = req.session_id or str(uuid.uuid4())

    try:
        result = _orchestrator.run(
            message=req.message,
            session_id=session_id,
            conversation_history=req.conversation_history,
        )
    except Exception as e:
        print(f"[오류] Orchestrator 실행 실패: {e}")
        raise HTTPException(status_code=500, detail=f"Multi-Agent 실행 중 오류 발생: {str(e)}")

    # PlaceResult 변환
    recommendations = None
    if result.get("recommendations"):
        recommendations = [
            PlaceResult(**r) if not isinstance(r, PlaceResult) else r
            for r in result["recommendations"]
        ]

    # AgentLogEntry 변환
    agent_log = [
        AgentLogEntry(**entry) if not isinstance(entry, AgentLogEntry) else entry
        for entry in result.get("agent_log", [])
    ]

    return ChatResponse(
        reply=result.get("reply", ""),
        complete=result.get("complete", True),
        session_id=session_id,
        recommendations=recommendations,
        validation_result=result.get("validation_result"),
        agent_log=agent_log,
        midpoint=result.get("midpoint"),
        midpoint_lat=result.get("midpoint_lat"),
        midpoint_lng=result.get("midpoint_lng"),
        participant_coords=result.get("participant_coords"),
        retry_count=result.get("retry_count", 0),
    )


# ─────────────────────────────────────────
# 즐겨찾기 / 대화 영속화
# ─────────────────────────────────────────

@app.get("/user/favorites")
async def get_favorites(current_user: dict = Depends(get_current_user)):
    path = _DATA_DIR / f"{current_user['username']}_favorites.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []


@app.post("/user/favorites")
async def save_favorites(data: list, current_user: dict = Depends(get_current_user)):
    path = _DATA_DIR / f"{current_user['username']}_favorites.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return {"ok": True}


@app.get("/user/conversations")
async def get_conversations(current_user: dict = Depends(get_current_user)):
    path = _DATA_DIR / f"{current_user['username']}_conversations.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []


@app.post("/user/conversations")
async def save_conversations(data: list, current_user: dict = Depends(get_current_user)):
    path = _DATA_DIR / f"{current_user['username']}_conversations.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return {"ok": True}


# ─────────────────────────────────────────
# 상태 확인
# ─────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "joyner-multi-agent",
        "port": 8003,
        "agents": ["location_agent", "search_agent", "recommend_agent", "validation_agent"],
    }
