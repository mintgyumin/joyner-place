"""
장소 검색 및 추천 파이프라인 모듈

공개 함수:
- run_recommendation_pipeline() : 전체 파이프라인 실행 → RecommendResponse 반환

내부 함수 (언더스코어로 시작):
- _get_coords()             : 주소/지역명 → 위도·경도
- _calculate_midpoint()     : 좌표 리스트 → 중간지점 좌표
- _get_midpoint_from_locs() : 지역명 리스트 → 중간지점 좌표
- _get_address_from_coords(): 좌표 → 주소 문자열
- _search_places()          : 카카오 키워드 검색
- _search_similar_places()  : FAISS 유사도 검색
- _recommend_places()       : GPT 추천 이유 생성
- _parse_recommendation()   : GPT 출력 파싱
- _category_leaf()          : 카테고리 최말단 추출
- _find_place_dict_by_doc() : 문서 텍스트로 원본 place dict 탐색
"""

import os
import re
import numpy as np
import requests
from openai import OpenAI
from dotenv import load_dotenv

from rank_bm25 import BM25Okapi
from indexing import build_place_documents, build_faiss_index, build_bm25_index
from schemas import PlaceSearchRequest, PlaceResult, RecommendResponse

load_dotenv()

KAKAO_API_KEY = os.getenv("KAKAO_API_KEY")
KAKAO_HEADERS = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "").strip())
EMBEDDING_MODEL = "text-embedding-3-small"

# ─────────────────────────────────────────
# 목적 → 카카오 검색어 매핑 테이블
# ─────────────────────────────────────────

PURPOSE_KEYWORD_MAP = {
    # 식사 / 음료
    "회식":     "음식점",
    "식사":     "음식점",
    "밥":       "음식점",
    "점심":     "음식점",
    "저녁":     "음식점",
    "브런치":   "브런치카페",
    "카페":     "카페",
    "커피":     "카페",
    "디저트":   "디저트카페",
    "술":       "술집",
    "맥주":     "술집",
    "와인":     "와인바",
    "이자카야": "이자카야",
    # 놀이 / 오락
    "노래":     "노래방",
    "노래방":   "노래방",
    "코인노래": "코인노래방",
    "볼링":     "볼링장",
    "당구":     "당구장",
    "포켓볼":   "당구장",
    "보드게임": "보드게임카페",
    "방탈출":   "방탈출카페",
    "다트":     "다트바",
    "오락":     "오락실",
    "게임":     "PC방",
    "pc":       "PC방",
    # 문화 / 취미
    "영화":     "영화관",
    "전시":     "전시관",
    "미술":     "미술관",
    "박물관":   "박물관",
    "공연":     "공연장",
    "클라이밍": "클라이밍센터",
    "볼더링":   "클라이밍센터",
    "요가":     "요가원",
    "필라테스": "필라테스",
    "수영":     "수영장",
    "헬스":     "헬스장",
    "사격":     "실내사격장",
    "탁구":     "탁구장",
    "배드민턴": "배드민턴장",
    # 학습 / 업무
    "스터디":   "카페",
    "공부":     "카페",
    "미팅":     "카페",
    "회의":     "카페",
    "업무":     "카페",
    "인터뷰":   "카페",
    # 관계 / 만남
    "데이트":   "카페",
    "소개팅":   "카페",
    "친구":     "카페",
    "동창":     "음식점",
    "가족":     "음식점",
    "모임":     "카페",
}


# ─────────────────────────────────────────
# 카카오 API 내부 함수
# ─────────────────────────────────────────

def _get_coords(address: str) -> tuple[float, float] | None:
    """주소/지역명을 (위도, 경도) 좌표로 변환한다. 실패하면 None 반환."""
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    params = {"query": address, "size": 1}

    response = requests.get(url, headers=KAKAO_HEADERS, params=params)
    response.raise_for_status()

    documents = response.json().get("documents", [])
    if not documents:
        print(f"[경고] '{address}'의 좌표를 찾을 수 없습니다.")
        return None

    x = float(documents[0]["x"])  # 경도 (longitude)
    y = float(documents[0]["y"])  # 위도  (latitude)
    return (y, x)  # 일반적인 (위도, 경도) 순서


def _calculate_midpoint(coords_list: list[tuple[float, float]]) -> tuple[float, float]:
    """여러 좌표의 무게중심(단순 평균)을 계산한다."""
    avg_lat = sum(c[0] for c in coords_list) / len(coords_list)
    avg_lng = sum(c[1] for c in coords_list) / len(coords_list)
    return (avg_lat, avg_lng)


