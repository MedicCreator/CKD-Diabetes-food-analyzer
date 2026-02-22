import streamlit as st
import requests

st.title("USDA Key Validation Test")

USDA_API_KEY = st.secrets["USDA_API_KEY"]

if st.button("Test USDA Key"):

    response = requests.get(
        "https://api.nal.usda.gov/fdc/v1/foods/search",
        params={
            "query": "banana",
            "api_key": USDA_API_KEY
        },
        timeout=15
    )

    st.write("Status Code:", response.status_code)
    st.write("Response Text:", response.text)
