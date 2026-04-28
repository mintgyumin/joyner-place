# JOYNER Place

> AI 기반 모임 장소 추천 서비스 — Kakao Maps + RAG + GPT

<p align="center">
  <img src="docs/images/banner.png" alt="JOYNER Place 배너" width="100%"/>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white"/>
  <img src="https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square&logo=fastapi&logoColor=white"/>
  <img src="https://img.shields.io/badge/Streamlit-1.35-FF4B4B?style=flat-square&logo=streamlit&logoColor=white"/>
  <img src="https://img.shields.io/badge/OpenAI-GPT--4-412991?style=flat-square&logo=openai&logoColor=white"/>
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white"/>
</p>

---

## 문제 정의

JOYNER는 AI 에이전트 간 자율 협상(A2A)으로 다중 참여자의 일정을 자동 조율하는 서비스입니다.

일정이 확정되는 순간, 자연스럽게 다음 질문이 생깁니다.

> **"그래서 우리 어디서 만나?"**

기존 방식은 여전히 수동입니다. 참여자가 각자 카카오맵·네이버지도를 열고, 장소를 검색하고, 단체 채팅방에 링크를 뿌리고, 또 다시 조율합니다. 일정 조율을 AI로 해결했지만 장소 결정은 여전히 사람이 반복 소통해야 하는 문제가 남아 있습니다.

특히 두 가지 상황이 반복적으로 불편합니다.

**1. 한 장소 기준 모임**
목적과 분위기에 맞는 장소를 직접 검색해야 하고, 인원·시간대·카테고리 조건을 모두 따져가며 고르는 데 상당한 시간이 걸립니다.

**2. 여러 곳에서 오는 모임**
참여자들이 서로 다른 지역에서 올 때 "어디가 중간이지?"를 계산하고, 그 주변에서 장소까지 찾는 과정이 이중으로 번거롭습니다.

---

## 해결 방향

**JOYNER Place**는 이 문제를 AI 파이프라인으로 자동화합니다.

자연어 한 문장만 입력하면 위치 파악 → 장소 검색 → 품질 검증 → 추천 이유 생성까지 모든 과정이 자동으로 처리됩니다.

```
"강남역이랑 홍대입구 중간에서 6명이서 저녁 고깃집"
         │
         ▼
  📍 중간지점 자동 계산 (공덕역 인근)
         │
         ▼
  🔍 Kakao API + FAISS + BM25 하이브리드 검색
         │
         ▼
  🤖 GPT 카테고리 필터링 + 맞춤 추천 이유 생성
         │
         ▼
  ✅ 규칙 기반 + LLM 품질 검증
         │
         ▼
  🗺️ 상위 5곳 추천 + 카카오 지도
```

**핵심 원칙 세 가지**

| 원칙 | 내용 |
|------|------|
| **자연어 입력** | 조건을 폼으로 채울 필요 없이 말하듯 입력 |
| **중간지점 자동화** | 여러 출발지를 입력하면 최적 중간지점을 계산해 그 주변을 탐색 |
| **근거 있는 추천** | GPT가 생성한 이유가 실제 장소 데이터에 기반하는지 LLM으로 재검증 |

---

## 트레이드오프 및 설계 결정

### 1. Single Agent vs Multi-Agent

초기 구현은 GPT 하나가 도구를 자율 선택하는 **Single Agent** 방식이었습니다. 유연하지만 예측이 어렵고, 어느 단계에서 실패했는지 디버깅하기 어렵다는 문제가 있었습니다.

**Multi-Agent 파이프라인**으로 전환한 이유:

- 각 에이전트가 하나의 책임만 가지므로 실패 지점을 즉시 파악 가능
- 오케스트레이터가 재시도 범위를 `Search → Recommend → Validate`로 한정해 불필요한 위치 재파싱을 방지
- 에이전트 로그로 각 단계 소요 시간과 결과를 투명하게 추적

**비용**: 파이프라인이 고정되어 단순 요청에도 4단계를 모두 거쳐야 합니다.

---

### 2. 키워드 검색만 쓰지 않고 RAG를 도입한 이유

Kakao Maps API의 키워드 검색은 정확도는 높지만 의미 기반 매칭이 약합니다. "분위기 좋은 고깃집"처럼 추상적인 표현을 처리하지 못하고, 동일 장소가 검색마다 순위가 달라집니다.

