"""
JOYNER Place Agent 핵심 로직

OpenAI 함수 호출(Function Calling / ReAct) 방식으로 동작한다.

[Agent 동작 순서]
1. 사용자 메시지를 받는다
2. GPT가 필요한 도구를 선택하고 파라미터를 결정한다
3. 선택된 도구를 실행하고 결과를 GPT에게 전달한다
4. GPT가 더 이상 도구가 필요 없으면 최종 응답을 생성한다
5. 검증 실패 시 3회까지 재시도한다
"""

import json
import os
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

from tools import TOOL_SCHEMAS, execute_tool

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "").strip())

# 시스템 프롬프트 로드
_PROMPT_PATH = Path(__file__).parent / "prompts" / "system_prompt.txt"
SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

# 최대 도구 실행 횟수 (무한 루프 방지)
MAX_TOOL_ITERATIONS = 10
# 검증 실패 시 재시도 횟수
MAX_RETRIES = 3


class JoynerAgent:
    """
    JOYNER Place AI 어시스턴트.

    사용 예시:
        agent = JoynerAgent()
        result = agent.run("강남역 근처 4명 회식 장소 추천해줘", session_id="abc123")
    """

    def __init__(self):
        # 세션별 중간 데이터 저장소
        # { session_id: { "midpoint": ..., "recommendations": [...], ... } }
        self._sessions: dict[str, dict] = {}

    def _get_session(self, session_id: str) -> dict:
        if session_id not in self._sessions:
            self._sessions[session_id] = {}
        return self._sessions[session_id]

    def run(self, message: str, session_id: str, conversation_history: list[dict] | None = None) -> dict:
        """
        사용자 메시지를 받아 장소 추천 결과를 반환한다.

        Args:
            message              : 사용자 자연어 입력
            session_id           : 대화 세션 ID (프론트엔드에서 생성)
            conversation_history : 이전 대화 전체 목록 (프론트엔드에서 전달)
                                   형식: [{"role": "user"|"assistant", "content": "..."}]
                                   없으면 빈 리스트로 처리 → 컨텍스트 없이 새로 시작

        Returns:
            {
                "reply": str,               # 자연어 응답
                "complete": bool,           # 추천 완료 여부
                "recommendations": list,    # 장소 목록
                "validation_result": dict,  # 검증 결과
                "tool_calls_log": list,     # 실행된 도구 로그
                "midpoint": str | None,
                "midpoint_lat": float | None,
                "midpoint_lng": float | None,
                "participant_coords": list,
            }
        """
        session_data = self._get_session(session_id)
        tool_calls_log: list[dict] = []

        # ── GPT에게 전달할 메시지 히스토리 구성 ─────────────────────
        # 1) 항상 시스템 프롬프트로 시작
        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

        # 2) 이전 대화 내용 삽입 (위치·인원·목적 컨텍스트 유지)
        #    프론트엔드가 전달한 {"role": "user"|"assistant", "content": "..."} 목록을 그대로 추가
        #    단, tool 역할 메시지는 GPT API 규격에 맞지 않으므로 user/assistant만 허용
        if conversation_history:
            for turn in conversation_history:
                if turn.get("role") in ("user", "assistant") and turn.get("content"):
                    messages.append({"role": turn["role"], "content": turn["content"]})

        # 3) 현재 사용자 메시지 추가
        messages.append({"role": "user", "content": message})

        final_reply = ""
        retry_count = 0

        while retry_count <= MAX_RETRIES:
            # ── Agent 실행 루프 ────────────────────────────────────
            # GPT가 "더 이상 도구가 필요 없다"고 할 때까지 반복
            iteration = 0
            while iteration < MAX_TOOL_ITERATIONS:
                iteration += 1
                print(f"[Agent] 반복 {iteration}/{MAX_TOOL_ITERATIONS}, retry={retry_count}")

                # GPT 호출 — 도구 목록과 함께
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    tools=TOOL_SCHEMAS,
                    tool_choice="auto",
                    temperature=0.7,
                )

                assistant_msg = response.choices[0].message

                # 도구 호출이 있으면 실행
                if assistant_msg.tool_calls:
                    # assistant 메시지를 히스토리에 추가
                    messages.append(assistant_msg)

                    # 각 도구 호출 처리
                    for tool_call in assistant_msg.tool_calls:
                        tool_name = tool_call.function.name
                        try:
                            tool_args = json.loads(tool_call.function.arguments)
                        except json.JSONDecodeError:
                            tool_args = {}

                        print(f"[Agent] 도구 실행: {tool_name}({tool_args})")
                        log_entry = {"tool": tool_name, "args": tool_args}

                        # 도구 실행
                        tool_result = execute_tool(tool_name, tool_args, session_data)
                        log_entry["result_summary"] = _summarize_result(tool_name, tool_result)
                        tool_calls_log.append(log_entry)

                        # 도구 결과를 메시지 히스토리에 추가
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(tool_result, ensure_ascii=False),
                        })

                else:
                    # 도구 호출 없음 → GPT 최종 응답
                    final_reply = assistant_msg.content or "추천을 완료했습니다."
                    messages.append({"role": "assistant", "content": final_reply})
                    break

            # ── 검증 확인 ──────────────────────────────────────────
            validation = session_data.get("validation")

            # 검증 결과가 없으면 직접 실행
            if not validation and session_data.get("recommendations"):
                validation = execute_tool(
                    "validate_result_tool",
                    {"results": session_data["recommendations"]},
                    session_data,
                )

            # 추천 수 부족 체크 (최소 3개)
            recs = session_data.get("recommendations", [])
            too_few = len(recs) < 3

            # 검증 통과 + 충분한 추천 수 or 더 이상 재시도 불가
            if (not validation or validation.get("passed", True)) and not too_few:
                break
            if retry_count >= MAX_RETRIES:
                break

            # 재시도 메시지 결정
            retry_count += 1
            if too_few and (not validation or validation.get("passed", True)):
                print(f"[Agent] 추천 부족({len(recs)}개) — 재시도 {retry_count}/{MAX_RETRIES}")
                retry_msg = (
                    f"추천 장소가 {len(recs)}개뿐입니다. 최소 3개 이상의 장소를 추천해야 합니다. "
                    f"search_places_tool부터 다시 실행해서 더 많은 장소를 찾아주세요. "
                    f"(재시도 {retry_count}/{MAX_RETRIES})"
                )
            else:
                issues = ", ".join(validation.get("issues", ["알 수 없는 문제"]))
                print(f"[Agent] 검증 실패 — 재시도 {retry_count}/{MAX_RETRIES}: {issues}")
                retry_msg = (
                    f"검증 실패: {issues}\n"
                    f"search_places_tool부터 다시 실행해서 더 나은 결과를 추천해주세요. "
                    f"(재시도 {retry_count}/{MAX_RETRIES})"
                )

            messages.append({"role": "user", "content": retry_msg})
            # 세션 데이터 일부 초기화 (검색 결과만 리셋, 중간지점은 유지)
            session_data.pop("recommendations", None)
            session_data.pop("validation", None)

        return {
            "reply": final_reply,
            "complete": True,
            "recommendations": session_data.get("recommendations"),
            "validation_result": session_data.get("validation"),
            "tool_calls_log": tool_calls_log,
            "midpoint": session_data.get("midpoint"),
            "midpoint_lat": session_data.get("midpoint_lat"),
            "midpoint_lng": session_data.get("midpoint_lng"),
            "participant_coords": session_data.get("participant_coords", []),
        }


def _summarize_result(tool_name: str, result: dict) -> str:
    """도구 실행 결과를 로그용 한 줄 요약으로 변환한다."""
    if not result.get("success", True):
        return f"실패: {result.get('error', '알 수 없는 오류')}"

    if tool_name == "search_places_tool":
        return f"{result.get('found_count', 0)}개 장소 검색됨 (search_id={result.get('search_id')})"
    elif tool_name == "get_place_recommendation_tool":
        return f"{len(result.get('recommendations', []))}개 추천 생성"
    elif tool_name == "calculate_midpoint_tool":
        return f"중간지점: {result.get('address', '-')} ({result.get('lat')}, {result.get('lng')})"
    elif tool_name == "validate_result_tool":
        passed = result.get("passed", False)
        issues = result.get("issues", [])
        return f"{'통과' if passed else '실패'}: {issues if issues else '문제 없음'}"
    return "완료"
