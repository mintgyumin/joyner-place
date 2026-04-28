"""
Agent 도구 모음 — JOYNER Place

Agent가 호출할 수 있는 4가지 도구를 구현한다.
각 도구는 독립적으로 실행되며, search_id를 통해 중간 결과를 공유한다.

[도구 목록]
1. search_places_tool          : 카카오 API + RAG로 장소 검색
2. get_place_recommendation_tool: GPT로 추천 이유 생성
3. calculate_midpoint_tool     : 다중 위치 중간지점 계산
4. validate_result_tool        : 추천 결과 품질 검증
"""

import os
import re
import uuid
import json
import numpy as np
import faiss
import requests

from openai import OpenAI
from dotenv import load_dotenv
from rank_bm25 import BM25Okapi

load_dotenv()

KAKAO_API_KEY = os.getenv("KAKAO_API_KEY")
KAKAO_HEADERS = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "").strip())
EMBEDDING_MODEL = "text-embedding-3-small"

# search_places_tool 결과를 임시 보관 (search_id → 데이터)
# Agent 루프 안에서 search_id를 키로 데이터를 전달하기 위해 사용
_search_cache: dict[str, dict] = {}

# 목적 → 카카오 검색어 매핑 (기본값: 음식점)
PURPOSE_KEYWORD_MAP = {
    "회식": "음식점", "식사": "음식점", "밥": "음식점",
    "점심": "음식점", "저녁": "음식점", "밥집": "음식점",
    "브런치": "브런치카페", "카페": "카페", "커피": "카페",
    "디저트": "디저트카페", "술": "술집", "맥주": "술집",
    "와인": "와인바", "이자카야": "이자카야",
    "노래": "노래방", "노래방": "노래방", "코인노래": "코인노래방",
    "볼링": "볼링장", "당구": "당구장", "포켓볼": "당구장",
    "보드게임": "보드게임카페", "방탈출": "방탈출카페",
    "다트": "다트바", "오락": "오락실", "게임": "PC방", "pc": "PC방",
    "영화": "영화관", "전시": "전시관", "미술": "미술관",
    "박물관": "박물관", "공연": "공연장",
    "클라이밍": "클라이밍센터", "볼더링": "클라이밍센터",
    "요가": "요가원", "필라테스": "필라테스", "수영": "수영장",
    "헬스": "헬스장", "사격": "실내사격장",
    "탁구": "탁구장", "배드민턴": "배드민턴장",
    "스터디": "카페", "공부": "스터디카페", "미팅": "카페",
    "회의": "카페", "업무": "카페", "인터뷰": "카페",
    # 데이트/소개팅은 시간대 포함 쿼리에서 음식점으로 처리
    "데이트": "음식점", "소개팅": "음식점",
    "친구": "음식점", "동창": "음식점", "가족": "음식점", "모임": "음식점",
}

# 광역 지역 중심 좌표 (지역명 → (위도, 경도))
# "서울", "강남" 같은 광역 입력 시 해당 좌표와 넓은 반경으로 검색
WIDE_AREA_COORDS: dict[str, tuple[float, float]] = {
    "서울": (37.5665, 126.9780), "서울시": (37.5665, 126.9780), "서울 전체": (37.5665, 126.9780),
    "강남": (37.5172, 127.0473), "강남구": (37.5172, 127.0473), "강남역": (37.4979, 127.0276),
    "홍대": (37.5563, 126.9240), "홍대입구": (37.5563, 126.9240),
    "신촌": (37.5558, 126.9368), "신촌역": (37.5558, 126.9368),
    "마포": (37.5663, 126.9016), "마포구": (37.5663, 126.9016),
    "이태원": (37.5348, 126.9941),
    "종로": (37.5735, 126.9789), "종로구": (37.5735, 126.9789),
    "혜화": (37.5822, 126.9985), "대학로": (37.5822, 126.9985),
    "건대": (37.5404, 127.0699), "건대입구": (37.5404, 127.0699),
    "잠실": (37.5131, 127.1024), "송파": (37.5145, 127.1059),
    "여의도": (37.5219, 126.9245), "영등포": (37.5261, 126.8963),
    "신림": (37.4843, 126.9296), "관악": (37.4784, 126.9516),
    "성북": (37.5894, 127.0167), "노원": (37.6542, 127.0568),
    "서대문": (37.5791, 126.9368), "강동": (37.5301, 127.1239),
    "합정": (37.5497, 126.9147), "상수": (37.5480, 126.9210),
    "성수": (37.5444, 127.0567), "뚝섬": (37.5479, 127.0469),
}

