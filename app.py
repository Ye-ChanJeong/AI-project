import streamlit as st
import os
from dotenv import load_dotenv  # 추가된 부분
from openai import OpenAI
import requests
import folium
import streamlit.components.v1 as components
import re

# -----------------------------------------------------------
# 🔐 환경 변수 로드 (수정됨)
# -----------------------------------------------------------
load_dotenv() # .env 파일 로드

# .env 파일에 저장된 키 이름으로 가져오기
# (파일에 OPENAI_API_KEY=..., KAKAO_API_KEY=... 로 저장되어 있어야 함)
env_openai_key = os.getenv("OPENAI_API_KEY")
env_kakao_key = os.getenv("KAKAO_API_KEY")


# -----------------------------------------------------------
# 🌊 기본 설정
# -----------------------------------------------------------
st.set_page_config(page_title="부산 로컬 라이프 어시스턴트", page_icon="🌊")

st.title("🌊 부산 로컬 라이프 어시스턴트")
st.write("부산에서 뭐 하고 싶은지 말해줘! 실제 데이터 기반으로 추천해줄게.")


# -----------------------------------------------------------
# 🔥 세션 상태 초기화
# -----------------------------------------------------------
if "last_answer" not in st.session_state:
    st.session_state.last_answer = None

if "places" not in st.session_state:
    st.session_state.places = None

if "map_html" not in st.session_state:
    st.session_state.map_html = None


# -----------------------------------------------------------
# Kakao 헬퍼들 (원본 그대로 유지)
# -----------------------------------------------------------
def get_center_from_location(location_text, kakao_key):
    """동네 이름 → 대략 중심좌표"""
    DEFAULT_X = 129.0756  # 경도
    DEFAULT_Y = 35.1796   # 위도

    if not location_text:
        return DEFAULT_X, DEFAULT_Y

    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK " + kakao_key}
    params = {"query": f"부산 {location_text}", "size": 3}

    try:
        res = requests.get(url, headers=headers, params=params).json()
        docs = res.get("documents", [])
    except Exception:
        return DEFAULT_X, DEFAULT_Y

    if not docs:
        return DEFAULT_X, DEFAULT_Y

    doc = docs[0]
    return float(doc["x"]), float(doc["y"])


def get_center_from_nearest_subway(location_text, kakao_key):
    """동네 중심 → 가장 가까운 지하철역 좌표 (없으면 그대로 사용)"""
    base_x, base_y = get_center_from_location(location_text, kakao_key)

    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK " + kakao_key}
    params = {
        "query": "지하철역",
        "x": base_x,
        "y": base_y,
        "radius": 3000,
        "size": 5,
        "sort": "distance"
    }

    try:
        res = requests.get(url, headers=headers, params=params).json()
        docs = res.get("documents", [])
        if docs:
            doc = docs[0]
            return float(doc["x"]), float(doc["y"])
    except Exception:
        return base_x, base_y

    return base_x, base_y


def get_nearby_places(keyword, x, y, kakao_key, radius=800):
    """주변 장소 10개 정도 가져오기"""
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK " + kakao_key}

    params = {
        "query": keyword,
        "x": x,
        "y": y,
        "radius": radius,
        "size": 10,
        "sort": "distance"
    }

    res = requests.get(url, headers=headers, params=params).json()
    docs = res.get("documents", [])
    # 부산만 우선
    busan_docs = [d for d in docs if "부산" in (d.get("address_name") or "")]
    return busan_docs or docs


# -----------------------------------------------------------
# GPT 헬퍼들 (원본 그대로 유지)
# -----------------------------------------------------------
def ask_gpt_for_search_keyword(client, query):
    """
    사용자 문장에서 카카오맵 검색에 넣을 '핵심 키워드' 한/두 단어만 추출.
    """
    prompt = f"""
너는 카카오 지도 검색 키워드를 뽑는 도우미야.

사용자 질문: {query}

규칙:
- 카카오맵 검색창에 넣기 좋은 한 단어 또는 두 단어만 뽑아.
- 장소/활동 위주로 뽑아야 해.
  예시:
  - "부경대 근처 소고기집 찾아줘" -> "소고기집"
  - "부산대에서 마라탕 먹고 싶어" -> "마라탕"
  - "서면에서 헬스장 어디갈까" -> "헬스장"
  - "부경대 앞 공부하기 좋은 곳" -> "스터디카페"
- 뚜렷한 키워드를 찾기 어려우면 "맛집"처럼 아주 짧은 일반적인 키워드를 사용해.
- 절대로 문장 전체를 그대로 쓰지 마.
- 아래 형식으로만 대답해:

키워드: <검색어>
"""
    # 네가 확인했다는 원본 코드 유지
    res = client.responses.create(
        model="gpt-5-mini",
        input=prompt
    )
    text = res.output_text

    m = re.search(r"키워드[:：]\s*(.+)", text)
    if not m:
        return None
    keyword = m.group(1).strip()
    # 안전장치: 너무 길면 잘라버리기
    if len(keyword) > 20:
        keyword = keyword[:20]
    return keyword


