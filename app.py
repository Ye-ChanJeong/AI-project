import streamlit as st
from openai import OpenAI

st.set_page_config(page_title="부산 로컬 라이프 어시스턴트", page_icon="🌊")

st.title("🌊 부산 로컬 라이프 어시스턴트")
st.write("부산 여행, 맛집, 카페, 명소 등 어떤 것이든 물어보세요!")

api_key = st.text_input("🔑 OpenAI API Key 입력", type="password")

category = st.selectbox("카테고리 선택", ["맛집", "카페", "관광지", "기타"])

query = st.text_input("💬 부산에 대해 무엇을 알고 싶나요?")

if st.button("검색하기"):
    if not api_key:
        st.error("API Key를 입력하세요!")
    elif not query:
        st.error("질문을 입력하세요!")
    else:
        try:
            client = OpenAI(api_key=api_key)

            prompt = f"""
            너는 부산 로컬 라이프 추천 도우미야.
            사용자가 선택한 카테고리: {category}
            사용자 질문: {query}
            부산 지역을 기반으로 실제 정보 위주로 추천해줘.
            """

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}]
            )

            answer = response.choices[0].message.content
            st.success(answer)

        except Exception as e:
            st.error(f"오류 발생: {e}")
