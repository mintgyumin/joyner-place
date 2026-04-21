"""
Streamlit UI - JOYNER Place (프론트엔드)

변경 사항 (기존 app.py 대비):
- 백엔드 모듈을 직접 import하지 않음
- 모든 데이터 조작은 FastAPI 백엔드에 HTTP 요청으로 처리
- 인증: streamlit-authenticator → JWT (session_state["token"])
- 백엔드 URL: BACKEND_URL 환경변수 (기본 http://localhost:8000)
"""

import os
# from datetime import date as date_type, timedelta  # 약속 기능 주석처리 시 불필요
import requests as req_lib
import streamlit as st
from urllib.parse import quote
from dotenv import load_dotenv

load_dotenv()

# 백엔드 FastAPI 서버 주소
# docker-compose 환경에서는 서비스 이름으로 접근 (예: http://backend:8000)
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# ─────────────────────────────────────────
# 페이지 기본 설정
# ─────────────────────────────────────────
st.set_page_config(
    page_title="JOYNER Place",
    page_icon="📍",
    layout="centered",
)

# ─────────────────────────────────────────
# CSS 주입 - JOYNER 디자인 시스템
# ─────────────────────────────────────────
st.markdown("""
<style>
    /* 레이아웃 */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 680px;
    }

    /* 헤더 */
    .joyner-header {
        text-align: center;
        padding: 1.5rem 0 1rem 0;
    }
    .joyner-header h1 {
        font-size: 2rem;
        font-weight: 700;
        color: #1A1A2E;
        margin: 0 0 0.3rem 0;
        letter-spacing: -0.5px;
    }
    .joyner-header p {
        font-size: 0.95rem;
        color: #6B6B8D;
        margin: 0;
    }
    .jd { border: none; border-top: 1.5px solid #E8E6FF; margin: 1.2rem 0; }

    /* 섹션 레이블 */
    .sec-label {
        font-size: 0.75rem;
        font-weight: 700;
        color: #7C6FF7;
        letter-spacing: 1.2px;
        text-transform: uppercase;
        margin-bottom: 0.8rem;
    }

    /* 라디오 - 탭 스타일 */
    div[data-testid="stRadio"] > label { display: none; }
    div[data-testid="stRadio"] > div {
        gap: 0.6rem;
        flex-direction: row !important;
    }
    div[data-testid="stRadio"] > div > label {
        background: #FFFFFF;
        border: 1.5px solid #E8E6FF !important;
        border-radius: 10px;
        padding: 0.45rem 1.1rem;
        color: #6B6B8D !important;
        font-size: 0.9rem;
        font-weight: 500;
        cursor: pointer;
    }
    div[data-testid="stRadio"] > div > label:has(input:checked) {
        border-color: #7C6FF7 !important;
        color: #7C6FF7 !important;
        background: #F0EEFF;
        font-weight: 600;
    }
    div[data-testid="stRadio"] p { color: inherit !important; }

    /* 텍스트 인풋 */
    div[data-testid="stTextInput"] input {
        border: 1.5px solid #E8E6FF !important;
        border-radius: 10px !important;
        background: #FFFFFF !important;
        color: #1A1A2E !important;
    }
    div[data-testid="stTextInput"] input:focus {
        border-color: #7C6FF7 !important;
        box-shadow: 0 0 0 2px rgba(124,111,247,0.15) !important;
    }

    /* 셀렉트박스 */
    div[data-testid="stSelectbox"] > div > div {
        border: 1.5px solid #E8E6FF !important;
        border-radius: 10px !important;
        background: #FFFFFF !important;
        color: #1A1A2E !important;
    }

    /* 넘버 인풋 */
    div[data-testid="stNumberInput"] input {
        border: 1.5px solid #E8E6FF !important;
        border-radius: 10px !important;
        background: #FFFFFF !important;
        color: #1A1A2E !important;
    }
    div[data-testid="stNumberInput"] > div {
        border: 1.5px solid #E8E6FF !important;
        border-radius: 10px !important;
        background: #FFFFFF !important;
    }
    div[data-testid="stNumberInput"] button {
        background: #FFFFFF !important;
        color: #7C6FF7 !important;
        border: none !important;
    }

    /* 메인 버튼 — primary + 일반 stButton 전부 보라색 통일 */
    button[kind="primary"],
    div.stButton > button,
    div.stFormSubmitButton > button {
        background: #7C6FF7 !important;
        background-color: #7C6FF7 !important;
        color: #FFFFFF !important;
        border: none !important;
        border-color: #7C6FF7 !important;
        border-radius: 12px !important;
        font-weight: 600 !important;
        transition: background 0.15s !important;
    }
    button[kind="primary"]:hover,
    div.stButton > button:hover,
    div.stFormSubmitButton > button:hover {
        background: #6358E8 !important;
        background-color: #6358E8 !important;
        border-color: #6358E8 !important;
    }

    /* 링크 버튼 */
    a[data-testid="stLinkButton"] {
        border: 1.5px solid #7C6FF7 !important;
        color: #7C6FF7 !important;
        border-radius: 10px !important;
        background: #FFFFFF !important;
        font-size: 0.88rem !important;
        font-weight: 500 !important;
    }
    a[data-testid="stLinkButton"]:hover { background: #F0EEFF !important; }

    /* 중간지점 뱃지 */
    .midpoint-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        background: #F0EEFF;
        color: #7C6FF7;
        border: 1.5px solid #D4CFFF;
        border-radius: 20px;
        padding: 0.35rem 0.9rem;
        font-size: 0.88rem;
        font-weight: 600;
        margin: 0.3rem 0 1rem 0;
    }

    /* 결과 카드 */
    .result-card {
        background: #FFFFFF;
        border: 1.5px solid #E8E6FF;
        border-radius: 16px;
        padding: 1.4rem 1.5rem 1rem 1.5rem;
        margin-bottom: 0.5rem;
        transition: box-shadow 0.2s;
    }
    .result-card:hover { box-shadow: 0 4px 18px rgba(124,111,247,0.1); }
    .place-badge {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 26px;
        height: 26px;
        background: #7C6FF7;
        color: #FFFFFF;
        border-radius: 50%;
        font-size: 0.78rem;
        font-weight: 700;
        margin-bottom: 0.6rem;
    }
    .place-name {
        font-size: 1.05rem;
        font-weight: 700;
        color: #1A1A2E;
        margin: 0.2rem 0 0.5rem 0;
    }
    .place-reason {
        font-size: 0.88rem;
        color: #6B6B8D;
        line-height: 1.65;
        margin-bottom: 0.5rem;
    }
    .result-title {
        font-size: 1.1rem;
        font-weight: 700;
        color: #1A1A2E;
        margin: 1.2rem 0 0.8rem 0;
    }
    .card-header {
        display: flex;
        align-items: center;
        gap: 0.6rem;
        margin-bottom: 0.5rem;
    }
    .cat-badge {
        background: #F0EEFF;
        color: #7C6FF7;
        border: 1px solid #D4CFFF;
        border-radius: 20px;
        padding: 0.15rem 0.65rem;
        font-size: 0.75rem;
        font-weight: 600;
        white-space: nowrap;
    }
    .card-meta {
        font-size: 0.82rem;
        color: #8F8FB0;
        margin-bottom: 0.7rem;
        display: flex;
        gap: 0.8rem;
        flex-wrap: wrap;
    }
    .card-divider {
        border: none;
        border-top: 1px solid #EEEEFF;
        margin: 0.6rem 0;
    }
    [data-testid="stAlert"] { border-radius: 10px !important; }

    /* 로그인 폼 */
    .login-wrap {
        max-width: 400px;
        margin: 0 auto;
        padding: 0.5rem 0 2rem 0;
    }

    /* st.tabs 스타일 */
    div[data-testid="stTabs"] button[role="tab"] {
        font-size: 0.92rem;
        font-weight: 600;
        color: #6B6B8D;
        border-bottom: 2px solid transparent;
    }
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
        color: #7C6FF7;
        border-bottom-color: #7C6FF7;
    }

    /* 유저 인사말 바 */
    .user-bar {
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 0.8rem;
        padding: 0.3rem 0 0.8rem 0;
        font-size: 0.88rem;
        color: #6B6B8D;
        font-weight: 500;
    }
    .user-name { color: #1A1A2E; font-weight: 600; }

    /* 약속 코드 카드 */
    .apt-code-card {
        background: linear-gradient(135deg, #7C6FF7, #9B8FF9);
        border-radius: 16px;
        padding: 1.6rem 1.5rem;
        text-align: center;
        margin: 0.8rem 0 0.4rem 0;
        color: #FFFFFF;
    }
    .apt-code-title  { font-size: 0.9rem; font-weight: 600; opacity: 0.9; margin-bottom: 0.25rem; }
    .apt-code-label  { font-size: 1rem; font-weight: 600; margin-bottom: 0.8rem; }
    .apt-code-value  { font-size: 2.4rem; font-weight: 800; letter-spacing: 0.35rem; margin-bottom: 0.45rem; }
    .apt-code-hint   { font-size: 0.82rem; opacity: 0.8; }

    /* 약속 목록 카드 */
    .apt-card {
        background: #FFFFFF;
        border: 1.5px solid #E8E6FF;
        border-radius: 14px;
        padding: 1.1rem 1.3rem;
        margin-bottom: 0.6rem;
    }
    .apt-card-title { font-size: 1rem; font-weight: 700; color: #1A1A2E; margin-bottom: 0.25rem; }
    .apt-card-place { font-size: 0.85rem; color: #6B6B8D; margin-bottom: 0.5rem; }
    .apt-card-meta  { font-size: 0.8rem; color: #8F8FB0; }

    /* 상태 뱃지 */
    .badge        { display: inline-block; padding: 0.18rem 0.6rem; border-radius: 20px; font-size: 0.78rem; font-weight: 600; }
    .badge-green  { background: #E6F9F0; color: #1A8A5A; border: 1px solid #B8EDD6; }
    .badge-yellow { background: #FFF8E6; color: #A07800; border: 1px solid #FFE8A3; }
    .badge-red    { background: #FFEDED; color: #C0392B; border: 1px solid #F5B7B1; }
    .badge-purple { background: #F0EEFF; color: #7C6FF7; border: 1px solid #D4CFFF; }

    /* 참여자 행 */
    .member-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.35rem 0;
        font-size: 0.88rem;
        color: #1A1A2E;
        border-bottom: 1px solid #F3F2FF;
    }
    .member-row:last-child { border-bottom: none; }

    /* 즐겨찾기 카드 */
    .fav-card {
        background: #FFFFFF;
        border: 1.5px solid #E8E6FF;
        border-radius: 16px;
        padding: 1.2rem 1.4rem 0.9rem 1.4rem;
        margin-bottom: 0.6rem;
    }
    .fav-card-header {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin-bottom: 0.3rem;
    }
    .fav-card-name    { font-size: 1rem; font-weight: 700; color: #1A1A2E; }
    .fav-card-address { font-size: 0.84rem; color: #6B6B8D; margin-bottom: 0.25rem; }
    .fav-card-date    { font-size: 0.78rem; color: #8F8FB0; margin-bottom: 0.6rem; }

    /* 약속 상세 카드 */
    .apt-detail-card {
        background: #FFFFFF;
        border: 1.5px solid #E8E6FF;
        border-radius: 16px;
        padding: 1.4rem 1.5rem;
        margin-bottom: 1rem;
    }
    .apt-detail-title   { font-size: 1.15rem; font-weight: 700; color: #1A1A2E; margin-bottom: 0.3rem; }
    .apt-detail-place   { font-size: 0.95rem; font-weight: 600; color: #7C6FF7; margin-bottom: 0.2rem; }
    .apt-detail-address { font-size: 0.85rem; color: #6B6B8D; margin-bottom: 0.8rem; }
    .apt-detail-datetime{ font-size: 0.9rem; color: #7C6FF7; font-weight: 600; margin: 0.3rem 0; }
    .apt-detail-by      { font-size: 0.8rem; color: #8F8FB0; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────
# 헤더 (항상 표시)
# ─────────────────────────────────────────
st.markdown("""
<div class="joyner-header">
    <h1><span style="color:#7C6FF7">JOYNER</span> place</h1>
    <p>AI가 찾아주는 우리의 중간지점</p>
</div>
<hr class="jd">
""", unsafe_allow_html=True)


# ─────────────────────────────────────────
# API 헬퍼 함수
# ─────────────────────────────────────────

def _auth_headers() -> dict:
    """현재 로그인한 유저의 JWT 토큰을 Authorization 헤더 형태로 반환한다."""
    token = st.session_state.get("token", "")
    return {"Authorization": f"Bearer {token}"}


def _api_call(method: str, path: str, data: dict = None, timeout: int = 60) -> dict:
    """
    백엔드 FastAPI에 HTTP 요청을 보내고 응답 JSON을 반환한다.

    Args:
        method  : HTTP 메서드 ("get", "post", "put", "delete")
        path    : API 경로 (예: "/auth/login", "/recommend")
        data    : 요청 바디 (JSON으로 전송)
        timeout : 요청 타임아웃 (초). 추천 API는 90초로 호출

    Returns:
        응답 JSON dict

    Raises:
        ValueError: API 오류 (detail 메시지 포함)
        ConnectionError: 백엔드 서버에 연결할 수 없을 때
    """
    url = f"{BACKEND_URL}{path}"
    fn = getattr(req_lib, method)  # req_lib.get / req_lib.post / ...

    try:
        response = fn(url, json=data, headers=_auth_headers(), timeout=timeout)

        # 401: 토큰 만료 → 자동 로그아웃
        if response.status_code == 401:
            for key in ["token", "username", "name"]:
                st.session_state.pop(key, None)
            st.error("로그인이 만료됐어요. 다시 로그인해주세요.")
            st.rerun()

        response.raise_for_status()
        return response.json()

    except req_lib.exceptions.HTTPError as e:
        # FastAPI가 반환하는 {"detail": "..."} 메시지 추출
        try:
            detail = e.response.json().get("detail", str(e))
        except Exception:
            detail = str(e)
        raise ValueError(detail)

    except req_lib.exceptions.ConnectionError:
        raise ConnectionError(f"백엔드 서버({BACKEND_URL})에 연결할 수 없어요.")

    except req_lib.exceptions.Timeout:
        raise ValueError("요청 시간이 초과됐어요. 잠시 후 다시 시도해주세요.")


def _refresh_favorites():
    """
    백엔드에서 즐겨찾기 목록을 불러와 session_state에 저장한다.
    페이지 렌더링 시 한 번만 호출해 O(1) 즐겨찾기 확인을 가능하게 한다.
    """
    try:
        favs = _api_call("get", "/favorites")
        st.session_state["favorites"] = favs
        # 장소명 집합 — _is_favorite()에서 O(1) 조회
        st.session_state["favorites_names"] = {f["place_name"] for f in favs}
    except Exception:
        st.session_state.setdefault("favorites", [])
        st.session_state.setdefault("favorites_names", set())


def _is_favorite(place_name: str) -> bool:
    """해당 장소가 즐겨찾기에 저장되어 있으면 True를 반환한다."""
    return place_name in st.session_state.get("favorites_names", set())


# ─────────────────────────────────────────
# 인증 상태 확인
# ─────────────────────────────────────────

is_logged_in = "token" in st.session_state

# ── 미로그인: 로그인 / 회원가입 탭 표시 ──
if not is_logged_in:
    _, col, _ = st.columns([1, 3, 1])

    with col:
        if "auth_view" not in st.session_state:
            st.session_state.auth_view = "login"

        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if st.button("로그인", use_container_width=True,
                         type="primary" if st.session_state.auth_view == "login" else "secondary"):
                st.session_state.auth_view = "login"
                st.rerun()
        with btn_col2:
            if st.button("회원가입", use_container_width=True,
                         type="primary" if st.session_state.auth_view == "signup" else "secondary"):
                st.session_state.auth_view = "signup"
                st.rerun()

        st.markdown('<hr class="jd">', unsafe_allow_html=True)

        # ── 로그인 뷰 ─────────────────────────
        if st.session_state.auth_view == "login":
            with st.form("login_form"):
                login_id = st.text_input("아이디", placeholder="영문/숫자")
                login_pw = st.text_input("비밀번호", type="password")
                login_submitted = st.form_submit_button("로그인", use_container_width=True, type="primary")

            if login_submitted:
                if not login_id or not login_pw:
                    st.error("아이디와 비밀번호를 모두 입력해주세요.")
                else:
                    try:
                        result = _api_call("post", "/auth/login", {
                            "username": login_id,
                            "password": login_pw,
                        })
                        st.session_state["token"]    = result["access_token"]
                        st.session_state["username"] = result["username"]
                        st.session_state["name"]     = result["name"]
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
                    except ConnectionError as e:
                        st.error(str(e))

        # ── 회원가입 뷰 ───────────────────────
        else:
            with st.form("signup_form", clear_on_submit=True):
                su_name     = st.text_input("이름",          placeholder="홍길동")
                su_username = st.text_input("아이디",        placeholder="영문/숫자")
                su_email    = st.text_input("이메일",        placeholder="you@example.com")
                su_pw       = st.text_input("비밀번호",      type="password")
                su_pw2      = st.text_input("비밀번호 확인", type="password")
                submitted   = st.form_submit_button("회원가입", use_container_width=True, type="primary")

            if submitted:
                if not all([su_name, su_username, su_email, su_pw, su_pw2]):
                    st.error("모든 항목을 입력해주세요.")
                elif su_pw != su_pw2:
                    st.error("비밀번호가 일치하지 않아요.")
                else:
                    try:
                        _api_call("post", "/auth/register", {
                            "username": su_username,
                            "name":     su_name,
                            "email":    su_email,
                            "password": su_pw,
                        })
                        st.markdown(
                            '<div style="background:#F0EEFF;color:#7C6FF7;border:1.5px solid #D4CFFF;'
                            'border-radius:10px;padding:0.7rem 1rem;font-weight:600;margin-top:0.5rem;">'
                            '✅ 가입 완료! 로그인해주세요.</div>',
                            unsafe_allow_html=True,
                        )
                    except ValueError as e:
                        st.error(str(e))
                    except ConnectionError as e:
                        st.error(str(e))

    st.stop()  # 로그인 안 하면 아래 내용 표시 안 함


# ── 로그인 완료: 즐겨찾기 로드 + 인사말 + 로그아웃 ──
_refresh_favorites()  # 페이지 렌더 시마다 최신 목록 동기화

current_user = st.session_state.get("username", "")
user_name    = st.session_state.get("name", "")

col_greeting, col_logout = st.columns([5, 1])
with col_greeting:
    st.markdown(
        f'<div class="user-bar">안녕하세요, <span class="user-name">{user_name}님</span> 👋</div>',
        unsafe_allow_html=True,
    )
with col_logout:
    if st.button("로그아웃"):
        # JWT와 사용자 정보를 session_state에서 제거
        for key in ["token", "username", "name", "favorites", "favorites_names", "rec"]:
            st.session_state.pop(key, None)
        st.rerun()


# ─────────────────────────────────────────
# 사이드바 네비게이션
# ─────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📍 JOYNER place")
    st.markdown("---")
    page = st.radio(
        "메뉴",
        ["🏠 장소 추천", "❤️ 즐겨찾기"],
        # ["🏠 장소 추천", "❤️ 즐겨찾기", "🔗 약속 참여하기", "📋 내 약속 목록"],  # 약속 메뉴 주석처리
        label_visibility="collapsed",
    )


# ─────────────────────────────────────────
# 공통 헬퍼 함수
# ─────────────────────────────────────────

def status_badge(status: str) -> str:
    """약속/참여 상태를 색상 뱃지 HTML로 변환한다."""
    mapping = {
        "수락":   '<span class="badge badge-green">✅ 수락</span>',
        "거절":   '<span class="badge badge-red">❌ 거절</span>',
        "대기중": '<span class="badge badge-yellow">⏳ 대기중</span>',
        "확정":   '<span class="badge badge-purple">🎉 확정</span>',
    }
    return mapping.get(status, status)


def render_apt_detail(detail: dict):
    """약속 상세 정보를 카드 형태로 렌더링하는 공통 함수."""
    apt_id = detail["id"]
    members = detail.get("members", [])
    my_status = next((m["status"] for m in members if m["username"] == current_user), None)

    apt_date = detail.get("date") or ""
    apt_time = detail.get("time") or ""
    date_line = ""
    if apt_date:
        date_line = f'<div class="apt-detail-datetime">🗓️ {apt_date}{"&nbsp;&nbsp;⏰ " + apt_time if apt_time else ""}</div>'

    st.markdown(f"""
<div class="apt-detail-card">
    <div class="apt-detail-title">{detail['title']} &nbsp; {status_badge(detail['status'])}</div>
    <div class="apt-detail-place">📍 {detail['place_name']}</div>
    <div class="apt-detail-address">📌 {detail.get('place_address') or '주소 정보 없음'}</div>
    {date_line}
    <div class="apt-detail-by">만든 사람: {detail['created_by']} · {detail['created_at'][:10]}</div>
</div>
""", unsafe_allow_html=True)

    if detail.get("place_url"):
        st.link_button("🗺️ 카카오맵에서 보기", url=detail["place_url"], use_container_width=True)

    # 캘린더 다운로드 — 수락한 사람 + 날짜 있을 때만 표시
    if my_status == "수락" and apt_date:
        dtstart = apt_date.replace("-", "") + "T" + (apt_time.replace(":", "") + "00" if apt_time else "090000")
        ics_content = f"""BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//JOYNER place//KR\r\nBEGIN:VEVENT\r\nSUMMARY:{detail['title']} @ {detail['place_name']}\r\nDTSTART:{dtstart}\r\nLOCATION:{detail.get('place_address', '')}\r\nDESCRIPTION:{detail.get('place_url', '')}\r\nEND:VEVENT\r\nEND:VCALENDAR"""
        st.download_button(
            label="📅 캘린더에 추가",
            data=ics_content.encode("utf-8"),
            file_name=f"joyner_{apt_id}.ics",
            mime="text/calendar",
            use_container_width=True,
        )

    st.markdown('<div class="sec-label">참여자 현황</div>', unsafe_allow_html=True)
    for m in members:
        st.markdown(
            f'<div class="member-row"><span>👤 {m["username"]}</span>{status_badge(m["status"])}</div>',
            unsafe_allow_html=True,
        )

    # 내 액션 버튼 (대기중일 때만 표시)
    if my_status == "대기중":
        st.markdown("")
        ac1, ac2 = st.columns(2)
        with ac1:
            if st.button("✅ 수락하기", key=f"accept_{apt_id}", use_container_width=True, type="primary"):
                try:
                    _api_call("post", f"/appointments/{apt_id}/respond", {"action": "수락"})
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
        with ac2:
            if st.button("❌ 거절하기", key=f"reject_{apt_id}", use_container_width=True):
                try:
                    _api_call("post", f"/appointments/{apt_id}/respond", {"action": "거절"})
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))


