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

# ---------------- DATABASE ----------------
conn = sqlite3.connect("nutrition.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS daily_log (
    log_date TEXT,
    ckd_risk REAL,
    dm_risk REAL,
    combined REAL
)
""")
conn.commit()

# ---------------- USDA ----------------

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
        nid = n.get("nutrient", {}).get("id") or n.get("nutrientId")
        val = n.get("amount") if n.get("amount") is not None else n.get("value")
        if nid in IMPORTANT_NUTRIENTS and val is not None:
            nutrients[IMPORTANT_NUTRIENTS[nid]] = val
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

# ---------------- CLINICAL ENGINE ----------------

def adjusted_limits(stage, serum_k, serum_phos):
    limits = {"sodium": 2000 if stage >= 4 else 2300,
              "potassium": 2500,
              "phosphorus": 1000}

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
    triggers = []
    max_percent = 0

    for n in ["sodium","potassium","phosphorus"]:
        percent = (total[n] / limits[n]) * 100
        max_percent = max(max_percent, percent)
        if percent > 100:
            triggers.append(n)

    # Stage multiplier
    if stage >= 4:
        max_percent *= 1.2

    return min(round(max_percent,1),100), triggers

def diabetes_risk(total, hba1c, fasting_glucose):
    score = 0
    if total["carbs"] > 60:
        score += 40
    if total["sugar"] > 25:
        score += 30
    if hba1c >= 7:
        score += 20
    if fasting_glucose >= 130:
        score += 20
    return min(score,100)

def risk_label(score):
    if score <= 40:
        return "🟢 Low Risk"
    elif score <= 70:
        return "🟡 Moderate Risk"
    return "🔴 High Risk"

# ---------------- SIDEBAR ----------------

st.sidebar.header("Patient Profile")

stage = st.sidebar.selectbox("CKD Stage", [1,2,3,4,5])
serum_k = st.sidebar.number_input("Serum Potassium", value=4.5)
serum_phos = st.sidebar.number_input("Serum Phosphorus", value=4.0)
hba1c = st.sidebar.number_input("HbA1c (%)", value=6.5)
fasting_glucose = st.sidebar.number_input("Fasting Glucose", value=100)

# ---------------- STATE ----------------

if "meal" not in st.session_state:
    st.session_state.meal = []

# ---------------- MEAL BUILDER ----------------

st.title("Renal + Diabetes Clinical Planner")

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
        "Select Portion Type",
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
        st.session_state.meal.append(scaled)

# ---------------- DISPLAY ----------------

if st.session_state.meal:

    remove_ids = []

    for item in st.session_state.meal:
        col1, col2 = st.columns([4,1])
        with col1:
            st.write(f"• {item['name']} ({item['portion']})")
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
    for k,v in total.items():
        st.write(f"{k.capitalize()}: {round(v,1)}")

    limits = adjusted_limits(stage, serum_k, serum_phos)

    ckd_score, triggers = ckd_risk(total, limits, stage)
    dm_score = diabetes_risk(total, hba1c, fasting_glucose)
    combined = round((ckd_score*0.6)+(dm_score*0.4),1)

    st.subheader("CKD Risk")
    st.metric("Score", ckd_score)
    st.write(risk_label(ckd_score))
    if triggers:
        st.warning(f"High levels detected in: {', '.join(triggers)}")

    st.subheader("Diabetes Risk")
    st.metric("Score", dm_score)
    st.write(risk_label(dm_score))

    st.subheader("Combined Risk")
    st.metric("Score", combined)
    st.write(risk_label(combined))

    if st.button("Save Day"):
        c.execute("INSERT INTO daily_log VALUES (?,?,?,?)",
                  (str(date.today()), ckd_score, dm_score, combined))
        conn.commit()
        st.success("Saved!")

st.markdown("---")
st.markdown("⚠️ Educational tool only. Not medical advice.")