def _get_midpoint_from_locs(locations: list[str]) -> tuple[float, float] | None:
    """지역명 리스트를 받아 중간지점 좌표를 반환한다. 유효 좌표 2개 미만이면 None."""
    coords_list = []
    for loc in locations:
        coords = _get_coords(loc)
        if coords:
            coords_list.append(coords)
    if len(coords_list) < 2:
        return None
    return _calculate_midpoint(coords_list)


def _get_address_from_coords(lat: float, lng: float) -> str:
    """좌표를 사람이 읽을 수 있는 주소 문자열로 변환한다. 실패 시 '알 수 없는 위치' 반환."""
    url = "https://dapi.kakao.com/v2/local/geo/coord2address.json"
    params = {"x": lng, "y": lat}

    try:
        response = requests.get(url, headers=KAKAO_HEADERS, params=params)
        response.raise_for_status()
        documents = response.json().get("documents", [])
        if not documents:
            return "알 수 없는 위치"

        addr = documents[0].get("road_address") or documents[0].get("address")
        if addr:
            region  = addr.get("region_1depth_name", "")
            region2 = addr.get("region_2depth_name", "")
            region3 = addr.get("region_3depth_name", "")
            return f"{region} {region2} {region3}".strip()
    except Exception as e:
        print(f"[경고] 주소 변환 실패: {e}")

    return "알 수 없는 위치"


def _search_places(query: str, x: float, y: float, radius: int = 1000) -> list[dict]:
    """카카오 키워드 검색으로 주변 장소를 가져온다. (최대 3페이지 × 15개 = 45개)"""
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    results = []
    for page in range(1, 4):  # 1, 2, 3페이지
        params = {
            "query":  query,
            "x":      x,
            "y":      y,
            "radius": radius,
            "size":   15,
            "sort":   "distance",
            "page":   page,
        }
        response = requests.get(url, headers=KAKAO_HEADERS, params=params)
        response.raise_for_status()
        data = response.json()
        docs = data.get("documents", [])
        results.extend(docs)
        if data.get("meta", {}).get("is_end", True):
            break
    return results


# ─────────────────────────────────────────
# RAG 내부 함수
# ─────────────────────────────────────────

def _search_similar_places(
    query: str,
    index,
    documents: list[str],
    top_k: int = 3,
) -> list[str]:
    """
    사용자 쿼리와 가장 유사한 장소를 FAISS로 검색한다.

    [동작 원리]
    1. 쿼리 텍스트를 임베딩 (장소 텍스트와 동일한 모델)
    2. FAISS가 인덱스 내 모든 벡터와 L2 거리를 계산
    3. 거리가 가장 짧은 top_k개 반환
    """
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=[query],
    )
    query_vector = np.array([response.data[0].embedding], dtype=np.float32)

    distances, indices = index.search(query_vector, top_k)
    return [documents[i] for i in indices[0]]


def _bm25_search(
    query: str,
    bm25: BM25Okapi,
    documents: list[str],
    top_k: int = 5,
) -> list[tuple[str, float]]:
    """BM25 키워드 검색으로 상위 문서와 점수를 반환한다."""
    tokenized_query = query.split()
    scores = bm25.get_scores(tokenized_query)
    top_indices = np.argsort(scores)[::-1][:top_k]
    return [(documents[i], float(scores[i])) for i in top_indices]


def _hybrid_search(
    query: str,
    index,
    bm25: BM25Okapi,
    documents: list[str],
    top_k: int = 5,
    faiss_weight: float = 0.7,
    bm25_weight: float = 0.3,
) -> list[str]:
    """
    FAISS 벡터 검색과 BM25 키워드 검색 점수를 결합해 상위 문서를 반환한다.

    두 점수를 0~1로 정규화한 뒤 가중합(faiss 0.7 + bm25 0.3)으로 최종 순위를 결정한다.
    FAISS는 거리 기반(낮을수록 유사)이므로 역수로 변환해 점수화한다.
    """
    # FAISS 검색 — 전체 문서 대상으로 거리 계산
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=[query])
    query_vector = np.array([response.data[0].embedding], dtype=np.float32)
    distances, indices = index.search(query_vector, len(documents))

    # FAISS 점수: 거리 → 유사도 (1 / (1 + d)), 0~1 정규화
    faiss_scores = np.zeros(len(documents))
    for rank, (idx, dist) in enumerate(zip(indices[0], distances[0])):
        faiss_scores[idx] = 1.0 / (1.0 + dist)
    faiss_max = faiss_scores.max()
    if faiss_max > 0:
        faiss_scores /= faiss_max

    # BM25 점수 0~1 정규화
    bm25_raw = bm25.get_scores(query.split())
    bm25_scores = np.array(bm25_raw, dtype=np.float32)
    bm25_max = bm25_scores.max()
    if bm25_max > 0:
        bm25_scores /= bm25_max

    # 가중합으로 최종 점수 계산
    combined = faiss_weight * faiss_scores + bm25_weight * bm25_scores
    top_indices = np.argsort(combined)[::-1][:top_k]
    return [documents[i] for i in top_indices]