# ─────────────────────────────────────────
# 페이지: 즐겨찾기
# ─────────────────────────────────────────
if page == "❤️ 즐겨찾기":
    st.markdown('<div class="sec-label">내 즐겨찾기</div>', unsafe_allow_html=True)

    # _refresh_favorites()로 이미 로드된 데이터 사용
    favs = st.session_state.get("favorites", [])

    if not favs:
        st.markdown("""
<div style="text-align:center;padding:2.5rem 1rem;color:#8F8FB0;">
    <div style="font-size:2rem;margin-bottom:0.6rem;">🥲</div>
    <div style="font-size:1rem;font-weight:600;color:#6B6B8D;margin-bottom:0.3rem;">아직 저장한 장소가 없어요</div>
    <div style="font-size:0.88rem;">장소를 추천받고 ♡를 눌러보세요!</div>
</div>
""", unsafe_allow_html=True)
    else:
        for fav in favs:
            fav_name = fav["place_name"]
            fav_id   = fav["id"]
            cat_html = f'<span class="cat-badge">{fav["category"]}</span>' if fav.get("category") else ""

            st.markdown(f"""
<div class="fav-card">
    <div class="fav-card-header">
        <div class="fav-card-name">{fav_name}</div>
        {cat_html}
    </div>
    <div class="fav-card-address">📌 {fav.get('place_address') or '주소 정보 없음'}</div>
    <div class="fav-card-date">저장일 {fav['saved_at'][:10]}</div>
</div>
""", unsafe_allow_html=True)

            # 메모 입력 (변경 감지 → 즉시 저장)
            memo_key = f"fav_memo_{fav_id}"
            memo_val = st.text_input(
                "메모",
                value=fav.get("memo", ""),
                placeholder="기억해두고 싶은 것을 적어보세요 (선택)",
                key=memo_key,
                label_visibility="collapsed",
            )
            if memo_val != fav.get("memo", ""):
                try:
                    _api_call("put", f"/favorites/{quote(fav_name, safe='')}/memo", {"memo": memo_val})
                except ValueError as e:
                    st.error(str(e))

            # 버튼 행
            fb1, fb2 = st.columns(2)
            # fb1, fb2, fb3 = st.columns(3)  # 약속 만들기 버튼 제거로 2열로 변경
            with fb1:
                if fav.get("place_url"):
                    st.link_button("🗺️ 카카오맵", url=fav["place_url"], use_container_width=True)
            # with fb2:  # 약속 만들기 버튼 주석처리
            #     if st.button("📅 약속 만들기", key=f"fav_apt_btn_{fav_id}", use_container_width=True):
            #         st.session_state["fav_apt_form"] = fav_id
            #         st.session_state.pop("fav_apt_created", None)
            #         st.rerun()
            with fb2:
                if st.button("🗑️ 삭제", key=f"fav_del_{fav_id}", use_container_width=True):
                    try:
                        _api_call("delete", f"/favorites/{quote(fav_name, safe='')}")
                        _refresh_favorites()
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

            # # 약속 만들기 폼 (즐겨찾기 페이지) — 주석처리
            # if st.session_state.get("fav_apt_form") == fav_id:
            #     _time_options = [
            #         f"{h:02d}:{m:02d}"
            #         for h in range(9, 24)
            #         for m in (0, 30)
            #     ]
            #     with st.form(f"fav_apt_form_{fav_id}"):
            #         fav_apt_title    = st.text_input("약속 이름", placeholder="예: 이번주 약속")
            #         fav_apt_date     = st.date_input("날짜", min_value=date_type.today(), value=date_type.today())
            #         fav_apt_time_sel = st.selectbox("시간", options=["미정"] + _time_options)
            #         ffc1, ffc2 = st.columns(2)
            #         with ffc1:
            #             fav_cancelled = st.form_submit_button("취소", use_container_width=True)
            #         with ffc2:
            #             fav_submitted = st.form_submit_button("약속 확정 ✓", type="primary", use_container_width=True)
            #
            #     if fav_cancelled:
            #         st.session_state.pop("fav_apt_form", None)
            #         st.rerun()
            #     if fav_submitted:
            #         if not fav_apt_title.strip():
            #             st.error("약속 이름을 입력해주세요.")
            #         else:
            #             try:
            #                 result = _api_call("post", "/appointments", {
            #                     "title":         fav_apt_title,
            #                     "place_name":    fav_name,
            #                     "place_address": fav.get("place_address", ""),
            #                     "place_url":     fav.get("place_url", ""),
            #                     "date": str(fav_apt_date),
            #                     "time": "" if fav_apt_time_sel == "미정" else fav_apt_time_sel,
            #                 })
            #                 st.session_state["fav_apt_created"] = {
            #                     "fav_id": fav_id,
            #                     "code":   result["code"],
            #                     "title":  fav_apt_title,
            #                 }
            #                 st.session_state.pop("fav_apt_form", None)
            #                 st.rerun()
            #             except ValueError as e:
            #                 st.error(str(e))
            #
            # # 생성된 코드 표시
            # fav_created = st.session_state.get("fav_apt_created", {})
            # if fav_created.get("fav_id") == fav_id:
            #     st.markdown(f"""
            # <div class="apt-code-card">
            #     <div class="apt-code-title">📋 약속이 만들어졌어요!</div>
            #     <div class="apt-code-label">{fav_created['title']}</div>
            #     <div class="apt-code-value">{fav_created['code']}</div>
            #     <div class="apt-code-hint">친구에게 이 코드를 공유하세요!</div>
            # </div>
            # """, unsafe_allow_html=True)
            #     st.code(fav_created["code"], language=None)

            st.markdown('<hr class="jd">', unsafe_allow_html=True)

    st.stop()


