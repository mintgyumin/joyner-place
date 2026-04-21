# ─────────────────────────────────────────
# JOYNER Place — Frontend Dockerfile
# ─────────────────────────────────────────
# 베이스 이미지: 공식 Python 3.12 슬림 버전
FROM python:3.12-slim

# 컨테이너 안에서 작업할 디렉토리
WORKDIR /app

# ── 의존성 설치 (캐시 최적화) ──────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── 앱 코드 + 테마 설정 복사 ──────────────────────────────────
COPY app.py .
COPY .streamlit/ .streamlit/

# ── 포트 노출 ─────────────────────────────────────────────────
# Streamlit 기본 포트
EXPOSE 8501

# ── 컨테이너 시작 명령어 ──────────────────────────────────────
# --server.address 0.0.0.0 : 컨테이너 외부에서 접속 허용
# --server.port 8501        : 포트 명시
# --server.headless true    : 브라우저 자동 실행 안 함 (Docker 환경)
CMD ["streamlit", "run", "app.py", "--server.address", "0.0.0.0", "--server.port", "8501", "--server.headless", "true"]
