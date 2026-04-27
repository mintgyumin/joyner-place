"""
Multi-Agent 공유 도구 모음 — JOYNER Place

에이전트들이 공통으로 사용하는 카카오 API, RAG 파이프라인 함수를 제공한다.
"""

import os
import re
import uuid
import numpy as np
import faiss
import requests

from openai import OpenAI
from dotenv import load_dotenv
from rank_bm25 import BM25Okapi

load_dotenv()

KAKAO_API_KEY = os.getenv("KAKAO_API_KEY")
KAKAO_HEADERS = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
EMBEDDING_MODEL = "text-embedding-3-small"

PURPOSE_KEYWORD_MAP = {
    "회식": "음식점", "식사": "음식점", "밥": "음식점",
    "점심": "음식점", "저녁": "음식점", "밥집": "음식점",
    "브런치": "브런치카페", "카페": "카페", "커피": "카페",
    "디저트": "디저트카페", "술": "술집", "술자리": "술집", "맥주": "술집",
    "와인": "와인바", "이자카야": "이자카야", "한잔": "술집",
    "노래": "노래방", "노래방": "노래방", "코인노래": "코인노래방",
    "볼링": "볼링장", "당구": "당구장",
    "보드게임": "보드게임카페", "방탈출": "방탈출카페",
    "다트": "다트바", "오락": "오락실", "게임": "PC방", "pc": "PC방",
    "영화": "영화관", "전시": "전시관", "미술": "미술관",
    "스터디": "카페", "공부": "스터디카페", "미팅": "카페",
    "회의": "카페", "업무": "카페",
    "데이트": "음식점", "소개팅": "음식점",
    "친구": "음식점", "동창": "음식점", "가족": "음식점", "모임": "음식점",
    "고깃집": "고기요리", "삼겹살": "삼겹살", "갈비": "갈비",
}

WIDE_AREA_COORDS: dict[str, tuple[float, float]] = {
    "서울": (37.5665, 126.9780), "서울시": (37.5665, 126.9780),
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

PURPOSE_CATEGORY_CODES: dict[str, list[str]] = {
    "회식": ["FD6"], "식사": ["FD6"], "밥": ["FD6"],
    "저녁": ["FD6"], "점심": ["FD6"], "브런치": ["FD6", "CE7"],
    "카페": ["CE7"], "스터디": ["CE7"], "공부": ["CE7"],
    "데이트": ["FD6", "CE7", "CT1"], "소개팅": ["FD6", "CE7"],
    "술": ["FD6"], "술자리": ["FD6"], "맥주": ["FD6"],
    "친구": ["FD6", "CE7"], "모임": ["FD6", "CE7"],
}

PURPOSE_ALLOWED_CATEGORIES = {
    "회식": ["음식점", "한식", "일식", "중식", "양식", "고기", "구이", "찜", "탕", "냉면", "국밥", "이자카야", "술집"],
    "식사": ["음식점", "한식", "일식", "중식", "양식", "고기", "구이", "찜", "탕", "냉면", "국밥", "브런치"],
    "술자리": ["술집", "이자카야", "호프", "바", "포차", "맥줏집", "맥주집", "와인바", "다트바"],
    "스터디": ["카페", "스터디카페", "북카페", "도서관"],
    "카페": ["카페", "스터디카페", "북카페", "디저트", "브런치카페"],
    "데이트": ["음식점", "카페", "한식", "일식", "중식", "양식", "고기", "구이", "브런치", "이탈리안", "레스토랑"],
    "소개팅": ["음식점", "카페", "한식", "일식", "중식", "양식", "레스토랑", "브런치"],
    "친구모임": ["음식점", "카페", "한식", "일식", "중식", "양식", "고기", "분식"],
    "친구": ["음식점", "카페", "한식", "일식", "중식", "양식", "고기", "분식"],
    "모임": ["음식점", "카페", "한식", "일식", "중식", "양식", "고기"],
    "고깃집": ["고기요리", "구이", "삼겹살", "갈비", "고기", "한식", "육류"],
    "삼겹살": ["삼겹살", "고기요리", "구이", "고기", "육류"],
    "갈비": ["갈비", "고기요리", "구이", "고기", "육류"],
}


# ─────────────────────────────────────────
# 카카오 API 헬퍼
# ─────────────────────────────────────────

def get_coords(address: str) -> tuple[float, float] | None:
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    resp = requests.get(url, headers=KAKAO_HEADERS, params={"query": address, "size": 1})
    resp.raise_for_status()
    docs = resp.json().get("documents", [])
    if not docs:
        return None
    return (float(docs[0]["y"]), float(docs[0]["x"]))


def get_address_from_coords(lat: float, lng: float) -> str:
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


def search_kakao_places(query: str, x: float, y: float, radius: int = 2000) -> list[dict]:
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


def search_kakao_by_category(category_code: str, x: float, y: float, radius: int = 2000) -> list[dict]:
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
# RAG 헬퍼
# ─────────────────────────────────────────

def build_place_documents(places: list[dict]) -> list[str]:
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


def build_faiss_index(documents: list[str]):
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=documents)
    embeddings = np.array([e.embedding for e in resp.data], dtype=np.float32)
    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(embeddings)
    return index, embeddings, documents


def build_bm25(documents: list[str]) -> BM25Okapi:
    return BM25Okapi([doc.split() for doc in documents])


def hybrid_search(query: str, index, bm25: BM25Okapi, documents: list[str], top_k: int = 10) -> list[str]:
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


def rerank(user_input: dict, candidates: list[str], top_k: int = 7) -> list[str]:
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


def generate_tags(places_info: list[dict]) -> list[list[str]]:
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


def category_leaf(category_name: str) -> str:
    return category_name.strip().split(">")[-1].strip() if category_name else ""


def find_place_by_doc(doc: str, places: list[dict]) -> dict:
    for p in places:
        if p.get("place_name", "") in doc:
            return p
    return {}


def find_place_by_name(name: str, places: list[dict]) -> dict:
    for p in places:
        pname = p.get("place_name", "")
        if pname in name or name in pname:
            return p
    return {}


# ─────────────────────────────────────────
# 중간지점 계산 (location_agent에서 사용)
# ─────────────────────────────────────────

def calculate_midpoint(locations: list[str]) -> dict:
    coords_list = []
    participant_coords = []

    for loc in locations:
        coords = get_coords(loc.strip())
        if coords:
            coords_list.append(coords)
            participant_coords.append({"lat": coords[0], "lng": coords[1], "label": loc})

    if len(coords_list) < 2:
        return {"success": False, "error": "유효한 위치가 2개 이상 필요해요."}

    avg_lat = sum(c[0] for c in coords_list) / len(coords_list)
    avg_lng = sum(c[1] for c in coords_list) / len(coords_list)
    address = get_address_from_coords(avg_lat, avg_lng)

    return {
        "success": True,
        "lat": round(avg_lat, 6),
        "lng": round(avg_lng, 6),
        "address": address,
        "participant_coords": participant_coords,
    }