# # ─────────────────────────────────────────
# # 페이지: 약속 참여하기 — 주석처리
# # ─────────────────────────────────────────
# if page == "🔗 약속 참여하기":
#     st.markdown('<div class="sec-label">약속 참여</div>', unsafe_allow_html=True)
#     st.markdown("친구에게 받은 **6자리 약속 코드**를 입력하세요.")
#
#     code_input = st.text_input(
#         "약속 코드",
#         placeholder="예: AB12CD",
#         max_chars=6,
#         label_visibility="collapsed",
#     ).strip().upper()
#
#     if st.button("참여하기", type="primary", use_container_width=True):
#         if len(code_input) != 6:
#             st.error("6자리 코드를 정확히 입력해주세요.")
#         else:
#             try:
#                 _api_call("post", f"/appointments/{code_input}/join")
#                 st.session_state["join_viewing"] = code_input
#                 st.rerun()
#             except ValueError as e:
#                 st.error(str(e))
#
#     viewing_code = st.session_state.get("join_viewing")
#     if viewing_code:
#         try:
#             detail = _api_call("get", f"/appointments/{viewing_code}")
#             st.markdown('<hr class="jd">', unsafe_allow_html=True)
#             render_apt_detail(detail)
#         except ValueError:
#             st.session_state.pop("join_viewing", None)
#
#     st.stop()


