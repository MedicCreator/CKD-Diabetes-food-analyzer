import streamlit as st

st.title("CKD Smart Nutrition Risk App")

try:
    USDA_API_KEY = st.secrets["USDA_API_KEY"]
    st.success("API key loaded successfully.")
except:
    st.error("API key NOT found.")
