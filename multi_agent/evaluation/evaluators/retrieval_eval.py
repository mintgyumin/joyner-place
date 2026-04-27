"""
Retrieval Evaluator — Precision@k, Recall@k

SearchAgent가 반환한 candidates 중 relevant(기대 장소) 항목이
얼마나 포함되어 있는지 측정한다.

- Precision@k : retrieved k개 중 relevant 비율
- Recall@k    : 전체 relevant 중 retrieved k개에 포함된 비율
"""

from __future__ import annotations


def _normalize(name: str) -> str:
    return name.strip().replace(" ", "").lower()


def precision_at_k(retrieved: list[str], relevant: list[str], k: int | None = None) -> float:
    """
    retrieved : SearchAgent candidates (doc 문자열 목록)
    relevant  : 테스트셋의 expected_places (장소명 목록)
    k         : 상위 k개만 평가. None이면 전체.
    """
    if not retrieved:
        return 0.0
    top = retrieved[:k] if k else retrieved
    rel_norm = {_normalize(r) for r in relevant}
    hits = sum(1 for doc in top if any(r in _normalize(doc) for r in rel_norm))
    return hits / len(top)


def recall_at_k(retrieved: list[str], relevant: list[str], k: int | None = None) -> float:
    if not relevant:
        return 1.0
    top = retrieved[:k] if k else retrieved
    rel_norm = {_normalize(r) for r in relevant}
    hits = sum(1 for r in rel_norm if any(r in _normalize(doc) for doc in top))
    return hits / len(rel_norm)


def evaluate(
    retrieved: list[str],
    relevant: list[str],
    k: int = 10,
) -> dict:
    """
    Returns:
        {
            "precision_at_k": float,
            "recall_at_k": float,
            "k": int,
            "retrieved_count": int,
            "relevant_count": int,
            "hits": list[str],   # relevant 중 실제로 retrieved된 장소명
        }
    """
    rel_norm = {_normalize(r) for r in relevant}
    top = retrieved[:k]
    hits = [r for r in relevant if any(_normalize(r) in _normalize(doc) for doc in top)]

    return {
        "precision_at_k": precision_at_k(retrieved, relevant, k),
        "recall_at_k": recall_at_k(retrieved, relevant, k),
        "k": k,
        "retrieved_count": len(retrieved),
        "relevant_count": len(relevant),
        "hits": hits,
    }