# 목적별 카카오 카테고리 코드 (키워드 검색 보조용)
# FD6: 음식점, CE7: 카페, CT1: 문화시설, MT1: 대형마트, CS2: 편의점, AC5: 스포츠, AT4: 관광명소
PURPOSE_CATEGORY_CODES: dict[str, list[str]] = {
    "회식": ["FD6"], "식사": ["FD6"], "밥": ["FD6"],
    "저녁": ["FD6"], "점심": ["FD6"], "브런치": ["FD6", "CE7"],
    "카페": ["CE7"], "스터디": ["CE7"], "공부": ["CE7"],
    "데이트": ["FD6", "CE7", "CT1"], "소개팅": ["FD6", "CE7"],
    "술": ["FD6"], "맥주": ["FD6"], "와인": ["FD6"],
    "쇼핑": ["MT1", "CS2"], "오락": ["AC5", "AT4"],
    "친구": ["FD6", "CE7"], "모임": ["FD6", "CE7"],
}

# 목적별 허용 카테고리 (필터링용)
PURPOSE_ALLOWED_CATEGORIES = {
    "회식": ["음식점", "한식", "일식", "중식", "양식", "고기", "구이", "찜", "탕", "냉면", "국밥", "분식", "이자카야", "술집"],
    "식사": ["음식점", "한식", "일식", "중식", "양식", "고기", "구이", "찜", "탕", "냉면", "국밥", "분식", "브런치"],
    "스터디": ["카페", "스터디카페", "북카페", "도서관"],
    "데이트": ["음식점", "카페", "한식", "일식", "중식", "양식", "고기", "구이", "브런치", "이탈리안", "레스토랑"],
    "소개팅": ["음식점", "카페", "한식", "일식", "중식", "양식", "레스토랑", "브런치"],
    "친구": ["음식점", "카페", "한식", "일식", "중식", "양식", "고기", "분식", "술집", "이자카야"],
    "모임": ["음식점", "카페", "한식", "일식", "중식", "양식", "고기"],
}


# ─────────────────────────────────────────
# 카카오 API 헬퍼 (내부 함수)
# ─────────────────────────────────────────

def _get_coords(address: str) -> tuple[float, float] | None:
    """지역명/주소 → (위도, 경도). 실패 시 None."""
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    resp = requests.get(url, headers=KAKAO_HEADERS, params={"query": address, "size": 1})
    resp.raise_for_status()
    docs = resp.json().get("documents", [])
    if not docs:
        return None
    return (float(docs[0]["y"]), float(docs[0]["x"]))  # (위도, 경도)


def _get_address_from_coords(lat: float, lng: float) -> str:
    """좌표 → 사람이 읽기 좋은 주소 문자열."""
    url = "https://dapi.kakao.com/v2/local/geo/coord2address.json"
    try:
        resp = requests.get(url, headers=KAKAO_HEADERS, params={"x": lng, "y": lat})
        resp.raise_for_status()
        docs = resp.json().get("documents", [])
        if docs:
            addr = docs[0].get("road_address") or docs[0].get("address")
            if addr:
                return f"{addr.get('region_1depth_name','')} {addr.get('region_2depth_name','')} {addr.get('region_3depth_name','')}".strip()
    except Exception:
        pass
    return "알 수 없는 위치"


