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
    find_place_by_name,
    find_place_by_doc,
    PURPOSE_ALLOWED_CATEGORIES,
)

load_dotenv()

_PROMPT = (Path(__file__).parent.parent / "prompts" / "recommend_agent_prompt.txt").read_text(encoding="utf-8")


def _get_allowed_cats(purpose: str) -> list[str] | None:
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
        filter_keys = [category]
        filter_label = category
    else:
        filter_keys = _get_allowed_cats(purpose)
        filter_label = purpose

    if filter_keys:
        filtered_docs = []
        for doc in candidates:
            place = find_place_by_doc(doc, raw_places)
            if not place:
                continue
            cat = category_leaf(place.get("category_name", ""))
            if any(k in cat or cat in k for k in filter_keys):
                filtered_docs.append(doc)
        if filtered_docs:
            candidates = filtered_docs
        else:
            print(f"[RecommendAgent] '{filter_label}' 필터 후 결과 없음 → 원본 유지")

    # 프롬프트 카테고리 제약
    if category:
        category_constraint = (
            f"\n[카테고리 제약] 사용자가 '{category}'을(를) 명시했습니다. "
            f"반드시 {category} 장소만 추천하세요. "
            f"분식·카페·편의점 등 {category}와 무관한 장소는 절대 포함하지 마세요."
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
[추천 장소 1] 장소명
- 추천 이유: (2~3문장)

[추천 장소 2] 장소명
- 추천 이유: (2~3문장)

[추천 장소 3] 장소명
- 추천 이유: (2~3문장)

[추천 장소 4] 장소명
- 추천 이유: (2~3문장)

[추천 장소 5] 장소명
- 추천 이유: (2~3문장)
"""

    resp = openai_client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "당신은 장소 추천 전문가입니다. 지정된 형식으로만 답변합니다."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
    )
    rec_text = resp.choices[0].message.content

    # 파싱
    pattern = r'\[추천 장소 \d+\]\s*(.+?)\n- 추천 이유:\s*([\s\S]+?)(?=\n\[추천 장소|\Z)'
    matches = re.findall(pattern, rec_text.strip())

    recommendations = []
    seen_names: set[str] = set()

    for name, reason in matches:
        name = name.strip()
        reason = reason.strip()
        if name in seen_names:
            continue
        seen_names.add(name)

        place_dict = find_place_by_name(name, raw_places)
        if not place_dict:
            continue

        address = place_dict.get("road_address_name") or place_dict.get("address_name", "")
        recommendations.append({
            "place_name": name,
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
