"""
Validation Agent — 추천 결과를 코드 검사 + LLM 검사 두 단계로 검증한다.
"""

import json
import os
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import client as openai_client

load_dotenv()

_PROMPT = (Path(__file__).parent.parent / "prompts" / "validation_agent_prompt.txt").read_text(encoding="utf-8")

_VALIDATE_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "validate_quality",
            "description": "추천 결과의 목적 적합성과 이유 구체성을 검증합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "purpose_match": {
                        "type": "boolean",
                        "description": "모든 장소가 목적에 맞는 카테고리인지 여부",
                    },
                    "reason_specific": {
                        "type": "boolean",
                        "description": "추천 이유에 인원수·시간대·목적이 구체적으로 반영되었는지",
                    },
                    "reason_length_ok": {
                        "type": "boolean",
                        "description": "각 이유가 2문장 이상인지",
                    },
                    "issues": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "발견된 문제 목록 (없으면 빈 배열)",
                    },
                },
                "required": ["purpose_match", "reason_specific", "reason_length_ok", "issues"],
            },
        },
    }
]


def _code_checks(results: list[dict]) -> tuple[dict, list[str]]:
    """규칙 기반 코드 검사."""
    checks = {}
    issues = []

    n = len(results)
    checks["result_count_ok"] = 1 <= n <= 10
    if not checks["result_count_ok"]:
        issues.append(f"추천 개수 이상: {n}개 (1~10개여야 함)")

    names = [r.get("place_name", "") for r in results]
    checks["no_duplicate"] = len(names) == len(set(names))
    if not checks["no_duplicate"]:
        issues.append("중복 장소 포함")

    checks["all_have_address"] = all(bool(r.get("address", "").strip()) for r in results)
    if not checks["all_have_address"]:
        issues.append("주소 없는 장소 포함")

    checks["all_have_url"] = all(bool(r.get("place_url", "").strip()) for r in results)
    if not checks["all_have_url"]:
        issues.append("카카오맵 URL 없는 장소 포함")

    checks["all_have_reason"] = all(bool(r.get("reason", "").strip()) for r in results)
    if not checks["all_have_reason"]:
        issues.append("추천 이유 없는 장소 포함")

    return checks, issues


def _llm_checks(results: list[dict], purpose: str, time_slot: str, people_count: int, category: str = "") -> tuple[dict, list[str]]:
    """LLM 기반 품질 검사."""
    places_text = "\n".join(
        f"{i+1}. {r.get('place_name','')} | 카테고리: {r.get('category','')} | 이유: {r.get('reason','')[:100]}..."
        for i, r in enumerate(results)
    )
    category_note = f"\n요청 카테고리: {category} (이에 맞지 않는 장소가 있으면 issues에 추가하고 purpose_match=false로 표시)" if category else ""
    prompt = f"""{_PROMPT}

[검증 대상]
모임 목적: {purpose}{category_note}
시간대: {time_slot}
인원수: {people_count}명

[추천 결과]
{places_text}
"""
    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            tools=_VALIDATE_SCHEMA,
            tool_choice={"type": "function", "function": {"name": "validate_quality"}},
            temperature=0.0,
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return {}, []
        args = json.loads(msg.tool_calls[0].function.arguments)
        llm_checks = {
            "purpose_match": args.get("purpose_match", True),
            "reason_specific": args.get("reason_specific", True),
            "reason_length_ok": args.get("reason_length_ok", True),
        }
        llm_issues = args.get("issues", [])
        return llm_checks, llm_issues
    except Exception as e:
        print(f"[ValidationAgent] LLM 검증 오류: {e}")
        return {}, []


def run(recommendations: list[dict], purpose: str, time_slot: str, people_count: int, category: str = "") -> dict:
    """
    추천 결과를 코드 검사 + LLM 검사로 검증한다.

    Returns:
        {
            "passed": bool,
            "issues": list[str],
            "checks": dict,   # 각 규칙별 pass/fail
        }
    """
    print(f"[ValidationAgent] {len(recommendations)}개 결과 검증 중")

    code_checks, code_issues = _code_checks(recommendations)
    llm_chk, llm_issues = _llm_checks(recommendations, purpose, time_slot, people_count, category)

    all_checks = {**code_checks, **llm_chk}
    all_issues = code_issues + llm_issues

    # 최소 3개 체크
    too_few = len(recommendations) < 3
    if too_few:
        all_issues.append(f"추천 장소가 {len(recommendations)}개로 부족합니다 (최소 3개 필요)")

    passed = all(v for v in code_checks.values()) and all(v for v in llm_chk.values()) and not too_few

    print(f"[ValidationAgent] 결과: {'통과' if passed else '실패'}, 문제: {all_issues}")
    return {
        "passed": passed,
        "issues": all_issues,
        "checks": all_checks,
    }
