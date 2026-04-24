"""
Pydantic 스키마 — Multi-Agent 백엔드
"""

from pydantic import BaseModel


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


class PlaceResult(BaseModel):
    place_name: str
    category: str
    address: str
    distance: str
    place_url: str
    reason: str
    tags: list[str] = []
    lat: float | None = None
    lng: float | None = None


class AgentLogEntry(BaseModel):
    agent: str
    status: str          # "done" | "failed" | "skipped"
    summary: str
    duration_ms: int = 0
    details: dict = {}


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    conversation_history: list[dict] = []


class ChatResponse(BaseModel):
    reply: str
    complete: bool
    session_id: str | None = None
    recommendations: list[PlaceResult] | None = None
    validation_result: dict | None = None
    agent_log: list[AgentLogEntry] = []
    midpoint: str | None = None
    midpoint_lat: float | None = None
    midpoint_lng: float | None = None
    participant_coords: list[dict] | None = None
    retry_count: int = 0
