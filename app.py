import streamlit as st
import requests
import pandas as pd
import sqlite3
import uuid
from datetime import date

st.set_page_config(page_title="Renal + Diabetes Clinical Planner", layout="wide")

USDA_API_KEY = st.secrets["USDA_API_KEY"]
BASE_URL = "https://api.nal.usda.gov/fdc/v1"

IMPORTANT_NUTRIENTS = {
    1093: "sodium",
    1092: "potassium",
    1091: "phosphorus",
    1005: "carbs",
    1003: "protein",
    1008: "calories",
    2000: "sugar"
}

MEAL_TYPES = ["Breakfast", "Lunch", "Dinner", "Snacks"]

# ========================= USDA API =========================

@st.cache_data(ttl=86400)
def search_food(query):
    try:
        r = requests.get(
            f"{BASE_URL}/foods/search",
            params={"query": query, "api_key": USDA_API_KEY, "pageSize": 5},
            timeout=20
        )
        if r.status_code != 200:
            return []
        return r.json().get("foods", [])
    except:
        return []

@st.cache_data(ttl=86400)
def get_food_details(fdc_id):
    try:
        r = requests.get(
            f"{BASE_URL}/food/{fdc_id}",
            params={"api_key": USDA_API_KEY},
            timeout=20
        )
        if r.status_code != 200 or not r.text.strip():
            return {}
        return r.json()
    except:
        return {}

def extract_nutrients(food_data):
    nutrients = {v: 0 for v in IMPORTANT_NUTRIENTS.values()}

    for n in food_data.get("foodNutrients", []):

        nutrient_id = None
        value = None

        # Foundation / SR
        if "nutrient" in n:
            nutrient_id = n["nutrient"].get("id")
            nutrient_number = n["nutrient"].get("number")
            value = n.get("amount")

            # Fallback using nutrient number (important fix)
            if nutrient_number == "307":  # Sodium
                nutrients["sodium"] = value or 0
            elif nutrient_number == "306":  # Potassium
                nutrients["potassium"] = value or 0
            elif nutrient_number == "305":  # Phosphorus
                nutrients["phosphorus"] = value or 0
            elif nutrient_number == "205":  # Carbs
                nutrients["carbs"] = value or 0
            elif nutrient_number == "203":  # Protein
                nutrients["protein"] = value or 0
            elif nutrient_number == "208":  # Calories
                nutrients["calories"] = value or 0
            elif nutrient_number == "269":  # Sugar
                nutrients["sugar"] = value or 0

        # Branded
        if not nutrient_id:
            nutrient_id = n.get("nutrientId")
            value = n.get("value")

        if nutrient_id in IMPORTANT_NUTRIENTS and value is not None:
            nutrients[IMPORTANT_NUTRIENTS[nutrient_id]] = value

    return nutrients

def extract_portions(food_data):
    portions = [{"description": "100 g", "gramWeight": 100}]
    if food_data.get("servingSize"):
        portions.append({
            "description": f"1 serving ({food_data['servingSize']} {food_data.get('servingSizeUnit','g')})",
            "gramWeight": food_data["servingSize"]
        })
    for p in food_data.get("foodPortions", []):
        if p.get("gramWeight") and p.get("portionDescription"):
            portions.append({
                "description": p["portionDescription"],
                "gramWeight": p["gramWeight"]
            })
    return portions

def scale_nutrients(nutrients, grams):
    factor = grams / 100
    return {k: round((v or 0) * factor, 2) for k, v in nutrients.items()}

# ========================= CLINICAL LIMITS =========================

def adjusted_limits(stage, serum_k, serum_phos):
    limits = {
        "sodium": 2000 if stage >= 4 else 2300,
        "potassium": 2500,
        "phosphorus": 1000,
        "carbs": 180  # default diabetes daily carb target
    }

    if serum_k >= 6:
        limits["potassium"] = 1500
    elif serum_k >= 5.5:
        limits["potassium"] = 1800

    if serum_phos >= 6:
        limits["phosphorus"] = 700
    elif serum_phos >= 5:
        limits["phosphorus"] = 800

    return limits