**하이브리드 RAG 구조 채택**:

- **FAISS** (의미 검색): 임베딩 유사도로 추상적 요건을 처리
- **BM25** (키워드 검색): 장소명·카테고리 정확 매칭 보완
- 두 결과를 병합해 다양성과 정확도를 동시에 확보

**비용**: 매 요청마다 FAISS 인덱스를 새로 빌드하므로 응답 시간이 늘어납니다. 사전 인덱싱 대신 실시간 빌드를 선택한 이유는 Kakao API 결과가 요청 시점마다 달라지기 때문입니다.

---

### 3. GPT 출력을 장소명이 아닌 인덱스 번호로 받는 이유

초기 프롬프트는 GPT에게 "추천 장소명을 직접 출력하라"고 했습니다. GPT는 실제로 존재하지 않는 장소명을 만들어내거나 (환각), 후보 목록에 없는 장소를 새로 생성하는 문제가 발생했습니다.

**인덱스 번호 방식으로 전환**:

```
[추천 장소 1] 3        ← 후보 목록의 3번 장소를 선택
- 추천 이유: ...
```

후보 목록의 번호만 출력하도록 강제해 GPT가 임의의 장소를 생성하는 것을 원천 차단했습니다.

---

### 4. 중간지점 탐색 반경을 넓게 잡은 이유

중간지점은 특정 행정동이 아니라 참여자들의 이동 거리 합이 최소인 지점입니다. 해당 좌표 주변 2km만 탐색하면 식당 밀도가 낮은 지역(주거지·공원 인근)에서 후보가 극히 부족해지는 문제가 있었습니다.

- 중간지점은 **5km 반경** 탐색으로 자동 확장
- 각 **참여자 출발지**에서도 추가 보조 검색 수행
- 세 검색 결과를 합산 후 중복 제거해 충분한 후보 풀 확보

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| **자연어 입력** | 위치 · 목적 · 인원 · 시간대를 자유롭게 입력 |
| **중간지점 계산** | 여러 출발지 입력 시 자동으로 중간지점 계산 |
| **하이브리드 검색** | Kakao API + FAISS(의미 검색) + BM25(키워드) 결합 |
| **GPT 추천 이유** | 각 장소에 맞춤형 추천 이유 생성 |
| **품질 검증** | 규칙 기반 + LLM 검증으로 부적절한 추천 필터링 |
| **즐겨찾기** | 마음에 드는 장소 저장 및 메모 관리 |
| **약속 관리** | 모임 생성 · 초대 · 참석 여부 관리 |
| **카카오 지도** | 추천 결과를 지도에서 바로 확인 |

---

## 스크린샷

### 메인 화면

<p align="center">
  <img src="docs/images/screenshot_main.png" alt="메인 화면" width="680"/>
</p>

### 단일 위치 추천 결과

한 장소를 기준으로 목적·인원·시간대에 맞는 장소를 추천합니다.

<p align="center">
  <img src="docs/images/screenshot_results_single.png" alt="단일 위치 추천 결과" width="680"/>
</p>

### 중간지점 추천 결과

여러 출발지를 입력하면 중간지점을 계산하고 그 주변 장소를 추천합니다.

<p align="center">
  <img src="docs/images/screenshot_results_midpoint.png" alt="중간지점 추천 결과" width="680"/>
</p>

### 카카오 지도

<p align="center">
  <img src="docs/images/screenshot_map.png" alt="카카오 지도" width="680"/>
</p>

### 즐겨찾기

<p align="center">
  <img src="docs/images/screenshot_favorites.png" alt="즐겨찾기" width="680"/>
</p>

---

## 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                     사용자 브라우저                        │
└──────┬─────────────────┬──────────────────┬─────────────┘
       │                 │                  │
   :8501 (폼)       :8502 (채팅)        :8503 (멀티에이전트 채팅)
       │                 │                  │
┌──────▼──────┐  ┌───────▼──────┐  ┌───────▼───────────────┐
│  기본 프론트  │  │ 단일 에이전트  │  │   멀티 에이전트 프론트  │
│  (Streamlit) │  │  프론트       │  │    (Streamlit)        │
└──────┬───────┘  └───────┬──────┘  └───────┬───────────────┘
       │                  │                  │
  HTTP │             HTTP │             HTTP │
       │                  │                  │
