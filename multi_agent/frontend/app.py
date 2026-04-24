"""
JOYNER Place Multi-Agent — Streamlit 채팅 프론트엔드
"""

import json
import os
import uuid
import requests
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv("MULTI_AGENT_BACKEND_URL", "http://localhost:8003")
KAKAO_JS_KEY = os.getenv("KAKAO_JS_KEY", "")

st.set_page_config(
    page_title="JOYNER Place Multi-Agent",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────
# CSS
# ─────────────────────────────────────────

st.markdown("""
<style>
html, body, [data-testid="stAppViewContainer"] {
    background: #F7F6FF !important;
    color: #1A1A2E !important;
    font-family: 'Pretendard', 'Apple SD Gothic Neo', sans-serif;
}
[data-testid="stSidebar"] {
    background: #FFFFFF !important;
    border-right: 1.5px solid #E8E6FF;
}
[data-testid="stSidebar"] * { color: #1A1A2E !important; }

.joyner-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 4px;
}
.joyner-header h1 {
    font-size: 1.6rem;
    font-weight: 700;
    color: #1A1A2E;
    margin: 0;
}
.joyner-header .accent { color: #7C6FF7; }
.joyner-sub {
    color: #6B6B8D;
    font-size: 0.9rem;
    margin-bottom: 1.2rem;
}
.jd { border: none; border-top: 1.5px solid #E8E6FF; margin: 1rem 0; }

button[kind="primary"],
button[kind="secondary"],
div[data-testid="stButton"] > button,
div.stButton > button,
div.stFormSubmitButton > button {
    background: #7C6FF7 !important;
    background-color: #7C6FF7 !important;
    color: #FFFFFF !important;
    border: none !important;
    border-color: #7C6FF7 !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    transition: background 0.15s !important;
}
button[kind="primary"]:hover,
button[kind="secondary"]:hover,
div[data-testid="stButton"] > button:hover,
div.stButton > button:hover,
div.stFormSubmitButton > button:hover {
    background: #6358E8 !important;
    background-color: #6358E8 !important;
    border-color: #6358E8 !important;
}

[data-testid="stChatInput"] textarea,
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea {
    border: 1.5px solid #E8E6FF !important;
    border-radius: 10px !important;
    background: #FFFFFF !important;
    color: #1A1A2E !important;
}
[data-testid="stChatInput"] textarea:focus,
[data-testid="stTextInput"] input:focus {
    border-color: #7C6FF7 !important;
    box-shadow: 0 0 0 2px rgba(124,111,247,0.15) !important;
}

[data-testid="stChatMessage"] {
    background: #FFFFFF !important;
    border: 1.5px solid #E8E6FF !important;
    border-radius: 14px !important;
    padding: 12px 16px !important;
    margin-bottom: 8px !important;
}

.place-card {
    background: #FFFFFF;
    border: 1.5px solid #E8E6FF;
    border-radius: 14px;
    padding: 18px 20px;
    margin: 10px 0;
    box-shadow: 0 2px 10px rgba(124,111,247,0.06);
    transition: box-shadow 0.15s;
}
.place-card:hover { box-shadow: 0 4px 18px rgba(124,111,247,0.12); }
.place-card .rank {
    display: inline-block;
    background: #7C6FF7;
    color: #fff;
    border-radius: 50%;
    width: 26px; height: 26px;
    line-height: 26px;
    text-align: center;
    font-size: 0.8rem;
    font-weight: 700;
    margin-right: 8px;
}
.place-card h4 {
    display: inline;
    font-size: 1.05rem;
    font-weight: 700;
    color: #1A1A2E;
}
.place-card .category { color: #6B6B8D; font-size: 0.82rem; margin: 6px 0; }
.place-card .reason { color: #495057; font-size: 0.88rem; line-height: 1.6; }
.tag {
    display: inline-block;
    background: #F0EEFF;
    color: #7C6FF7;
    border: 1px solid #D4CFFF;
    border-radius: 20px;
    padding: 2px 10px;
    font-size: 0.75rem;
    margin: 3px 2px 0 0;
    font-weight: 500;
}
.place-card .dist { color: #7C6FF7; font-weight: 600; }

/* ── 에이전트 로그 ── */
.agent-log-item {
    background: #F7F6FF;
    border-left: 3px solid #7C6FF7;
    border-radius: 6px;
    padding: 8px 14px;
    margin: 5px 0;
    font-size: 0.82rem;
    color: #1A1A2E;
}
.agent-log-item.failed { border-left-color: #E53935; background: #FFF5F5; }
.agent-log-item .al-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 2px;
}
.al-name { font-weight: 700; color: #7C6FF7; }
.al-name.failed { color: #E53935; }
.al-duration { color: #9999BB; font-size: 0.75rem; margin-left: auto; }
.al-summary { color: #6B6B8D; margin-top: 2px; }

.badge-done {
    display: inline-block;
    background: #E6FAF0;
    color: #1A9C5B;
    border-radius: 12px;
    padding: 1px 8px;
    font-size: 0.72rem;
    font-weight: 600;
}
.badge-failed {
    display: inline-block;
    background: #FFECEC;
    color: #E53935;
    border-radius: 12px;
    padding: 1px 8px;
    font-size: 0.72rem;
    font-weight: 600;
}
.badge-pass {
    display: inline-block;
    background: #E6FAF0;
    color: #1A9C5B;
    border-radius: 20px;
    padding: 3px 12px;
    font-size: 0.8rem;
    font-weight: 600;
}
.badge-warn {
    display: inline-block;
    background: #FFF8E6;
    color: #B07D00;
    border-radius: 20px;
    padding: 3px 12px;
    font-size: 0.8rem;
    font-weight: 600;
}

.sidebar-section {
    font-size: 0.78rem;
    font-weight: 700;
    color: #7C6FF7;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    margin: 16px 0 6px 0;
}

[data-testid="stExpander"] {
    border: 1.5px solid #E8E6FF !important;
    border-radius: 10px !important;
    background: #FFFFFF !important;
}

.kakao-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    background: #7C6FF7;
    color: #FFFFFF !important;
    font-weight: 600;
    font-size: 0.83rem;
    text-decoration: none !important;
    padding: 8px 0;
    border-radius: 8px;
    border: none;
    width: 100%;
    transition: background 0.15s, transform 0.1s;
}
.kakao-btn:hover { background: #6358E8; transform: translateY(-1px); color: #FFFFFF !important; }
.kakao-btn-outline {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    background: #FFFFFF;
    color: #7C6FF7 !important;
    font-weight: 600;
    font-size: 0.83rem;
    text-decoration: none !important;
    padding: 8px 0;
    border-radius: 8px;
    border: 1.5px solid #7C6FF7;
    width: 100%;
    transition: background 0.15s, transform 0.1s;
}
.kakao-btn-outline:hover { background: #F0EEFF; transform: translateY(-1px); color: #6358E8 !important; }

iframe {
    display: block;
    margin: 0 !important;
    padding: 0 !important;
}
.element-container:has(iframe) {
    margin-bottom: 0 !important;
    padding-bottom: 0 !important;
}

/* ── 파이프라인 진행 표시 ── */
.pipeline-bar {
    display: flex;
    align-items: center;
    gap: 4px;
    margin: 8px 0 12px 0;
    flex-wrap: wrap;
}
.pipeline-step {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: #F0EEFF;
    border: 1px solid #D4CFFF;
    border-radius: 20px;
    padding: 3px 10px;
    font-size: 0.75rem;
    font-weight: 600;
    color: #7C6FF7;
}
.pipeline-step.done {
    background: #E6FAF0;
    border-color: #B2DFCE;
    color: #1A9C5B;
}
.pipeline-step.failed {
    background: #FFECEC;
    border-color: #FFCDD2;
    color: #E53935;
}
.pipeline-arrow { color: #CCCCDD; font-size: 0.8rem; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────
# 세션 상태 초기화
# ─────────────────────────────────────────

def _init_state():
    defaults = {
        "token": None,
        "username": None,
        "name": None,
        "session_id": None,
        "messages": [],
        "conversations": [],
        "favorites": [],
        "page": "login",
        "conversation_history": [],
        "data_loaded": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    if st.session_state.token and st.session_state.page == "login":
        st.session_state.page = "chat"

_init_state()


# ─────────────────────────────────────────
# API 헬퍼
# ─────────────────────────────────────────

def _headers():
    return {"Authorization": f"Bearer {st.session_state.token}"} if st.session_state.token else {}


def api_login(username: str, password: str) -> dict | None:
    try:
        r = requests.post(f"{BACKEND_URL}/auth/login", json={"username": username, "password": password}, timeout=10)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def api_register(username: str, name: str, email: str, password: str) -> tuple[bool, str]:
    try:
        r = requests.post(
            f"{BACKEND_URL}/auth/register",
            json={"username": username, "name": name, "email": email, "password": password},
            timeout=10,
        )
        return (True, "회원가입 완료!") if r.status_code == 200 else (False, r.json().get("detail", "오류 발생"))
    except Exception as e:
        return False, str(e)


def api_load_favorites() -> list:
    try:
        r = requests.get(f"{BACKEND_URL}/user/favorites", headers=_headers(), timeout=5)
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []


def api_save_favorites(favorites: list) -> None:
    try:
        requests.post(f"{BACKEND_URL}/user/favorites", json=favorites, headers=_headers(), timeout=5)
    except Exception:
        pass


def api_load_conversations() -> list:
    try:
        r = requests.get(f"{BACKEND_URL}/user/conversations", headers=_headers(), timeout=5)
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []


def api_save_conversations(conversations: list) -> None:
    try:
        requests.post(f"{BACKEND_URL}/user/conversations", json=conversations, headers=_headers(), timeout=5)
    except Exception:
        pass


def api_chat(message: str, session_id: str | None, conversation_history: list[dict] | None = None) -> dict | None:
    try:
        r = requests.post(
            f"{BACKEND_URL}/chat",
            json={
                "message": message,
                "session_id": session_id,
                "conversation_history": conversation_history or [],
            },
            headers=_headers(),
            timeout=180,
        )
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


if st.session_state.token and not st.session_state.data_loaded:
    loaded_favs = api_load_favorites()
    loaded_convs = api_load_conversations()
    if loaded_favs:
        st.session_state.favorites = loaded_favs
    if loaded_convs:
        st.session_state.conversations = loaded_convs
    st.session_state.data_loaded = True


# ─────────────────────────────────────────
# UI 컴포넌트
# ─────────────────────────────────────────

_AGENT_ICONS = {
    "Location Agent": "📍",
    "Search Agent":   "🔍",
    "Recommend Agent": "🤖",
    "Validation Agent": "✅",
}


def render_agent_log(log: list[dict], retry_count: int = 0):
    """에이전트 실행 로그를 파이프라인 형태로 렌더링한다."""
    if not log:
        return

    # 파이프라인 진행 바 (첫 번째 시도 기준 4개 에이전트)
    first_agents = [e for e in log if "(재시도" not in e.get("agent", "")]
    if first_agents:
        steps_html = ""
        for i, entry in enumerate(first_agents):
            agent_short = entry["agent"].split(" (")[0]
            icon = _AGENT_ICONS.get(agent_short, "⚙️")
            status_cls = "done" if entry["status"] == "done" else "failed"
            steps_html += f'<span class="pipeline-step {status_cls}">{icon} {agent_short}</span>'
            if i < len(first_agents) - 1:
                steps_html += '<span class="pipeline-arrow">→</span>'
        if retry_count > 0:
            steps_html += f'<span class="pipeline-arrow">↩</span>'
            steps_html += f'<span class="pipeline-step">재시도 {retry_count}회</span>'
        st.markdown(f'<div class="pipeline-bar">{steps_html}</div>', unsafe_allow_html=True)

    with st.expander("🧠 Multi-Agent 실행 과정", expanded=False):
        for entry in log:
            agent_name = entry.get("agent", "")
            agent_short = agent_name.split(" (")[0]
            icon = _AGENT_ICONS.get(agent_short, "⚙️")
            status = entry.get("status", "done")
            summary = entry.get("summary", "")
            duration_ms = entry.get("duration_ms", 0)

            status_badge = (
                '<span class="badge-done">✓ 완료</span>' if status == "done"
                else '<span class="badge-failed">✗ 실패</span>'
            )
            item_cls = "agent-log-item" + (" failed" if status != "done" else "")
            name_cls = "al-name" + (" failed" if status != "done" else "")

            st.markdown(
                f'<div class="{item_cls}">'
                f'  <div class="al-header">'
                f'    <span class="{name_cls}">{icon} {agent_name}</span>'
                f'    {status_badge}'
                f'    <span class="al-duration">{duration_ms}ms</span>'
                f'  </div>'
                f'  <div class="al-summary">{summary}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


def _inline_map_html(lat: float, lng: float, name: str) -> str:
    import json as _json
    name_js = _json.dumps(name, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html><head>
  <meta charset="utf-8">
  <style>
    body{{margin:0;padding:0;background:#f7f6ff;}}
    #map{{width:100%;height:350px;border-radius:12px;overflow:hidden;}}
    #err{{padding:16px;color:#e53935;font-size:13px;display:none;}}
    #loading{{padding:16px;color:#7C6FF7;font-size:13px;}}
  </style>
</head>
<body>
  <div id="loading">지도를 불러오는 중...</div>
  <div id="map" style="display:none"></div>
  <div id="err"></div>
  <script>
  (function() {{
    var script = document.createElement('script');
    script.src = 'https://dapi.kakao.com/v2/maps/sdk.js?appkey={KAKAO_JS_KEY}&autoload=false';
    script.onload = function() {{
      kakao.maps.load(function() {{
        try {{
          document.getElementById('loading').style.display = 'none';
          document.getElementById('map').style.display = 'block';
          var container = document.getElementById('map');
          var map = new kakao.maps.Map(container, {{
            center: new kakao.maps.LatLng({lat}, {lng}),
            level: 4
          }});
          new kakao.maps.CustomOverlay({{
            map: map,
            position: new kakao.maps.LatLng({lat}, {lng}),
            content: '<div style="background:#7C6FF7;color:#fff;padding:6px 14px;border-radius:20px;'
                   + 'font-size:13px;font-weight:700;white-space:nowrap;'
                   + 'box-shadow:0 3px 10px rgba(124,111,247,0.45);cursor:default;">📍 ' + {name_js} + '</div>',
            yAnchor: 1.8
          }});
        }} catch(e) {{
          document.getElementById('loading').style.display = 'none';
          document.getElementById('err').style.display = 'block';
          document.getElementById('err').innerText = '지도 생성 오류: ' + e.message;
        }}
      }});
    }};
    script.onerror = function() {{
      document.getElementById('loading').style.display = 'none';
      document.getElementById('err').style.display = 'block';
      document.getElementById('err').innerText = 'Kakao SDK 로드 실패 — 네트워크 또는 앱키를 확인하세요.';
    }};
    document.head.appendChild(script);
  }})();
  </script>
</body></html>"""


def render_place_card(place: dict, idx: int, turn_key: str = ""):
    tags_html = "".join(f'<span class="tag">{t}</span>' for t in place.get("tags", []))
    dist = place.get("distance", "")
    dist_text = f" &nbsp;·&nbsp; <span class='dist'>{dist}m</span>" if dist else ""

    st.markdown(
        f'<div class="place-card">'
        f'<div style="display:flex;align-items:center;margin-bottom:8px">'
        f'  <span class="rank">{idx}</span><h4>{place["place_name"]}</h4>'
        f'</div>'
        f'<div class="category">{place.get("category", "")}{dist_text}</div>'
        f'<div class="reason">{place.get("reason", "")}</div>'
        f'<div style="margin-top:12px;display:flex;align-items:center;gap:8px;flex-wrap:wrap">'
        f'  {tags_html}'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    is_fav = any(f["place_name"] == place["place_name"] for f in st.session_state.favorites)
    fav_label = "★ 저장됨" if is_fav else "♡ 즐겨찾기"
    place_url = place.get("place_url", "")
    lat, lng, pname = place.get("lat"), place.get("lng"), place.get("place_name", "")

    map_key = f"show_map_{turn_key}_{idx}_{pname}"
    if map_key not in st.session_state:
        st.session_state[map_key] = False
    show_map = st.session_state[map_key]

    col_fav, col_kakao, col_map = st.columns(3)
    with col_fav:
        if st.button(fav_label, key=f"fav_{turn_key}_{idx}_{pname}", use_container_width=True):
            if is_fav:
                st.session_state.favorites = [f for f in st.session_state.favorites if f["place_name"] != pname]
            else:
                st.session_state.favorites.append(place)
            api_save_favorites(st.session_state.favorites)
            st.rerun()
    with col_kakao:
        if place_url:
            st.markdown(
                f'<a href="{place_url}" target="_blank" class="kakao-btn-outline">🗺️ 카카오맵</a>',
                unsafe_allow_html=True,
            )
    with col_map:
        if lat and lng and KAKAO_JS_KEY:
            map_btn_label = "▲ 지도 닫기" if show_map else "🗺️ 지도 보기"
            if st.button(map_btn_label, key=f"mapbtn_{turn_key}_{idx}_{pname}", use_container_width=True):
                st.session_state[map_key] = not show_map
                st.rerun()

    if show_map and lat and lng:
        components.html(_inline_map_html(lat, lng, pname), height=355, scrolling=False)


def render_recommendations(data: dict, turn_key: str = ""):
    recommendations = data.get("recommendations") or []
    if not recommendations:
        return

    st.markdown('<hr class="jd">', unsafe_allow_html=True)
    st.markdown("### 🏆 추천 장소")

    validation = data.get("validation_result")
    if validation:
        badge = '<span class="badge-pass">✅ 검증 완료</span>' if validation.get("passed") else \
                f'<span class="badge-warn">⚠️ {", ".join(validation.get("issues", [])[:2])}</span>'
        st.markdown(badge, unsafe_allow_html=True)
        st.markdown("")

    place_dicts = [p if isinstance(p, dict) else p.model_dump() for p in recommendations]
    for i, place in enumerate(place_dicts, 1):
        render_place_card(place, i, turn_key=turn_key)

    # 다운로드 버튼
    try:
        dl_data = json.dumps(place_dicts, ensure_ascii=False, indent=2)
        st.download_button(
            label="⬇️ 추천 결과 저장 (JSON)",
            data=dl_data,
            file_name=f"joyner_recommendations_{turn_key}.json",
            mime="application/json",
            key=f"dl_{turn_key}",
        )
    except Exception:
        pass


def render_json_view(data: dict, turn_key: str = ""):
    """전체 응답 JSON을 토글로 표시한다."""
    with st.expander("🔎 전체 응답 JSON", expanded=False):
        try:
            st.json(data)
        except Exception:
            st.code(str(data))


# ─────────────────────────────────────────
# 사이드바
# ─────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.markdown(
            '<div class="joyner-header" style="margin-bottom:8px">'
            '<span style="font-size:1.5rem">🧠</span>'
            '<span style="font-size:1.2rem;font-weight:700;color:#1A1A2E">'
            'JOYNER <span style="color:#7C6FF7">Multi-Agent</span></span>'
            '</div>',
            unsafe_allow_html=True,
        )

        if st.session_state.token:
            st.markdown(
                f'<div style="color:#6B6B8D;font-size:0.85rem">안녕하세요, '
                f'<b style="color:#7C6FF7">{st.session_state.name}</b>님!</div>',
                unsafe_allow_html=True,
            )
            st.markdown("")
            if st.button("🚪 로그아웃", use_container_width=True):
                for k in ["token", "username", "name", "session_id", "messages"]:
                    st.session_state[k] = None if k != "messages" else []
                st.session_state.page = "login"
                st.rerun()

        st.markdown('<hr class="jd">', unsafe_allow_html=True)

        # 파이프라인 설명
        st.markdown('<div class="sidebar-section">파이프라인</div>', unsafe_allow_html=True)
        st.markdown(
            '<div style="font-size:0.78rem;color:#6B6B8D;line-height:1.8">'
            '📍 Location Agent<br>'
            '🔍 Search Agent<br>'
            '🤖 Recommend Agent<br>'
            '✅ Validation Agent'
            '</div>',
            unsafe_allow_html=True,
        )

        st.markdown('<hr class="jd">', unsafe_allow_html=True)

        if st.button("✏️ 새 대화 시작", use_container_width=True, type="primary"):
            if st.session_state.messages:
                title = st.session_state.messages[0]["content"][:28] + "…"
                st.session_state.conversations.append({
                    "id": st.session_state.session_id or str(uuid.uuid4()),
                    "title": title,
                    "messages": st.session_state.messages.copy(),
                })
                api_save_conversations(st.session_state.conversations)
            st.session_state.messages = []
            st.session_state.session_id = None
            st.session_state.conversation_history = []
            st.rerun()

        if st.session_state.conversations:
            st.markdown('<div class="sidebar-section">이전 대화</div>', unsafe_allow_html=True)
            for conv in reversed(st.session_state.conversations[-8:]):
                if st.button(f"💬 {conv['title']}", key=f"conv_{conv['id']}", use_container_width=True):
                    st.session_state.messages = conv["messages"].copy()
                    st.session_state.session_id = conv["id"]
                    st.rerun()

        if st.session_state.favorites:
            st.markdown('<hr class="jd">', unsafe_allow_html=True)
            st.markdown('<div class="sidebar-section">⭐ 즐겨찾기</div>', unsafe_allow_html=True)
            for fav in st.session_state.favorites:
                with st.expander(fav["place_name"]):
                    st.markdown(
                        f'<span style="color:#6B6B8D;font-size:0.82rem">📍 {fav.get("address","")}</span>',
                        unsafe_allow_html=True,
                    )
                    if fav.get("place_url"):
                        st.markdown(f"[카카오맵]({fav['place_url']})")
                    if st.button("삭제", key=f"del_{fav['place_name']}"):
                        st.session_state.favorites = [
                            f for f in st.session_state.favorites if f["place_name"] != fav["place_name"]
                        ]
                        api_save_favorites(st.session_state.favorites)
                        st.rerun()


# ─────────────────────────────────────────
# 로그인 / 회원가입
# ─────────────────────────────────────────

def render_login():
    col = st.columns([1, 2, 1])[1]
    with col:
        st.markdown(
            '<div class="joyner-header" style="justify-content:center;margin-bottom:4px">'
            '<span style="font-size:2rem">🧠</span>'
            '<h1 style="font-size:1.8rem;font-weight:700;color:#1A1A2E;margin:0">'
            'JOYNER <span style="color:#7C6FF7">Multi-Agent</span></h1>'
            '</div>'
            '<p style="text-align:center;color:#6B6B8D;margin-bottom:2rem">4개 AI 에이전트가 협력하는 장소 추천</p>',
            unsafe_allow_html=True,
        )
        with st.form("login_form"):
            username = st.text_input("아이디", placeholder="아이디를 입력하세요")
            password = st.text_input("비밀번호", type="password", placeholder="비밀번호를 입력하세요")
            submitted = st.form_submit_button("로그인", use_container_width=True, type="primary")

        if submitted:
            result = api_login(username, password)
            if result:
                st.session_state.token = result["access_token"]
                st.session_state.username = result["username"]
                st.session_state.name = result["name"]
                st.session_state.page = "chat"
                st.rerun()
            else:
                st.error("아이디 또는 비밀번호가 올바르지 않아요.")

        st.markdown('<hr class="jd">', unsafe_allow_html=True)
        if st.button("회원가입하기", use_container_width=True):
            st.session_state.page = "register"
            st.rerun()


def render_register():
    col = st.columns([1, 2, 1])[1]
    with col:
        st.markdown(
            '<h2 style="font-weight:700;color:#1A1A2E">회원가입</h2>'
            '<p style="color:#6B6B8D;margin-bottom:1.5rem">JOYNER Multi-Agent에 오신 걸 환영해요!</p>',
            unsafe_allow_html=True,
        )
        with st.form("register_form"):
            username = st.text_input("아이디")
            name = st.text_input("이름")
            email = st.text_input("이메일")
            password = st.text_input("비밀번호", type="password")
            submitted = st.form_submit_button("가입하기", use_container_width=True, type="primary")

        if submitted:
            ok, msg = api_register(username, name, email, password)
            if ok:
                st.success(msg)
                st.session_state.page = "login"
                st.rerun()
            else:
                st.error(msg)

        if st.button("← 로그인으로 돌아가기"):
            st.session_state.page = "login"
            st.rerun()


# ─────────────────────────────────────────
# 채팅 페이지
# ─────────────────────────────────────────

def render_chat():
    st.markdown(
        '<div class="joyner-header">'
        '<span style="font-size:1.8rem">🧠</span>'
        '<h1 style="font-size:1.5rem;font-weight:700;color:#1A1A2E;margin:0">'
        'JOYNER <span style="color:#7C6FF7">Place Multi-Agent</span></h1>'
        '</div>'
        '<p class="joyner-sub">4개 AI 에이전트가 순서대로 협력해 최적의 장소를 찾아드려요!</p>',
        unsafe_allow_html=True,
    )

    for msg_i, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("data"):
                data = msg["data"]
                render_agent_log(data.get("agent_log", []), retry_count=data.get("retry_count", 0))
                if data.get("recommendations"):
                    render_recommendations(data, turn_key=str(msg_i))
                    render_json_view(data, turn_key=str(msg_i))

    user_input = st.chat_input("예: 강남역 5명 저녁 회식 장소 추천해줘")
    if not user_input:
        return

    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("4개 에이전트가 최적 장소를 찾고 있어요..."):
            result = api_chat(
                user_input,
                st.session_state.session_id,
                st.session_state.conversation_history,
            )

        if result:
            st.session_state.session_id = result.get("session_id")
            reply = result.get("reply", "추천을 완료했습니다.")
            st.markdown(reply)

            retry_count = result.get("retry_count", 0)
            render_agent_log(result.get("agent_log", []), retry_count=retry_count)

            if result.get("recommendations"):
                turn_key = str(len(st.session_state.messages))
                render_recommendations(result, turn_key=turn_key)
                render_json_view(result, turn_key=turn_key)

            st.session_state.conversation_history.append({"role": "user", "content": user_input})
            st.session_state.conversation_history.append({"role": "assistant", "content": reply})
            st.session_state.messages.append({"role": "assistant", "content": reply, "data": result})
        else:
            msg = "서버 오류가 발생했어요. 잠시 후 다시 시도해주세요."
            st.error(msg)
            st.session_state.messages.append({"role": "assistant", "content": msg})


# ─────────────────────────────────────────
# 메인
# ─────────────────────────────────────────

render_sidebar()

if st.session_state.token:
    render_chat()
elif st.session_state.page == "register":
    render_register()
else:
    render_login()