def percent_and_excess(value, limit):
    percent = (value / limit) * 100 if limit else 0
    excess = max(value - limit, 0)
    return round(percent,1), round(excess,1)

# ========================= SIDEBAR =========================

st.sidebar.header("Patient Profile")

stage = st.sidebar.selectbox("CKD Stage", [1,2,3,4,5])
serum_k = st.sidebar.number_input("Serum Potassium", value=4.5)
serum_phos = st.sidebar.number_input("Serum Phosphorus", value=4.0)
hba1c = st.sidebar.number_input("HbA1c (%)", value=6.5)
fasting_glucose = st.sidebar.number_input("Fasting Glucose", value=100)

# ========================= SESSION STATE =========================

if "meals" not in st.session_state:
    st.session_state.meals = {meal: [] for meal in MEAL_TYPES}

# ========================= UI =========================

st.title("Renal + Diabetes Clinical Daily Planner")

meal_choice = st.selectbox("Select Meal Section", MEAL_TYPES)

query = st.text_input("Search Food")

if st.button("Search"):
    st.session_state.results = search_food(query)

if "results" in st.session_state and st.session_state.results:

    selected = st.selectbox(
        "Select Food",
        st.session_state.results,
        format_func=lambda x: x["description"]
    )

    food_data = get_food_details(selected["fdcId"])
    nutrients = extract_nutrients(food_data)
    portions = extract_portions(food_data)

    portion_choice = st.selectbox(
        "Select Portion",
        portions,
        format_func=lambda x: x["description"]
    )

    quantity = st.number_input("How many portions?", value=1.0, step=0.1)

    if st.button("Add Food"):
        grams = portion_choice["gramWeight"] * quantity
        scaled = scale_nutrients(nutrients, grams)
        scaled["id"] = str(uuid.uuid4())
        scaled["name"] = selected["description"]
        scaled["portion"] = portion_choice["description"]
        st.session_state.meals[meal_choice].append(scaled)

# ========================= DISPLAY MEALS WITH REMOVE =========================

daily_total = {k:0 for k in IMPORTANT_NUTRIENTS.values()}

for meal in MEAL_TYPES:
    st.subheader(meal)
    for item in st.session_state.meals[meal]:
        col1, col2 = st.columns([4,1])
        with col1:
            st.write(f"• {item['name']} ({item['portion']})")
        with col2:
            if st.button("Remove", key=item["id"]):
                st.session_state.meals[meal] = [
                    i for i in st.session_state.meals[meal]
                    if i["id"] != item["id"]
                ]
                st.rerun()

        for k in daily_total:
            daily_total[k] += item.get(k,0)

# ========================= DAILY TOTAL =========================

st.header("Daily Total")

limits = adjusted_limits(stage, serum_k, serum_phos)

for nutrient in ["sodium","potassium","phosphorus","carbs"]:
    value = daily_total[nutrient]
    limit = limits[nutrient]
    percent, excess = percent_and_excess(value, limit)

    st.write(
        f"{nutrient.capitalize()}: {round(value,1)} "
        f"(Limit: {limit} | {percent}% | +{excess} over)"
    )

# ========================= RISK =========================

ckd_percent = max(
    percent_and_excess(daily_total["sodium"], limits["sodium"])[0],
    percent_and_excess(daily_total["potassium"], limits["potassium"])[0],
    percent_and_excess(daily_total["phosphorus"], limits["phosphorus"])[0]
)

dm_percent = percent_and_excess(daily_total["carbs"], limits["carbs"])[0]

combined = round((ckd_percent*0.6)+(dm_percent*0.4),1)

st.subheader("CKD Risk")
st.metric("Score", round(ckd_percent,1))

st.subheader("Diabetes Risk")
st.metric("Score", round(dm_percent,1))

st.subheader("Combined Risk")
st.metric("Score", combined)

# ========================= DISCLAIMER =========================

st.markdown("---")
st.markdown("""
### ⚠️ Medical & Data Disclaimer

This application is for educational purposes only.
It does not provide medical advice.

Risk scores are generalized estimates based on dietary guidance
and user-entered laboratory values.

Always consult your physician before making dietary decisions.

Nutritional data provided by USDA FoodData Central.
Not affiliated with or endorsed by the USDA.
""")
