"""
JWT 인증 모듈
- hash_password()       : 평문 비밀번호 → bcrypt 해시
- verify_password()     : 입력 비밀번호와 해시 비교
- create_access_token() : JWT 토큰 생성
- get_current_user()    : FastAPI 의존성 — Authorization 헤더에서 토큰 추출 + 검증
- register_user()       : 새 유저를 users.yaml에 등록
- authenticate_user()   : 아이디 + 비밀번호 검증 → 유저 정보 반환
"""

import os
import yaml
from datetime import datetime, timedelta, timezone

import bcrypt

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

# ─────────────────────────────────────────
# 설정값
# ─────────────────────────────────────────

# JWT 서명 키 — 반드시 .env에서 강력한 값으로 교체
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "joyner-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7  # 토큰 유효 기간: 7일

# users.yaml 경로 (컨테이너 기준 /app/users.yaml)
USERS_YAML = os.path.join(os.path.dirname(__file__), "users.yaml")

# ─────────────────────────────────────────
# 비밀번호 해시 도구 (bcrypt)
# ─────────────────────────────────────────

# OAuth2PasswordBearer: "Authorization: Bearer <token>" 헤더에서 토큰을 추출해준다
# tokenUrl은 Swagger UI에서 "Authorize" 버튼 클릭 시 이동하는 로그인 URL
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ─────────────────────────────────────────
# 유저 YAML 초기화
# ─────────────────────────────────────────

def _init_users_yaml():
    """users.yaml이 없거나 유저가 0명이면 데모 계정을 자동 생성한다."""
    # 파일이 없으면 빈 구조 생성
    if not os.path.exists(USERS_YAML):
        config = {"users": {}}
        with open(USERS_YAML, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

    # 유저가 한 명도 없으면 데모 계정 추가 — 아이디: demo / 비밀번호: demo123
    with open(USERS_YAML, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    users = config.get("users") or {}

    if not users:
        config["users"] = {
            "demo": {
                "name": "데모 유저",
                "email": "demo@joyner.com",
                "password": hash_password("demo123"),
            }
        }
        with open(USERS_YAML, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        print("[auth] users.yaml 초기화 완료. 데모 계정: demo / demo123")


def _load_users() -> dict:
    """users.yaml을 읽어 유저 딕셔너리를 반환한다."""
    _init_users_yaml()
    with open(USERS_YAML, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    return config.get("users", {})


def _save_users(users: dict):
    """유저 딕셔너리를 users.yaml에 저장한다."""
    with open(USERS_YAML, "w", encoding="utf-8") as f:
        yaml.dump({"users": users}, f, allow_unicode=True, default_flow_style=False)


# ─────────────────────────────────────────
# 비밀번호 처리
# ─────────────────────────────────────────

def hash_password(password: str) -> str:
    """평문 비밀번호를 bcrypt 해시 문자열로 변환한다."""
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """입력한 비밀번호가 저장된 해시와 일치하는지 검증한다."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


# ─────────────────────────────────────────
# JWT 토큰
# ─────────────────────────────────────────

def create_access_token(data: dict) -> str:
    """
    JWT 액세스 토큰을 생성한다.

    Args:
        data: 토큰에 담을 정보 (예: {"sub": "username", "name": "홍길동"})

    Returns:
        서명된 JWT 문자열
    """
    payload = data.copy()
    # 만료 시각 설정 (UTC 기준)
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload["exp"] = expire

    # jose 라이브러리로 서명
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """
    FastAPI 의존성 함수 — 모든 인증 필요 엔드포인트에서 사용.

    Authorization: Bearer <token> 헤더에서 토큰을 꺼내
    서명과 만료를 검증한 후 유저 정보를 반환한다.

    Raises:
        HTTPException 401: 토큰이 없거나 유효하지 않을 때
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="인증 정보가 유효하지 않아요. 다시 로그인해주세요.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # 토큰 디코딩 + 서명 검증 + 만료 확인
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # DB에서 유저 존재 여부 재확인 (탈퇴/변경 대응)
    users = _load_users()
    user = users.get(username)
    if user is None:
        raise credentials_exception

    return {"username": username, "name": user.get("name", ""), "email": user.get("email", "")}


# ─────────────────────────────────────────
# 회원가입 / 로그인
# ─────────────────────────────────────────

def register_user(username: str, name: str, email: str, password: str) -> None:
    """
    새 유저를 users.yaml에 등록한다.

    Raises:
        ValueError: 이미 존재하는 아이디일 때
    """
    users = _load_users()

    if username in users:
        raise ValueError(f"이미 사용 중인 아이디예요: {username}")

    users[username] = {
        "name": name,
        "email": email,
        "password": hash_password(password),
    }
    _save_users(users)


def authenticate_user(username: str, password: str) -> dict | None:
    """
    아이디와 비밀번호를 검증하고, 성공하면 유저 정보를 반환한다.

    Returns:
        유저 정보 dict (username, name, email 포함).
        인증 실패 시 None 반환.
    """
    users = _load_users()
    user = users.get(username)

    if user is None:
        return None  # 존재하지 않는 아이디

    if not verify_password(password, user["password"]):
        return None  # 비밀번호 불일치

    return {"username": username, "name": user.get("name", ""), "email": user.get("email", "")}
