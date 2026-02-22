import streamlit as st
import requests

st.title("CKD Smart Nutrition Risk App")

USDA_API_KEY = st.secrets["USDA_API_KEY"]

st.write("Page loaded.")

clicked = st.button("Test USDA API")

st.write("Button state:", clicked)

if clicked:
    st.write("Inside button block")

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