def ask_gpt_for_summary(client, query, places):
    """
    실제 Kakao 장소 데이터 기반으로 '상권 분위기'만 요약.
    """
    prompt = f"""
너는 부산 로컬 안내 전문가야.

아래는 실제 Kakao 장소 데이터야.
절대로 존재하지 않는 메뉴, 가격 등 허위 정보 생성 금지.
오직 '상권 분위기'와 '대략 어떤 종류 가게들이 모여있는지' 정도만 요약해줘.

사용자 질문: {query}

실제 장소 데이터:
{places}

형식:
1) 설명:
"""
    # 네가 확인했다는 원본 코드 유지
    res = client.responses.create(
        model="gpt-5-mini",
        input=prompt
    )
    return res.output_text


# -----------------------------------------------------------
# 🔹 입력 폼 (수정됨: API Key 입력창 제거)
#   👉 기준 지역을 위로, 하고 싶은 활동을 아래로 배치
# -----------------------------------------------------------
with st.form("search_form"):
    # 원래 있던 st.text_input(키 입력) 두 줄 삭제함

    # 1. 기준 구역이 위
    location_text = st.text_input("📍 기준 지역 (예: 부경대, 부산대, 서면, 해운대)", "")

    # 2. 하고 싶은 활동이 아래
    query = st.text_input("💬 무엇을 하고 싶나요? (예: 소고기집, 마라탕, 스터디카페)")

    submitted = st.form_submit_button("검색하기")


# -----------------------------------------------------------
# 🔥 검색 로직 (폼 제출 시 한 번만 실행)
# -----------------------------------------------------------
if submitted:
    # (수정됨) 입력창 값이 아니라 환경변수 값 확인
    if not env_openai_key:
        st.error("❌ .env 파일에 OpenAI Key가 없습니다.")
        st.stop()
    if not env_kakao_key:
        st.error("❌ .env 파일에 Kakao REST API Key가 없습니다.")
        st.stop()
    if not query:
        st.error("❌ 검색어를 입력하세요.")
        st.stop()

    # (수정됨) 환경변수 키 사용
    client = OpenAI(api_key=env_openai_key)

    # 1) GPT에게 검색 키워드 추출 맡기기
    keyword = ask_gpt_for_search_keyword(client, query)
    if not keyword:
        keyword = "맛집"  # 최종 안전 장치

    # 2) 중심 좌표 (지하철 기준) -> (수정됨) 환경변수 키 전달
    cx, cy = get_center_from_nearest_subway(location_text, env_kakao_key)

    # 3) Kakao 실제 장소 검색 -> (수정됨) 환경변수 키 전달
    places = get_nearby_places(keyword, cx, cy, env_kakao_key)

    if not places:
        st.error("❌ 주변에서 해당 키워드로 찾은 장소가 없어요. 다른 표현으로 다시 시도해줘!")
        st.stop()

    # 4) 상위 3곳만 사용
    top3 = places[:3]
    st.session_state.places = top3

    # 5) GPT로 분위기 요약
    summary = ask_gpt_for_summary(client, query, top3)
    st.session_state.last_answer = summary

    # 6) Folium 지도 생성 → HTML로 저장해두기
    m = folium.Map(location=[cy, cx], zoom_start=15)
    for p in top3:
        name = p["place_name"]
        addr = p["address_name"]
        px = float(p["x"])
        py = float(p["y"])
        folium.Marker(
            [py, px],
            popup=f"{name}\n{addr}",
        ).add_to(m)

    st.session_state.map_html = m._repr_html_()


# -----------------------------------------------------------
# 🗺 지도 출력 (텍스트 변경: 지도 보기 → 지도 표시)
# -----------------------------------------------------------
if st.session_state.map_html:
    st.subheader("📍 지도 표시")
    components.html(st.session_state.map_html, height=500)


# -----------------------------------------------------------
# 🤖 GPT 상권 요약
# -----------------------------------------------------------
if st.session_state.last_answer:
    st.subheader("🤖 지역 분위기 설명")
    st.write(st.session_state.last_answer)


# -----------------------------------------------------------
# 🏆 실제 가게 3곳 정보 (+ 카카오맵 페이지 열기 링크 추가)
# -----------------------------------------------------------
if st.session_state.places:
    st.subheader("🏆 추천 장소 3곳")
    for i, p in enumerate(st.session_state.places, start=1):
        kakao_url = p.get("place_url")
        url_line = f"- 🔗 [카카오맵에서 보기]({kakao_url})" if kakao_url else ""

        st.markdown(f"""
### {i}. {p['place_name']}
- 📍 주소: {p['address_name']}
- 📞 전화: {p['phone'] if p['phone'] else '전화 정보 없음'}
- 📏 거리: {p['distance']}m
{url_line}
""")