def _search_kakao_places(query: str, x: float, y: float, radius: int = 2000) -> list[dict]:
    """카카오 키워드 검색 (최대 3페이지 × 15개)."""
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    results = []
    for page in range(1, 4):
        params = {"query": query, "x": x, "y": y, "radius": radius,
                  "size": 15, "sort": "distance", "page": page}
        resp = requests.get(url, headers=KAKAO_HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()
        results.extend(data.get("documents", []))
        if data.get("meta", {}).get("is_end", True):
            break
    return results


def _search_kakao_by_category(category_code: str, x: float, y: float, radius: int = 2000) -> list[dict]:
    """카카오 카테고리 코드 검색 (최대 3페이지 × 15개)."""
    url = "https://dapi.kakao.com/v2/local/search/category.json"
    results = []
    for page in range(1, 4):
        params = {
            "category_group_code": category_code,
            "x": x, "y": y, "radius": radius,
            "size": 15, "sort": "distance", "page": page,
        }
        resp = requests.get(url, headers=KAKAO_HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()
        results.extend(data.get("documents", []))
        if data.get("meta", {}).get("is_end", True):
            break
    return results


# ─────────────────────────────────────────
# RAG 헬퍼 (내부 함수)
# ─────────────────────────────────────────

def _build_place_documents(places: list[dict]) -> list[str]:
    """카카오 장소 딕셔너리 → RAG용 텍스트 변환."""
    docs = []
    for p in places:
        address = p.get("road_address_name") or p.get("address_name", "주소 없음")
        docs.append(
            f"장소명: {p.get('place_name', '')} | "
            f"카테고리: {p.get('category_name', '')} | "
            f"주소: {address} | "
            f"거리: {p.get('distance', '?')}m"
        )
    return docs


def _build_faiss_index(documents: list[str]):
    """텍스트 리스트 → FAISS 인덱스 + 임베딩."""
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=documents)
    embeddings = np.array([e.embedding for e in resp.data], dtype=np.float32)
    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(embeddings)
    return index, embeddings, documents


def _build_bm25(documents: list[str]) -> BM25Okapi:
    return BM25Okapi([doc.split() for doc in documents])


def _hybrid_search(
    query: str, index, bm25: BM25Okapi, documents: list[str], top_k: int = 7
) -> list[str]:
    """FAISS 0.7 + BM25 0.3 하이브리드 검색."""
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=[query])
    qv = np.array([resp.data[0].embedding], dtype=np.float32)

    dists, idxs = index.search(qv, len(documents))
    faiss_scores = np.zeros(len(documents))
    for idx, dist in zip(idxs[0], dists[0]):
        faiss_scores[idx] = 1.0 / (1.0 + dist)
    if faiss_scores.max() > 0:
        faiss_scores /= faiss_scores.max()

    bm25_scores = np.array(bm25.get_scores(query.split()), dtype=np.float32)
    if bm25_scores.max() > 0:
        bm25_scores /= bm25_scores.max()

    combined = 0.7 * faiss_scores + 0.3 * bm25_scores
    top_indices = np.argsort(combined)[::-1][:top_k]
    return [documents[i] for i in top_indices]


def _rerank(user_input: dict, candidates: list[str], top_k: int = 5) -> list[str]:
    """GPT로 후보 재정렬."""
    numbered = "\n".join(f"{i+1}. {doc}" for i, doc in enumerate(candidates))
    prompt = (
        f"사용자 조건: 위치={user_input.get('location')}, 목적={user_input.get('purpose')}, "
        f"시간대={user_input.get('time')}, 인원={user_input.get('people')}명\n\n"
        f"아래 장소들을 조건에 맞는 순서로 재정렬해서 번호만 쉼표로 나열하세요.\n"
        f"예시: 3,1,5,2,4\n\n{numbered}\n\n번호만 쉼표로 나열:"
    )
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=20,
    )
    raw = resp.choices[0].message.content.strip()
    try:
        order = [int(x.strip()) - 1 for x in raw.split(",") if x.strip().isdigit()]
        seen, reranked = set(), []
        for idx in order:
            if 0 <= idx < len(candidates) and idx not in seen:
                reranked.append(candidates[idx])
                seen.add(idx)
        for idx, doc in enumerate(candidates):
            if idx not in seen:
                reranked.append(doc)
        return reranked[:top_k]
    except Exception:
        return candidates[:top_k]


def _generate_tags(places_info: list[dict]) -> list[list[str]]:
    """장소 태그 배치 생성."""
    numbered = "\n".join(
        f"{i+1}. {p.get('name','')} | {p.get('category','')} | {p.get('address','')}"
        for i, p in enumerate(places_info)
    )
    prompt = (
        f"아래 장소 목록에서 각 장소의 특징 태그 3~5개를 생성해주세요.\n"
        f"태그 형식: #해시태그\n"
        f"각 장소를 번호와 함께 태그만 한 줄로 나열하세요.\n\n{numbered}\n\n"
        f"출력 형식:\n1. #태그1 #태그2 #태그3\n2. ..."
    )
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=300,
    )
    result: list[list[str]] = []
    for line in resp.choices[0].message.content.strip().split("\n"):
        line = re.sub(r"^\d+\.\s*", "", line.strip())
        tags = [t.strip() for t in line.split() if t.startswith("#")]
        result.append(tags[:5])
    while len(result) < len(places_info):
        result.append([])
    return result[:len(places_info)]


