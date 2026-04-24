"""
RAG 인덱싱 모듈
- build_place_documents(): 카카오 장소 데이터 → 텍스트 변환
- build_faiss_index()    : 텍스트 → 임베딩 → FAISS 인덱스 생성
- build_bm25_index()     : 텍스트 → BM25 키워드 인덱스 생성

이 모듈은 "데이터 준비" 단계를 담당한다.
실제 검색은 retrieval.py가 수행한다.
"""

import os
import numpy as np
import faiss
from openai import OpenAI
from dotenv import load_dotenv
from rank_bm25 import BM25Okapi

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# text-embedding-3-small: 비용이 저렴하고 성능이 충분한 임베딩 모델
EMBEDDING_MODEL = "text-embedding-3-small"


def build_place_documents(places: list[dict]) -> list[str]:
    """
    카카오 API 검색 결과를 RAG에 쓰기 좋은 텍스트 형식으로 변환한다.

    RAG는 "어떤 텍스트를 넣느냐"가 검색 품질을 결정한다.
    중요한 정보(이름, 카테고리, 주소, 거리)를 한 줄에 담아
    임베딩이 의미를 잘 파악하도록 구성한다.

    Args:
        places: kakao_search API가 반환한 장소 딕셔너리 리스트

    Returns:
        각 장소를 한 줄 텍스트로 표현한 리스트
        예: ["장소명: 스타벅스 강남점 | 카테고리: 음식점 > 카페 | 주소: 서울 강남구 ... | 거리: 42m"]
    """
    documents = []

    for place in places:
        # 도로명 주소가 있으면 우선 사용, 없으면 지번 주소 사용
        address = place.get("road_address_name") or place.get("address_name", "주소 없음")

        text = (
            f"장소명: {place.get('place_name', '')} | "
            f"카테고리: {place.get('category_name', '')} | "
            f"주소: {address} | "
            f"거리: {place.get('distance', '?')}m"
        )
        documents.append(text)

    return documents


def build_bm25_index(documents: list[str]) -> BM25Okapi:
    """
    텍스트 리스트로 BM25 키워드 검색 인덱스를 생성한다.

    BM25는 단어 빈도(TF)와 역문서 빈도(IDF)를 결합한 고전적 키워드 검색 알고리즘이다.
    FAISS 벡터 검색이 의미(semantic)를 잡는다면, BM25는 정확한 키워드 매칭을 보완한다.
    두 점수를 결합하면 키워드+의미 모두 커버하는 Hybrid Search가 된다.

    Args:
        documents: build_place_documents()가 반환한 텍스트 리스트

    Returns:
        BM25Okapi 인덱스 객체
    """
    tokenized = [doc.split() for doc in documents]
    return BM25Okapi(tokenized)


def build_faiss_index(documents: list[str]) -> tuple:
    """
    텍스트 리스트를 임베딩하고 FAISS 인덱스를 생성한다.

    [동작 원리]
    1. OpenAI API로 각 텍스트를 숫자 벡터(임베딩)로 변환
       - text-embedding-3-small은 1536차원 벡터를 생성
    2. FAISS IndexFlatL2 인덱스에 벡터를 추가
       - IndexFlatL2: L2 거리(유클리드 거리)로 유사도 계산
       - 벡터가 가까울수록 = 의미가 비슷한 장소

    Args:
        documents: build_place_documents()가 반환한 텍스트 리스트

    Returns:
        (index, embeddings, documents) 튜플
        - index     : FAISS 검색 인덱스
        - embeddings: numpy 배열 (shape: [문서수, 1536])
        - documents : 원본 텍스트 리스트 (검색 결과 복원용)
    """
    print(f"[임베딩] {len(documents)}개 장소 텍스트를 벡터화 중...")

    # OpenAI API로 모든 문서를 한 번에 임베딩 (배치 처리로 API 호출 최소화)
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=documents,
    )

    # API 응답에서 벡터값만 추출 → numpy float32 배열로 변환 (FAISS 요구사항)
    embeddings = np.array(
        [item.embedding for item in response.data],
        dtype=np.float32,
    )

    dimension = embeddings.shape[1]  # text-embedding-3-small = 1536

    # FAISS 인덱스 생성 및 벡터 추가
    index = faiss.IndexFlatL2(dimension)  # L2 거리 기반 인덱스
    index.add(embeddings)                 # 모든 장소 벡터를 인덱스에 등록

    print(f"[임베딩 완료] 인덱스에 {index.ntotal}개 벡터 저장됨 (차원: {dimension})")
    return index, embeddings, documents
