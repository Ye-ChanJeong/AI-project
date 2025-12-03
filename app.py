import streamlit as st
import os
from dotenv import load_dotenv
from openai import OpenAI
import requests
import folium
import streamlit.components.v1 as components
import re

# -----------------------------------------------------------
# 🔐 환경 변수 로드
# -----------------------------------------------------------
load_dotenv()
env_openai_key = os.getenv("OPENAI_API_KEY")
env_kakao_key = os.getenv("KAKAO_API_KEY")

# -----------------------------------------------------------
# 🌊 기본 설정
# -----------------------------------------------------------
st.set_page_config(page_title="부산 로컬 라이프 어시스턴트", page_icon="🌊")

st.title("🌊 부산 로컬 라이프 어시스턴트")
st.write("부산에서 뭐 하고 싶은지 말해줘! 실제 데이터 기반으로 추천해줄게.")

# -----------------------------------------------------------
# 🗂 세션 상태 초기화
# -----------------------------------------------------------
if "favorites" not in st.session_state:
    st.session_state.favorites = []

if "last_answer" not in st.session_state:
    st.session_state.last_answer = None

if "places" not in st.session_state:
    st.session_state.places = None

if "map_html" not in st.session_state:
    st.session_state.map_html = None


# -----------------------------------------------------------
# ⭐ 즐겨찾기 기능
# -----------------------------------------------------------
def add_favorite(place):
    if place not in st.session_state.favorites:
        st.session_state.favorites.append(place)

def delete_favorite(name, address):
    st.session_state.favorites = [
        p for p in st.session_state.favorites if not (p["place_name"] == name and p["address_name"] == address)
    ]


# -----------------------------------------------------------
# ⭐ 사이드바 – 즐겨찾기 목록
# -----------------------------------------------------------
with st.sidebar:
    st.header("⭐ 내 즐겨찾기")

    if not st.session_state.favorites:
        st.write("아직 즐겨찾기가 없습니다.")
    else:
        for idx, p in enumerate(st.session_state.favorites):
            with st.expander(f"{p['place_name']}", expanded=False):
                st.write(f"📍 {p['address_name']}")
                st.write(f"📞 {p['phone'] or '없음'}")
                if st.button(f"❌ 삭제 ({p['place_name']})", key=f"del_{idx}"):
                    delete_favorite(p["place_name"], p["address_name"])
                    st.rerun()


# -----------------------------------------------------------
# 📍 GPS 위치 요청 버튼
# -----------------------------------------------------------
st.subheader("🧭 GPS 기반 추천")

gps_clicked = st.button("📍 내 현재 위치 받기")

if gps_clicked:
    gps_script = """
        <script>
            navigator.geolocation.getCurrentPosition(
                (pos) => {
                    const lat = pos.coords.latitude;
                    const lon = pos.coords.longitude;
                    window.location.search = `?latitude=${lat}&longitude=${lon}`;
                },
                (err) => {
                    alert("❌ 위치 권한을 허용해야 GPS 기반 추천이 가능합니다!");
                }
            );
        </script>
    """
    st.components.v1.html(gps_script, height=0)

params = st.query_params
gps_enabled = False

if "latitude" in params and "longitude" in params:
    gps_enabled = True
    gps_lat = float(params["latitude"][0])
    gps_lon = float(params["longitude"][0])
    st.success("🟢 GPS 위치 불러오기 성공!")
else:
    st.info("🕊 GPS를 사용하려면 '위치 권한 허용'을 눌러주세요!")


# -----------------------------------------------------------
# 📍 Kakao 지도 API 헬퍼
# -----------------------------------------------------------
def get_nearby_places(keyword, x, y, kakao_key, radius=800):
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {kakao_key}"}
    params = {"query": keyword, "x": x, "y": y, "radius": radius, "size": 10, "sort": "distance"}

    res = requests.get(url, headers=headers, params=params).json()
    docs = res.get("documents", [])
    return docs


# -----------------------------------------------------------
# 🤖 GPT 헬퍼
# -----------------------------------------------------------
def ask_gpt_for_search_keyword(client, query):
    prompt = f"""
    너는 카카오맵 검색 키워드를 뽑는 도우미야.
    사용자 질문: {query}

    아래 형식으로 한 단어만 대답해:
    키워드: <검색어>
    """
    res = client.responses.create(model="gpt-4o", input=prompt)
    m = re.search(r"키워드[:：]\s*(.+)", res.output_text)
    return m.group(1).strip() if m else "맛집"


def ask_gpt_for_summary(client, query, places):
    prompt = f"""
    부산 로컬 분석가처럼 아래 실제 데이터를 기반으로 주변 분위기를 요약해줘.
    {places}
    형식:
    1) 설명:
    """
    res = client.responses.create(model="gpt-4o", input=prompt)
    return res.output_text


# -----------------------------------------------------------
# 🔎 검색 폼 (단 1개만!)
# -----------------------------------------------------------
st.subheader("🔎 장소 검색")

with st.form("search_form"):
    location_text = st.text_input("📍 기준 지역 (GPS 사용 시 비워도 됨)", "")
    query = st.text_input("💬 무엇을 하고 싶나요? (예: 카페, 마라탕 등)")
    submitted = st.form_submit_button("검색하기")


# -----------------------------------------------------------
# 🔥 검색 처리
# -----------------------------------------------------------
if submitted:
    if not env_openai_key or not env_kakao_key:
        st.error("❌ API Key가 없습니다. .env 파일을 확인하세요!")
        st.stop()

    client = OpenAI(api_key=env_openai_key)

    # 검색 키워드 추출
    keyword = ask_gpt_for_search_keyword(client, query)

    # 위치 결정
    if gps_enabled:
        cx, cy = gps_lon, gps_lat
    else:
        st.warning("⚠ GPS 미사용 — 기준 지역을 직접 입력하세요.")
        st.stop()

    # 장소 검색
    places = get_nearby_places(keyword, cx, cy, env_kakao_key)
    if not places:
        st.error("❌ 해당 주변에서 장소를 찾을 수 없습니다.")
        st.stop()

    top3 = places[:3]
    st.session_state.places = top3
    st.session_state.last_answer = ask_gpt_for_summary(client, query, top3)

    # 지도 생성
    m = folium.Map(location=[cy, cx], zoom_start=15)
    for p in top3:
        folium.Marker([float(p["y"]), float(p["x"])], popup=p["place_name"]).add_to(m)
    st.session_state.map_html = m._repr_html_()
    st.rerun()


# -----------------------------------------------------------
# 🗺 지도 출력
# -----------------------------------------------------------
if st.session_state.map_html:
    st.subheader("📍 지도 보기")
    components.html(st.session_state.map_html, height=500)


# -----------------------------------------------------------
# 📝 장소 정보 + 즐겨찾기 버튼
# -----------------------------------------------------------
if st.session_state.places:
    st.subheader("🏆 추천 장소 3곳")
    for i, p in enumerate(st.session_state.places, start=1):
        st.markdown(f"""
### {i}. {p['place_name']}
- 📍 주소: {p['address_name']}
- 📞 전화: {p['phone'] or '정보 없음'}
- 📏 거리: {p['distance']}m
""")

        if st.button(f"⭐ 즐겨찾기 추가 ({p['place_name']})", key=f"fav_{i}"):
            add_favorite(p)
            st.success(f"'{p['place_name']}' 즐겨찾기 추가 완료!")
            st.rerun()
