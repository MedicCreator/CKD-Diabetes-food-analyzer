import streamlit as st
import requests
import pandas as pd
import sqlite3
import uuid
from datetime import date

# ======================================================
# CONFIG
# ======================================================

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

# ======================================================
# DATABASE
# ======================================================

conn = sqlite3.connect("nutrition.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS daily_log (
    log_date TEXT,
    ckd REAL,
    diabetes REAL,
    combined REAL
)
""")
conn.commit()

# ======================================================
# USDA API (DEFENSIVE)
# ======================================================

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

        data = r.json()
        return data.get("foods", [])

    except Exception:
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

    except Exception:
        return {}

# ======================================================
# USDA PARSING
# ======================================================

def extract_nutrients(food_data):
    nutrients = {v: 0 for v in IMPORTANT_NUTRIENTS.values()}

    for n in food_data.get("foodNutrients", []):
        nutrient_id = None
        value = None

        if "nutrient" in n:
            nutrient_id = n["nutrient"].get("id")
            value = n.get("amount")

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

# ======================================================
# CLINICAL ENGINE
# ======================================================

def adjusted_limits(stage, serum_k, serum_phos):
    limits = {
        "sodium": 2000 if stage >= 4 else 2300,
        "potassium": 2500,
        "phosphorus": 1000
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

def ckd_risk(total, limits, stage):
    max_percent = 0
    triggers = []

    for n in ["sodium","potassium","phosphorus"]:
        percent = (total[n] / limits[n]) * 100 if limits[n] else 0
        max_percent = max(max_percent, percent)
        if percent > 100:
            triggers.append(n)

    if stage >= 4:
        max_percent *= 1.2

    return min(round(max_percent,1),100), triggers

def diabetes_risk(total, hba1c, fasting_glucose):
    score = 0
    triggers = []

    if total["carbs"] > 180:
        score += 40
        triggers.append("high carbs")

    if total["sugar"] > 50:
        score += 30
        triggers.append("high sugar")

    if hba1c >= 7:
        score += 20
        triggers.append("HbA1c")

    if fasting_glucose >= 130:
        score += 20
        triggers.append("fasting glucose")

    return min(score,100), triggers

def risk_label(score):
    if score <= 40:
        return "🟢 Low Risk — Within recommended limits."
    elif score <= 70:
        return "🟡 Moderate Risk — Approaching or partially exceeding limits."
    return "🔴 High Risk — Exceeds recommended limits."

# ======================================================
# SIDEBAR
# ======================================================

st.sidebar.header("Patient Profile")

stage = st.sidebar.selectbox("CKD Stage", [1,2,3,4,5])
serum_k = st.sidebar.number_input("Serum Potassium", value=4.5)
serum_phos = st.sidebar.number_input("Serum Phosphorus", value=4.0)
hba1c = st.sidebar.number_input("HbA1c (%)", value=6.5)
fasting_glucose = st.sidebar.number_input("Fasting Glucose", value=100)

# ======================================================
# SESSION STATE
# ======================================================

if "meals" not in st.session_state:
    st.session_state.meals = {meal: [] for meal in MEAL_TYPES}

# ======================================================
# UI
# ======================================================

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

# ======================================================
# DISPLAY MEALS
# ======================================================

daily_total = {k:0 for k in IMPORTANT_NUTRIENTS.values()}

for meal in MEAL_TYPES:
    st.subheader(meal)
    for item in st.session_state.meals[meal]:
        st.write(f"• {item['name']} ({item['portion']})")
        for k in daily_total:
            daily_total[k] += item.get(k,0)

# ======================================================
# DAILY TOTAL
# ======================================================

st.header("Daily Total")

for k,v in daily_total.items():
    st.write(f"{k.capitalize()}: {round(v,1)}")

limits = adjusted_limits(stage, serum_k, serum_phos)

ckd_score, ckd_triggers = ckd_risk(daily_total, limits, stage)
dm_score, dm_triggers = diabetes_risk(daily_total, hba1c, fasting_glucose)
combined = round((ckd_score*0.6)+(dm_score*0.4),1)

st.subheader("CKD Risk")
st.metric("Score", ckd_score)
st.write(risk_label(ckd_score))
if ckd_triggers:
    st.error(f"Triggered by: {', '.join(ckd_triggers)}")

st.subheader("Diabetes Risk")
st.metric("Score", dm_score)
st.write(risk_label(dm_score))
if dm_triggers:
    st.error(f"Triggered by: {', '.join(dm_triggers)}")

st.subheader("Combined Risk")
st.metric("Score", combined)
st.write(risk_label(combined))

if st.button("Save Full Day"):
    c.execute(
        "INSERT INTO daily_log VALUES (?,?,?,?)",
        (str(date.today()), ckd_score, dm_score, combined)
    )
    conn.commit()
    st.success("Daily summary saved.")

# ======================================================
# WEEKLY TREND
# ======================================================

st.header("Weekly Risk Trend")

df = pd.read_sql_query(
    "SELECT * FROM daily_log ORDER BY log_date DESC LIMIT 7",
    conn
)

if not df.empty:
    df["log_date"] = pd.to_datetime(df["log_date"])
    df = df.sort_values("log_date")
    st.line_chart(df.set_index("log_date")[["ckd","diabetes","combined"]])

# ======================================================
# DISCLAIMER
# ======================================================

st.markdown("---")

st.markdown("""
### ⚠️ Medical & Data Disclaimer

This application is intended for educational and informational purposes only.
It does not provide medical advice, diagnosis, or treatment.

Risk scores are generalized estimates based on public dietary guidance and 
user-entered laboratory values. They are not individualized medical prescriptions.

Always consult your physician, nephrologist, endocrinologist, or registered 
dietitian before making dietary or medical decisions.

Nutritional data provided by USDA FoodData Central (https://fdc.nal.usda.gov/).
This application is not affiliated with, endorsed by, certified by, or sponsored by the USDA.
""")
