# JOYNER Place — RAG 평가 파이프라인

JOYNER Place의 장소 추천 품질을 자동으로 측정하는 평가 도구입니다.

---

## 평가 지표 설명

| 지표 | 설명 | 범위 |
|------|------|------|
| **Precision@K** | 추천된 장소 중 실제로 관련 있는 카테고리 비율 | 0~1 |
| **Faithfulness** | GPT 추천 이유가 실제 장소 데이터에 근거하는지 (Hallucination 탐지) | 0~1 |
| **Req. Coverage** | 사용자 요구사항(목적·시간대·인원)이 추천 결과에 얼마나 반영됐는지 | 0~1 |
| **Rule-based** | 결과 개수·중복·주소·URL·추천이유 등 기본 품질 체크 | pass/fail |

> 점수가 1에 가까울수록 좋습니다.

---

## 폴더 구조

```
evaluation/
├── evaluator.py        ← 4가지 평가 함수 구현
├── run_evaluation.py   ← 통합 실행 스크립트
├── testset.json        ← 테스트 케이스 모음
└── README.md           ← 이 파일
```

---

## 설치 방법

```bash
# evaluation 폴더에서 실행
cd joyner_place/evaluation

# 필요 패키지 설치
pip install requests openai python-dotenv
```

---

## 환경변수 설정

프로젝트 루트의 `.env` 파일에 다음 항목이 있어야 합니다:

```env
OPENAI_API_KEY=sk-...          # GPT 평가에 사용
BACKEND_URL=http://localhost:8000  # 백엔드 주소 (docker: http://backend:8000)

# 평가용 계정 (백엔드에 미리 가입된 계정이어야 함)
EVAL_USERNAME=eval_user
EVAL_PASSWORD=eval_pass
```

> **주의**: `EVAL_USERNAME` / `EVAL_PASSWORD`는 백엔드에 실제로 가입된 계정이어야 합니다.
> 아직 계정이 없다면 앱에서 회원가입하거나 API를 직접 호출해서 만드세요.

---

## 실행 방법

백엔드 서버가 실행 중인 상태에서 아래 명령을 실행합니다.

```bash
# 기본 실행 (testset.json 사용, 백엔드: .env의 BACKEND_URL)
python run_evaluation.py

# 옵션 지정
python run_evaluation.py --testset testset.json --backend http://localhost:8000

# 리포트를 다른 폴더에 저장
python run_evaluation.py --output-dir ./reports
```

---

## 출력 파일

실행 후 두 개의 리포트 파일이 생성됩니다.

| 파일 | 설명 |
|------|------|
| `evaluation_report.json` | 모든 수치가 담긴 상세 결과 (프로그래밍으로 분석 가능) |
| `evaluation_report.md`   | 사람이 읽기 좋은 Markdown 리포트 |

---

## testset.json 작성 방법

새 테스트 케이스를 추가하려면 `test_cases` 배열에 항목을 추가합니다.

### 단일 위치 케이스

```json
{
  "id": "test_006",
  "input": {
    "location": "신촌",
    "purpose": "노래방",
    "time_slot": "심야 (21:00~)",
    "people_count": 5
  },
  "expected": {
    "min_results": 1,
    "max_results": 5,
    "relevant_categories": ["노래방", "코인노래방"],
    "requirements": ["5인 수용", "심야 운영"]
  }
}
```

### 다중 참여자 (중간지점 자동 계산) 케이스

```json
{
  "id": "test_007",
  "input": {
    "locations": ["잠실역", "건대입구"],
    "location": "",
    "purpose": "카페",
    "time_slot": "오후 (14:00~17:00)",
    "people_count": 2
  },
  "expected": {
    "min_results": 1,
    "max_results": 5,
    "relevant_categories": ["카페"],
    "requirements": ["2인 모임", "오후 운영"]
  }
}
```

### 필드 설명

| 필드 | 설명 |
|------|------|
| `id` | 케이스 고유 ID (중복 금지) |
| `input.location` | 단일 위치 (다중 모드에서는 `""`) |
| `input.locations` | 다중 위치 리스트 (단일 모드에서는 생략) |
| `input.purpose` | 모임 목적 (자유 텍스트) |
| `input.time_slot` | 시간대 (앱의 선택지와 동일하게 작성) |
| `input.people_count` | 인원수 |
| `expected.min_results` | 최소 추천 개수 (보통 1) |
| `expected.max_results` | 최대 추천 개수 (보통 5) |
| `expected.relevant_categories` | 관련 카테고리 (Precision@K 계산에 사용) |
| `expected.requirements` | 요구사항 목록 (Req. Coverage 계산에 사용) |

---

## 결과 해석 방법

```
Precision@K       : 0.8   → 추천 5개 중 4개가 관련 카테고리 (좋음)
Faithfulness      : 0.9   → 추천 이유가 실제 데이터에 잘 근거함 (좋음)
Req. Coverage     : 0.7   → 요구사항 70% 반영 (보통)
Rule Pass Rate    : 1.0   → 모든 케이스가 기본 품질 규칙 통과 (완벽)
```

### 점수 기준 (권장)

| 점수 | 의미 |
|------|------|
| 0.8 이상 | 우수 |
| 0.6~0.8 | 양호 |
| 0.4~0.6 | 개선 필요 |
| 0.4 미만 | 심각한 문제 |
