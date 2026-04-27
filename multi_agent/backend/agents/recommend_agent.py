"""
Recommend Agent — 검색 후보에서 최적 장소를 선별하고 추천 이유를 생성한다.
"""

import re
import os
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import (
    client as openai_client,
    generate_tags,
    category_leaf,
    find_place_by_doc,
    PURPOSE_ALLOWED_CATEGORIES,
)

load_dotenv()

_PROMPT = (Path(__file__).parent.parent / "prompts" / "recommend_agent_prompt.txt").read_text(encoding="utf-8")


_CATEGORY_SYNONYMS: dict[str, list[str]] = {
    "고깃집": ["고기요리", "구이", "삼겹살", "갈비", "고기", "육류", "바베큐", "고기전문", "구이전문", "정육", "소고기", "돼지고기"],
    "삼겹살": ["삼겹살", "고기요리", "구이", "고기", "육류"],
    "갈비": ["갈비", "고기요리", "구이", "고기", "육류"],
    "이자카야": ["이자카야", "일본식주점", "술집", "바"],
    "술집": ["술집", "호프", "바", "포차", "이자카야", "일본식주점"],
}


def _get_allowed_cats(purpose: str, category: str = "") -> list[str] | None:
    if category:
        syns = _CATEGORY_SYNONYMS.get(category)
        if syns:
            return syns
        for key, cats in PURPOSE_ALLOWED_CATEGORIES.items():
            if key in category:
                return cats
    for key, cats in PURPOSE_ALLOWED_CATEGORIES.items():
        if key in purpose:
            return cats
    return None


