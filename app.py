import streamlit as st
import requests

st.set_page_config(page_title="CKD Smart Nutrition", layout="wide")

st.title("CKD Smart Nutrition Risk App")
st.caption("Educational tool. Not medical advice.")

USDA_API_KEY = st.secrets["USDA_API_KEY"]

IMPORTANT_NUTRIENTS = {
    1093: "Sodium (mg)",
    1092: "Potassium (mg)",
    1091: "Phosphorus (mg)"
}

if "foods" not in st.session_state:
    st.session_state.foods = None

food_name = st.text_input("Enter food name")

if st.button("Search"):
    if food_name.strip() != "":
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
            st.session_state.foods = data.get("foods", [])
        else:
            st.error("API Error")

# Show dropdown only if foods exist
if st.session_state.foods:

    food_options = {
        food["description"]: food["fdcId"]
        for food in st.session_state.foods
    }

    selected_food = st.selectbox(
        "Select a food",
        list(food_options.keys())
    )

    if st.button("Get Nutrients"):

        fdc_id = food_options[selected_food]

        detail_response = requests.get(
            f"https://api.nal.usda.gov/fdc/v1/food/{fdc_id}",
            params={"api_key": USDA_API_KEY},
            timeout=15
        )

        if detail_response.status_code == 200:
            food_data = detail_response.json()

            st.subheader("Nutrient Information")

            for nutrient in food_data.get("foodNutrients", []):
                nutrient_id = nutrient.get("nutrient", {}).get("id") or nutrient.get("nutrientId")
                value = nutrient.get("amount") or nutrient.get("value")

                if nutrient_id in IMPORTANT_NUTRIENTS:
                    st.write(IMPORTANT_NUTRIENTS[nutrient_id], ":", value)

        else:
            st.error("Failed to fetch nutrient data.")

st.markdown("---")
st.markdown(
    "Nutritional data provided by USDA FoodData Central "
    "(https://fdc.nal.usda.gov/). "
    "This product is not affiliated with or endorsed by the USDA."
)
