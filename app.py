import streamlit as st
import requests

st.title("Network Test")

if st.button("Test Google"):

    try:
        response = requests.get("https://www.google.com", timeout=5)
        st.write("Google Status:", response.status_code)
    except Exception as e:
        st.write("Google failed:", str(e))
