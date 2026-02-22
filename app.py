import streamlit as st
import requests

st.set_page_config(page_title="CKD Smart Nutrition", layout="wide")

st.title("CKD Smart Nutrition Risk App")
st.caption("Educational tool. Not medical advice.")

USDA_API_KEY = st.secrets["USDA_API_KEY"]

food_name = st.text_input("Enter food name")

if st.button("Analyze Food"):

    if food_name.strip() == "":
        st.warning("Please enter a food name.")
    else:
        st.write("Searching for:", food_name)

        response = requests.get(
            "https://api.nal.usda.gov/fdc/v1/foods/search",
            params={
                "query": food_name,
                "api_key": USDA_API_KEY,
                "pageSize": 5
            },
            timeout=15
        )

        if response.status_code == 200:
            data = response.json()
            foods = data.get("foods", [])

            if foods:
                st.subheader("Results")
                for food in foods:
                    st.write(food["description"])
            else:
                st.warning("No foods found.")
        else:
            st.error("API Error")
            st.write(response.text)

st.markdown("---")
st.markdown(
    "Nutritional data provided by USDA FoodData Central "
    "(https://fdc.nal.usda.gov/). "
    "This product is not affiliated with or endorsed by the USDA."
)
