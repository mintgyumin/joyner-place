"""
Multi-Agent Orchestrator — 4개 에이전트를 순서대로 실행하고 결과를 조합한다.

[실행 순서]
1. LocationAgent  → 위치·목적·인원·시간대 파싱
2. SearchAgent    → 카카오 API + RAG 장소 검색
3. RecommendAgent → GPT 추천 이유 생성
4. ValidationAgent → 코드 + LLM 품질 검증
※ 검증 실패 시 SearchAgent부터 최대 3회 재시도
"""

import time
import os
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

from agents import location_agent, search_agent, recommend_agent, validation_agent

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MAX_RETRIES = 3
WIDE_AREA_KEYS = {
    "서울", "서울시", "강남", "강남구", "강남역", "홍대", "홍대입구",
    "신촌", "마포", "마포구", "이태원", "종로", "혜화", "건대",
    "잠실", "여의도", "신림", "관악", "노원", "성수", "합정",
}


def _is_wide_area(location_name: str) -> bool:
    return any(k in location_name for k in WIDE_AREA_KEYS)


def _make_reply(message: str, recommendations: list[dict], loc_result: dict, retry_count: int) -> str:
    """최종 응답 한 줄 생성."""
    purpose = loc_result.get("purpose", "모임")
    location = loc_result.get("location_name", "")
    people = loc_result.get("people_count", 4)
    is_midpoint = loc_result.get("is_midpoint", False)

    midpoint_note = f" (중간지점: {location})" if is_midpoint else ""
    retry_note = f" (재시도 {retry_count}회)" if retry_count > 0 else ""

    return (
        f"{location}{midpoint_note}에서 {people}명 {purpose}에 딱 맞는 장소들을 찾았어요! "
        f"즐거운 시간 되세요! 🎉{retry_note}"
    )


