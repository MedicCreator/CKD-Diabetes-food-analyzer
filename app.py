import streamlit as st
import requests

st.title("CKD Smart Nutrition Risk App")
st.caption("Educational tool. Not medical advice.")

USDA_API_KEY = st.secrets["USDA_API_KEY"]

query = st.text_input("Search Food")

if query != "":
    st.write("Searching for:", query)

    url = "https://api.nal.usda.gov/fdc/v1/foods/search"
    params = {
        "query": query,
        "api_key": USDA_API_KEY,
        "pageSize": 5
    }

    response = requests.get(url, params=params)

    st.write("Status Code:", response.status_code)

    data = response.json()
    st.write("Raw Response:", data)

    foods = data.get("foods", [])

    if foods:
        st.subheader("Results")
        for food in foods:
            st.write(food["description"])
    else:
        st.write("No foods found.")

st.markdown("---")
st.markdown(
    "Nutritional data provided by USDA FoodData Central "
    "(https://fdc.nal.usda.gov/). "
    "This product is not affiliated with or endorsed by the USDA."
)
