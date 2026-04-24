"""
RAG 평가 통합 실행 스크립트 - JOYNER Place

testset.json의 각 테스트 케이스마다:
  1. 백엔드 /recommend API를 직접 호출
  2. 4가지 평가 지표 계산
  3. JSON + Markdown 리포트 생성

실행 방법:
  python run_evaluation.py
  python run_evaluation.py --testset testset.json
  python run_evaluation.py --backend http://localhost:8000
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

# 평가 함수 import
from evaluator import (
    faithfulness_score,
    precision_at_k,
    requirement_coverage,
    rule_based_evaluation,
)

load_dotenv()

# 백엔드 기본 주소 (docker-compose 환경이면 http://backend:8000)
DEFAULT_BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000")


# ─────────────────────────────────────────
# 백엔드 API 호출
# ─────────────────────────────────────────

def get_jwt_token(backend: str) -> str:
    """
    테스트용 더미 계정으로 로그인해서 JWT 토큰을 받아온다.

    평가 스크립트는 인증이 필요한 /recommend 엔드포인트를 호출하므로
    먼저 로그인 토큰을 얻어야 한다.

    계정 정보는 환경변수에서 읽는다:
      EVAL_USERNAME, EVAL_PASSWORD (기본값: eval_user / eval_pass)
    """
    username = os.getenv("EVAL_USERNAME", "liz1108")
    password = os.getenv("EVAL_PASSWORD", "1234")

    try:
        resp = requests.post(
            f"{backend}/auth/login",
            json={"username": username, "password": password},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()["access_token"]
    except Exception as e:
        print(f"[경고] 로그인 실패: {e}")

    return ""


def call_recommend(backend: str, token: str, input_data: dict) -> dict | None:
    """
    /recommend API를 호출해서 추천 결과를 받아온다.

    Args:
        backend    : 백엔드 URL
        token      : JWT 토큰
        input_data : testset.json의 input 항목

    Returns:
        추천 결과 dict (places, midpoint 등) or None (실패 시)
    """
    headers = {"Authorization": f"Bearer {token}"}

    # testset input → API 요청 형식 변환
    payload = {
        "location":     input_data.get("location", ""),
        "purpose":      input_data.get("purpose", ""),
        "time_slot":    input_data.get("time_slot", ""),
        "people_count": input_data.get("people_count", 2),
        "locations":    input_data.get("locations"),  # 다중 참여자 모드 (없으면 None)
    }

    try:
        print(f"  → API 호출 중... (최대 90초 소요)")
        resp = requests.post(
            f"{backend}/recommend",
            json=payload,
            headers=headers,
            timeout=90,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        print(f"  [오류] API 응답 실패: {e.response.status_code} - {e.response.text[:200]}")
    except requests.exceptions.Timeout:
        print("  [오류] API 응답 시간 초과 (90초)")
    except Exception as e:
        print(f"  [오류] 예외 발생: {e}")

    return None


# ─────────────────────────────────────────
# 단일 케이스 평가
# ─────────────────────────────────────────

def evaluate_one(case: dict, backend: str, token: str) -> dict:
    """
    테스트 케이스 하나를 평가하고 결과 dict를 반환한다.

    Args:
        case    : testset.json의 test_cases 항목 하나
        backend : 백엔드 URL
        token   : JWT 토큰

    Returns:
        평가 결과 dict (점수, 규칙 체크, 오류 여부 포함)
    """
    case_id  = case.get("id", "unknown")
    input_d  = case.get("input", {})
    expected = case.get("expected", {})

    print(f"\n[{case_id}] 평가 시작")
    print(f"  위치: {input_d.get('location') or input_d.get('locations')}")
    print(f"  목적: {input_d.get('purpose')} / 시간: {input_d.get('time_slot')}")

    # API 호출
    rec = call_recommend(backend, token, input_d)
    if rec is None:
        return {
            "id":    case_id,
            "error": True,
            "scores": {},
            "rules":  {},
        }

    places = rec.get("places", [])
    print(f"  추천 결과: {len(places)}개")

    # ── 평가 1: Precision@K ──────────────────────────────────────
    retrieved_cats   = [p.get("category", "") for p in places]
    relevant_cats    = expected.get("relevant_categories", [])
    k                = expected.get("max_results", 5)
    prec_k           = precision_at_k(retrieved_cats, relevant_cats, k, purpose=input_d.get("purpose", ""))

    # ── 평가 2: Faithfulness ─────────────────────────────────────
    # 모든 추천 이유를 합쳐서 평가 (장소 데이터를 컨텍스트로 사용)
    all_reasons  = " ".join(p.get("reason", "") for p in places)
    all_contexts = [
        f"{p.get('place_name')} | {p.get('category')} | {p.get('address')}"
        for p in places
    ]
    faith = faithfulness_score(all_reasons, all_contexts)

    # ── 평가 3: Requirement Coverage ────────────────────────────
    requirements = expected.get("requirements", [])
    coverage = requirement_coverage(
        all_reasons,
        requirements,
        people_count=input_d.get("people_count", 0),
        time_slot=input_d.get("time_slot", ""),
    )

    # ── 평가 4: Rule-based ───────────────────────────────────────
    rules = rule_based_evaluation(places, expected)

    scores = {
        "precision_at_k":       round(prec_k,   3),
        "faithfulness":         round(faith,    3),
        "requirement_coverage": round(coverage, 3),
        "average":              round((prec_k + faith + coverage) / 3, 3),
    }

    print(f"  Precision@K       : {scores['precision_at_k']:.3f}")
    print(f"  Faithfulness      : {scores['faithfulness']:.3f}")
    print(f"  Req. Coverage     : {scores['requirement_coverage']:.3f}")
    print(f"  Average           : {scores['average']:.3f}")
    print(f"  Rules overall_pass: {rules.get('overall_pass')}")

    return {
        "id":     case_id,
        "input":  input_d,
        "error":  False,
        "places": places,
        "scores": scores,
        "rules":  rules,
    }


# ─────────────────────────────────────────
# 리포트 생성
# ─────────────────────────────────────────

def build_json_report(results: list[dict]) -> dict:
    """평가 결과를 JSON 리포트 형식으로 집계한다."""
    valid = [r for r in results if not r.get("error")]

    if not valid:
        return {"error": "평가 가능한 케이스가 없습니다.", "results": results}

    avg_scores = {
        key: round(sum(r["scores"][key] for r in valid) / len(valid), 3)
        for key in ["precision_at_k", "faithfulness", "requirement_coverage", "average"]
    }
    rule_pass_rate = round(
        sum(1 for r in valid if r["rules"].get("overall_pass", False)) / len(valid), 3
    )

    return {
        "generated_at":  datetime.now().isoformat(),
        "total_cases":   len(results),
        "success_cases": len(valid),
        "error_cases":   len(results) - len(valid),
        "aggregate": {
            "avg_scores":    avg_scores,
            "rule_pass_rate": rule_pass_rate,
        },
        "results": results,
    }


def build_markdown_report(report: dict) -> str:
    """평가 결과를 Markdown 형식으로 변환한다."""
    lines = []
    lines.append("# JOYNER Place — RAG 평가 리포트\n")
    lines.append(f"생성 시각: {report.get('generated_at', '-')}\n")
    lines.append(f"총 케이스: {report.get('total_cases', 0)}개 "
                 f"(성공: {report.get('success_cases', 0)}개 / 오류: {report.get('error_cases', 0)}개)\n")

    agg = report.get("aggregate", {})
    if agg:
        avg = agg.get("avg_scores", {})
        lines.append("\n## 전체 평균 점수\n")
        lines.append("| 지표 | 점수 |")
        lines.append("|------|------|")
        lines.append(f"| Precision@K       | {avg.get('precision_at_k', '-')} |")
        lines.append(f"| Faithfulness      | {avg.get('faithfulness', '-')} |")
        lines.append(f"| Req. Coverage     | {avg.get('requirement_coverage', '-')} |")
        lines.append(f"| **평균**          | **{avg.get('average', '-')}** |")
        lines.append(f"| Rule Pass Rate    | {agg.get('rule_pass_rate', '-')} |")
        lines.append("")

    lines.append("\n## 케이스별 상세 결과\n")

    for r in report.get("results", []):
        lines.append(f"### {r['id']}")
        if r.get("error"):
            lines.append("- **오류**: API 호출 실패\n")
            continue

        inp = r.get("input", {})
        lines.append(f"- 위치: `{inp.get('location') or inp.get('locations', '-')}`")
        lines.append(f"- 목적: `{inp.get('purpose', '-')}` / 시간: `{inp.get('time_slot', '-')}`")
        lines.append(f"- 인원: `{inp.get('people_count', '-')}명`\n")

        sc = r.get("scores", {})
        lines.append("| 지표 | 점수 |")
        lines.append("|------|------|")
        lines.append(f"| Precision@K       | {sc.get('precision_at_k', '-')} |")
        lines.append(f"| Faithfulness      | {sc.get('faithfulness', '-')} |")
        lines.append(f"| Req. Coverage     | {sc.get('requirement_coverage', '-')} |")
        lines.append(f"| 평균              | {sc.get('average', '-')} |")
        lines.append("")

        rules = r.get("rules", {})
        if rules:
            lines.append("**규칙 검사**\n")
            icon = lambda v: "✅" if v else "❌"
            lines.append(f"- {icon(rules.get('result_count_ok'))} 추천 개수 범위 준수")
            lines.append(f"- {icon(rules.get('no_duplicate'))} 중복 장소 없음")
            lines.append(f"- {icon(rules.get('all_have_address'))} 모든 장소에 주소 있음")
            lines.append(f"- {icon(rules.get('all_have_url'))} 모든 장소에 카카오맵 URL 있음")
            lines.append(f"- {icon(rules.get('all_have_reason'))} 모든 장소에 추천 이유 있음")
            lines.append(f"- **전체 통과: {icon(rules.get('overall_pass'))}**\n")

        places = r.get("places", [])
        if places:
            lines.append("**추천 결과**\n")
            for j, p in enumerate(places, 1):
                lines.append(f"{j}. **{p.get('place_name')}** ({p.get('category', '-')}) — {p.get('address', '-')}")
            lines.append("")

        lines.append("---\n")

    return "\n".join(lines)


# ─────────────────────────────────────────
# 메인 실행
# ─────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="JOYNER Place RAG 평가 스크립트")
    parser.add_argument(
        "--testset",
        default="testset.json",
        help="테스트셋 JSON 파일 경로 (기본: testset.json)",
    )
    parser.add_argument(
        "--backend",
        default=DEFAULT_BACKEND,
        help=f"백엔드 URL (기본: {DEFAULT_BACKEND})",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="리포트 저장 폴더 (기본: 현재 폴더)",
    )
    args = parser.parse_args()

    # ── testset.json 로드 ────────────────────────────────────────
    testset_path = Path(args.testset)
    if not testset_path.exists():
        print(f"[오류] testset 파일을 찾을 수 없습니다: {testset_path}")
        sys.exit(1)

    with open(testset_path, encoding="utf-8") as f:
        testset = json.load(f)

    test_cases = testset.get("test_cases", [])
    if not test_cases:
        print("[오류] test_cases가 비어 있습니다.")
        sys.exit(1)

    print(f"=== JOYNER Place RAG 평가 시작 ===")
    print(f"백엔드: {args.backend}")
    print(f"테스트 케이스: {len(test_cases)}개")

    # ── JWT 토큰 발급 ─────────────────────────────────────────────
    print("\n[인증] 로그인 중...")
    token = get_jwt_token(args.backend)
    if not token:
        print("[경고] 로그인 실패. EVAL_USERNAME / EVAL_PASSWORD 환경변수를 확인하세요.")
        print("       평가를 계속 진행하지만 API 호출이 실패할 수 있습니다.")

    # ── 각 케이스 평가 ────────────────────────────────────────────
    results = []
    for case in test_cases:
        result = evaluate_one(case, args.backend, token)
        results.append(result)

    # ── 리포트 생성 ───────────────────────────────────────────────
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    report = build_json_report(results)

    json_path = output_dir / "evaluation_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    md_path = output_dir / "evaluation_report.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(build_markdown_report(report))

    # ── 최종 요약 출력 ────────────────────────────────────────────
    print("\n=== 평가 완료 ===")
    agg = report.get("aggregate", {})
    if agg:
        avg = agg.get("avg_scores", {})
        print(f"Precision@K       : {avg.get('precision_at_k', '-')}")
        print(f"Faithfulness      : {avg.get('faithfulness', '-')}")
        print(f"Req. Coverage     : {avg.get('requirement_coverage', '-')}")
        print(f"전체 평균         : {avg.get('average', '-')}")
        print(f"Rule Pass Rate    : {agg.get('rule_pass_rate', '-')}")
    print(f"\n리포트 저장 완료:")
    print(f"  {json_path}")
    print(f"  {md_path}")


if __name__ == "__main__":
    main()
