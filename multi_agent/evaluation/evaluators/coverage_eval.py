"""
Requirement Coverage Evaluator — 사용자 요건 충족도 평가

추천 결과가 사용자의 핵심 요건을 얼마나 커버하는지 측정한다.

체크 항목:
1. location_proximity  : 추천 장소들이 요청 반경 내에 있는가 (distance 필드)
2. category_match      : 요청 카테고리(또는 목적)에 맞는 장소인가
3. people_capacity     : 인원수에 적합한 장소 유형인가 (이유에 단체석/인원 언급)
4. time_relevance      : 시간대가 이유에 반영되었는가
"""

from __future__ import annotations
import re


_LARGE_GROUP_KEYWORDS = ["단체", "대형홀", "넓은", "룸", "좌석 많", "대관", "대형"]
_SMALL_GROUP_KEYWORDS = ["아늑", "분위기", "조용", "커플", "둘이", "소규모"]

_TIME_KEYWORDS = {
    "점심": ["점심", "런치", "낮", "오전"],
    "낮": ["낮", "점심", "런치", "오전", "오후"],
    "저녁": ["저녁", "디너", "밤", "야간"],
    "브런치": ["브런치", "아침", "오전"],
    "야식": ["야식", "밤", "심야", "24시"],
}

_CATEGORY_SYNONYMS: dict[str, list[str]] = {
    "이자카야": ["이자카야", "일본식주점", "술집", "바"],
    "고깃집": ["고기요리", "구이", "삼겹살", "갈비", "고기", "육류"],
    "삼겹살": ["삼겹살", "고기요리", "구이", "고기", "육류"],
    "갈비": ["갈비", "고기요리", "구이", "고기", "육류"],
    "술자리": ["술집", "호프", "바", "포차", "이자카야", "일본식주점"],
    "식사": ["음식점", "한식", "일식", "중식", "양식", "국밥", "탕", "찜", "구이", "고기요리"],
    "회식": ["음식점", "한식", "일식", "중식", "양식", "국밥", "탕", "고기요리", "뷔페"],
    "데이트": ["음식점", "카페", "레스토랑", "이탈리안", "한식", "일식"],
    "카페": ["카페", "테마카페", "스터디카페", "북카페", "디저트", "브런치카페", "사주카페"],
    "스터디": ["카페", "스터디카페", "테마카페", "북카페"],
}


def _check_location_proximity(recommendations: list[dict], max_distance_m: int = 3000) -> dict:
    total = len(recommendations)
    if total == 0:
        return {"pass_rate": 0.0, "within_range": 0, "total": 0}

    within = 0
    for rec in recommendations:
        dist_raw = rec.get("distance", "")
        try:
            dist = int(str(dist_raw).replace("m", "").strip())
            if dist <= max_distance_m:
                within += 1
        except (ValueError, TypeError):
            within += 1  # 거리 정보 없으면 통과로 처리

    return {
        "pass_rate": round(within / total, 3),
        "within_range": within,
        "total": total,
        "max_distance_m": max_distance_m,
    }


def _check_category_match(recommendations: list[dict], purpose: str, category: str = "") -> dict:
    total = len(recommendations)
    if total == 0:
        return {"pass_rate": 0.0, "matched": 0, "total": 0}

    key = (category.strip() if category else purpose.strip()).lower()
    # 동의어 목록 구성: 직접 입력값 + 매핑된 동의어
    synonyms = {key}
    for k, vals in _CATEGORY_SYNONYMS.items():
        if k.lower() == key:
            synonyms.update(v.lower() for v in vals)
    # purpose/category 자체도 동의어로 체크
    synonyms.update(v.lower() for v in _CATEGORY_SYNONYMS.get(purpose.strip(), []))

    matched = 0
    details = []
    for rec in recommendations:
        rec_cat = rec.get("category", "").lower()
        reason = rec.get("reason", "").lower()
        is_match = (
            any(s in rec_cat or rec_cat in s for s in synonyms)
            or any(s in reason for s in synonyms)
        )
        if is_match:
            matched += 1
        details.append({"place": rec.get("place_name"), "category": rec.get("category"), "match": is_match})

    return {
        "pass_rate": round(matched / total, 3),
        "matched": matched,
        "total": total,
        "target": key,
        "details": details,
    }


def _check_people_capacity(recommendations: list[dict], people_count: int) -> dict:
    total = len(recommendations)
    if total == 0:
        return {"pass_rate": 0.0, "mentioned": 0, "total": 0}

    mentioned = 0
    for rec in recommendations:
        reason = rec.get("reason", "")
        if people_count >= 8:
            if any(kw in reason for kw in _LARGE_GROUP_KEYWORDS) or str(people_count) in reason:
                mentioned += 1
        elif people_count <= 2:
            if any(kw in reason for kw in _SMALL_GROUP_KEYWORDS) or str(people_count) in reason:
                mentioned += 1
        else:
            # 3~7명: 인원수 언급 or 단체석 언급
            if str(people_count) in reason or any(kw in reason for kw in _LARGE_GROUP_KEYWORDS + ["인원", "명"]):
                mentioned += 1

    return {
        "pass_rate": round(mentioned / total, 3),
        "mentioned": mentioned,
        "total": total,
        "people_count": people_count,
    }


def _check_time_relevance(recommendations: list[dict], time_slot: str) -> dict:
    total = len(recommendations)
    if total == 0:
        return {"pass_rate": 0.0, "mentioned": 0, "total": 0}

    keywords = []
    for key, kws in _TIME_KEYWORDS.items():
        if key in time_slot:
            keywords.extend(kws)
    if not keywords:
        keywords = [time_slot]

    mentioned = 0
    for rec in recommendations:
        reason = rec.get("reason", "")
        if any(kw in reason for kw in keywords):
            mentioned += 1

    return {
        "pass_rate": round(mentioned / total, 3),
        "mentioned": mentioned,
        "total": total,
        "time_slot": time_slot,
    }


def evaluate(
    recommendations: list[dict],
    purpose: str,
    time_slot: str,
    people_count: int,
    category: str = "",
    max_distance_m: int = 3000,
) -> dict:
    """
    Returns:
        {
            "overall_coverage": float,   # 4개 항목의 평균
            "location_proximity": dict,
            "category_match": dict,
            "people_capacity": dict,
            "time_relevance": dict,
        }
    """
    loc = _check_location_proximity(recommendations, max_distance_m)
    cat = _check_category_match(recommendations, purpose, category)
    ppl = _check_people_capacity(recommendations, people_count)
    tim = _check_time_relevance(recommendations, time_slot)

    overall = round(
        (loc["pass_rate"] + cat["pass_rate"] + ppl["pass_rate"] + tim["pass_rate"]) / 4, 3
    )

    return {
        "overall_coverage": overall,
        "location_proximity": loc,
        "category_match": cat,
        "people_capacity": ppl,
        "time_relevance": tim,
    }
