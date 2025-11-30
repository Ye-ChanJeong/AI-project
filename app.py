import streamlit as st
from openai import OpenAI
import requests
import re
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="부산 로컬 라이프 어시스턴트", page_icon="🌊")

st.title("🌊 부산 로컬 라이프 어시스턴트")
st.write("부산 여행, 맛집, 카페, 명소 등 어떤 것이든 물어보세요!")

openai_key = st.text_input("🔑 OpenAI API Key", type="password")
kakao_key = st.text_input("🗺️ 카카오 REST API Key (KakaoAK ...)", type="password")

category = st.selectbox("카테고리 선택", ["맛집", "카페", "관광지", "기타"])
query = st.text_input("💬 부산에 대해 무엇을 알고 싶나요?")

# 지도 상태
if "map_obj" not in st.session_state:
    st.session_state.map_obj = None

# ⭐ AI 답변 상태 (새로 추가됨)
if "last_answer" not in st.session_state:
    st.session_state.last_answer = None


# -----------------------------------------------------------
# 🔥 1) 스마트 카카오 키워드 검색 (강화 버전)
# -----------------------------------------------------------
def smart_search_place(keyword, kakao_api_key, category):
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {kakao_api_key}"}

    enhanced_keywords = [
        keyword,
        keyword.replace(" ", ""),
        keyword.split()[0],
        f"부산 {keyword}",
        f"{keyword} 부산",
        f"부산 {category} {keyword}",
        f"{keyword} {category} 부산",
        f"{category} {keyword}",
        f"{keyword} {category}",
        f"부산 {keyword}점",
        f"{keyword} 본점",
        f"{keyword} 부산대",
        f"{keyword} 서면",
        f"{keyword} 해운대"
    ]

    for q in enhanced_keywords:
        params = {"query": q}
        res = requests.get(url, headers=headers, params=params).json()

        if res.get("documents"):
            place = res["documents"][0]
            name = place.get("place_name")
            address = place.get("road_address_name") or place.get("address_name")
            lat = float(place["y"])
            lon = float(place["x"])
            return name, address, lat, lon

    return None, None, None, None


# -----------------------------------------------------------
# 🔥 2) GPT에게 “지점명까지 포함한 실제 장소명” 요청
# -----------------------------------------------------------
def ask_gpt_for_place_name(client, category, query):
    prompt = f"""
    너는 부산 로컬 추천 전문가야.

    카테고리: {category}
    사용자 질문: {query}

    ❗ 매우 중요 ❗
    - 반드시 실제 존재하는 장소명만 말해.
    - 반드시 "지점명까지 포함된" 장소명을 반환해.
      예: "이디야 부산대점", "스타벅스 서면본점", "요아정 해운대점"
    - 절대로 모호하게 "이디야" 처럼 단일 단어로 말하지 마.
    - 최소 2단어 이상으로 지점명을 포함해 반환해.

    아래 형식으로만 대답해:
    1) 설명
    2) 장소명: 실제 지점명 포함 장소명
    """

    res = client.responses.create(
        model="gpt-4o-mini",
        input=prompt
    )

    return res.output_text


# -----------------------------------------------------------
# 🔥 3) 검색 버튼 로직
# -----------------------------------------------------------
if st.button("검색하기"):
    if not openai_key:
        st.error("OpenAI Key를 입력하세요!")
    elif not kakao_key:
        st.error("카카오 REST API Key를 입력하세요!")
    elif not query:
        st.error("질문을 입력하세요!")
    else:
        client = OpenAI(api_key=openai_key)

        # GPT에게 장소명 요청
        answer_text = ask_gpt_for_place_name(client, category, query)

        # ⭐ GPT 응답 저장 (새로 추가)
        st.session_state.last_answer = answer_text

        st.success(answer_text)

        # 장소명 추출
        match = re.search(r"장소명[:：]\s*(.+)", answer_text)
        if not match:
            st.error("❌ AI가 장소명을 반환하지 않았습니다.")
        else:
            place_name = match.group(1).strip()

            # 스마트 검색 실행
            name, address, lat, lon = smart_search_place(place_name, kakao_key, category)

            if not lat:
                st.error("❌ 카카오 지도에서 해당 장소를 찾을 수 없습니다.")
            else:
                # 지도 생성
                m = folium.Map(location=[lat, lon], zoom_start=15)
                folium.Marker([lat, lon], popup=f"{name}\n{address}").add_to(m)
                st.session_state.map_obj = m

                # -----------------------------------------------------------
# ⭐ 5) 지도 아래에 AI 답변 항상 보이게
# -----------------------------------------------------------
if st.session_state.last_answer:
    st.subheader("🤖 AI 추천 설명")
    with st.expander("AI 추천 내용 열기 / 닫기"):
        st.write(st.session_state.last_answer)



# -----------------------------------------------------------
# 🔥 4) 지도 표시
# -----------------------------------------------------------
if st.session_state.map_obj:
    st.subheader("📍 추천 장소 지도 보기")
    st_folium(st.session_state.map_obj, width=700, height=500)