import streamlit as st
import requests

st.set_page_config(page_title="CKD Smart Nutrition")

st.title("CKD Smart Nutrition Risk App")
st.caption("Educational tool. Not medical advice.")

# Get API key safely
try:
    USDA_API_KEY = st.secrets["USDA_API_KEY"]
except:
    st.error("USDA API Key not found in Streamlit Secrets.")
    st.stop()

# Input box
query = st.text_input("Enter food name")

# Analyze button
analyze = st.button("Analyze")

# Only run API when button is clicked
if analyze:
    if query.strip() == "":
        st.warning("Please enter a food name.")
    else:
        st.write("Searching for:", query)

        url = "https://api.nal.usda.gov/fdc/v1/foods/search"

        response = requests.get(
            url,
            params={
                "query": query,
                "api_key": USDA_API_KEY,
                "pageSize": 5
            }
        )

        st.write("Status Code:", response.status_code)

        if response.status_code != 200:
            st.error("API request failed.")
            st.write(response.text)
        else:
            data = response.json()
            foods = data.get("foods", [])

            if foods:
                st.subheader("Results")
                for food in foods:
                    st.write(food["description"])
            else:
                st.warning("No foods found.")

st.markdown("---")
st.markdown(
    "Nutritional data provided by USDA FoodData Central "
    "(https://fdc.nal.usda.gov/). "
    "This product is not affiliated with or endorsed by the USDA."
)