def _rerank_results(
    user_input: dict,
    candidates: list[str],
    top_k: int = 5,
) -> list[str]:
    """
    GPT를 사용해 Hybrid Search 후보를 사용자 조건에 맞게 재정렬한다.

    벡터+BM25 점수만으로는 잡기 어려운 맥락(분위기, 인원수, 시간대 적합성)을
    GPT가 판단해 최종 순서를 결정한다.

    Returns:
        재정렬된 문서 텍스트 리스트 (상위 top_k개)
    """
    numbered = "\n".join(f"{i+1}. {doc}" for i, doc in enumerate(candidates))
    prompt = (
        f"사용자 조건: 위치={user_input['location']}, 목적={user_input['purpose']}, "
        f"시간대={user_input['time']}, 인원={user_input['people']}명\n\n"
        f"아래 장소들을 조건에 가장 잘 맞는 순서로 재정렬해서 번호만 쉼표로 나열하세요.\n"
        f"예시: 3,1,5,2,4\n\n"
        f"{numbered}\n\n"
        f"번호만 쉼표로 나열:"
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=20,
    )
    raw = response.choices[0].message.content.strip()
    try:
        order = [int(x.strip()) - 1 for x in raw.split(",") if x.strip().isdigit()]
        # 유효 인덱스만 사용, 누락된 항목은 원래 순서로 보완
        seen = set()
        reranked = []
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
    """
    여러 장소의 특징 태그를 GPT로 한 번에 생성한다.

    개별 호출 대신 배치로 처리해 API 비용을 줄인다.

    Args:
        places_info: [{"name": ..., "category": ..., "address": ...}, ...]

    Returns:
        각 장소에 대한 태그 리스트의 리스트
        예: [["#조용한분위기", "#주차가능"], ["#넓은좌석", "#늦은시간운영"], ...]
    """
    numbered = "\n".join(
        f"{i+1}. {info.get('name', '')} | {info.get('category', '')} | {info.get('address', '')}"
        for i, info in enumerate(places_info)
    )
    prompt = (
        f"아래 장소 목록에서 각 장소의 특징 태그 3~5개를 생성해주세요.\n"
        f"태그 형식: #해시태그 (예: #조용한분위기 #넓은좌석 #주차가능 #늦은시간운영)\n"
        f"각 장소를 번호와 함께 태그만 한 줄로 나열하세요. 설명 없이 태그만 작성하세요.\n\n"
        f"{numbered}\n\n"
        f"출력 형식:\n"
        f"1. #태그1 #태그2 #태그3\n"
        f"2. #태그1 #태그2 #태그3\n"
        f"..."
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=300,
    )
    raw = response.choices[0].message.content.strip()

    result: list[list[str]] = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^\d+\.\s*", "", line)
        tags = [t.strip() for t in line.split() if t.startswith("#")]
        result.append(tags[:5])

    # 파싱 실패 시 빈 리스트로 패딩
    while len(result) < len(places_info):
        result.append([])
    return result[:len(places_info)]


