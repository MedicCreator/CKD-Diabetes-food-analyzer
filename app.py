import streamlit as st
import requests
import uuid
import sqlite3
import pandas as pd
from datetime import date, timedelta

# =====================================================
# CONFIG
# =====================================================

st.set_page_config(page_title="Renal + Diabetes Clinical Planner", layout="wide")

USDA_API_KEY = st.secrets["USDA_API_KEY"]
BASE_URL = "https://api.nal.usda.gov/fdc/v1"

MEALS = ["Breakfast", "Lunch", "Dinner", "Snacks"]

MEAL_DISTRIBUTION = {
    "Breakfast": 0.25,
    "Lunch": 0.30,
    "Dinner": 0.30,
    "Snacks": 0.15
}

# =====================================================
# DATABASE SETUP
# =====================================================

conn = sqlite3.connect("renal_tracker.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS daily_log (
    log_date TEXT PRIMARY KEY,
    sodium REAL,
    potassium REAL,
    phosphorus REAL,
    carbs REAL,
    protein REAL,
    calories REAL,
    ckd_risk REAL,
    diabetes_risk REAL,
    combined_risk REAL
)
""")
conn.commit()

# =====================================================
# USDA FUNCTIONS
# =====================================================

@st.cache_data(ttl=86400)
def search_food(query):
    try:
        r = requests.get(
            f"{BASE_URL}/foods/search",
            params={"query": query, "api_key": USDA_API_KEY, "pageSize": 5},
            timeout=20,
        )
        return r.json().get("foods", []) if r.status_code == 200 else []
    except:
        return []

@st.cache_data(ttl=86400)
def get_food_details(fdc_id):
    try:
        r = requests.get(
            f"{BASE_URL}/food/{fdc_id}",
            params={"api_key": USDA_API_KEY},
            timeout=20,
        )
        return r.json() if r.status_code == 200 else {}
    except:
        return {}

def extract_nutrients(food):
    nutrients = {
        "sodium":0,"potassium":0,"phosphorus":0,
        "carbs":0,"protein":0,"calories":0,"water":0
    }

    for n in food.get("foodNutrients", []):
        if "nutrient" in n:
            number = n["nutrient"].get("number")
            val = float(n.get("amount") or 0)

            if number == "307": nutrients["sodium"] = val
            elif number == "306": nutrients["potassium"] = val
            elif number == "305": nutrients["phosphorus"] = val
            elif number == "205": nutrients["carbs"] = val
            elif number == "203": nutrients["protein"] = val
            elif number == "208": nutrients["calories"] = val
            elif number == "255": nutrients["water"] = val

    return nutrients

def extract_portions(food):
    portions = [{"desc": "100 g", "grams": 100}]

    for p in food.get("foodPortions", []):
        if p.get("gramWeight") and p.get("portionDescription"):
            portions.append({
                "desc": p["portionDescription"],
                "grams": float(p["gramWeight"])
            })

    return portions

def scale(nutrients, grams):
    factor = grams / 100
    return {k: round(v * factor, 2) for k, v in nutrients.items()}

# =====================================================
# PATIENT PROFILE
# =====================================================

st.sidebar.header("Patient Profile")

stage = st.sidebar.selectbox("CKD Stage", [1,2,3,4,5])
dialysis = st.sidebar.checkbox("On Dialysis")
weight = st.sidebar.number_input("Body Weight (kg)", 70.0)

serum_k = st.sidebar.number_input("Serum Potassium", 4.5)
serum_phos = st.sidebar.number_input("Serum Phosphorus", 4.0)

hba1c = st.sidebar.number_input("HbA1c (%)", 6.5)
fasting_glucose = st.sidebar.number_input("Fasting Glucose", 100)

fluid_limit = st.sidebar.number_input("Daily Fluid Limit (ml)", 2000.0)

# =====================================================
# LIMITS
# =====================================================

def get_ckd_limits(stage, dialysis):
    if dialysis:
        return {"sodium":2000,"potassium":3000,"phosphorus":1000}
    if stage <= 2:
        return {"sodium":2300,"potassium":3500,"phosphorus":1000}
    if stage == 3:
        return {"sodium":2000,"potassium":2500,"phosphorus":900}
    if stage == 4:
        return {"sodium":2000,"potassium":2000,"phosphorus":800}
    return {"sodium":2000,"potassium":1500,"phosphorus":700}

limits = get_ckd_limits(stage, dialysis)

if serum_k >= 6: limits["potassium"] = 1500
if serum_phos >= 6: limits["phosphorus"] = 700

if hba1c < 6.5: carb_limit = 200
elif hba1c <= 7.5: carb_limit = 180
else: carb_limit = 150

limits["carbs"] = carb_limit
protein_target = weight * (1.2 if dialysis else 0.8)

# =====================================================
# SESSION
# =====================================================

if "meals" not in st.session_state:
    st.session_state.meals = {m: [] for m in MEALS}

# =====================================================
# MEAL BUILDER
# =====================================================

st.title("Renal + Diabetes Clinical Daily Planner")

meal_choice = st.selectbox("Meal Section", MEALS)
query = st.text_input("Search Food")

if st.button("Search"):
    st.session_state.results = search_food(query)

if "results" in st.session_state and st.session_state.results:
    selected = st.selectbox(
        "Select Food",
        st.session_state.results,
        format_func=lambda x: x["description"]
    )

    food = get_food_details(selected["fdcId"])
    base = extract_nutrients(food)
    portions = extract_portions(food)

    portion_choice = st.selectbox(
        "Select Portion",
        portions,
        format_func=lambda x: x["desc"]
    )

    qty = st.number_input("How many portions?", 1.0, step=0.5)

    if st.button("Add Food"):
        st.session_state.meals[meal_choice].append({
            "id": str(uuid.uuid4()),
            "name": selected["description"],
            "grams": portion_choice["grams"] * qty,
            "base": base
        })

# =====================================================
# TOTALS
# =====================================================

daily = {"sodium":0,"potassium":0,"phosphorus":0,
         "carbs":0,"protein":0,"calories":0,"water":0}

for meal in MEALS:
    st.subheader(meal)
    for item in st.session_state.meals[meal]:
        col1,col2,col3 = st.columns([4,2,1])

        with col1:
            st.write(item["name"])

        with col2:
            item["grams"] = st.number_input("grams", item["grams"], key=item["id"])

        with col3:
            if st.button("Remove", key="r"+item["id"]):
                st.session_state.meals[meal] = [
                    i for i in st.session_state.meals[meal]
                    if i["id"] != item["id"]
                ]
                st.rerun()

        scaled = scale(item["base"], item["grams"])
        for k in scaled:
            daily[k] += scaled[k]

# =====================================================
# RISK CALCULATION
# =====================================================

def risk_label(p):
    if p <= 40: return "Low","🟢"
    elif p <= 70: return "Moderate","🟡"
    return "High","🔴"

ckd_score = max(
    (daily["sodium"]/limits["sodium"])*100,
    (daily["potassium"]/limits["potassium"])*100,
    (daily["phosphorus"]/limits["phosphorus"])*100
)

dm_score = (daily["carbs"]/limits["carbs"])*100
combined = round((ckd_score*0.6)+(dm_score*0.4),1)

# =====================================================
# SAVE DAILY LOG
# =====================================================

today = str(date.today())

c.execute("""
INSERT OR REPLACE INTO daily_log
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    today,
    daily["sodium"],
    daily["potassium"],
    daily["phosphorus"],
    daily["carbs"],
    daily["protein"],
    daily["calories"],
    ckd_score,
    dm_score,
    combined
))
conn.commit()