def _category_leaf(category_name: str) -> str:
    return category_name.strip().split(">")[-1].strip() if category_name else ""


def _find_place_by_doc(doc: str, places: list[dict]) -> dict:
    for p in places:
        if p.get("place_name", "") in doc:
            return p
    return {}


def _find_place_by_name(name: str, places: list[dict]) -> dict:
    for p in places:
        pname = p.get("place_name", "")
        if pname in name or name in pname:
            return p
    return {}


# ─────────────────────────────────────────
# 도구 1: search_places_tool
# ─────────────────────────────────────────

def search_places_tool(
    location: str,
    purpose: str,
    time_slot: str,
    people_count: int,
    lat: float | None = None,
    lng: float | None = None,
) -> dict:
    """
    카카오 API로 장소를 검색하고 RAG(Hybrid Search + Reranking)로 상위 5개를 선정한다.

    Args:
        location    : 검색 기준 위치 이름 (표시용)
        purpose     : 모임 목적
        time_slot   : 시간대
        people_count: 인원수
        lat, lng    : 좌표 (calculate_midpoint_tool 결과 사용 시 전달)

    Returns:
        {"search_id": str, "found_count": int, "places_summary": list}
        search_id를 get_place_recommendation_tool에 전달해야 한다.
    """
    print(f"[search_places_tool] location={location}, purpose={purpose}")

    # 좌표 결정 — 외부에서 전달받은 경우 그대로 사용
    radius = 2000

    if lat is None or lng is None:
        # 광역 지역 체크 (서울, 강남, 홍대 등)
        location_key = location.split()[0]
        wide_coords = WIDE_AREA_COORDS.get(location_key) or WIDE_AREA_COORDS.get(location)
        if wide_coords:
            lat, lng = wide_coords
            radius = 5000
        else:
            geo_query = location_key if len(location.split()) >= 3 else location
            coords = _get_coords(geo_query) or _get_coords(location)
            if not coords:
                return {"success": False, "error": f"'{location}' 위치를 찾을 수 없어요."}
            lat, lng = coords

    # 카카오 검색 키워드 결정
    if len(location.split()) >= 3:
        kakao_query = location  # "길음역 근처 단체석 있는 회식 음식점" 등 상세 쿼리
    else:
        kakao_query = next(
            (v for k, v in PURPOSE_KEYWORD_MAP.items() if k in purpose), "음식점"
        )

    # 키워드 검색
    raw_places = _search_kakao_places(query=kakao_query, x=lng, y=lat, radius=radius)

    # 결과 부족 시 반경 2배 재시도
    if len(raw_places) < 10:
        print(f"[search_places_tool] 결과 부족({len(raw_places)}개) — 반경 {radius*2}m로 재시도")
        raw_places = _search_kakao_places(query=kakao_query, x=lng, y=lat, radius=radius * 2)

    # 카테고리 코드 보조 검색 (중복 제거 후 합산)
    purpose_key = next((k for k in PURPOSE_CATEGORY_CODES if k in purpose), None)
    if purpose_key:
        cat_codes = PURPOSE_CATEGORY_CODES[purpose_key]
        existing_ids = {p.get("id") for p in raw_places}
        for code in cat_codes:
            cat_results = _search_kakao_by_category(code, x=lng, y=lat, radius=radius)
            for p in cat_results:
                if p.get("id") not in existing_ids:
                    raw_places.append(p)
                    existing_ids.add(p.get("id"))

    if not raw_places:
        return {"success": False, "error": "주변에 장소를 찾지 못했어요."}

    print(f"[search_places_tool] 총 {len(raw_places)}개 후보 확보")

    # RAG 파이프라인
    documents = _build_place_documents(raw_places)
    index, _, docs = _build_faiss_index(documents)
    bm25 = _build_bm25(documents)

    user_input = {"location": location, "purpose": purpose,
                  "time": time_slot, "people": people_count}
    query = f"{people_count}인 {purpose} {time_slot} 분위기"

    hybrid_docs = _hybrid_search(query, index, bm25, docs, top_k=10)
    top_docs = _rerank(user_input, hybrid_docs, top_k=7)
    top_place_dicts = [_find_place_by_doc(doc, raw_places) for doc in top_docs]

    # 결과를 캐시에 저장 (get_place_recommendation_tool에서 사용)
    search_id = str(uuid.uuid4())[:8]
    _search_cache[search_id] = {
        "raw_places": raw_places,
        "top_docs": top_docs,
        "top_place_dicts": top_place_dicts,
        "user_input": user_input,
    }

    places_summary = [
        {
            "name": p.get("place_name", ""),
            "category": _category_leaf(p.get("category_name", "")),
            "address": p.get("road_address_name") or p.get("address_name", ""),
        }
        for p in top_place_dicts if p
    ]

    return {
        "success": True,
        "search_id": search_id,
        "found_count": len(places_summary),
        "places_summary": places_summary,
    }


