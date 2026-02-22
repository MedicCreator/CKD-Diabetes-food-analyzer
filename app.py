import streamlit as st
import requests

st.title("CKD Smart Nutrition Risk App")

USDA_API_KEY = st.secrets["USDA_API_KEY"]

if st.button("Test USDA API"):

    st.write("Button clicked. Making request...")

    url = "https://api.nal.usda.gov/fdc/v1/foods/search"

    try:
        response = requests.get(
            url,
            params={
                "query": "banana",
                "api_key": USDA_API_KEY,
                "pageSize": 3
            },
            timeout=10
        )

        st.write("Request completed.")
        st.write("Status Code:", response.status_code)

        if response.status_code == 200:
            data = response.json()
            foods = data.get("foods", [])
            st.write("Foods returned:", len(foods))

            for food in foods:
                st.write(food["description"])
        else:
            st.write("Response text:", response.text)

    except Exception as e:
        st.error("Request failed.")
        st.write(str(e))
