import streamlit as st
import requests

st.title("CKD Smart Nutrition Risk App")

USDA_API_KEY = st.secrets["USDA_API_KEY"]

if st.button("Test USDA API"):

    url = "https://api.nal.usda.gov/fdc/v1/foods/search"

    response = requests.get(
        url,
        params={
            "query": "banana",
            "api_key": USDA_API_KEY,
            "pageSize": 3
        }
    )

    st.write("Status Code:", response.status_code)

    if response.status_code == 200:
        data = response.json()
        st.write("API Working ✅")

        foods = data.get("foods", [])
        for food in foods:
            st.write(food["description"])
    else:
        st.error("API Failed ❌")
        st.write(response.text)