def _recommend_places(user_input: dict, places: list[str]) -> str:
    """
    RAG로 추출된 장소 5개에 대해 GPT가 추천 이유를 자연어로 생성한다.

    Args:
        user_input: {"location": ..., "purpose": ..., "time": ..., "people": ...}
        places    : 상위 5개 장소 텍스트 리스트

    Returns:
        GPT가 생성한 추천 결과 문자열
    """
    places_text = "\n".join(f"{i+1}. {place}" for i, place in enumerate(places))

    n = len(places)
    prompt = f"""당신은 친절한 장소 추천 AI입니다.
반드시 아래 후보 장소 목록에서만 선택하여 최대 {n}곳을 추천하고, 각각의 추천 이유를 설명해주세요.
후보에 없는 장소를 만들거나 (대체장소없음) 같은 임의 항목을 추가하지 마세요.
후보가 {n}개뿐이라면 {n}개만 추천하면 됩니다.

[사용자 조건]
- 위치: {user_input['location']}
- 모임 목적: {user_input['purpose']}
- 시간대: {user_input['time']}
- 인원수: {user_input['people']}명

[후보 장소]
{places_text}

[출력 형식 - 반드시 아래 형식으로 작성]
추천 이유에는 장소의 분위기·특징뿐 아니라 위치(거리, 주소)도 자연스럽게 언급해주세요.

[추천 장소 1] 장소명
- 추천 이유: (2~3문장으로 이 장소가 위 조건에 어울리는 이유 설명. 거리나 주소 정보 포함)

[추천 장소 2] 장소명
- 추천 이유: (2~3문장으로 이 장소가 위 조건에 어울리는 이유 설명. 거리나 주소 정보 포함)

[추천 장소 3] 장소명
- 추천 이유: (2~3문장으로 이 장소가 위 조건에 어울리는 이유 설명. 거리나 주소 정보 포함)

[추천 장소 4] 장소명
- 추천 이유: (2~3문장으로 이 장소가 위 조건에 어울리는 이유 설명. 거리나 주소 정보 포함)

[추천 장소 5] 장소명
- 추천 이유: (2~3문장으로 이 장소가 위 조건에 어울리는 이유 설명. 거리나 주소 정보 포함)
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "당신은 장소 추천 전문가입니다. 항상 지정된 형식으로만 답변합니다."},
            {"role": "user",   "content": prompt},
        ],
        temperature=0.7,
    )
    return response.choices[0].message.content


# ─────────────────────────────────────────
# 파싱 헬퍼
# ─────────────────────────────────────────

def _parse_recommendation(text: str) -> list[dict]:
    """GPT 출력 텍스트에서 장소명과 추천 이유를 추출한다."""
    pattern = r'\[추천 장소 (\d+)\]\s*(.+?)\n- 추천 이유:\s*([\s\S]+?)(?=\n\[추천 장소|\Z)'
    matches = re.findall(pattern, text.strip())
    return [{"num": n, "name": name.strip(), "reason": reason.strip()} for n, name, reason in matches]


def _category_leaf(category_name: str) -> str:
    """'음식점 > 카페 > 커피전문점' 형태에서 마지막 항목만 추출한다."""
    if not category_name:
        return ""
    return category_name.strip().split(">")[-1].strip()


def _find_place_dict_by_doc(doc_text: str, places: list[dict]) -> dict:
    """문서 텍스트에 장소명이 포함된 place dict를 반환한다. 없으면 빈 dict."""
    for p in places:
        if p.get("place_name", "") in doc_text:
            return p
    return {}


def _find_place_dict_by_name(name: str, places: list[dict]) -> dict:
    """GPT가 출력한 장소명으로 원본 place dict를 탐색한다."""
    for p in places:
        pname = p.get("place_name", "")
        if pname in name or name in pname:
            return p
    return {}


# ─────────────────────────────────────────
# 공개 파이프라인
# ─────────────────────────────────────────

def run_recommendation_pipeline(req: PlaceSearchRequest) -> RecommendResponse:
    """
    장소 추천 전체 파이프라인을 실행한다.

    [파이프라인 순서]
    1. 좌표 결정 (단일 위치 or 중간지점 계산)
    2. 카카오 API 장소 검색
    3. 텍스트 문서 변환 (build_place_documents)
    4. Contextual Embedding — GPT로 각 문서에 컨텍스트 접두어 추가
    5. FAISS 인덱스 + BM25 인덱스 생성
    6. Hybrid Search (FAISS 0.7 + BM25 0.3)
    7. GPT Reranking — 조건에 맞게 후보 재정렬
    8. GPT 추천 이유 생성 (_recommend_places)
    9. 결과 파싱 → PlaceResult 리스트 조립

    Args:
        req: PlaceSearchRequest (location, purpose, time_slot, people_count, locations)

    Returns:
        RecommendResponse (places: list[PlaceResult], midpoint: str | None)

    Raises:
        ValueError: 위치 좌표 변환 실패, 또는 주변 장소 없음
    """
    midpoint_address: str | None = None
    midpoint_lat: float | None = None
    midpoint_lng: float | None = None
    participant_coords: list[dict] = []

    # ── STEP 1: 좌표 결정 ───────────────────────────────────────
    if req.locations and len(req.locations) >= 2:
        # 다중 참여자 모드 — 중간지점 계산
        filled = [loc.strip() for loc in req.locations if loc.strip()]
        if len(filled) < 2:
            raise ValueError("참여자 위치를 2개 이상 입력해주세요.")

        # 각 참여자 좌표 수집 (지도 핀 표시용)
        coords_list = []
        for loc in filled:
            coords = _get_coords(loc)
            if coords:
                coords_list.append(coords)
                participant_coords.append({"lat": coords[0], "lng": coords[1], "label": loc})

        if len(coords_list) < 2:
            raise ValueError("유효한 위치가 2개 이상 필요해요. 입력한 위치명을 확인해주세요.")

        midpoint = _calculate_midpoint(coords_list)
        lat, lng = midpoint
        midpoint_lat, midpoint_lng = lat, lng
        midpoint_address = _get_address_from_coords(lat, lng)
        display_location = midpoint_address

    else:
        # 단일 위치 모드
        if not req.location.strip():
            raise ValueError("위치를 입력해주세요.")

        coords = _get_coords(req.location)
        if coords is None:
            raise ValueError(f"'{req.location}' 위치를 찾을 수 없어요. 다른 지역명으로 시도해보세요.")

        lat, lng = coords
        # 단일 모드에서는 입력 위치를 참여자 좌표로 저장
        participant_coords = [{"lat": lat, "lng": lng, "label": req.location}]
        display_location = req.location

    # ── STEP 2: 카카오 장소 검색 ────────────────────────────────
    kakao_query = next(
        (v for k, v in PURPOSE_KEYWORD_MAP.items() if k in req.purpose),
        "카페",
    )
    places = _search_places(query=kakao_query, x=lng, y=lat, radius=1000)

    if not places:
        raise ValueError("주변에 장소를 찾지 못했어요. 반경을 넓히거나 다른 위치를 시도해보세요.")

    # ── STEP 3: 텍스트 문서 변환 ────────────────────────────────
    documents = build_place_documents(places)

    user_input = {
        "location": display_location,
        "purpose":  req.purpose,
        "time":     req.time_slot,
        "people":   req.people_count,
    }

    # ── STEP 4: FAISS + BM25 인덱스 생성 ────────────────────────
    index, _, docs = build_faiss_index(documents)
    bm25 = build_bm25_index(documents)

    # ── STEP 5: Hybrid Search ────────────────────────────────────
    query = f"{req.people_count}인 {req.purpose} {req.time_slot} 분위기"
    hybrid_docs = _hybrid_search(
        query=query,
        index=index,
        bm25=bm25,
        documents=docs,
        top_k=7,
    )

    # ── STEP 7: GPT Reranking ────────────────────────────────────
    print("[Reranking] GPT로 후보 재정렬 중...")
    top_docs = _rerank_results(user_input=user_input, candidates=hybrid_docs, top_k=5)
    top_place_dicts = [_find_place_dict_by_doc(doc, places) for doc in top_docs]

    # ── STEP 8: GPT 추천 이유 생성 ──────────────────────────────
    recommendation_text = _recommend_places(user_input=user_input, places=top_docs)

    # ── STEP 9: 결과 파싱 → PlaceResult 조립 (중복 제거 포함) ──
    parsed_cards = _parse_recommendation(recommendation_text)

    place_results: list[PlaceResult] = []
    seen_names: set[str] = set()

    for i, card in enumerate(parsed_cards):
        # place_name 기준 중복 제거 — 같은 장소가 두 번 나오면 첫 번째만 사용
        if card["name"] in seen_names:
            continue
        seen_names.add(card["name"])

        # GPT가 출력한 장소명으로 원본 카카오 데이터 찾기
        place_dict = (
            top_place_dicts[i]
            if i < len(top_place_dicts)
            else _find_place_dict_by_name(card["name"], places)
        )

        # 카카오 데이터가 없으면 GPT가 만들어낸 가짜 장소 — 건너뜀
        if not place_dict:
            continue

        address = (
            place_dict.get("road_address_name")
            or place_dict.get("address_name")
            or ""
        )
        # 카카오 API는 경도를 "x", 위도를 "y"로 반환 (반직관적이므로 주의)
        place_results.append(PlaceResult(
            place_name=card["name"],
            category=_category_leaf(place_dict.get("category_name", "")),
            address=address,
            distance=place_dict.get("distance", ""),
            place_url=place_dict.get("place_url", ""),
            reason=card["reason"],
            lat=float(place_dict["y"]) if place_dict.get("y") else None,
            lng=float(place_dict["x"]) if place_dict.get("x") else None,
        ))

    # ── STEP 10: 태그 생성 (중복 제거 후 최종 결과 기준) ────────
    print(f"[태그 생성] {len(place_results)}개 장소 태그 생성 중...")
    tags_batch = _generate_tags([
        {"name": pr.place_name, "category": pr.category, "address": pr.address}
        for pr in place_results
    ])
    for pr, tags in zip(place_results, tags_batch):
        pr.tags = tags

    return RecommendResponse(
        places=place_results,
        midpoint=midpoint_address,
        midpoint_lat=midpoint_lat,
        midpoint_lng=midpoint_lng,
        participant_coords=participant_coords,
    )