# # ─────────────────────────────────────────
# # 페이지: 내 약속 목록 — 주석처리
# # ─────────────────────────────────────────
# elif page == "📋 내 약속 목록":
#     st.markdown('<div class="sec-label">내 약속 목록</div>', unsafe_allow_html=True)
#
#     try:
#         my_apts = _api_call("get", "/appointments")
#     except ValueError as e:
#         st.error(str(e))
#         st.stop()
#
#     if not my_apts:
#         st.info("아직 약속이 없어요. 장소 추천을 받아 약속을 만들어보세요!")
#     else:
#         detail_key = "apt_detail_viewing"
#
#         for apt in my_apts:
#             apt_id = apt["id"]
#             is_open = st.session_state.get(detail_key) == apt_id
#
#             _apt_date_str = apt.get("date") or ""
#             _apt_time_str = apt.get("time") or ""
#             _datetime_info = ""
#             if _apt_date_str:
#                 _datetime_info = f" · 🗓️ {_apt_date_str}" + (f" {_apt_time_str}" if _apt_time_str else "")
#             st.markdown(f"""
# <div class="apt-card">
#     <div class="apt-card-title">{apt['title']} &nbsp; {status_badge(apt['status'])}</div>
#     <div class="apt-card-place">📍 {apt['place_name']}</div>
#     <div class="apt-card-meta">코드: <b>{apt_id}</b> · 내 상태: {status_badge(apt['my_status'])}{_datetime_info}</div>
# </div>
# """, unsafe_allow_html=True)
#
#             btn_label = "▲ 닫기" if is_open else "자세히 보기"
#             if st.button(btn_label, key=f"toggle_{apt_id}", use_container_width=True):
#                 if is_open:
#                     st.session_state.pop(detail_key, None)
#                 else:
#                     st.session_state[detail_key] = apt_id
#                 st.rerun()
#
#             if is_open:
#                 try:
#                     detail = _api_call("get", f"/appointments/{apt_id}")
#                     render_apt_detail(detail)
#                 except ValueError as e:
#                     st.error(str(e))
#                 st.markdown('<hr class="jd">', unsafe_allow_html=True)
#
#     st.stop()


