"""
JWT 인증 모듈 — Multi-Agent 백엔드
"""

import os
import yaml
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

# ─────────────────────────────────────────
# 설정
# ─────────────────────────────────────────

SECRET_KEY = os.getenv("MULTI_AGENT_JWT_SECRET_KEY", "joyner-multi-agent-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

_DATA_DIR = Path(os.getenv("DATA_DIR", os.path.dirname(os.path.abspath(__file__))))
USERS_YAML = str(_DATA_DIR / "users.yaml")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ─────────────────────────────────────────
# YAML 헬퍼
# ─────────────────────────────────────────

def _init_users_yaml():
    if not os.path.exists(USERS_YAML):
        with open(USERS_YAML, "w", encoding="utf-8") as f:
            yaml.dump({"users": {}}, f, allow_unicode=True)

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
            yaml.dump(config, f, allow_unicode=True)
        print("[auth] 데모 계정 생성: demo / demo123")


def _load_users() -> dict:
    _init_users_yaml()
    with open(USERS_YAML, encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("users", {})


def _save_users(users: dict):
    with open(USERS_YAML, "w", encoding="utf-8") as f:
        yaml.dump({"users": users}, f, allow_unicode=True)


# ─────────────────────────────────────────
# 비밀번호
# ─────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ─────────────────────────────────────────
# JWT
# ─────────────────────────────────────────

def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="인증 정보가 유효하지 않아요. 다시 로그인해주세요.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username:
            raise exc
    except JWTError:
        raise exc

    users = _load_users()
    user = users.get(username)
    if not user:
        raise exc

    return {"username": username, "name": user.get("name", ""), "email": user.get("email", "")}


# ─────────────────────────────────────────
# 회원가입 / 로그인
# ─────────────────────────────────────────

def register_user(username: str, name: str, email: str, password: str) -> None:
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
    users = _load_users()
    user = users.get(username)
    if not user or not verify_password(password, user["password"]):
        return None
    return {"username": username, "name": user.get("name", ""), "email": user.get("email", "")}
