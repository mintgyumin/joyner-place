"""
Search Agent — 카카오 API + RAG 파이프라인으로 장소 후보를 검색한다.

위치 좌표, 목적, 인원, 시간대를 받아 최대 15개 후보를 반환한다.
"""

import json
import os
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import (
    client as openai_client,
    search_kakao_places,
    search_kakao_by_category,
    build_place_documents,
    build_faiss_index,
    build_bm25,
    hybrid_search,
    rerank,
    find_place_by_doc,
    WIDE_AREA_COORDS,
    PURPOSE_KEYWORD_MAP,
    PURPOSE_CATEGORY_CODES,
)

load_dotenv()

_PROMPT = (Path(__file__).parent.parent / "prompts" / "search_agent_prompt.txt").read_text(encoding="utf-8")

_QUERY_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "generate_search_query",
            "description": "목적과 인원에 맞는 카카오 검색 쿼리를 생성합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "카카오 키워드 검색에 사용할 쿼리 (예: '길음역 근처 단체석 있는 회식 음식점')",
                    }
                },
                "required": ["query"],
            },
        },
    }
]


def _build_kakao_query(location_name: str, purpose: str, people_count: int, time_slot: str, category: str = "") -> str:
    """규칙 기반으로 검색 쿼리를 생성한다. category가 있으면 우선 사용한다."""
    if category:
        keyword = category
    else:
        keyword = next(
            (v for k, v in PURPOSE_KEYWORD_MAP.items() if k in purpose),
            "음식점",
        )
    size_hint = ""
    if people_count >= 10:
        size_hint = " 단체 대형홀"
    elif people_count >= 5:
        size_hint = " 단체석"

    loc_part = location_name
    if len(location_name.split()) == 1 and "역" not in location_name and "동" not in location_name:
        loc_part = f"{location_name} 근처"

    return f"{loc_part} {keyword}{size_hint}".strip()


def run(
    lat: float,
    lng: float,
    location_name: str,
    purpose: str,
    time_slot: str,
    people_count: int,
    is_wide_area: bool = False,
    category: str = "",
) -> dict:
    """
    카카오 API + RAG로 장소 후보를 검색한다.

    Returns:
        {
            "success": bool,
            "candidates": list[dict],   # rerank된 상위 후보 (doc 문자열)
            "raw_places": list[dict],   # 카카오 원본 데이터 (추천 에이전트용)
            "search_query": str,
        }
    """
    radius = 5000 if is_wide_area else 2000

    # 검색 쿼리 결정
    search_query = _build_kakao_query(location_name, purpose, people_count, time_slot, category)
    print(f"[SearchAgent] 쿼리='{search_query}', 반경={radius}m, category='{category}'")

    # 카카오 키워드 검색
    raw_places = search_kakao_places(query=search_query, x=lng, y=lat, radius=radius)

    # 결과 부족 시 반경 확장
    if len(raw_places) < 10:
        print(f"[SearchAgent] 결과 부족({len(raw_places)}개) → 반경 {radius*2}m 재시도")
        raw_places = search_kakao_places(query=search_query, x=lng, y=lat, radius=radius * 2)

    # 카테고리 코드 보조 검색
    purpose_key = next((k for k in PURPOSE_CATEGORY_CODES if k in purpose), None)
    if purpose_key:
        existing_ids = {p.get("id") for p in raw_places}
        for code in PURPOSE_CATEGORY_CODES[purpose_key]:
            cat_results = search_kakao_by_category(code, x=lng, y=lat, radius=radius)
            for p in cat_results:
                if p.get("id") not in existing_ids:
                    raw_places.append(p)
                    existing_ids.add(p.get("id"))

    if not raw_places:
        return {"success": False, "error": "주변에 장소를 찾지 못했어요."}

    print(f"[SearchAgent] 총 {len(raw_places)}개 후보 확보")

    # RAG 파이프라인
    documents = build_place_documents(raw_places)
    index, _, docs = build_faiss_index(documents)
    bm25 = build_bm25(documents)

    user_input = {
        "location": location_name,
        "purpose": purpose,
        "time": time_slot,
        "people": people_count,
    }
    rag_query = f"{people_count}인 {category or purpose} {time_slot} 분위기"
    hybrid_docs = hybrid_search(rag_query, index, bm25, docs, top_k=12)
    top_docs = rerank(user_input, hybrid_docs, top_k=10)

    return {
        "success": True,
        "candidates": top_docs,
        "raw_places": raw_places,
        "search_query": search_query,
        "found_count": len(raw_places),
    }