# =====================================================
# DISPLAY RISKS
# =====================================================

st.header("Risk Summary")

l1,i1 = risk_label(ckd_score)
l2,i2 = risk_label(dm_score)
l3,i3 = risk_label(combined)

st.write(f"CKD: {i1} {l1} ({round(ckd_score,1)}%)")
st.write(f"Diabetes: {i2} {l2} ({round(dm_score,1)}%)")
st.write(f"Combined: {i3} {l3} ({combined}%)")

# =====================================================
# WEEKLY DASHBOARD
# =====================================================

st.header("Weekly Risk Trend")

week_ago = str(date.today() - timedelta(days=7))

df = pd.read_sql_query(
    "SELECT * FROM daily_log WHERE log_date >= ?",
    conn,
    params=(week_ago,)
)

if not df.empty:
    st.line_chart(df.set_index("log_date")[["ckd_risk","diabetes_risk","combined_risk"]])
else:
    st.info("No data yet for weekly trend.")

# =====================================================
# DISCLAIMER
# =====================================================

st.markdown("---")
st.markdown("""
### Medical & Data Disclaimer
Educational tool only. Not medical advice.
Consult your healthcare provider before dietary changes.

Nutritional data provided by USDA FoodData Central.
Not affiliated with or endorsed by USDA.
""")
