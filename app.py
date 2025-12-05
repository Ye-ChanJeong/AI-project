import streamlit as st
import os
from dotenv import load_dotenv
from openai import OpenAI
import requests
import folium
import streamlit.components.v1 as components
import re
import random

# -----------------------------------------------------------
# 🌐 환경 변수 로드
# -----------------------------------------------------------
load_dotenv()
env_openai_key = os.getenv("OPENAI_API_KEY")
env_kakao_key = os.getenv("KAKAO_API_KEY")

# -----------------------------------------------------------
# 🌊 기본 화면 설정
# -----------------------------------------------------------
st.set_page_config(page_title="부산 로컬 라이프 어시스턴트", page_icon="🌊", layout="wide")

st.title("🌊 부산 로컬 라이프 어시스턴트")
st.write("부산에서 뭐 하고 싶은지 말해줘! 실제 데이터 기반으로 추천해줄게.")

# -----------------------------------------------------------
# 🔥 세션 상태 초기화
# -----------------------------------------------------------
st.session_state.setdefault("last_answer", None)
st.session_state.setdefault("places", None)
st.session_state.setdefault("map_html", None)
st.session_state.setdefault("favorites", [])
st.session_state.setdefault("recent_search", [])
st.session_state.setdefault("restore_location", "")
st.session_state.setdefault("restore_query", "")
st.session_state.setdefault("auto_search", False)

# -----------------------------------------------------------
# 🗺 Kakao API 헬퍼
# -----------------------------------------------------------
def get_center_from_location(location_text, kakao_key):
    DEFAULT_X = 129.0756
    DEFAULT_Y = 35.1796

    if not location_text:
        return DEFAULT_X, DEFAULT_Y

    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {kakao_key}"}
    params = {"query": f"부산 {location_text}", "size": 3}

    try:
        res = requests.get(url, headers=headers, params=params).json()
        docs = res.get("documents", [])
    except:
        return DEFAULT_X, DEFAULT_Y

    if not docs:
        return DEFAULT_X, DEFAULT_Y

    return float(docs[0]["x"]), float(docs[0]["y"])


def get_nearby_places(keyword, x, y, kakao_key, radius=800):
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {kakao_key}"}

    params = {"query": keyword, "x": x, "y": y, "radius": radius, "size": 10, "sort": "distance"}

    res = requests.get(url, headers=headers, params=params).json()
    docs = res.get("documents", [])
    busan_docs = [d for d in docs if "부산" in d.get("address_name", "")]
    return busan_docs or docs

# -----------------------------------------------------------
# 🤖 GPT 헬퍼
# -----------------------------------------------------------
def ask_gpt_for_search_keyword(client, query):
    prompt = f"""
사용자 질문에서 카카오맵 검색 키워드를 한 단어 또는 두 단어로 추출해줘.
질문: {query}

형식:
키워드: <검색어>
"""
    res = client.responses.create(model="gpt-4o-mini", input=prompt)
    text = res.output_text
    m = re.search(r"키워드[:：]\s*(.+)", text)
    return m.group(1).strip()[:20] if m else None


def ask_gpt_for_summary(client, query, places):
    prompt = f"""
부산 로컬 안내 전문가처럼 아래 실제 장소 데이터를 기반으로 상권 분위기만 요약해줘.

사용자 질문: {query}

장소 데이터:
{places}
"""
    res = client.responses.create(model="gpt-4o-mini", input=prompt)
    return res.output_text

# -----------------------------------------------------------
# 🔍 검색 입력 폼
# -----------------------------------------------------------
with st.form("search_form"):
    location_text = st.text_input("📍 기준 지역", st.session_state.restore_location)
    query = st.text_input("💬 무엇을 하고 싶나요?", st.session_state.restore_query)

    submitted = st.form_submit_button("검색하기")

# 최근 검색 → 자동 검색 실행 요청이 있으면 제출 처리
if st.session_state.auto_search:
    submitted = True
    location_text = st.session_state.restore_location
    query = st.session_state.restore_query
    st.session_state.auto_search = False

