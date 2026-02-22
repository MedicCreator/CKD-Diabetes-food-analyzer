import streamlit as st
import requests
import os

st.set_page_config(page_title="CKD Smart Nutrition", layout="wide")

USDA_API_KEY = st.secrets["USDA_API_KEY"]

st.title("CKD Smart Nutrition Risk App")
st.caption("Educational tool. Not medical advice.")

query = st.text_input("Search Food")

if query:
    url = "https://api.nal.usda.gov/fdc/v1/foods/search"
    params = {
        "query": query,
        "api_key": USDA_API_KEY,
        "pageSize": 5
    }

    response = requests.get(url, params=params)
    foods = response.json().get("foods", [])

    if foods:
        for food in foods:
            st.write(food["description"])

st.markdown("---")
st.markdown(
    "Nutritional data provided by USDA FoodData Central "
    "(https://fdc.nal.usda.gov/). "
    "This product is not affiliated with or endorsed by the USDA."
)
