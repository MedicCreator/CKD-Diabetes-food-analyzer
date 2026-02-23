import streamlit as st
import requests
import pandas as pd
import sqlite3
import uuid
from datetime import datetime, date

# =====================================
# CONFIG
# =====================================

st.set_page_config(page_title="Renal + Diabetes Smart Planner (Beta)", layout="wide")

USDA_API_KEY = st.secrets["USDA_API_KEY"]
BASE_URL = "https://api.nal.usda.gov/fdc/v1"

IMPORTANT_NUTRIENTS = {
    1093: "sodium",
    1092: "potassium",
    1091: "phosphorus",
    1005: "carbs",
    1003: "protein",
    1008: "calories"
}

# =====================================
# DATABASE SETUP
# =====================================

conn = sqlite3.connect("nutrition.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS daily_log (
    log_date TEXT,
    calories REAL,
    protein REAL,
    potassium REAL,
    phosphorus REAL,
    sodium REAL,
    risk_score REAL
)
""")
conn.commit()

# =====================================
# USDA FUNCTIONS
# =====================================

@st.cache_data(ttl=86400)
def search_food(query):
    r = requests.get(
        f"{BASE_URL}/foods/search",
        params={"query": query, "api_key": USDA_API_KEY, "pageSize": 5},
        timeout=20
    )
    return r.json().get("foods", [])

@st.cache_data(ttl=86400)
def get_food_details(fdc_id):
    r = requests.get(
        f"{BASE_URL}/food/{fdc_id}",
        params={"api_key": USDA_API_KEY},
        timeout=20
    )
    return r.json()

def extract_nutrients(food_data):
    nutrients = {v: 0 for v in IMPORTANT_NUTRIENTS.values()}
    for n in food_data.get("foodNutrients", []):
        nutrient_id = n.get("nutrient", {}).get("id") or n.get("nutrientId")
        value = n.get("amount") or n.get("value")
        if nutrient_id in IMPORTANT_NUTRIENTS:
            nutrients[IMPORTANT_NUTRIENTS[nutrient_id]] = value if value else 0
    return nutrients

def scale_nutrients(nutrients, grams):
    factor = grams / 100
    return {k: round((v or 0) * factor, 2) for k, v in nutrients.items()}

# =====================================
# CLINICAL LOGIC
# =====================================

def protein_target(weight, dialysis):
    if dialysis:
        return 1.2 * weight
    return 0.8 * weight

def ckd_risk(total):
    score = 0
    score += min((total["potassium"] / 2500) * 100, 100)
    score += min((total["phosphorus"] / 1000) * 100, 100)
    score += min((total["sodium"] / 2300) * 100, 100)
    return round(score / 3, 1)

def risk_label(score):
    if score <= 40:
        return "🟢 Low"
    elif score <= 70:
        return "🟡 Moderate"
    return "🔴 High"

# =====================================
# UI
# =====================================

st.title("Renal + Diabetes Smart Meal Planner (Beta)")

st.sidebar.header("Patient Profile")
weight = st.sidebar.number_input("Body Weight (kg)", value=70.0)
dialysis = st.sidebar.checkbox("On Dialysis")

protein_daily_target = protein_target(weight, dialysis)

if "meal" not in st.session_state:
    st.session_state.meal = []

# =====================================
# MEAL BUILDER
# =====================================

st.header("Build Meal")

query = st.text_input("Search Food")

if st.button("Search"):
    st.session_state.results = search_food(query)

if "results" in st.session_state and st.session_state.results:
    selected = st.selectbox(
        "Select Food",
        st.session_state.results,
        format_func=lambda x: x["description"]
    )

    grams = st.number_input("Quantity (grams)", value=100.0)

    if st.button("Add Food"):
        food_data = get_food_details(selected["fdcId"])
        nutrients = extract_nutrients(food_data)
        scaled = scale_nutrients(nutrients, grams)

        scaled["id"] = str(uuid.uuid4())
        scaled["name"] = selected["description"]
        st.session_state.meal.append(scaled)

# =====================================
# MEAL SUMMARY
# =====================================

if st.session_state.meal:

    st.subheader("Current Meal")

    remove_ids = []

    for item in st.session_state.meal:
        col1, col2 = st.columns([4,1])
        with col1:
            st.write(f"• {item['name']}")
        with col2:
            if st.button("Remove", key=item["id"]):
                remove_ids.append(item["id"])

    if remove_ids:
        st.session_state.meal = [
            i for i in st.session_state.meal if i["id"] not in remove_ids
        ]
        st.rerun()

    total = {k:0 for k in IMPORTANT_NUTRIENTS.values()}
    for item in st.session_state.meal:
        for k in total:
            total[k] += item.get(k,0)

    st.subheader("Nutrient Totals")

    st.write(f"Calories: {round(total['calories'],1)} kcal")
    st.write(f"Protein: {round(total['protein'],1)} g")
    st.write(f"Potassium: {round(total['potassium'],1)} mg")
    st.write(f"Phosphorus: {round(total['phosphorus'],1)} mg")
    st.write(f"Sodium: {round(total['sodium'],1)} mg")

    # Protein comparison
    st.write(f"Daily Protein Target: {round(protein_daily_target,1)} g")
    if total["protein"] < protein_daily_target / 3:
        st.warning("Protein intake may be low for this meal.")
    elif total["protein"] > protein_daily_target / 2:
        st.warning("High protein load for single meal.")

    # Risk
    risk = ckd_risk(total)
    st.subheader("CKD Risk Score")
    st.metric("Score", risk)
    st.write(risk_label(risk))

    # Save to DB
    if st.button("Save Day Summary"):
        c.execute(
            "INSERT INTO daily_log VALUES (?,?,?,?,?,?,?)",
            (
                str(date.today()),
                total["calories"],
                total["protein"],
                total["potassium"],
                total["phosphorus"],
                total["sodium"],
                risk
            )
        )
        conn.commit()
        st.success("Saved to database!")

# =====================================
# WEEKLY DASHBOARD
# =====================================

st.header("Weekly Dashboard")

df = pd.read_sql_query(
    "SELECT * FROM daily_log ORDER BY log_date DESC LIMIT 7",
    conn
)

if not df.empty:
    df["log_date"] = pd.to_datetime(df["log_date"])
    df = df.sort_values("log_date")

    st.line_chart(df.set_index("log_date")[["risk_score"]])
    st.line_chart(df.set_index("log_date")[["calories"]])

# =====================================
# DISCLAIMER
# =====================================

st.markdown("---")
st.markdown("""
⚠️ **Beta Disclaimer**

This beta tool is for educational purposes only.
It does not replace medical advice.
Always consult your healthcare provider.

Nutritional data provided by USDA FoodData Central.
Not affiliated with or endorsed by the USDA.
""")
