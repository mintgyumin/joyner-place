# ─────────────────────────────────────────
# JOYNER Place — Backend Dockerfile
# ─────────────────────────────────────────
# 베이스 이미지: 공식 Python 3.12 슬림 버전
FROM python:3.12-slim

# 컨테이너 안에서 작업할 디렉토리
WORKDIR /app

# ── 의존성 설치 (캐시 최적화) ──────────────────────────────────
# requirements.txt를 먼저 복사하는 이유:
# 코드가 바뀌어도 패키지가 변하지 않으면 이 레이어를 캐시에서 재사용 → 빌드 속도 향상
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# ── 앱 코드 전체 복사 ──────────────────────────────────────────
COPY . .

# DB 저장 디렉토리 미리 생성 (볼륨 마운트 전 경로 보장)
RUN mkdir -p /app/data

# ── 포트 노출 ─────────────────────────────────────────────────
# FastAPI 백엔드는 8000번 포트 사용 (Streamlit 8501과 분리)
EXPOSE 8000

# ── 컨테이너 시작 명령어 ──────────────────────────────────────
# uvicorn: FastAPI용 ASGI 서버
# --host 0.0.0.0  : 컨테이너 외부에서 접속 허용
# --port 8000     : 포트 명시
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
