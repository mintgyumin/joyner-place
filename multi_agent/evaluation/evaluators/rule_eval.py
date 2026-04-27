"""
Rule-based Evaluator — 규칙 기반 품질 검사

추천 결과의 형식·구조적 요건을 검사한다.
ValidationAgent의 코드 검사를 독립적으로 재현하되,
평가용 추가 규칙을 포함한다.
"""

from __future__ import annotations
import re


def evaluate(
    recommendations: list[dict],
    min_count: int = 3,
    max_count: int = 10,
    min_reason_sentences: int = 2,
    required_fields: list[str] | None = None,
    max_distance_m: int | None = None,
) -> dict:
    """
    recommendations : RecommendAgent 결과 목록

    Returns:
        {
            "passed": bool,
            "score": float,          # 통과 규칙 수 / 전체 규칙 수
            "checks": dict,          # 규칙별 결과
            "issues": list[str],
        }
    """
    if required_fields is None:
        required_fields = ["place_name", "address", "place_url", "reason", "category"]

    checks: dict[str, bool] = {}
    issues: list[str] = []
    n = len(recommendations)

    # 1. 개수
    checks["result_count_ok"] = min_count <= n <= max_count
    if not checks["result_count_ok"]:
        issues.append(f"추천 개수 {n}개 (기대: {min_count}~{max_count}개)")

    # 2. 중복 없음
    names = [r.get("place_name", "") for r in recommendations]
    checks["no_duplicate"] = len(names) == len(set(names))
    if not checks["no_duplicate"]:
        from collections import Counter
        dupes = [k for k, v in Counter(names).items() if v > 1]
        issues.append(f"중복 장소: {dupes}")

    # 3. 필수 필드
    for field in required_fields:
        key = f"all_have_{field}"
        checks[key] = all(bool(str(r.get(field, "")).strip()) for r in recommendations)
        if not checks[key]:
            missing = [r.get("place_name", "?") for r in recommendations if not r.get(field)]
            issues.append(f"{field} 없는 장소: {missing}")

    # 4. 이유 문장 수
    def sentence_count(text: str) -> int:
        return len([s for s in re.split(r'[.!?。\n]', text) if s.strip()])

    reason_ok = all(
        sentence_count(r.get("reason", "")) >= min_reason_sentences
        for r in recommendations
    )
    checks["reason_length_ok"] = reason_ok
    if not reason_ok:
        short = [r.get("place_name") for r in recommendations
                 if sentence_count(r.get("reason", "")) < min_reason_sentences]
        issues.append(f"이유 {min_reason_sentences}문장 미만: {short}")

    # 5. 좌표 존재
    checks["all_have_coords"] = all(
        r.get("lat") is not None and r.get("lng") is not None
        for r in recommendations
    )
    if not checks["all_have_coords"]:
        no_coord = [r.get("place_name") for r in recommendations
                    if r.get("lat") is None or r.get("lng") is None]
        issues.append(f"좌표 없는 장소: {no_coord}")

    # 6. 거리 범위 (선택적)
    if max_distance_m is not None:
        within = []
        for r in recommendations:
            try:
                d = int(str(r.get("distance", "0")).replace("m", "").strip())
                within.append(d <= max_distance_m)
            except (ValueError, TypeError):
                within.append(True)
        checks["distance_within_range"] = all(within)
        if not checks["distance_within_range"]:
            issues.append(f"반경 {max_distance_m}m 초과 장소 포함")

    passed = all(checks.values())
    score = round(sum(checks.values()) / len(checks), 3) if checks else 0.0

    return {
        "passed": passed,
        "score": score,
        "checks": checks,
        "issues": issues,
    }