class MultiAgentOrchestrator:
    """
    4개 에이전트를 순서대로 실행하는 오케스트레이터.

    사용 예시:
        orch = MultiAgentOrchestrator()
        result = orch.run("강남역 근처 4명 회식", session_id="abc")
    """

    def __init__(self):
        # 세션별 위치 정보 캐시 (동일 세션에서 "거기서 추가로" 등 처리)
        self._sessions: dict[str, dict] = {}

    def _get_session(self, session_id: str) -> dict:
        if session_id not in self._sessions:
            self._sessions[session_id] = {}
        return self._sessions[session_id]

    def run(
        self,
        message: str,
        session_id: str,
        conversation_history: list[dict] | None = None,
    ) -> dict:
        """
        오케스트레이터 실행.

        Returns:
            {
                "reply": str,
                "complete": bool,
                "recommendations": list,
                "validation_result": dict,
                "agent_log": list[dict],
                "midpoint": str | None,
                "midpoint_lat": float | None,
                "midpoint_lng": float | None,
                "participant_coords": list,
                "retry_count": int,
            }
        """
        session = self._get_session(session_id)
        agent_log: list[dict] = []
        history = conversation_history or []

        # ── Step 1: Location Agent ────────────────────────────────
        t0 = time.time()
        loc_result = location_agent.run(message, history)
        loc_ms = int((time.time() - t0) * 1000)

        if not loc_result.get("success"):
            agent_log.append({
                "agent": "Location Agent",
                "status": "failed",
                "summary": f"위치 파싱 실패: {loc_result.get('error')}",
                "duration_ms": loc_ms,
                "details": loc_result,
            })
            return {
                "reply": loc_result.get("error", "위치를 파악하지 못했어요."),
                "complete": False,
                "recommendations": None,
                "validation_result": None,
                "agent_log": agent_log,
                "midpoint": None,
                "midpoint_lat": None,
                "midpoint_lng": None,
                "participant_coords": [],
                "retry_count": 0,
            }

        lat = loc_result["lat"]
        lng = loc_result["lng"]
        location_name = loc_result["location_name"]
        purpose = loc_result["purpose"]
        time_slot = loc_result["time_slot"]
        people_count = loc_result["people_count"]
        is_midpoint = loc_result.get("is_midpoint", False)
        participant_coords = loc_result.get("participant_coords", [])

        # 세션에 위치 저장 (다음 대화에서 재사용 가능)
        session.update({
            "lat": lat, "lng": lng,
            "location_name": location_name,
            "is_midpoint": is_midpoint,
            "participant_coords": participant_coords,
        })

        agent_log.append({
            "agent": "Location Agent",
            "status": "done",
            "summary": (
                f"📍 {location_name} | 목적: {purpose} | "
                f"인원: {people_count}명 | 시간: {time_slot}"
                + (" (중간지점)" if is_midpoint else "")
            ),
            "duration_ms": loc_ms,
            "details": {
                "location_name": location_name,
                "lat": lat, "lng": lng,
                "purpose": purpose,
                "time_slot": time_slot,
                "people_count": people_count,
                "is_midpoint": is_midpoint,
            },
        })

        category = loc_result.get("category", "")
        is_wide = _is_wide_area(location_name)
        final_recommendations = None
        final_validation = None
        retry_count = 0

        # ── Step 2~4: 검색 → 추천 → 검증 (재시도 루프) ──────────
        for attempt in range(MAX_RETRIES + 1):
            retry_count = attempt

            # ── Step 2: Search Agent ──────────────────────────────
            t0 = time.time()
            search_result = search_agent.run(
                lat=lat, lng=lng,
                location_name=location_name,
                purpose=purpose,
                time_slot=time_slot,
                people_count=people_count,
                is_wide_area=is_wide,
                category=category,
            )
            search_ms = int((time.time() - t0) * 1000)

            if not search_result.get("success"):
                agent_log.append({
                    "agent": f"Search Agent{' (재시도 '+str(attempt)+')' if attempt else ''}",
                    "status": "failed",
                    "summary": f"검색 실패: {search_result.get('error')}",
                    "duration_ms": search_ms,
                    "details": search_result,
                })
                break

            found_count = search_result.get("found_count", 0)
            search_query = search_result.get("search_query", "")
            agent_log.append({
                "agent": f"Search Agent{' (재시도 '+str(attempt)+')' if attempt else ''}",
                "status": "done",
                "summary": f"🔍 '{search_query}' 검색 → {found_count}개 후보 확보",
                "duration_ms": search_ms,
                "details": {
                    "search_query": search_query,
                    "found_count": found_count,
                },
            })

            # ── Step 3: Recommend Agent ───────────────────────────
            t0 = time.time()
            rec_result = recommend_agent.run(
                candidates=search_result["candidates"],
                raw_places=search_result["raw_places"],
                location_name=location_name,
                purpose=purpose,
                time_slot=time_slot,
                people_count=people_count,
                category=category,
            )
            rec_ms = int((time.time() - t0) * 1000)

            recommendations = rec_result.get("recommendations", [])
            agent_log.append({
                "agent": f"Recommend Agent{' (재시도 '+str(attempt)+')' if attempt else ''}",
                "status": "done" if rec_result.get("success") else "failed",
                "summary": f"🤖 {len(recommendations)}개 장소 추천 생성",
                "duration_ms": rec_ms,
                "details": {"count": len(recommendations)},
            })

            # ── Step 4: Validation Agent ──────────────────────────
            t0 = time.time()
            val_result = validation_agent.run(
                recommendations=recommendations,
                purpose=purpose,
                time_slot=time_slot,
                people_count=people_count,
                category=category,
            )
            val_ms = int((time.time() - t0) * 1000)

            passed = val_result.get("passed", False)
            issues = val_result.get("issues", [])
            agent_log.append({
                "agent": f"Validation Agent{' (재시도 '+str(attempt)+')' if attempt else ''}",
                "status": "done" if passed else "failed",
                "summary": (
                    "✅ 검증 통과" if passed
                    else f"⚠️ 검증 실패: {', '.join(issues[:2])}"
                ),
                "duration_ms": val_ms,
                "details": val_result,
            })

            final_recommendations = recommendations
            final_validation = val_result

            if passed and len(recommendations) >= 3:
                break

            if attempt >= MAX_RETRIES:
                print(f"[Orchestrator] 최대 재시도 횟수 초과 → 현재 결과로 반환")
                break

            print(f"[Orchestrator] 재시도 {attempt+1}/{MAX_RETRIES}: {issues}")

        # ── 최종 응답 생성 ────────────────────────────────────────
        reply = _make_reply(message, final_recommendations or [], loc_result, retry_count)

        return {
            "reply": reply,
            "complete": True,
            "recommendations": final_recommendations,
            "validation_result": final_validation,
            "agent_log": agent_log,
            "midpoint": location_name if is_midpoint else None,
            "midpoint_lat": lat if is_midpoint else None,
            "midpoint_lng": lng if is_midpoint else None,
            "participant_coords": participant_coords,
            "retry_count": retry_count,
        }