# -----------------------------------------------------------
# 🔥 검색 실행
# -----------------------------------------------------------
if submitted:
    client = OpenAI(api_key=env_openai_key)

    keyword = ask_gpt_for_search_keyword(client, query) or "맛집"
    cx, cy = get_center_from_location(location_text, env_kakao_key)
    places = get_nearby_places(keyword, cx, cy, env_kakao_key)

    st.session_state.places = places[:3]
    st.session_state.last_answer = ask_gpt_for_summary(client, query, st.session_state.places)

    # 최근 검색 저장 (중복 방지)
    new_item = {"location": location_text, "query": query}
    if new_item not in st.session_state.recent_search:
        st.session_state.recent_search.insert(0, new_item)
    st.session_state.recent_search = st.session_state.recent_search[:5]

    # 지도 생성
    
    m = folium.Map(location=[cy, cx], zoom_start=15)
    for p in st.session_state.places:
        folium.Marker([float(p["y"]), float(p["x"])], popup=p["place_name"]).add_to(m)

    st.session_state.map_html = m._repr_html_()

# -----------------------------------------------------------
# ⭐ 사이드바 (즐겨찾기 + 최근 검색 + 랜덤 추천)
# -----------------------------------------------------------
with st.sidebar:

    # ⭐ 즐겨찾기
    st.title("⭐ 내 즐겨찾기")

    if st.session_state.favorites:
        for idx, fav in enumerate(st.session_state.favorites):
            col1, col2 = st.columns([7, 1])
            with col1:
                st.write(f"• {fav['place_name']}")
            with col2:
                if st.button("🗑", key=f"fav_del_{idx}"):
                    st.session_state.favorites.pop(idx)
                    st.rerun()
    else:
        st.write("즐겨찾기 없음")

    st.markdown("---")

    # ⏱ 최근 검색
    st.subheader("⏱ 최근 검색")

    if st.session_state.recent_search:
        for idx, item in enumerate(st.session_state.recent_search):
            col1, col2 = st.columns([7, 1])

            with col1:
                label = f"{item['location']} · {item['query']}"
                if st.button(label, key=f"recent_btn_{idx}"):

                    # 검색창 복원 + 자동 검색 실행 요청
                    st.session_state.restore_location = item["location"]
                    st.session_state.restore_query = item["query"]
                    st.session_state.auto_search = True
                    st.rerun()

            with col2:
                if st.button("🗑", key=f"recent_del_{idx}"):
                    st.session_state.recent_search.pop(idx)
                    st.rerun()

    else:
        st.write("최근 검색 없음")

    st.markdown("---")

    # 🎲 랜덤 추천
    st.subheader("🎲 랜덤 추천")
    if st.button("오늘의 랜덤  뽑기 🍀"):
        st.success("오늘 추천 👉 " + random.choice([
            "라면", "삼겹살", "파스타", "마라탕", "초밥", "카페", "디저트", "돈까스"
        ]))


# -----------------------------------------------------------
# 🗺 지도 출력
# -----------------------------------------------------------
if st.session_state.map_html:
    st.subheader("📍 지도 표시")
    components.html(st.session_state.map_html, height=500)

# -----------------------------------------------------------
# 🤖 GPT 요약 출력
# -----------------------------------------------------------
if st.session_state.last_answer:
    st.subheader("🤖 지역 분위기 설명")
    st.write(st.session_state.last_answer)

# -----------------------------------------------------------
# 🏆 추천 장소 목록 + 즐겨찾기 버튼
# -----------------------------------------------------------
if st.session_state.places:
    st.subheader("🏆 추천 장소 3곳")

    for idx, p in enumerate(st.session_state.places, start=1):
        st.markdown(f"""
### {idx}. {p['place_name']}
- 📍 주소: {p['address_name']}
- 📞 전화: {p['phone'] or '전화 없음'}
- 📏 거리: {p['distance']}m
- 🔗 [카카오맵에서 보기]({p.get('place_url', '')})
""")

        if st.button(f"⭐ 즐겨찾기 추가 ({p['place_name']})", key=f"fav_add_{idx}"):
            st.session_state.favorites.append(p)
            st.rerun()