# ─────────────────────────────────────────
# 페이지: 장소 추천 (메인)
# ─────────────────────────────────────────

# ── 모드 선택 ────────────────────────────
mode = st.radio(
    "검색 모드",
    options=["단일 위치", "다중 참여자 (중간지점 자동 계산)"],
    horizontal=True,
)
st.markdown('<hr class="jd">', unsafe_allow_html=True)

# ── 입력 섹션 ────────────────────────────
st.markdown('<div class="sec-label">모임 정보 입력</div>', unsafe_allow_html=True)

if mode == "단일 위치":
    location = st.text_input("위치 또는 지역명", placeholder="예: 강남역, 홍대, 판교역")
else:
    num_participants = st.number_input(
        "참여자 수", min_value=2, max_value=5, value=2, step=1,
        help="2~5명까지 입력 가능해요",
    )
    st.write("각 참여자의 출발 위치를 입력해주세요.")
    participant_locations = []
    for i in range(int(num_participants)):
        loc = st.text_input(
            f"참여자 {i+1} 위치",
            placeholder="예: 강남역, 홍대입구, 잠실역",
            key=f"participant_{i}",
        )
        participant_locations.append(loc)

purpose = st.text_input("모임 목적", placeholder="예: 팀 회식, 친구 모임, 스터디, 데이트, 볼링")

