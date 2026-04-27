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
    category_leaf,
    WIDE_AREA_COORDS,
    PURPOSE_KEYWORD_MAP,
    PURPOSE_CATEGORY_CODES,
)

load_dotenv()

_PROMPT = (Path(__file__).parent.parent / "prompts" / "search_agent_prompt.txt").read_text(encoding="utf-8")

_CATEGORY_FILTER_KEYS: dict[str, list[str]] = {
    "고깃집": ["고기요리", "구이", "삼겹살", "갈비", "고기", "육류", "바베큐", "고기전문", "구이전문", "정육", "소고기", "돼지고기"],
    "삼겹살": ["삼겹살", "고기요리", "구이", "고기", "육류", "돼지고기"],
    "갈비": ["갈비", "고기요리", "구이", "고기", "육류", "소고기"],
    "이자카야": ["이자카야", "일본식주점", "술집", "바"],
    "술집": ["술집", "호프", "바", "포차", "이자카야", "일본식주점"],
}

_CATEGORY_MULTI_QUERIES: dict[str, list[str]] = {
    "고깃집": ["삼겹살", "갈비"],
    "삼겹살": ["삼겹살", "고기구이"],
    "갈비": ["갈비", "소갈비"],
    "이자카야": ["이자카야", "일본식주점"],
    "술집": ["호프", "포차"],
}

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
    participant_coords: list | None = None,
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

    # 특정 카테고리 — 초기 결과에서 매칭 수 부족할 때만 추가 검색 (최대 2쿼리 × 1페이지)
    size_hint = " 단체 대형홀" if people_count >= 10 else (" 단체석" if people_count >= 5 else "")
    extra_queries = _CATEGORY_MULTI_QUERIES.get(category, [])
    if extra_queries:
        filter_keys = _CATEGORY_FILTER_KEYS.get(category, [])
        current_match_count = sum(
            1 for p in raw_places
            if any(
                k in category_leaf(p.get("category_name", ""))
                or category_leaf(p.get("category_name", "")) in k
                or k in p.get("place_name", "")
                for k in filter_keys)
        ) if filter_keys else 0

        if current_match_count < 5:
            existing_ids = {p.get("id") for p in raw_places}
            for eq in extra_queries:
                # 1페이지만 검색해 API 호출 최소화
                extra_places = search_kakao_places(
                    query=f"{location_name} {eq}{size_hint}", x=lng, y=lat, radius=radius
                )[:15]
                for p in extra_places:
                    if p.get("id") not in existing_ids:
                        raw_places.append(p)
                        existing_ids.add(p.get("id"))
            print(f"[SearchAgent] 다중 쿼리 후 총 {len(raw_places)}개 확보")

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

    # 중간지점 케이스: 각 참여자 위치에서도 보조 검색
    if participant_coords and len(participant_coords) > 1:
        existing_ids = {p.get("id") for p in raw_places}
        for coord in participant_coords:
            p_lat = coord.get("lat")
            p_lng = coord.get("lng")
            if not p_lat or not p_lng:
                continue
            if abs(p_lat - lat) < 0.001 and abs(p_lng - lng) < 0.001:
                continue  # 이미 중간지점과 동일한 좌표
            p_results = search_kakao_places(query=search_query, x=p_lng, y=p_lat, radius=5000)
            for p in p_results:
                if p.get("id") not in existing_ids:
                    raw_places.append(p)
                    existing_ids.add(p.get("id"))
        print(f"[SearchAgent] 참여자 좌표 보조 검색 후 총 {len(raw_places)}개")

    if not raw_places:
        return {"success": False, "error": "주변에 장소를 찾지 못했어요."}

    print(f"[SearchAgent] 총 {len(raw_places)}개 후보 확보")

    # RAG 파이프라인 — 특정 카테고리는 필터링 후 랭킹 (BBQ 등이 비관련 장소에 묻히지 않도록)
    rag_source = raw_places
    pre_filter_keys = _CATEGORY_FILTER_KEYS.get(category)
    if pre_filter_keys:
        cat_filtered = [
            p for p in raw_places
            if any(
                k in category_leaf(p.get("category_name", ""))
                or category_leaf(p.get("category_name", "")) in k
                or k in p.get("place_name", "")
                for k in pre_filter_keys
            )
        ]
        if len(cat_filtered) >= 1:
            rag_source = cat_filtered
            print(f"[SearchAgent] RAG 사전필터: {len(rag_source)}개 ({category})")

    documents = build_place_documents(rag_source)
    index, _, docs = build_faiss_index(documents)
    bm25 = build_bm25(documents)

    user_input = {
        "location": location_name,
        "purpose": purpose,
        "time": time_slot,
        "people": people_count,
    }
    rag_query = f"{people_count}인 {category or purpose} {time_slot} 분위기"
    top_k = 15 if is_wide_area else 10
    hybrid_docs = hybrid_search(rag_query, index, bm25, docs, top_k=top_k + 3)
    top_docs = rerank(user_input, hybrid_docs, top_k=top_k)

    return {
        "success": True,
        "candidates": top_docs,
        "raw_places": raw_places,
        "search_query": search_query,
        "found_count": len(raw_places),
    }
