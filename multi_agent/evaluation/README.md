# Multi-Agent RAG Evaluation Pipeline

JOYNER Place Multi-Agent 시스템의 추천 품질을 4가지 관점에서 자동 평가한다.

---

## 구조

```
evaluation/
├── evaluators/
│   ├── retrieval_eval.py    # Precision@k, Recall@k
│   ├── faithfulness_eval.py # LLM 기반 사실 충실도
│   ├── coverage_eval.py     # 요건 충족도 (위치·카테고리·인원·시간)
│   └── rule_eval.py         # 규칙 기반 형식 검사
├── run_evaluation.py        # 통합 실행 스크립트
├── testset.json             # 테스트 케이스 (7개 기본 제공)
└── results/                 # 평가 결과 저장 (자동 생성)
```

---

## 평가 항목

### 1. Retrieval (retrieval_eval.py)
| 지표 | 설명 |
|------|------|
| Precision@k | 검색된 상위 k개 중 기대 장소 비율 |
| Recall@k | 기대 장소 중 상위 k개에 포함된 비율 |

> `testset.json`의 `expected_places`에 장소명을 지정했을 때만 측정.

### 2. Faithfulness (faithfulness_eval.py)
추천 이유가 장소 정보와 모순 없이 사실에 근거했는지 GPT로 검증.
- 0.0 ~ 1.0 점수 (높을수록 충실)
- 장소별 세부 이슈 목록 제공

### 3. Requirement Coverage (coverage_eval.py)
| 항목 | 설명 |
|------|------|
| location_proximity | 추천 장소가 요청 반경 내에 있는지 |
| category_match | 요청 카테고리/목적과 장소 카테고리 일치 여부 |
| people_capacity | 이유에 인원수 관련 표현 포함 여부 |
| time_relevance | 이유에 시간대 관련 표현 포함 여부 |

### 4. Rule-based (rule_eval.py)
| 항목 |
|------|
| 추천 수 1~10개 범위 |
| 중복 장소 없음 |
| 필수 필드 (place_name, address, place_url, reason, category) 존재 |
| 추천 이유 2문장 이상 |
| 좌표(lat/lng) 존재 |
| 반경 내 거리 (선택적) |

---

## 사용법

### 설치
```bash
cd multi_agent/evaluation
pip install requests python-dotenv openai
```

### 환경 변수 (.env)
```
OPENAI_API_KEY=sk-...
BACKEND_URL=http://localhost:8003   # 선택 (기본값)
EVAL_TOKEN=eyJhbGci...              # 선택 (--token 으로도 전달 가능)
```

### 실행

PowerShell에서는 토큰을 먼저 변수에 저장한 뒤 사용한다:

```powershell
# 1. 토큰 발급
$resp = Invoke-RestMethod -Method POST -Uri "http://localhost:8003/token" `
    -ContentType "application/x-www-form-urlencoded" `
    -Body "username=admin&password=yourpassword"
$token = $resp.access_token

# 2. 전체 테스트 케이스 실행
python run_evaluation.py --mode api --url http://localhost:8003 --token $token

# 3. 특정 케이스만
python run_evaluation.py --mode api --filter TC001,TC003 --token $token

# 4. 미리 저장된 API 결과로 실행 (백엔드 불필요)
python run_evaluation.py --mode file --results ./results/my_result.json

# 5. 출력 파일명 접두어 지정
python run_evaluation.py --mode api --output sprint1 --token $token
```

bash/zsh 환경:

```bash
TOKEN=$(curl -s -X POST http://localhost:8003/token \
    -d "username=admin&password=yourpassword" | jq -r .access_token)
python run_evaluation.py --mode api --token "$TOKEN"
```

`.env`에 `EVAL_TOKEN`을 설정하면 `--token` 생략 가능:

```
EVAL_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### 결과 파일
```
results/
├── 20240427_153000_results.json   # 상세 JSON
└── 20240427_153000_report.md      # Markdown 요약 리포트
```

---

## 테스트셋 확장

`testset.json`에 케이스를 추가한다:

```json
{
  "id": "TC008",
  "description": "케이스 설명",
  "input": {
    "message": "사용자 메시지",
    "session_id": "eval_tc008"
  },
  "expected": {
    "location_name": "장소명",
    "purpose": "회식",
    "time_slot": "저녁",
    "people_count": 4,
    "category": "",
    "expected_places": ["특정 기대 장소명"],
    "forbidden_categories": ["분식", "카페"],
    "allowed_categories": ["음식점", "한식"],
    "min_recommendations": 3
  }
}
```

`expected_places`는 Retrieval 평가에 사용. 비워두면 Precision/Recall은 N/A로 표시.

---

## 개별 평가 모듈 직접 사용

```python
from evaluators import rule_eval, coverage_eval, faithfulness_eval, retrieval_eval

# Rule-based
result = rule_eval.evaluate(recommendations)

# Coverage
result = coverage_eval.evaluate(
    recommendations, purpose="회식", time_slot="저녁",
    people_count=5, category="고깃집"
)

# Faithfulness (OpenAI API 필요)
result = faithfulness_eval.evaluate(recommendations, retrieved_docs)

# Retrieval
result = retrieval_eval.evaluate(retrieved_docs, expected_places, k=10)
```