time_slot = st.selectbox(
    "시간대",
    options=["아침 (07:00~11:00)", "점심 (11:00~14:00)", "오후 (14:00~17:00)", "저녁 (17:00~21:00)", "심야 (21:00~)"],
)

if mode == "단일 위치":
    people = st.number_input("인원수", min_value=1, max_value=20, value=2, step=1)
else:
    people = int(num_participants)

st.markdown('<hr class="jd">', unsafe_allow_html=True)

# ─────────────────────────────────────────
# 추천 버튼 — 백엔드 API 호출
# ─────────────────────────────────────────
if st.button("장소 추천받기 🔍", type="primary", use_container_width=True):

    if not purpose.strip():
        st.warning("모임 목적을 입력해주세요.")
        st.stop()

    # 요청 데이터 조립
    if mode == "단일 위치":
        request_data = {
            "location":    location,
            "purpose":     purpose,
            "time_slot":   time_slot,
            "people_count": people,
        }
    else:
        filled_locs = [l.strip() for l in participant_locations if l.strip()]
        if len(filled_locs) < 2:
            st.warning("참여자 위치를 2개 이상 입력해주세요.")
            st.stop()
        request_data = {
            "location":    "",
            "purpose":     purpose,
            "time_slot":   time_slot,
            "people_count": people,
            "locations":   filled_locs,
        }

    with st.status("🔍 AI가 장소를 찾고 있어요...", expanded=True) as status_widget:
        st.write("📌 위치 확인 및 장소 검색 중...")
        try:
            # 추천 파이프라인은 최대 90초 소요 (임베딩 + GPT)
            rec = _api_call("post", "/recommend", request_data, timeout=90)
            status_widget.update(label="추천 완료!", state="complete", expanded=False)
        except ValueError as e:
            status_widget.update(label="오류 발생", state="error")
            st.error(str(e))
            st.stop()
        except ConnectionError as e:
            status_widget.update(label="연결 오류", state="error")
            st.error(str(e))
            st.stop()

    # 결과를 session_state에 저장 (버튼 재클릭 없이도 약속 만들기 등 인터랙션 유지)
    st.session_state["rec"] = {
        "places":   rec["places"],       # list[PlaceResult dict]
        "midpoint": rec.get("midpoint"), # 중간지점 주소 or None
        "mode":     mode,
    }
    for _k in ["apt_form_card", "apt_created"]:
        st.session_state.pop(_k, None)