def run(
    candidates: list[str],
    raw_places: list[dict],
    location_name: str,
    purpose: str,
    time_slot: str,
    people_count: int,
    category: str = "",
) -> dict:
    """
    후보 장소에서 최적 5곳을 선별하고 추천 이유를 생성한다.

    Returns:
        {
            "success": bool,
            "recommendations": list[dict],
        }
    """
    print(f"[RecommendAgent] {len(candidates)}개 후보 처리 중")

    # 카테고리 필터링: category(고깃집 등 명시) > purpose 기반 allowed_cats
    if category:
        filter_keys = _get_allowed_cats(purpose, category) or [category]
        filter_label = category
    else:
        filter_keys = _get_allowed_cats(purpose)
        filter_label = purpose

    no_category_match = False
    if filter_keys:
        filtered_docs = []
        for doc in candidates:
            place = find_place_by_doc(doc, raw_places)
            if not place:
                continue
            cat = category_leaf(place.get("category_name", ""))
            name = place.get("place_name", "")
            if any(k in cat or cat in k or k in name for k in filter_keys):
                filtered_docs.append(doc)
        if len(filtered_docs) >= 3:
            candidates = filtered_docs
        elif filtered_docs:
            # 필터 결과가 너무 적으면 원본과 합쳐 최소 후보 확보
            merged = filtered_docs + [d for d in candidates if d not in filtered_docs]
            candidates = merged
            print(f"[RecommendAgent] '{filter_label}' 필터 결과 {len(filtered_docs)}개 → 원본 병합")
        else:
            no_category_match = True
            print(f"[RecommendAgent] '{filter_label}' 필터 후 결과 없음 → 원본 유지 (카테고리 제약 완화)")

    # 프롬프트 카테고리 제약
    if category and no_category_match:
        # 카테고리 매칭 장소가 전혀 없음 → 반드시 5개 반환, 유사 업종 허용
        category_constraint = (
            f"\n[카테고리 안내] 사용자가 '{category}'을(를) 원했으나 후보 목록에 해당 장소가 없습니다. "
            f"반드시 위 목록에서 5개를 선정하세요. "
            f"카페·편의점·분식은 제외하고, 음식점 중 가장 분위기가 맞는 곳을 추천하세요."
        )
    elif category:
        # 카테고리 매칭 장소 있음 → 우선 추천, 부족하면 유사 업종으로 채우기
        category_constraint = (
            f"\n[카테고리 제약] 사용자가 '{category}'을(를) 명시했습니다. "
            f"삼겹살·갈비·구이 등 {category}에 해당하는 장소를 최우선으로 추천하세요. "
            f"{category} 장소가 5개 미만이면 고기요리·한식 음식점으로 채워 반드시 5개를 완성하세요. "
            f"카페·분식·편의점은 제외하세요."
        )
    elif filter_keys:
        excluded = "카페·커피숍" if "카페" not in filter_keys else ""
        category_constraint = (
            f"\n[카테고리 제약] 목적이 '{purpose}'이므로 반드시 "
            f"{', '.join(filter_keys[:6])} 카테고리 장소만 추천하세요."
            + (f" {excluded}은 절대 추천하지 마세요." if excluded else "")
        )
    else:
        category_constraint = ""

    n = len(candidates)
    places_text = "\n".join(f"{i+1}. {doc}" for i, doc in enumerate(candidates))

    prompt = f"""{_PROMPT}
{category_constraint}

[사용자 조건]
- 위치: {location_name}
- 모임 목적: {purpose}
- 시간대: {time_slot}
- 인원수: {people_count}명

[후보 장소]
{places_text}

[출력 형식 - 반드시 준수]
위 후보 목록에서 가장 적합한 장소를 최소 3곳, 가능하면 5곳 고르세요.
반드시 위 목록의 번호(숫자)를 그대로 사용하고, 새로운 장소명을 만들지 마세요.
후보가 3개 이상이면 반드시 3개 이상 선정해야 합니다.

[추천 장소 1] 번호
- 추천 이유: (2~3문장)

[추천 장소 2] 번호
- 추천 이유: (2~3문장)

[추천 장소 3] 번호
- 추천 이유: (2~3문장)

[추천 장소 4] 번호
- 추천 이유: (2~3문장)

[추천 장소 5] 번호
- 추천 이유: (2~3문장)
"""

    resp = openai_client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "당신은 장소 추천 전문가입니다. 지정된 형식으로만 답변합니다. 반드시 후보 목록의 번호만 사용하세요."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
    )
    rec_text = resp.choices[0].message.content

    # 파싱: 번호 → candidates 인덱스 → find_place_by_doc
    pattern = r'\[추천 장소 \d+\]\s*(\d+)\s*\n- 추천 이유:\s*([\s\S]+?)(?=\n\[추천 장소|\Z)'
    matches = re.findall(pattern, rec_text.strip())

    recommendations = []
    seen_indices: set[int] = set()

    for num_str, reason in matches:
        reason = reason.strip()
        try:
            idx = int(num_str.strip()) - 1
        except ValueError:
            continue
        if idx < 0 or idx >= len(candidates) or idx in seen_indices:
            continue
        seen_indices.add(idx)

        place_dict = find_place_by_doc(candidates[idx], raw_places)
        if not place_dict:
            continue

        address = place_dict.get("road_address_name") or place_dict.get("address_name", "")
        recommendations.append({
            "place_name": place_dict.get("place_name", ""),
            "category": category_leaf(place_dict.get("category_name", "")),
            "address": address,
            "distance": place_dict.get("distance", ""),
            "place_url": place_dict.get("place_url", ""),
            "reason": reason,
            "tags": [],
            "lat": float(place_dict["y"]) if place_dict.get("y") else None,
            "lng": float(place_dict["x"]) if place_dict.get("x") else None,
        })

    # 태그 생성
    if recommendations:
        tags_batch = generate_tags([
            {"name": r["place_name"], "category": r["category"], "address": r["address"]}
            for r in recommendations
        ])
        for rec, tags in zip(recommendations, tags_batch):
            rec["tags"] = tags

    print(f"[RecommendAgent] {len(recommendations)}개 추천 생성 완료")
    return {"success": True, "recommendations": recommendations}
