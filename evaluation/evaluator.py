"""
RAG 평가 모듈 - JOYNER Place

RAG(Retrieval-Augmented Generation) 시스템의 성능을 4가지 기준으로 측정한다.

[평가 지표]
1. Precision@K     : 검색 정확도 — 추천된 장소 중 관련 있는 비율
2. Faithfulness    : 충실도 — GPT 추천 이유가 실제 장소 데이터에 근거하는지
3. Req. Coverage   : 요구사항 반영도 — 사용자 조건이 추천에 얼마나 반영됐는지
4. Rule-based      : 규칙 준수 — 추천 결과가 기본 품질 기준을 만족하는지
"""

import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ─────────────────────────────────────────
# 목적별 관련 카테고리 매핑 테이블
# ─────────────────────────────────────────

PURPOSE_CATEGORY_MAP = {
    "팀 회식":    ["음식점", "레스토랑", "한식", "일식", "양식", "중식", "분식", "고깃집", "술집"],
    "회식":       ["음식점", "레스토랑", "한식", "일식", "양식", "중식", "분식", "고깃집", "술집"],
    "스터디":     ["카페", "스터디카페", "북카페", "도서관"],
    "데이트":     ["카페", "음식점", "레스토랑", "문화시설", "영화관", "전시", "공원", "바"],
    "친구 모임":  ["카페", "음식점", "레스토랑", "브런치", "술집"],
    "친구모임":   ["카페", "음식점", "레스토랑", "브런치", "술집"],
    "볼링":       ["볼링장", "스포츠"],
    "노래방":     ["노래방", "코인노래방"],
    "카페":       ["카페", "브런치", "북카페", "디저트"],
}

# 장소 데이터에 원래 없는, GPT가 hallucinate하기 쉬운 키워드
HALLUCINATION_KEYWORDS = [
    "주차", "와이파이", "wifi", "콘센트", "충전",
    "반려동물", "펫", "애완", "금연", "흡연",
    "예약 필수", "단체석", "룸", "프라이빗",
    "조식", "뷔페", "무한리필",
]

# 인원 관련 언급 키워드
PEOPLE_KEYWORDS = ["명", "인", "팀", "그룹", "단체", "소규모", "대규모", "수용"]

# 시간 관련 언급 키워드
TIME_KEYWORDS = [
    "오전", "오후", "저녁", "점심", "심야", "새벽", "낮",
    "운영", "영업", "오픈", "시간", "시까지", "시부터",
    "11:00", "12:00", "13:00", "14:00", "17:00", "18:00", "21:00", "22:00",
]


# ─────────────────────────────────────────
# 1. Precision@K — Retrieval 정확도
# ─────────────────────────────────────────

def precision_at_k(
    retrieved: list[str],
    relevant: list[str],
    k: int,
    purpose: str = "",
) -> float:
    """
    상위 K개 추천 결과 중 실제로 관련 있는 항목의 비율을 반환한다.

    목적(purpose)이 주어지면 PURPOSE_CATEGORY_MAP에서 엄격한 관련 카테고리 목록을
    가져와 매칭한다. 목적이 없거나 맵에 없으면 relevant 파라미터를 그대로 사용한다.

    Args:
        retrieved : 추천된 장소 카테고리 리스트
        relevant  : 관련 있는 카테고리 리스트 (목적 맵이 없을 때 사용)
        k         : 상위 몇 개를 평가할지
        purpose   : 모임 목적 (예: "팀 회식", "스터디")

    Returns:
        0~1 사이의 점수
    """
    if not retrieved or k == 0:
        return 0.0

    # 목적에 맞는 엄격한 카테고리 목록 결정
    effective_relevant = relevant
    for key, cats in PURPOSE_CATEGORY_MAP.items():
        if key in purpose:
            effective_relevant = cats
            break

    top_k = retrieved[:k]
    relevant_set = {r.lower() for r in effective_relevant}

    hit_count = 0
    for cat in top_k:
        cat_lower = cat.lower()
        for rel in relevant_set:
            if rel in cat_lower or cat_lower in rel:
                hit_count += 1
                break

    return hit_count / len(top_k)


# ─────────────────────────────────────────
# 2. Faithfulness — 추천 이유의 근거 충실도
# ─────────────────────────────────────────