# ─────────────────────────────────────────
# 도구 2: get_place_recommendation_tool
# ─────────────────────────────────────────

def get_place_recommendation_tool(
    search_id: str,
    location: str,
    purpose: str,
    time_slot: str,
    people_count: int,
) -> dict:
    """
    search_places_tool이 찾은 장소에 GPT가 추천 이유를 생성한다.

    Args:
        search_id   : search_places_tool이 반환한 ID
        location    : 위치 (표시용)
        purpose     : 모임 목적
        time_slot   : 시간대
        people_count: 인원수

    Returns:
        {"success": bool, "recommendations": list[dict]}
    """
    print(f"[get_place_recommendation_tool] search_id={search_id}")

    cached = _search_cache.get(search_id)
    if not cached:
        return {"success": False, "error": f"search_id '{search_id}'를 찾을 수 없어요. 먼저 search_places_tool을 실행하세요."}

    top_docs = cached["top_docs"]
    top_place_dicts = cached["top_place_dicts"]
    raw_places = cached["raw_places"]
    user_input = cached.get("user_input", {
        "location": location, "purpose": purpose,
        "time": time_slot, "people": people_count,
    })

    # 목적에 맞는 허용 카테고리로 후보 필터링
    allowed_cats = None
    for key, cats in PURPOSE_ALLOWED_CATEGORIES.items():
        if key in purpose:
            allowed_cats = cats
            break

    if allowed_cats:
        filtered_dicts, filtered_docs = [], []
        for doc, p in zip(top_docs, top_place_dicts):
            if not p:
                continue
            cat = _category_leaf(p.get("category_name", ""))
            if any(a in cat or cat in a for a in allowed_cats):
                filtered_dicts.append(p)
                filtered_docs.append(doc)
        # 필터링 후 결과가 있으면 적용, 없으면 원본 유지
        if filtered_dicts:
            top_place_dicts = filtered_dicts
            top_docs = filtered_docs

    category_constraint = ""
    if allowed_cats:
        excluded = "카페·커피숍" if "카페" not in allowed_cats else ""
        category_constraint = (
            f"\n[카테고리 제약] 목적이 '{purpose}'이므로 반드시 "
            f"{', '.join(allowed_cats[:6])} 카테고리 장소만 추천하세요."
            + (f" {excluded}은 절대 추천하지 마세요." if excluded else "")
        )

    # GPT 추천 이유 생성
    places_text = "\n".join(f"{i+1}. {doc}" for i, doc in enumerate(top_docs))
    n = len(top_docs)
    prompt = f"""당신은 친절한 장소 추천 AI입니다.
반드시 아래 후보 장소 목록에서만 선택하여 최대 {n}곳을 추천하고, 각각의 추천 이유를 설명해주세요.
후보에 없는 장소를 만들거나 (대체장소없음) 같은 임의 항목을 추가하지 마세요.
후보가 {n}개뿐이라면 {n}개만 추천하면 됩니다.
{category_constraint}

[사용자 조건]
- 위치: {user_input.get('location', location)}
- 모임 목적: {user_input.get('purpose', purpose)}
- 시간대: {user_input.get('time', time_slot)}
- 인원수: {user_input.get('people', people_count)}명

[후보 장소]
{places_text}

[출력 형식 - 반드시 아래 형식으로 작성]
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
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "당신은 장소 추천 전문가입니다. 지정된 형식으로만 답변합니다."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
    )
    rec_text = resp.choices[0].message.content

    # 파싱
    pattern = r'\[추천 장소 (\d+)\]\s*(.+?)\n- 추천 이유:\s*([\s\S]+?)(?=\n\[추천 장소|\Z)'
    matches = re.findall(pattern, rec_text.strip())
    parsed = [{"num": n, "name": name.strip(), "reason": reason.strip()} for n, name, reason in matches]

    # PlaceResult 조립 (중복 제거 + 가짜 장소 필터)
    recommendations = []
    seen_names: set[str] = set()

    for i, card in enumerate(parsed):
        if card["name"] in seen_names:
            continue
        seen_names.add(card["name"])

        # 반드시 이름으로 매칭 — GPT가 순서를 바꾸기 때문에
        # top_place_dicts[i] (인덱스 기반)를 쓰면 URL/좌표가 뒤섞임
        place_dict = _find_place_by_name(card["name"], raw_places)
        if not place_dict:
            # 이름 매칭 실패 시 인덱스로 폴백 (최후 수단)
            place_dict = top_place_dicts[i] if i < len(top_place_dicts) else {}
        if not place_dict:
            continue  # 카카오 API에 없는 가짜 장소 → 제외

        address = place_dict.get("road_address_name") or place_dict.get("address_name", "")
        recommendations.append({
            "place_name": card["name"],
            "category": _category_leaf(place_dict.get("category_name", "")),
            "address": address,
            "distance": place_dict.get("distance", ""),
            "place_url": place_dict.get("place_url", ""),
            "reason": card["reason"],
            "tags": [],
            "lat": float(place_dict["y"]) if place_dict.get("y") else None,
            "lng": float(place_dict["x"]) if place_dict.get("x") else None,
        })

    # 태그 생성
    if recommendations:
        tags_batch = _generate_tags([
            {"name": r["place_name"], "category": r["category"], "address": r["address"]}
            for r in recommendations
        ])
        for rec, tags in zip(recommendations, tags_batch):
            rec["tags"] = tags

    return {"success": True, "recommendations": recommendations}


# ─────────────────────────────────────────
# 도구 3: calculate_midpoint_tool
# ─────────────────────────────────────────

def calculate_midpoint_tool(locations: list[str]) -> dict:
    """
    여러 위치의 중간지점을 계산한다.

    Args:
        locations: 위치 이름 리스트 (예: ["강남역", "홍대입구"])

    Returns:
        {"success": bool, "lat": float, "lng": float, "address": str, "participant_coords": list}
    """
    print(f"[calculate_midpoint_tool] locations={locations}")

    coords_list = []
    participant_coords = []

    for loc in locations:
        coords = _get_coords(loc.strip())
        if coords:
            coords_list.append(coords)
            participant_coords.append({"lat": coords[0], "lng": coords[1], "label": loc})

    if len(coords_list) < 2:
        return {"success": False, "error": "유효한 위치가 2개 이상 필요해요."}

    # 무게중심(단순 평균)
    avg_lat = sum(c[0] for c in coords_list) / len(coords_list)
    avg_lng = sum(c[1] for c in coords_list) / len(coords_list)
    address = _get_address_from_coords(avg_lat, avg_lng)

    return {
        "success": True,
        "lat": round(avg_lat, 6),
        "lng": round(avg_lng, 6),
        "address": address,
        "participant_coords": participant_coords,
    }


# ─────────────────────────────────────────
# 도구 4: validate_result_tool
# ─────────────────────────────────────────

def validate_result_tool(results: list[dict]) -> dict:
    """
    추천 결과의 품질을 검증한다.

    Args:
        results: get_place_recommendation_tool이 반환한 recommendations 리스트

    Returns:
        {"passed": bool, "issues": list, 각 규칙 pass/fail ...}
    """
    print(f"[validate_result_tool] {len(results)}개 결과 검증")

    checks = {}
    issues = []

    # 규칙 1: 개수 (1~10개)
    n = len(results)
    checks["result_count_ok"] = 1 <= n <= 10
    if not checks["result_count_ok"]:
        issues.append(f"추천 개수 이상: {n}개 (1~10개여야 함)")

    # 규칙 2: 중복 없음
    names = [r.get("place_name", "") for r in results]
    checks["no_duplicate"] = len(names) == len(set(names))
    if not checks["no_duplicate"]:
        issues.append("중복 장소 포함")

    # 규칙 3: 모든 장소에 주소
    checks["all_have_address"] = all(bool(r.get("address", "").strip()) for r in results)
    if not checks["all_have_address"]:
        issues.append("주소 없는 장소 포함")

    # 규칙 4: 모든 장소에 카카오맵 URL
    checks["all_have_url"] = all(bool(r.get("place_url", "").strip()) for r in results)
    if not checks["all_have_url"]:
        issues.append("카카오맵 URL 없는 장소 포함")

    # 규칙 5: 모든 장소에 추천 이유
    checks["all_have_reason"] = all(bool(r.get("reason", "").strip()) for r in results)
    if not checks["all_have_reason"]:
        issues.append("추천 이유 없는 장소 포함")

    passed = all(checks.values())
    return {"passed": passed, "issues": issues, **checks}


# ─────────────────────────────────────────
# OpenAI 함수 호출용 도구 스키마 정의
# ─────────────────────────────────────────
# GPT가 어떤 도구를 어떤 파라미터로 호출할지 판단하는 데 사용된다.

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "calculate_midpoint_tool",
            "description": "여러 위치의 중간지점 좌표를 계산합니다. 다중 위치 모드일 때 반드시 먼저 실행하세요.",
            "parameters": {
                "type": "object",
                "properties": {
                    "locations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "위치 이름 리스트 (예: ['강남역', '홍대입구'])",
                    }
                },
                "required": ["locations"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_places_tool",
            "description": (
                "카카오 API와 RAG로 주변 장소를 검색합니다. "
                "다중 위치라면 calculate_midpoint_tool의 lat, lng를 전달하세요."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "검색 기준 위치 이름 (표시용, 예: '강남역' 또는 '강남구 삼성동')",
                    },
                    "purpose": {"type": "string", "description": "모임 목적 (예: 팀 회식)"},
                    "time_slot": {"type": "string", "description": "시간대 (예: 저녁 (17:00~21:00))"},
                    "people_count": {"type": "integer", "description": "인원수"},
                    "lat": {"type": "number", "description": "위도 (calculate_midpoint_tool 결과)"},
                    "lng": {"type": "number", "description": "경도 (calculate_midpoint_tool 결과)"},
                },
                "required": ["location", "purpose", "time_slot", "people_count"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_place_recommendation_tool",
            "description": "search_places_tool이 찾은 장소에 GPT로 추천 이유를 생성합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_id": {
                        "type": "string",
                        "description": "search_places_tool이 반환한 search_id",
                    },
                    "location": {"type": "string", "description": "위치 이름"},
                    "purpose": {"type": "string", "description": "모임 목적"},
                    "time_slot": {"type": "string", "description": "시간대"},
                    "people_count": {"type": "integer", "description": "인원수"},
                },
                "required": ["search_id", "location", "purpose", "time_slot", "people_count"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_result_tool",
            "description": "추천 결과의 품질을 검증합니다. 항상 get_place_recommendation_tool 직후에 실행하세요.",
            "parameters": {
                "type": "object",
                "properties": {
                    "results": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "get_place_recommendation_tool의 recommendations 배열",
                    }
                },
                "required": ["results"],
            },
        },
    },
]


# ─────────────────────────────────────────
# 도구 실행 디스패처
# ─────────────────────────────────────────

def execute_tool(tool_name: str, args: dict, session_data: dict) -> dict:
    """
    GPT가 선택한 도구를 실행하고 결과를 반환한다.
    session_data에 중간 결과를 저장해 도구 간 데이터를 공유한다.
    """
    if tool_name == "calculate_midpoint_tool":
        result = calculate_midpoint_tool(**args)
        if result.get("success"):
            # 중간지점 정보를 세션에 저장 (최종 응답에 포함)
            session_data["midpoint"] = result.get("address")
            session_data["midpoint_lat"] = result.get("lat")
            session_data["midpoint_lng"] = result.get("lng")
            session_data["participant_coords"] = result.get("participant_coords", [])
        return result

    elif tool_name == "search_places_tool":
        result = search_places_tool(**args)
        if result.get("success"):
            session_data["last_search_id"] = result.get("search_id")
        return result

    elif tool_name == "get_place_recommendation_tool":
        result = get_place_recommendation_tool(**args)
        if result.get("success"):
            session_data["recommendations"] = result.get("recommendations", [])
        return result

    elif tool_name == "validate_result_tool":
        # results 파라미터가 없으면 세션에서 가져옴
        results = args.get("results") or session_data.get("recommendations", [])
        result = validate_result_tool(results)
        session_data["validation"] = result
        return result

    return {"error": f"알 수 없는 도구: {tool_name}"}
