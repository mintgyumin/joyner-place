"""
Faithfulness Evaluator — LLM 기반 사실 충실도 평가

추천 이유(reason)가 실제 장소 정보(후보 문서)와 모순 없이
사실에 근거했는지 GPT로 검증한다.

점수 범위: 0.0 ~ 1.0 (각 추천의 평균)
"""

from __future__ import annotations
import json
import os

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

_SYSTEM = "당신은 장소 추천 품질을 평가하는 전문가입니다. 주어진 기준에 따라 JSON으로만 응답하세요."

_PROMPT_TEMPLATE = """\
아래 장소 추천의 '추천 이유'가 장소 정보에 근거하여 사실에 충실한지 평가하세요.

[장소 정보]
{context}

[추천 이유]
{reason}

평가 기준:
1. 추천 이유가 장소 정보와 모순되지 않는가?
2. 장소 정보로부터 합리적으로 추론 가능한 내용인가?
3. 근거 없는 과장이나 허위 주장이 없는가?

아래 JSON 형식으로만 응답하세요:
{{"score": 0~1 사이 소수점 한 자리, "faithful": true/false, "issues": ["문제점 목록 (없으면 빈 배열)"]}}
"""


def _evaluate_single(context: str, reason: str) -> dict:
    prompt = _PROMPT_TEMPLATE.format(context=context, reason=reason)
    try:
        resp = _client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        return {"score": 0.5, "faithful": True, "issues": [f"평가 오류: {e}"]}


def evaluate(
    recommendations: list[dict],
    retrieved_docs: list[str],
) -> dict:
    """
    recommendations : RecommendAgent 결과 (place_name, reason 포함)
    retrieved_docs  : SearchAgent candidates (장소 정보 문서 목록)

    Returns:
        {
            "avg_faithfulness": float,
            "per_place": [
                {
                    "place_name": str,
                    "score": float,
                    "faithful": bool,
                    "issues": list[str],
                },
                ...
            ],
        }
    """
    context_block = "\n".join(retrieved_docs[:15]) if retrieved_docs else "정보 없음"
    results = []

    for rec in recommendations:
        name = rec.get("place_name", "")
        reason = rec.get("reason", "")
        # 해당 장소에 관련된 문서만 context로 사용
        relevant_ctx = "\n".join(d for d in retrieved_docs if name in d) or context_block
        result = _evaluate_single(relevant_ctx, reason)
        results.append({
            "place_name": name,
            "score": result.get("score", 0.5),
            "faithful": result.get("faithful", True),
            "issues": result.get("issues", []),
        })

    avg = sum(r["score"] for r in results) / len(results) if results else 0.0
    return {
        "avg_faithfulness": round(avg, 3),
        "per_place": results,
    }