def faithfulness_score(answer: str, contexts: list[str]) -> float:
    """
    GPT 추천 이유가 실제 장소 데이터에 근거하는지 GPT로 판단한 뒤,
    장소 원본 데이터에 없는 키워드(주차, 와이파이 등)가 추천 이유에 포함되면
    키워드당 0.1씩 추가 감점한다.

    Args:
        answer   : GPT가 생성한 추천 이유 텍스트
        contexts : 검색된 장소 정보 텍스트 리스트

    Returns:
        0~1 사이의 점수 (1에 가까울수록 hallucination 없음)
    """
    if not answer or not contexts:
        return 0.0

    context_text = "\n".join(f"- {c}" for c in contexts)

    prompt = f"""아래 [장소 정보]와 [추천 이유]를 비교해서 평가해주세요.

[장소 정보]
{context_text}

[추천 이유]
{answer}

평가 기준:
- 추천 이유가 장소 정보에 실제로 있는 내용을 근거로 하면 점수가 높습니다.
- 장소 정보에 없는 내용을 임의로 만들어냈으면 점수가 낮습니다.

0.0(전혀 근거 없음) ~ 1.0(완전히 근거 있음) 사이의 숫자 하나만 출력하세요.
예: 0.8"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=10,
    )

    raw = response.choices[0].message.content.strip()
    try:
        gpt_score = float(raw)
        gpt_score = max(0.0, min(1.0, gpt_score))
    except ValueError:
        gpt_score = 0.0

    # 장소 데이터에 없는 hallucination 키워드 감점
    answer_lower = answer.lower()
    context_lower = context_text.lower()
    penalty = 0.0
    for kw in HALLUCINATION_KEYWORDS:
        if kw in answer_lower and kw not in context_lower:
            penalty += 0.1

    return max(0.0, gpt_score - penalty)


# ─────────────────────────────────────────
# 3. Requirement Coverage — 요구사항 반영도
# ─────────────────────────────────────────

def requirement_coverage(
    answer: str,
    requirements: list[str],
    people_count: int = 0,
    time_slot: str = "",
) -> float:
    """
    GPT 판단 점수와 키워드 체크 점수의 평균으로 요구사항 반영도를 측정한다.

    - GPT 판단: 각 요구사항이 추천 이유에 언급됐는지 GPT가 0~1 점수 반환
    - 키워드 체크:
        * people_count > 0 이면 추천 이유에 인원 관련 키워드 있는지 확인
        * time_slot 이 주어지면 추천 이유에 시간 관련 키워드 있는지 확인
      두 항목의 평균을 키워드 점수로 사용 (해당 항목 없으면 제외)

    Args:
        answer       : GPT가 생성한 추천 이유 텍스트
        requirements : 사용자 요구사항 리스트
        people_count : 인원수 (0이면 체크 안 함)
        time_slot    : 시간대 문자열 (빈 문자열이면 체크 안 함)

    Returns:
        0~1 사이의 점수
    """
    if not answer or not requirements:
        return 0.0

    # ── GPT 판단 점수 ─────────────────────────────────────────────
    reqs_text = "\n".join(f"- {r}" for r in requirements)

    prompt = f"""아래 [사용자 요구사항]이 [추천 이유]에 얼마나 반영됐는지 평가해주세요.

[사용자 요구사항]
{reqs_text}

[추천 이유]
{answer}

평가 기준:
- 각 요구사항이 추천 이유에 직접적으로 또는 간접적으로 언급되면 반영된 것으로 봅니다.
- 요구사항이 전혀 언급되지 않으면 점수가 낮습니다.

0.0(전혀 반영 안됨) ~ 1.0(모두 반영됨) 사이의 숫자 하나만 출력하세요.
예: 0.7"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=10,
    )

    raw = response.choices[0].message.content.strip()
    try:
        gpt_score = float(raw)
        gpt_score = max(0.0, min(1.0, gpt_score))
    except ValueError:
        gpt_score = 0.0

    # ── 키워드 체크 점수 ──────────────────────────────────────────
    answer_lower = answer.lower()
    keyword_scores = []

    if people_count > 0:
        people_hit = any(kw in answer_lower for kw in PEOPLE_KEYWORDS)
        # 구체적인 숫자(인원수)가 언급되면 추가 인정
        if str(people_count) in answer:
            people_hit = True
        keyword_scores.append(1.0 if people_hit else 0.0)

    if time_slot:
        time_hit = any(kw in answer_lower for kw in TIME_KEYWORDS)
        # time_slot 문자열 자체가 포함되면 추가 인정
        if time_slot in answer:
            time_hit = True
        keyword_scores.append(1.0 if time_hit else 0.0)

    keyword_score = sum(keyword_scores) / len(keyword_scores) if keyword_scores else gpt_score

    return round((gpt_score + keyword_score) / 2, 3)


# ─────────────────────────────────────────
# 4. Rule-based Evaluation — 규칙 기반 검사
# ─────────────────────────────────────────

def rule_based_evaluation(results: list[dict], expected: dict) -> dict:
    """
    추천 결과가 기본 품질 규칙을 만족하는지 체크리스트로 확인한다.

    Args:
        results  : 추천 장소 리스트 (place_name, address, place_url 등 포함)
        expected : testset.json의 expected 항목 (min_results, max_results 등)

    Returns:
        각 규칙의 pass/fail 딕셔너리
    """
    checks = {}

    n = len(results)
    min_r = expected.get("min_results", 1)
    max_r = expected.get("max_results", 5)
    checks["result_count_ok"] = min_r <= n <= max_r

    place_names = [r.get("place_name", "") for r in results]
    checks["no_duplicate"] = len(place_names) == len(set(place_names))

    checks["all_have_address"] = all(
        bool(r.get("address", "").strip()) for r in results
    )

    checks["all_have_url"] = all(
        bool(r.get("place_url", "").strip()) for r in results
    )

    checks["all_have_reason"] = all(
        bool(r.get("reason", "").strip()) for r in results
    )

    checks["overall_pass"] = all(checks.values())

    return checks
