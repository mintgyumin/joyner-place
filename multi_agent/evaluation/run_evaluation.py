"""
RAG Evaluation Runner — 통합 평가 스크립트

사용법:
    # 백엔드 API 통해 실행 (백엔드 서버 필요)
    python run_evaluation.py --mode api --url http://localhost:8003 --token <JWT>

    # 미리 수집한 결과 파일로 실행
    python run_evaluation.py --mode file --results ./results/tc001.json

    # 특정 테스트 케이스만
    python run_evaluation.py --mode api --filter TC001,TC002

출력:
    evaluation_report.json   — 상세 결과
    evaluation_report.md     — Markdown 요약
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

# 평가 모듈 경로 추가
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from evaluators import retrieval_eval, faithfulness_eval, coverage_eval, rule_eval

TESTSET_PATH = Path(__file__).parent / "testset.json"
OUTPUT_DIR = Path(__file__).parent / "results"


def load_testset(filter_ids: list[str] | None = None) -> list[dict]:
    cases = json.loads(TESTSET_PATH.read_text(encoding="utf-8"))
    if filter_ids:
        cases = [c for c in cases if c["id"] in filter_ids]
    return cases


def call_backend(
    message: str,
    session_id: str,
    backend_url: str,
    token: str,
) -> dict:
    """백엔드 /chat API 호출."""
    resp = requests.post(
        f"{backend_url}/chat",
        json={"message": message, "session_id": session_id, "conversation_history": []},
        headers={"Authorization": f"Bearer {token}"},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def run_single_case(
    case: dict,
    backend_url: str | None,
    token: str | None,
    preloaded_result: dict | None = None,
) -> dict:
    """단일 테스트 케이스 평가."""
    print(f"\n[{case['id']}] {case['description']}")
    expected = case["expected"]

    # 1. 백엔드 호출 or 기존 결과 사용
    if preloaded_result:
        api_result = preloaded_result
    elif backend_url and token:
        print(f"  → API 호출 중...")
        t0 = time.time()
        try:
            api_result = call_backend(
                message=case["input"]["message"],
                session_id=case["input"]["session_id"],
                backend_url=backend_url,
                token=token,
            )
            elapsed = round(time.time() - t0, 2)
            print(f"  → 완료 ({elapsed}s)")
        except Exception as e:
            print(f"  → API 오류: {e}")
            return {"id": case["id"], "error": str(e), "skipped": True}
    else:
        print(f"  → 결과 파일 없음 — 건너뜀")
        return {"id": case["id"], "skipped": True}

    recommendations = api_result.get("recommendations") or []
    candidates = [
        f"장소명: {r.get('place_name','')} | 카테고리: {r.get('category','')} | 주소: {r.get('address','')} | 거리: {r.get('distance','')}m"
        for r in recommendations
    ]

    # 2. Rule-based 평가
    rule_result = rule_eval.evaluate(
        recommendations=recommendations,
        min_count=expected.get("min_recommendations", 3),
    )
    print(f"  Rule  : {'✅' if rule_result['passed'] else '❌'} score={rule_result['score']:.2f}")

    # 3. Retrieval 평가
    expected_places = expected.get("expected_places", [])
    if expected_places and candidates:
        ret_result = retrieval_eval.evaluate(candidates, expected_places, k=10)
        print(f"  Retrieval P@10={ret_result['precision_at_k']:.2f} R@10={ret_result['recall_at_k']:.2f}")
    else:
        ret_result = {"precision_at_k": None, "recall_at_k": None, "note": "expected_places 없음"}

    # 4. Coverage 평가
    cov_result = coverage_eval.evaluate(
        recommendations=recommendations,
        purpose=expected.get("purpose", ""),
        time_slot=expected.get("time_slot", ""),
        people_count=expected.get("people_count", 4),
        category=expected.get("category", ""),
    )
    print(f"  Coverage overall={cov_result['overall_coverage']:.2f}")

    # 5. Faithfulness 평가
    if recommendations:
        faith_result = faithfulness_eval.evaluate(
            recommendations=recommendations,
            retrieved_docs=candidates,
        )
        print(f"  Faithfulness avg={faith_result['avg_faithfulness']:.2f}")
    else:
        faith_result = {"avg_faithfulness": None, "note": "추천 결과 없음"}

    # 6. 금지 카테고리 위반 검사
    forbidden = expected.get("forbidden_categories", [])
    violations = []
    if forbidden and recommendations:
        for rec in recommendations:
            cat = rec.get("category", "").lower()
            for fb in forbidden:
                if fb.lower() in cat or cat in fb.lower():
                    violations.append(f"{rec['place_name']} ({rec['category']}) — 금지 카테고리 '{fb}'")

    return {
        "id": case["id"],
        "description": case["description"],
        "input": case["input"]["message"],
        "recommendation_count": len(recommendations),
        "rule_eval": rule_result,
        "retrieval_eval": ret_result,
        "coverage_eval": cov_result,
        "faithfulness_eval": faith_result,
        "forbidden_violations": violations,
        "overall_pass": rule_result["passed"] and not violations,
        "recommendations_preview": [
            {"place_name": r.get("place_name"), "category": r.get("category")}
            for r in recommendations[:5]
        ],
    }


def generate_markdown_report(results: list[dict], output_path: Path) -> None:
    lines = [
        "# RAG Evaluation Report",
        f"\n생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"\n테스트 케이스: {len(results)}개\n",
        "---\n",
        "## 요약\n",
        "| ID | 설명 | 추천수 | Rule | Coverage | Faithfulness | 금지위반 | 통과 |",
        "|---|---|---|---|---|---|---|---|",
    ]

    total_pass = 0
    for r in results:
        if r.get("skipped"):
            lines.append(f"| {r['id']} | — | — | — | — | — | — | ⏭️ 건너뜀 |")
            continue

        rule_score = r["rule_eval"].get("score", 0)
        cov = r["coverage_eval"].get("overall_coverage", 0)
        faith = r["faithfulness_eval"].get("avg_faithfulness")
        faith_str = f"{faith:.2f}" if faith is not None else "N/A"
        violations = len(r.get("forbidden_violations", []))
        passed = r.get("overall_pass", False)
        if passed:
            total_pass += 1

        lines.append(
            f"| {r['id']} | {r['description'][:30]} | {r['recommendation_count']} | "
            f"{rule_score:.2f} | {cov:.2f} | {faith_str} | "
            f"{'⚠️ '+str(violations)+'건' if violations else '없음'} | "
            f"{'✅' if passed else '❌'} |"
        )

    lines.append(f"\n**전체 통과율: {total_pass}/{len([r for r in results if not r.get('skipped')])}**\n")
    lines.append("---\n")
    lines.append("## 케이스별 상세\n")

    for r in results:
        if r.get("skipped"):
            continue
        lines.append(f"### {r['id']} — {r['description']}\n")
        lines.append(f"- 입력: `{r['input']}`")
        lines.append(f"- 추천 수: {r['recommendation_count']}개")
        lines.append(f"- 추천 목록: {', '.join(p['place_name'] + '(' + p['category'] + ')' for p in r.get('recommendations_preview', []))}")

        rc = r["rule_eval"]
        lines.append(f"\n**Rule-based** (score={rc['score']:.2f})")
        for k, v in rc["checks"].items():
            lines.append(f"  - {'✅' if v else '❌'} {k}")
        if rc["issues"]:
            lines.append(f"  - 문제: {'; '.join(rc['issues'])}")

        cov = r["coverage_eval"]
        lines.append(f"\n**Coverage** (overall={cov['overall_coverage']:.2f})")
        lines.append(f"  - 위치 근접성: {cov['location_proximity']['pass_rate']:.2f}")
        lines.append(f"  - 카테고리 일치: {cov['category_match']['pass_rate']:.2f}")
        lines.append(f"  - 인원 수용: {cov['people_capacity']['pass_rate']:.2f}")
        lines.append(f"  - 시간대 반영: {cov['time_relevance']['pass_rate']:.2f}")

        faith = r["faithfulness_eval"]
        if faith.get("avg_faithfulness") is not None:
            lines.append(f"\n**Faithfulness** (avg={faith['avg_faithfulness']:.2f})")

        if r.get("forbidden_violations"):
            lines.append(f"\n**⚠️ 금지 카테고리 위반**")
            for v in r["forbidden_violations"]:
                lines.append(f"  - {v}")

        lines.append("\n---\n")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n📄 Markdown 리포트 저장: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Multi-Agent RAG Evaluation Runner")
    parser.add_argument("--mode", choices=["api", "file"], default="api", help="실행 모드")
    parser.add_argument("--url", default=os.getenv("BACKEND_URL", "http://localhost:8003"), help="백엔드 URL")
    parser.add_argument("--token", default=os.getenv("EVAL_TOKEN", ""), help="JWT 토큰")
    parser.add_argument("--results", default="", help="기존 결과 JSON 파일 경로 (mode=file 시)")
    parser.add_argument("--filter", default="", help="평가할 케이스 ID 쉼표 구분 (예: TC001,TC002)")
    parser.add_argument("--output", default="", help="출력 파일명 접두어")
    args = parser.parse_args()

    filter_ids = [x.strip() for x in args.filter.split(",") if x.strip()] if args.filter else None
    testset = load_testset(filter_ids)
    print(f"📋 테스트 케이스 {len(testset)}개 로드")

    OUTPUT_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = args.output or ts

    all_results = []

    for case in testset:
        preloaded = None
        if args.mode == "file" and args.results:
            results_file = Path(args.results)
            if results_file.exists():
                preloaded = json.loads(results_file.read_text(encoding="utf-8"))

        result = run_single_case(
            case=case,
            backend_url=args.url if args.mode == "api" else None,
            token=args.token if args.mode == "api" else None,
            preloaded_result=preloaded,
        )
        all_results.append(result)

    # JSON 저장
    json_path = OUTPUT_DIR / f"{prefix}_results.json"
    json_path.write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"📊 JSON 결과 저장: {json_path}")

    # Markdown 리포트
    md_path = OUTPUT_DIR / f"{prefix}_report.md"
    generate_markdown_report(all_results, md_path)

    # 요약 출력
    passed = sum(1 for r in all_results if r.get("overall_pass"))
    total = sum(1 for r in all_results if not r.get("skipped"))
    print(f"\n✅ 평가 완료: {passed}/{total} 통과 ({passed/total*100:.1f}%)" if total else "\n평가 케이스 없음")


if __name__ == "__main__":
    main()
