"""
Location Agent — 사용자 메시지에서 위치·목적·인원·시간대를 파싱한다.

GPT 함수 호출로 구조화된 데이터를 추출하고,
단일 위치면 카카오 지오코딩, 복수 위치면 중간지점을 계산한다.
"""

import json
import os
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import get_coords, calculate_midpoint, WIDE_AREA_COORDS

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "").strip())

_PROMPT = (Path(__file__).parent.parent / "prompts" / "location_agent_prompt.txt").read_text(encoding="utf-8")

_EXTRACT_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "extract_location_info",
            "description": "사용자 메시지에서 위치, 목적, 인원, 시간대를 추출합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "locations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "언급된 위치 목록. 복수이면 중간지점을 계산합니다.",
                    },
                    "purpose": {
                        "type": "string",
                        "description": "모임 목적: 술자리/회식/카페/스터디/데이트/친구모임/모임",
                    },
                    "time_slot": {
                        "type": "string",
                        "description": "시간대: 아침/점심/저녁/밤",
                    },
                    "people_count": {
                        "type": "integer",
                        "description": "인원수 (미언급 시 4)",
                    },
                    "category": {
                        "type": "string",
                        "description": "장소 유형 필터. 음식 종류나 장소 유형이 명시적으로 언급된 경우만 추출 (예: 고깃집, 이자카야, 파스타, 한식, 초밥). 없으면 빈 문자열.",
                    },
                },
                "required": ["locations", "purpose", "time_slot", "people_count", "category"],
            },
        },
    }
]


def run(user_message: str, conversation_history: list[dict]) -> dict:
    """
    자연어 메시지에서 위치 정보를 파싱한다.

    Returns:
        {
            "success": bool,
            "lat": float, "lng": float,
            "location_name": str,
            "is_midpoint": bool,
            "participant_coords": list,
            "purpose": str,
            "time_slot": str,
            "people_count": int,
        }
    """
    print(f"[LocationAgent] 메시지 분석 중: {user_message[:60]}")

    # 메시지 구성
    messages = [{"role": "system", "content": _PROMPT}]
    for turn in (conversation_history or []):
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": user_message})

    # GPT 호출
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=_EXTRACT_SCHEMA,
        tool_choice={"type": "function", "function": {"name": "extract_location_info"}},
        temperature=0.0,
    )

    msg = response.choices[0].message
    if not msg.tool_calls:
        return {"success": False, "error": "위치 정보를 파싱하지 못했어요."}

    try:
        args = json.loads(msg.tool_calls[0].function.arguments)
    except json.JSONDecodeError:
        return {"success": False, "error": "위치 파싱 결과를 읽지 못했어요."}

    locations = args.get("locations", [])
    purpose = args.get("purpose", "모임")
    time_slot = args.get("time_slot", "저녁")
    people_count = args.get("people_count", 4)
    category = args.get("category", "")

    print(f"[LocationAgent] 추출 결과: locations={locations}, purpose={purpose}, people={people_count}, category='{category}'")

    if not locations:
        return {"success": False, "error": "위치를 파악하지 못했어요. 출발지나 목적지를 알려주세요."}

    # 단일 위치 처리
    if len(locations) == 1:
        loc = locations[0]
        # 광역 지역 체크
        wide = WIDE_AREA_COORDS.get(loc) or WIDE_AREA_COORDS.get(loc.split()[0])
        if wide:
            lat, lng = wide
        else:
            coords = get_coords(loc)
            if not coords:
                return {"success": False, "error": f"'{loc}' 위치를 찾을 수 없어요."}
            lat, lng = coords
        return {
            "success": True,
            "lat": lat, "lng": lng,
            "location_name": loc,
            "is_midpoint": False,
            "participant_coords": [{"lat": lat, "lng": lng, "label": loc}],
            "purpose": purpose,
            "time_slot": time_slot,
            "people_count": people_count,
            "category": category,
        }

    # 복수 위치 → 중간지점
    result = calculate_midpoint(locations)
    if not result.get("success"):
        return {"success": False, "error": result.get("error", "중간지점 계산 실패")}

    return {
        "success": True,
        "lat": result["lat"],
        "lng": result["lng"],
        "location_name": result["address"],
        "is_midpoint": True,
        "participant_coords": result.get("participant_coords", []),
        "purpose": purpose,
        "time_slot": time_slot,
        "people_count": people_count,
        "category": category,
    }