# ─────────────────────────────────────────
# 결과 섹션 (session_state에서 렌더링 — 재실행 후에도 유지)
# ─────────────────────────────────────────
if "rec" in st.session_state:
    rec = st.session_state["rec"]
    st.markdown('<hr class="jd">', unsafe_allow_html=True)

    # 중간지점 뱃지 (다중 참여자 모드)
    if rec.get("midpoint"):
        st.markdown(
            f'<div class="midpoint-badge">📍 중간지점: {rec["midpoint"]} 근처</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="result-title">🏆 AI 추천 장소</div>', unsafe_allow_html=True)

    places = rec.get("places", [])

    if places:
        for i, place in enumerate(places):
            # place는 PlaceResult 스키마 기반 dict
            # 백엔드에서 이미 조립했으므로 복잡한 매핑 없이 바로 사용
            place_name = place["place_name"]
            category   = place.get("category", "")
            address    = place.get("address", "")
            distance   = place.get("distance", "")
            place_url  = place.get("place_url", "")
            reason     = place.get("reason", "")

            dist_label = "중간지점" if rec.get("midpoint") else address.split()[0] if address else "출발지"
            cat_html  = f'<span class="cat-badge">{category}</span>' if category else ""
            meta_parts = []
            if address:
                meta_parts.append(f"📌 {address}")
            if distance:
                meta_parts.append(f"📍 {dist_label}에서 {distance}m")
            meta_html = '<span style="color:#C5C3E0">·</span>'.join(meta_parts) if meta_parts else ""

            st.markdown(f"""
<div class="result-card">
    <div class="card-header">
        <div class="place-badge">{i+1}</div>
        <div class="place-name">{place_name}</div>
        {cat_html}
    </div>
    {f'<div class="card-meta">{meta_html}</div>' if meta_html else ""}
    <hr class="card-divider">
    <div class="place-reason">{reason}</div>
</div>
""", unsafe_allow_html=True)

            # ── 카드 하단 버튼 행 ──────────────────
            favorited = _is_favorite(place_name)
            fav_label = "♥ 저장됨" if favorited else "♡ 즐겨찾기"

            btn_col1, btn_col2 = st.columns(2)
            # btn_col1, btn_col2, btn_col3 = st.columns(3)  # 약속 만들기 버튼 제거로 2열로 변경
            with btn_col1:
                if st.button(fav_label, key=f"fav_btn_{i}", use_container_width=True):
                    try:
                        if favorited:
                            _api_call("delete", f"/favorites/{quote(place_name, safe='')}")
                        else:
                            _api_call("post", "/favorites", {
                                "place_name":    place_name,
                                "place_address": address,
                                "place_url":     place_url,
                                "category":      category,
                            })
                        _refresh_favorites()
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
            with btn_col2:
                if place_url:
                    st.link_button("🗺️ 카카오맵", url=place_url, use_container_width=True)
            # with btn_col3:  # 약속 만들기 버튼 주석처리
            #     if st.button("📅 약속 만들기", key=f"apt_btn_{i}", use_container_width=True):
            #         st.session_state["apt_form_card"] = i
            #         st.session_state.pop("apt_created", None)
            #         st.rerun()

            # # ── 약속 만들기 폼 — 주석처리 ───────────────────────
            # if st.session_state.get("apt_form_card") == i:
            #     _time_options = [
            #         f"{h:02d}:{m:02d}"
            #         for h in range(9, 24)
            #         for m in (0, 30)
            #     ]
            #     with st.form(f"apt_form_{i}"):
            #         apt_title    = st.text_input("약속 이름", placeholder="예: 이번주 팀 회식")
            #         apt_date     = st.date_input("날짜", min_value=date_type.today(), value=date_type.today())
            #         apt_time_sel = st.selectbox("시간", options=["미정"] + _time_options)
            #         fc1, fc2 = st.columns(2)
            #         with fc1:
            #             cancelled = st.form_submit_button("취소", use_container_width=True)
            #         with fc2:
            #             submitted = st.form_submit_button("약속 확정 ✓", type="primary", use_container_width=True)
            #
            #     if cancelled:
            #         st.session_state.pop("apt_form_card", None)
            #         st.rerun()
            #     if submitted:
            #         if not apt_title.strip():
            #             st.error("약속 이름을 입력해주세요.")
            #         else:
            #             try:
            #                 result = _api_call("post", "/appointments", {
            #                     "title":         apt_title,
            #                     "place_name":    place_name,
            #                     "place_address": address,
            #                     "place_url":     place_url,
            #                     "date": str(apt_date),
            #                     "time": "" if apt_time_sel == "미정" else apt_time_sel,
            #                 })
            #                 st.session_state["apt_created"] = {
            #                     "card": i, "code": result["code"], "title": apt_title,
            #                 }
            #                 st.session_state.pop("apt_form_card", None)
            #                 st.rerun()
            #             except ValueError as e:
            #                 st.error(str(e))
            #
            # # ── 생성된 약속 코드 표시 — 주석처리 ─────────────────
            # if st.session_state.get("apt_created", {}).get("card") == i:
            #     created = st.session_state["apt_created"]
            #     st.markdown(f"""
            # <div class="apt-code-card">
            #     <div class="apt-code-title">📋 약속이 만들어졌어요!</div>
            #     <div class="apt-code-label">{created['title']}</div>
            #     <div class="apt-code-value">{created['code']}</div>
            #     <div class="apt-code-hint">친구에게 이 코드를 공유하세요!</div>
            # </div>
            # """, unsafe_allow_html=True)
            #     st.code(created["code"], language=None)

    else:
        st.info("추천 결과가 없어요. 다시 시도해보세요.")