┌──────▼────────┐  ┌──────▼────────┐  ┌─────▼─────────────────┐
│  기본 백엔드   │  │ 단일 에이전트  │  │    멀티 에이전트 백엔드   │
│  :8000        │  │  백엔드 :8001  │  │    :8003               │
│  - RAG 추천   │  │  - Function   │  │    - Location Agent    │
│  - 즐겨찾기   │  │    Calling    │  │    - Search Agent      │
│  - 약속 관리  │  │  - 도구 실행   │  │    - Recommend Agent   │
│  - 인증       │  │  - 검증       │  │    - Validation Agent  │
└──────┬────────┘  └───────────────┘  └────────────────────────┘
       │
   SQLite DB
```

---

## 버전 안내

이 레포지토리는 세 가지 구현을 포함합니다.

### 기본 버전 (`/backend`, `/frontend`)
- 폼 기반 UI로 직접 조건 입력
- RAG 파이프라인으로 장소 검색 및 추천
- SQLite 기반 즐겨찾기·약속 관리

### Single Agent 버전 (`/agent`) — [자세히 보기](agent/README.md)
- 채팅 UI에서 자연어로 대화
- OpenAI Function Calling 기반 ReAct 에이전트
- 에이전트가 도구를 스스로 선택하고 반복 실행

### Multi-Agent 버전 (`/multi_agent`) — [자세히 보기](multi_agent/README.md)
- 4개 전문 에이전트가 순차 파이프라인으로 협업
- 오케스트레이터가 에이전트 실행 관리 및 재시도
- 에이전트 로그로 각 단계 투명하게 추적

---

## 기술 스택

| 분류 | 기술 |
|------|------|
| **프론트엔드** | Streamlit, Kakao Maps JS SDK |
| **백엔드** | FastAPI, Uvicorn |
| **인증** | JWT, bcrypt |
| **데이터베이스** | SQLite |
| **장소 검색** | Kakao Maps API |
| **벡터 검색** | OpenAI Embeddings, FAISS |
| **키워드 검색** | BM25 (rank-bm25) |
| **AI** | OpenAI GPT-4.1, GPT-4.1-mini |
| **컨테이너** | Docker, Docker Compose |

---

## 빠른 시작

### 사전 준비

- Docker & Docker Compose
- OpenAI API 키
- Kakao REST API 키

### 환경 변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열어 아래 항목을 채웁니다.

```env
OPENAI_API_KEY=sk-...
KAKAO_REST_API_KEY=...
SECRET_KEY=your-jwt-secret
```

### 실행

```bash
docker-compose up --build
```

| 서비스 | URL |
|--------|-----|
| 기본 UI | http://localhost:8501 |
| Single Agent 채팅 | http://localhost:8502 |
| Multi-Agent 채팅 | http://localhost:8503 |
| 기본 API 문서 | http://localhost:8000/docs |
| Single Agent API 문서 | http://localhost:8001/docs |
| Multi-Agent API 문서 | http://localhost:8003/docs |

---

## 프로젝트 구조

```
joyner_place/
├── backend/              # 기본 RAG 백엔드 (port 8000)
│   ├── main.py           # FastAPI 앱 & 라우터
│   ├── retrieval.py      # RAG 파이프라인
│   ├── indexing.py       # FAISS/BM25 인덱스 구성
│   ├── auth.py           # JWT 인증
│   ├── database.py       # SQLite 연동
│   ├── favorites.py      # 즐겨찾기 관리
│   └── appointment.py    # 약속 관리
├── frontend/             # 기본 Streamlit UI (port 8501)
├── agent/                # Single Agent 버전
│   ├── backend/          # Function Calling 에이전트 (port 8001)
│   └── frontend/         # 채팅 UI (port 8502)
├── multi_agent/          # Multi-Agent 버전
│   ├── backend/          # 4-에이전트 오케스트레이터 (port 8003)
│   ├── frontend/         # 채팅 UI (port 8503)
│   └── evaluation/       # 평가 파이프라인
├── evaluation/           # 기본 버전 평가
├── data/                 # SQLite DB
└── docker-compose.yml    # 전체 스택 실행
```

---

## 라이선스

MIT License
